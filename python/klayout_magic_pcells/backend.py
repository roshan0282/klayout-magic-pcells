"""The Magic backend: one persistent ``magic -dnull`` child on pipes.

``MagicServer`` owns the child process and speaks the protocol in
protocol.py. ``Generator`` puts an in-memory memo and the disk cache in front
of it. Nothing in this module imports KLayout.
"""

import atexit
import collections
import hashlib
import json
import logging
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

from . import protocol
from .cache import CacheError
from .config import TCL_DIR

log = logging.getLogger("klayout_magic_pcells")

SERVER_TCL = os.path.join(TCL_DIR, "kmp_server.tcl")


class BackendError(Exception):
    """Magic could not answer a request."""


class _Transient(Exception):
    """Timeout, EOF or framing error: restart Magic and retry once."""


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def parse_magic_version(banner):
    """'Version 8.3 revision 681.  Compiled ...' -> '8.3.681'."""
    m = re.search(r"Version\s+(\d+\.\d+)\s+revision\s+(\d+)", banner or "")
    return "%s.%s" % (m.group(1), m.group(2)) if m else ""


def read_open_pdks(pdk_path):
    """The open_pdks commit from $PDK_ROOT/<pdk>/SOURCES, or ''."""
    path = os.path.join(pdk_path, "SOURCES")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[0] == "open_pdks":
                    return parts[1]
    except OSError:
        pass
    return ""


def defaults_digest(defaults):
    """SHA-256 over the canonical JSON of {device: [[key, value], ...]}."""
    items = [[dev, [[str(k), str(v)] for k, v in defaults[dev]]] for dev in sorted(defaults)]
    text = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Versions:
    """What the running Magic and PDK are; feeds the cache key and stamps."""

    FIELDS = ("magic", "magic_banner", "tech", "tech_name", "tech_file", "tcl", "pdk",
              "open_pdks", "code", "techfile", "defaults_digest", "protocol")

    def __init__(self, **kw):
        for f in self.FIELDS:
            setattr(self, f, kw.get(f, ""))
        self.defaults = kw.get("defaults", {})

    def as_dict(self):
        return {f: getattr(self, f) for f in self.FIELDS}

    def __repr__(self):
        return "Versions(magic=%s, tech=%s, open_pdks=%s)" % (self.magic, self.tech, self.open_pdks)


class GenReply:
    def __init__(self, cell, checked, log_text, us, restart=False):
        self.cell = cell
        self.checked = checked
        self.log = log_text
        self.us = us
        self.restart = restart


class CheckReply:
    def __init__(self, checked, log_text):
        self.checked = checked
        self.log = log_text


def _make_pdeathsig():
    """A preexec_fn that asks Linux to kill the child when its parent dies.

    The libc function is resolved here, in the parent, so the child only makes
    one C call between fork and exec. PR_SET_PDEATHSIG fires when the thread
    that forked exits; KLayout calls produce on its main thread.
    """
    if not sys.platform.startswith("linux"):
        return None
    try:
        import ctypes
        prctl = ctypes.CDLL("libc.so.6", use_errno=True).prctl
    except Exception:
        return None
    sig = int(signal.SIGKILL)

    def _pre():
        prctl(1, sig, 0, 0, 0)  # PR_SET_PDEATHSIG = 1
    return _pre


def _private_run_dir(cfg):
    """A fresh directory for one Magic process: under <cache>/run when the
    disk cache is on and writable, else in the system temp directory."""
    if cfg.cache_enabled:
        base = os.path.join(cfg.cache_dir, "run")
        try:
            os.makedirs(base, exist_ok=True)
            return tempfile.mkdtemp(prefix="kmp-run-", dir=base)
        except OSError:
            pass
    return tempfile.mkdtemp(prefix="kmp-run-")


