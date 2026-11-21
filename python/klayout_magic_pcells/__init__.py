"""KLayout PCells for the sky130A devices that Magic generates.

``register()`` checks the configuration, starts one Magic process, and
registers the ``sky130_magic`` library. If anything is missing it logs one
error and returns None without registering, so cells in files that are open
stay ``<defunct>`` and keep their stored geometry until a later
``register()`` succeeds.
"""

import logging
import os
import tempfile

__version__ = "0.2.0"
LIBRARY_NAME = "sky130_magic"

log = logging.getLogger("klayout_magic_pcells")


class _State:
    def __init__(self):
        self.cfg = None
        self.manifest = None
        self.server = None
        self.cache = None
        self.generator = None
        self.versions = None
        self.created_stamp = ""
        self.stamp_dict = {}
        self.library = None
        self.defaults_mismatch = []
        self.last_error = None


state = _State()


def _log_error(msg):
    try:
        from ._kl import error
        error(msg)
    except Exception:
        log.error(msg)


def _log_warn(msg):
    try:
        from ._kl import warn
        warn(msg)
    except Exception:
        log.warning(msg)


# Appended to the "not registered" error, by cause.
HINT_SETUP = ("Set KMP_MAGIC to the Magic executable, PDK_ROOT to the directory holding sky130A "
              "(or KMP_MAGICRC to the rcfile), or put them in "
              "~/.config/klayout-magic-pcells/config.ini")
HINT_DEVICES = ("Check PDK_ROOT and KMP_MAGICRC, or build a manifest for this PDK "
                "(tools/build_manifest.py --out FILE) and set KMP_MANIFEST to it")


class StartError(RuntimeError):
    """The backend can't serve the library; ``hint`` says what to set."""

    def __init__(self, msg, hint=HINT_SETUP):
        super().__init__(msg)
        self.hint = hint


def _cache_dir_problem(path):
    """None if ``path`` exists or can be made and is writable, else why not."""
    try:
        os.makedirs(path, exist_ok=True)
        fd, probe = tempfile.mkstemp(prefix=".kmp-probe-", dir=path)
        os.close(fd)
        os.remove(probe)
        return None
    except OSError as e:
        return str(e)


def missing_devices(manifest, live_defaults):
    """Manifest devices that the running Magic doesn't define."""
    return [d.name for d in manifest.devices if d.name not in live_defaults]


def start_backend(cfg=None):
    """Resolve the configuration, start Magic and build the generator.

    Returns the state object; raises on failure. Does not register anything.
    Refuses (StartError) when the running Magic lacks any device of the
    manifest: every such PCell could only draw the error marker, and saving
    a file opened that way replaces the stored geometry with markers (K2).
    """
    from .backend import Generator, make_server
    from .cache import GdsCache, versions_fields
    from .config import Config
    from .manifest import Manifest, diff_defaults
    from .stamp import make_stamp, parse_stamp

    if state.generator is not None:
        return state
    cfg = cfg or Config.load()
    problems = cfg.problems()
    if problems:
        raise StartError("; ".join(problems), hint="")
    manifest = Manifest.load(cfg.manifest)
    if manifest.pdk != cfg.pdk:
        raise StartError("manifest %s is for %s, not %s" % (cfg.manifest, manifest.pdk, cfg.pdk),
                         hint="Set KMP_MANIFEST or KMP_PDK")
    if cfg.cache_enabled:
        why = _cache_dir_problem(cfg.cache_dir)
        if why:
            _log_warn("sky130_magic: the cache directory %s can't be used (%s); continuing without "
                      "the disk cache. Set KMP_CACHE_DIR to a writable directory, or KMP_CACHE=0."
                      % (cfg.cache_dir, why))
            cfg.cache_enabled = False
            cfg.sources["cache_enabled"] = "off: KMP_CACHE_DIR not writable"
    server = make_server(cfg)
    try:
        versions = server.start()
        missing = missing_devices(manifest, versions.defaults)
        if missing:
            raise StartError(
                "the running Magic defines %d of the manifest's %d devices (missing: %s%s): "
                "sky130A.tcl did not load, or Magic loaded another PDK"
                % (len(manifest.devices) - len(missing), len(manifest.devices),
                   ", ".join(missing[:4]), ", ..." if len(missing) > 4 else ""),
                hint=HINT_DEVICES)
    except Exception:
        server.close()
        raise
    mismatch = diff_defaults(manifest.defaults_by_device(), versions.defaults)
    if versions.defaults_digest != manifest.defaults_digest:
        _log_warn("sky130_magic: the defaults of %d device(s) in the running Magic differ from "
                  "the manifest %s (run 'python3 -m klayout_magic_pcells doctor')"
                  % (len(mismatch), cfg.manifest))
    cache = GdsCache(cfg.cache_dir, versions_fields(versions, cfg.pdk), enabled=cfg.cache_enabled)
    state.cfg, state.manifest, state.server, state.cache = cfg, manifest, server, cache
    state.versions = versions
    state.generator = Generator(server, cache, versions)
    state.created_stamp = make_stamp(versions)
    state.stamp_dict = parse_stamp(state.created_stamp)
    state.defaults_mismatch = mismatch
    return state


def register(cfg=None):
    """Register the library; return it, or None if the backend can't start.

    Idempotent: a second call returns the registered library and starts no
    second Magic (registering again would replace the library).
    """
    if state.library is not None:
        return state.library
    try:
        start_backend(cfg)
    except Exception as e:
        state.last_error = str(e)
        hint = getattr(e, "hint", HINT_SETUP)
        _log_error("sky130_magic: not registered: %s. %s"
                   % (str(e).rstrip(". "), (hint + ", then call" if hint else "Then call")
                      + " klayout_magic_pcells.register()."))
        shutdown()
        return None
    try:
        from .library import Sky130MagicLibrary
        state.library = Sky130MagicLibrary(state.manifest, state)
    except Exception as e:  # e.g. a rebuilt manifest whose names collide (PCellNameError)
        state.last_error = str(e)
        state.library = None
        _log_error("sky130_magic: not registered: %s" % e)
        shutdown()
        return None
    return state.library


def unregister():
    """Unregister the library and stop Magic."""
    lib, state.library = state.library, None
    if lib is not None:
        try:
            lib.unregister()
        except Exception as e:
            log.debug("unregister: %s", e)
    shutdown()


def shutdown():
    if state.server is not None:
        try:
            state.server.close()
        except Exception:
            pass
    if state.cache is not None:
        state.cache.close()
    state.server = state.generator = state.cache = None


def generator():
    return state.generator
