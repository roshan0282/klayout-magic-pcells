"""Disk cache of Magic's GDS output, keyed by request and versions.

Layout: ``<root>/v1/<versions digest, 12 hex>/<device>/<key, 24 hex>.gds``
plus a ``.json`` sidecar next to it. A GDS without its sidecar is a miss.
The sidecar records the SHA-256 of the GDS as stored; a GDS whose bytes no
longer match it (truncated, overwritten, another entry's file) is a miss,
and the entry is deleted so that Magic regenerates it.
"""

import atexit
import hashlib
import json
import os
import shutil
import tempfile

from . import protocol

# 2: the sidecar carries gds_sha256. 3: the versions fields cover the PDK
# commit, every file in libs.tech/magic and the fixed devices' vendor GDS.
# A new format starts a new versions directory, so older entries are never
# read.
FORMAT = 3


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def canonical_json(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def versions_fields(versions, pdk):
    """Every key field except device, form and request."""
    return {
        "format": FORMAT,
        "protocol": protocol.PROTOCOL,
        "pdk": pdk,
        "magic": versions.magic,
        "open_pdks": versions.open_pdks,
        "tech": versions.tech,
        "code": versions.code,
        "techfile": versions.techfile,
        "pdk_commit": getattr(versions, "pdk_commit", ""),
        "techdir": getattr(versions, "techdir", ""),
        "vendor": getattr(versions, "vendor", ""),
    }


def versions_digest(fields):
    return hashlib.sha256(canonical_json(fields).encode("utf-8")).hexdigest()


def cache_key(fields, device, form, request):
    obj = dict(fields)
    obj["device"] = device
    obj["form"] = form
    obj["request"] = {str(k): str(v) for k, v in request.items()}
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def _atomic_write_text(path, text):
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


class CacheError(Exception):
    pass


def count_top_cells(gds_path):
    """Read the file with KLayout and return its top cell names."""
    from ._kl import db
    ly = db.Layout()
    ly.read(gds_path)
    return [c.name for c in ly.top_cells()]


class GdsCache:
    """``enabled=False`` keeps nothing on disk between sessions (KMP_CACHE=0)."""

    def __init__(self, root, fields, enabled=True, validate=count_top_cells):
        self.root = root
        self.fields = dict(fields)
        self.enabled = enabled
        self.validate = validate
        self.vdigest = versions_digest(self.fields)[:12]
        self.stats_counts = {"evicted": 0}
        self._own_dir = None
        if enabled:
            self.base = os.path.join(root, "v1", self.vdigest)
            self.tmp_dir = os.path.join(root, "tmp")
        else:
            # The session's entries live here and are deleted with it.
            self.base = self._own_dir = tempfile.mkdtemp(prefix="kmp-nocache-")
            self.tmp_dir = os.path.join(self.base, "tmp")
            atexit.register(self.close)
        os.makedirs(self.tmp_dir, exist_ok=True)

    def close(self):
        """Delete the session directory of a disabled cache (KMP_CACHE=0)."""
        if self._own_dir:
            shutil.rmtree(self._own_dir, ignore_errors=True)
            self._own_dir = None

    def key(self, device, form, request):
        return cache_key(self.fields, device, form, request)

    def paths(self, key, device):
        d = os.path.join(self.base, device)
        return os.path.join(d, key[:24] + ".gds"), os.path.join(d, key[:24] + ".json")

    def tmp_path(self, key):
        return os.path.join(self.tmp_dir, "%s.%d.gds" % (key[:24], os.getpid()))

    def lookup(self, key, device):
        """Return (gds_path, sidecar) or None.

        A sidecar that can't be read or names another key is a miss. A
        sidecar for another device, or a GDS whose SHA-256 differs from the
        one recorded at store time, is a miss and the entry is deleted.
        """
        if not self.enabled:
            return None
        gds, side = self.paths(key, device)
        if not (os.path.isfile(gds) and os.path.isfile(side)):
            return None
        try:
            with open(side, encoding="utf-8") as f:
                sidecar = json.load(f)
        except (OSError, ValueError):
            return None
        if not isinstance(sidecar, dict) or sidecar.get("key") != key:
            return None
        try:
            good = sidecar.get("device") == device and sha256_file(gds) == sidecar.get("gds_sha256")
        except OSError:
            good = False
        if not good:
            self.evict(key, device)
            return None
        return gds, sidecar

    def evict(self, key, device):
        """Delete one entry (both files); a missing file is no error."""
        for p in self.paths(key, device):
            try:
                os.remove(p)
            except OSError:
                pass
        self.stats_counts["evicted"] += 1

    def store(self, key, device, tmp_gds, sidecar):
        """Validate ``tmp_gds``, move it into place, then write the sidecar.

        Sets ``device`` and ``gds_sha256`` in ``sidecar``.
        """
        if not os.path.isfile(tmp_gds) or os.path.getsize(tmp_gds) == 0:
            raise CacheError("Magic wrote no GDS at %s" % tmp_gds)
        if self.validate is not None:
            tops = self.validate(tmp_gds)
            if len(tops) != 1:
                raise CacheError("%s: expected one top cell, found %d (%s)"
                                 % (tmp_gds, len(tops), ", ".join(tops)))
        sidecar["device"] = device
        sidecar["gds_sha256"] = sha256_file(tmp_gds)
        gds, side = self.paths(key, device)
        os.makedirs(os.path.dirname(gds), exist_ok=True)
        os.replace(tmp_gds, gds)
        _atomic_write_text(side, json.dumps(sidecar, indent=1, sort_keys=True) + "\n")
        return gds

    # -- maintenance ----------------------------------------------------------

    def version_dirs(self):
        top = os.path.join(self.root, "v1")
        if not os.path.isdir(top):
            return []
        return sorted(os.path.join(top, d) for d in os.listdir(top))

    def prune(self, keep=None):
        """Delete every version directory except the current one (or the
        ones whose digests are in ``keep``: one per PDK)."""
        keep = set(keep or ()) | {self.vdigest}
        removed = []
        for d in self.version_dirs():
            if os.path.basename(d) not in keep:
                shutil.rmtree(d, ignore_errors=True)
                removed.append(d)
        shutil.rmtree(os.path.join(self.root, "tmp"), ignore_errors=True)
        return removed

    def clear(self):
        """Delete the whole cache."""
        for name in ("v1", "tmp"):
            shutil.rmtree(os.path.join(self.root, name), ignore_errors=True)

    def stats(self):
        n = size = 0
        for d in self.version_dirs():
            for dirpath, _, files in os.walk(d):
                for fn in files:
                    if fn.endswith(".gds"):
                        n += 1
                    size += os.path.getsize(os.path.join(dirpath, fn))
        return {"entries": n, "bytes": size, "versions": len(self.version_dirs()),
                "current": self.vdigest}