class MagicServer:
    """One ``magic -dnull -noconsole`` child serving requests over pipes.

    Without ``run_dir`` the server makes a private working directory for
    Magic and deletes it in close(), so two sessions sharing a cache never
    share one, and the CLI leaves nothing behind.
    """

    def __init__(self, cfg, run_dir=None, server_tcl=SERVER_TCL):
        self.cfg = cfg
        self._own_run_dir = run_dir is None
        self.run_dir = run_dir or _private_run_dir(cfg)
        self.server_tcl = server_tcl
        self.versions = None
        self.stats = {"spawns": 0, "restarts": 0, "requests": 0, "generate": 0, "check": 0}
        self._lock = threading.RLock()
        self._proc = None
        self._lines = None
        self._next_id = 0
        self._needs_restart = False
        self._threads = []
        self._stderr = collections.deque(maxlen=40)  # (sequence number, line)
        self._stderr_seq = 0
        self._trace = None
        if cfg.log:
            try:
                self._trace = open(cfg.log, "a", encoding="utf-8")
            except OSError as e:
                log.warning("cannot open KMP_LOG %s: %s", cfg.log, e)

    # -- process management -------------------------------------------------

    def _trace_line(self, direction, text):
        if self._trace:
            try:
                self._trace.write("%.3f %s %s\n" % (time.time(), direction, text.rstrip("\n")))
                self._trace.flush()
            except OSError:
                pass

    def _env(self):
        env = dict(os.environ)
        env["PDK_ROOT"] = self.cfg.pdk_root
        # The sky130A rcfile reads only PDK_ROOT; PDK is set so that nothing
        # the rcfile sources picks up an IHP default from the environment.
        env["PDK"] = self.cfg.pdk
        env.pop("DISPLAY", None)
        return env

    def stderr_mark(self):
        """A position in Magic's stderr, for stderr_since()."""
        return self._stderr_seq

    def stderr_since(self, mark, wait=0.05):
        """Lines Magic wrote on stderr after ``mark`` (most recent 40 kept).

        Magic's C code writes its messages there directly, not through Tcl's
        puts; ``wait`` gives the reader thread a moment to catch up.
        """
        if wait:
            time.sleep(wait)
        return [t for n, t in list(self._stderr) if n > mark and t.strip()]

    def _said(self, mark=0):
        lines = self.stderr_since(mark, wait=0)
        return ("; Magic said: " + " | ".join(lines[-4:])) if lines else ""

    def _spawn(self):
        if os.path.isdir(self.run_dir):
            shutil.rmtree(self.run_dir, ignore_errors=True)
        os.makedirs(self.run_dir, exist_ok=True)
        cmd = [self.cfg.magic, "-dnull", "-noconsole", "-rcfile", self.cfg.magicrc]
        try:
            proc = subprocess.Popen(
                cmd, cwd=self.run_dir, env=self._env(), stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0,
                preexec_fn=_make_pdeathsig(), close_fds=True)
        except OSError as e:
            raise BackendError("cannot start Magic (%s): %s" % (self.cfg.magic, e))
        lines = queue.Queue()

        # The pipes may be closed under these threads by _kill(); a reader
        # that finds its pipe closed just stops.
        def read_stdout(stream, q):
            try:
                for raw in iter(stream.readline, b""):
                    q.put(raw.decode("utf-8", errors="replace"))
            except (OSError, ValueError):
                pass
            finally:
                q.put(None)

        def read_stderr(stream):
            try:
                for raw in iter(stream.readline, b""):
                    text = raw.decode("utf-8", errors="replace").rstrip("\n")
                    self._stderr_seq += 1
                    self._stderr.append((self._stderr_seq, text))
                    log.debug("magic stderr: %s", text)
                    self._trace_line("ERR", text)
            except (OSError, ValueError):
                pass

        self._stderr.clear()
        self._threads = [
            threading.Thread(target=read_stdout, args=(proc.stdout, lines), daemon=True,
                             name="kmp-magic-stdout"),
            threading.Thread(target=read_stderr, args=(proc.stderr,), daemon=True,
                             name="kmp-magic-stderr")]
        for t in self._threads:
            t.start()
        self._proc, self._lines = proc, lines
        self._parser = protocol.ReplyParser()
        self.stats["spawns"] += 1
        budget = max(self.cfg.timeout, 10.0)
        deadline = time.monotonic() + budget
        printed = []
        try:
            self._send("source %s\n" % protocol.tcl_word(self.server_tcl))
            while True:
                line = self._get_line(deadline, budget, waiting_for="Magic to load kmp_server.tcl")
                kind, val = self._parser.feed(line)
                if kind == "ready":
                    if val != str(protocol.PROTOCOL):
                        self._kill()
                        raise BackendError("kmp_server.tcl speaks protocol %s, expected %d"
                                           % (val, protocol.PROTOCOL))
                    break
                if kind == "other":
                    log.debug("magic: %s", line.rstrip())
                    if line.strip():
                        printed.append(line.strip())
        except _Transient as e:
            # Say why: Magic's exit status and its last stderr lines (for
            # example "Could not find file .../sky130A.tech"), or what the
            # executable printed if it never answered.
            text = str(e)
            if text.startswith("cannot write"):
                text = self._exit_text() or text
            elif text.startswith("timed out") and printed:
                text += " (it printed %r; is %s Magic?)" % (printed[-1][:80], self.cfg.magic)
            raise _Transient(text + self._said())
        self._needs_restart = False

    def _exit_text(self):
        """'Magic exited (status N)' once the child has exited, else ''."""
        proc = self._proc
        if proc is None:
            return ""
        try:
            code = proc.wait(timeout=2)
        except Exception:
            return ""
        # let the stderr reader drain what the process wrote before it died
        for t in self._threads[1:]:
            t.join(timeout=1)
        return "Magic exited (status %s)" % code

    def _send(self, text):
        self._trace_line(">>", text)
        try:
            self._proc.stdin.write(text.encode("utf-8"))
            self._proc.stdin.flush()
        except (OSError, ValueError) as e:
            raise _Transient("cannot write to Magic: %s" % e)

    def _get_line(self, deadline, budget, waiting_for="Magic"):
        remaining = deadline - time.monotonic()
        try:
            if remaining <= 0:
                raise queue.Empty
            line = self._lines.get(timeout=remaining)
        except queue.Empty:
            raise _Transient("timed out after %.0f s waiting for %s" % (budget, waiting_for))
        if line is None:
            raise _Transient(self._exit_text() or "Magic closed its output")
        self._trace_line("<<", line)
        return line

    def _kill(self):
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            proc.kill()
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
        # The readers see EOF once the process is gone; wait for them before
        # closing the pipes, so that no thread reads a closed file.
        for t in self._threads:
            t.join(timeout=1)
        for s in (proc.stdin, proc.stdout, proc.stderr):
            try:
                s.close()
            except Exception:
                pass

    @property
    def pid(self):
        return self._proc.pid if self._proc else None

    def alive(self):
        return self._proc is not None and self._proc.poll() is None

    def start(self):
        """Start Magic and read its versions. Returns a ``Versions``."""
        with self._lock:
            if not self.alive():
                try:
                    self._spawn()
                except _Transient as e:
                    self._kill()
                    raise BackendError("Magic did not start: %s" % e)
            if self.versions is None:
                self.versions = self._read_versions()
            return self.versions

    def close(self):
        """Ask Magic to quit, close its stdin, kill it after 2 s, and delete
        the private run directory."""
        with self._lock:
            proc = self._proc
            if proc is not None:
                try:
                    self._send("quit -noprompt\n")
                    proc.stdin.close()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=2)
                except Exception:
                    pass
                self._kill()
            if self._own_run_dir:
                shutil.rmtree(self.run_dir, ignore_errors=True)

    # -- requests -----------------------------------------------------------

    def _roundtrip(self, obj):
        self._next_id += 1
        rid = self._next_id
        self._send(protocol.encode_request(rid, obj))
        deadline = time.monotonic() + self.cfg.timeout
        while True:
            line = self._get_line(deadline, self.cfg.timeout)
            try:
                kind, val = self._parser.feed(line)
            except protocol.ProtocolError as e:
                raise _Transient(str(e))
            if kind == "reply":
                if val.id == rid:
                    return val
                log.debug("dropping stale reply %d", val.id)
            elif kind == "other":
                log.debug("magic: %s", line.rstrip())

    def request(self, obj):
        """Send one request; restart Magic and retry once on a transient error."""
        with self._lock:
            self.stats["requests"] += 1
            last = None
            for attempt in (1, 2):
                mark = self.stderr_mark()
                try:
                    if not self.alive() or self._needs_restart:
                        if self._proc is not None or self.stats["spawns"]:
                            self.stats["restarts"] += 1
                        self._kill()
                        self._spawn()
                        mark = self.stderr_mark()
                    return self._roundtrip(obj)
                except _Transient as e:
                    text = str(e)
                    if "Magic said:" not in text:
                        text += self._said(mark)
                    last = text
                    log.warning("Magic request failed (%s); restarting Magic", text)
                    self._kill()
            raise BackendError("Magic failed twice: %s" % last)

    def _read_versions(self):
        procs_out = os.path.join(self.run_dir, "procs.txt")
        defaults_out = os.path.join(self.run_dir, "defaults.json")
        rep = self.request({"op": "versions", "procs_out": procs_out, "defaults_out": defaults_out})
        if not rep.ok:
            raise BackendError("versions request failed: %s" % rep.error)
        kv = rep.kv
        try:
            with open(defaults_out, encoding="utf-8") as f:
                defaults = json.load(f)
            code = sha256_file(procs_out)
        except (OSError, ValueError) as e:
            raise BackendError("cannot read Magic's version dump: %s" % e)
        for p in (procs_out, defaults_out):  # about 300 KB, needed only for the digest
            try:
                os.remove(p)
            except OSError:
                pass
        tech_file = kv.get("tech_file", "")
        techfile_digest = sha256_file(tech_file) if tech_file and os.path.isfile(tech_file) else ""
        return Versions(
            magic=parse_magic_version(kv.get("magic_banner", "")),
            magic_banner=kv.get("magic_banner", ""),
            tech=kv.get("tech", ""), tech_name=kv.get("tech_name", ""),
            tech_file=tech_file, tcl=kv.get("tcl", ""), pdk=self.cfg.pdk,
            open_pdks=read_open_pdks(self.cfg.pdk_path), code=code,
            techfile=techfile_digest, defaults_digest=defaults_digest(defaults),
            defaults=defaults, protocol=kv.get("protocol", ""))

    def ping(self):
        rep = self.request({"op": "ping"})
        return rep.ok

    def generate(self, device, params, form, out_path):
        """Generate one device into ``out_path``. Raises BackendError."""
        self.stats["generate"] += 1
        rep = self.request({"op": "generate", "device": device, "params": dict(params),
                            "form": form, "out": out_path})
        if not rep.ok:
            lines = []
            for ln in rep.log.strip().splitlines():
                if ln.strip() and ln not in lines:
                    lines.append(ln)
            raise BackendError("%s: %s" % (device, rep.error.strip() or "generation failed")
                               + (("\n" + "\n".join(lines)) if lines else ""))
        restart = rep.kv.get("restart") == "1"
        if restart:
            log.warning("Magic kept cells after a request (%s); restarting it",
                        rep.kv.get("leftover", ""))
            self._needs_restart = True
        try:
            us = int(rep.kv.get("us", "0"))
        except ValueError:
            us = 0
        return GenReply(rep.kv.get("cell", ""), rep.params, rep.log, us, restart)

    def check(self, device, params):
        """Run ``_check`` once on the merged defaults; nothing is drawn."""
        self.stats["check"] += 1
        rep = self.request({"op": "check", "device": device, "params": dict(params)})
        if not rep.ok:
            raise BackendError("%s: %s" % (device, rep.error.strip() or "check failed"))
        return CheckReply(rep.params, rep.log)


class MagicOneShot:
    """The same interface with one Magic process per request (debugging)."""

    def __init__(self, cfg, run_dir=None):
        self.cfg = cfg
        self.run_dir = run_dir
        self.versions = None
        self.stats = {"spawns": 0, "restarts": 0, "requests": 0, "generate": 0, "check": 0}

    def _once(self, fn):
        s = MagicServer(self.cfg, run_dir=self.run_dir)
        try:
            s.start()
            if self.versions is None:
                self.versions = s.versions
            return fn(s)
        finally:
            s.close()
            for k in self.stats:
                self.stats[k] += s.stats.get(k, 0)

    def start(self):
        if self.versions is None:
            self._once(lambda s: None)
        return self.versions

    def generate(self, device, params, form, out_path):
        return self._once(lambda s: s.generate(device, params, form, out_path))

    def check(self, device, params):
        return self._once(lambda s: s.check(device, params))

    def ping(self):
        return self._once(lambda s: s.ping())

    def close(self):
        pass

    def alive(self):
        return False

    pid = None


class Result:
    """A generated device: Magic's GDS on disk plus what Magic said about it."""

    def __init__(self, key, gds_path, sidecar, source):
        self.key = key
        self.gds_path = gds_path
        self.sidecar = sidecar
        self.source = source  # "memo", "disk" or "magic"

    @property
    def checked(self):
        return self.sidecar.get("checked", {})

    @property
    def messages(self):
        return self.sidecar.get("messages", "")

    @property
    def magic_cell(self):
        return self.sidecar.get("magic_cell", "")

    @property
    def stamp(self):
        return self.sidecar.get("stamp", "")


class Generator:
    """memo, then the disk cache, then Magic."""

    def __init__(self, server, cache, versions):
        from .stamp import make_stamp
        self.server = server
        self.cache = cache
        self.versions = versions
        self._make_stamp = make_stamp
        self._memo = {}
        self._lock = threading.RLock()
        self.stats = {"memo": 0, "disk": 0, "magic": 0, "evicted": 0}

    def key(self, spec, request):
        return self.cache.key(spec.name, spec.form, request)

    def peek(self, spec, request):
        """The memo entry for this request, or None. Never calls Magic."""
        return self._memo.get(self.key(spec, request))

    def get(self, spec, request):
        key = self.key(spec, request)
        with self._lock:
            hit = self._memo.get(key)
            if hit is not None:
                self.stats["memo"] += 1
                return Result(hit.key, hit.gds_path, hit.sidecar, "memo")
            entry = self.cache.lookup(key, spec.name)
            if entry is not None:
                self.stats["disk"] += 1
                res = Result(key, entry[0], entry[1], "disk")
                self._memo[key] = res
                return res
            tmp = self.cache.tmp_path(key)
            mark = self.server.stderr_mark() if hasattr(self.server, "stderr_mark") else None
            try:
                rep = self.server.generate(spec.name, request, spec.form, tmp)
                stamp = self._make_stamp(self.versions, key)
                sidecar = {
                    "key": key, "device": spec.name, "form": spec.form,
                    "request": dict(request), "checked": rep.checked,
                    "messages": rep.log, "magic_cell": rep.cell,
                    "versions": self.versions.as_dict(), "stamp": stamp,
                    "gen_us": rep.us,
                    "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                try:
                    gds_path = self.cache.store(key, spec.name, tmp, sidecar)
                except CacheError as e:
                    said = [ln for ln in rep.log.strip().splitlines() if ln.strip()]
                    if mark is not None:
                        said += self.server.stderr_since(mark)
                    if said:
                        raise CacheError("%s; Magic said: %s" % (e, " | ".join(said[-5:])))
                    raise
            finally:
                if os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
            self.stats["magic"] += 1
            res = Result(key, gds_path, sidecar, "magic")
            self._memo[key] = res
            return res

    def check(self, spec, request):
        return self.server.check(spec.name, request)

    def evict(self, spec, request):
        """Forget one variant in the memo and on disk, so the next get()
        asks Magic."""
        key = self.key(spec, request)
        with self._lock:
            self._memo.pop(key, None)
            self.cache.evict(key, spec.name)
            self.stats["evicted"] += 1

    def clear_memo(self):
        with self._lock:
            self._memo.clear()


_to_close = []


def _close_all():
    for s in list(_to_close):
        try:
            s.close()
        except Exception:
            pass


atexit.register(_close_all)


def make_server(cfg):
    s = MagicOneShot(cfg) if cfg.backend == "oneshot" else MagicServer(cfg)
    _to_close.append(s)
    return s
