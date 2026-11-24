"""Generation, cache and stamps for the sky130_power library.

``HWGenerator.get(params)`` looks in an in-memory memo, then in the disk
cache, and only then draws the HW FET (``hybrid_waffle.write_gds``, which
asks Magic, through klayout-magic-pcells, for the unit device and the vias).
The disk cache is klayout-magic-pcells' ``GdsCache`` under
``<KMP_CACHE_DIR>/power``: ``v1/<versions digest>/HW_FET/<key>.gds`` and a
JSON sidecar holding the request, the generator's numbers (pitch, devices,
total W), the stamp and the SHA-256 of the GDS. The key covers the request,
the sky130A Magic/PDK/generator-code versions that klayout-magic-pcells
stamps its own cells with, this package's version and the text of the
generator module, so a new Magic, PDK or generator starts new entries.

Stamps have the form
``hw1;version=0.3.0;code=<12 hex>;magic=8.3.685;tech=...;pdk=sky130A;digest=<12 hex>``:
``code`` is a digest of ``hybrid_waffle.py`` and ``digest`` is
klayout-magic-pcells' versions digest of sky130A (Magic, PDK commit, tech
file, generator procs). The generated-by stamp adds ``;key=<16 hex>;grid=<nm>``
and is a GDS property (attribute 100) on one shape of the cell; the
created-with stamp is the hidden PCell parameter ``hw_created``.
"""

import hashlib
import json
import logging
import os
import time

PDK = "sky130A"
CELL = "HW_FET"
FORM = "flat"
STAMP_PREFIX = "hw1"
STAMP_ATTR = 100
FORMAT = 1          # cache format of this package's entries

log = logging.getLogger("klayout_power_pcells")

_HERE = os.path.dirname(os.path.abspath(__file__))
_CODE_FILES = ("hybrid_waffle.py",)


def code_digest(full=False):
    """SHA-256 over the generator's source: what decides the geometry."""
    h = hashlib.sha256()
    for name in _CODE_FILES:
        with open(os.path.join(_HERE, name), "rb") as f:
            h.update(name.encode() + b"\0" + f.read() + b"\0")
    d = h.hexdigest()
    return d if full else d[:12]


def _version():
    from . import __version__
    return __version__


def request_of(params):
    """The request text of an HWParams: every value as text, floats at 12
    significant digits (KLayout reopens a saved double up to one ULP off;
    see klayout-magic-pcells' README), pitch None as ''."""
    out = {}
    for k, v in sorted(params.as_dict().items()):
        if v is None:
            out[k] = ""
        elif isinstance(v, bool):
            out[k] = "1" if v else "0"
        elif isinstance(v, float):
            out[k] = "%.12g" % v
        else:
            out[k] = str(v)
    return out


def params_of(request):
    """The HWParams of a request (inverse of request_of)."""
    from .hybrid_waffle import HWParams
    r = request
    return HWParams(l=float(r["l"]), w=float(r["w"]), nf=int(r["nf"]), nx=int(r["nx"]),
                    ny=int(r["ny"]), strap_w=float(r["strap_w"]),
                    pitch=float(r["pitch"]) if r.get("pitch") else None,
                    device=r["device"], bulk=r["bulk"])


# -- stamps ----------------------------------------------------------------------

def make_stamp(kmp_versions, key=None, grid=None):
    from klayout_magic_pcells.stamp import versions_digest
    v = kmp_versions
    parts = [STAMP_PREFIX, "version=%s" % _version(), "code=%s" % code_digest(),
             "magic=%s" % v.magic, "tech=%s" % v.tech, "pdk=%s" % v.pdk,
             "digest=%s" % versions_digest(v)]
    if key:
        parts.append("key=%s" % key[:16])
    if grid:
        parts.append("grid=%s" % grid)
    return ";".join(parts)


def parse_stamp(text):
    if not isinstance(text, str) or not text.startswith(STAMP_PREFIX + ";"):
        return None
    out = {"format": STAMP_PREFIX}
    for part in text.split(";")[1:]:
        k, _, val = part.partition("=")
        out[k] = val
    return out


def same_versions(a, b):
    """Same generator code, Magic, tech, PDK and klayout-magic-pcells digest.
    The package version alone doesn't count: it changes without the geometry."""
    return all(a.get(k) == b.get(k) for k in ("code", "magic", "tech", "pdk", "digest"))


def describe(st):
    return " ".join("%s=%s" % (k, st.get(k)) for k in ("version", "code", "magic", "tech", "pdk", "digest")
                    if st.get(k))


def apply_stamp(layout, cell, stamp):
    from klayout_magic_pcells.stamp import _stamp_target
    sh = _stamp_target(layout, cell)
    if sh is None:
        return False
    sh.set_property(STAMP_ATTR, stamp)
    return True


def read_stamp(cell):
    layout = cell.layout()
    for li in layout.layer_indices():
        for sh in cell.shapes(li).each():
            if sh.prop_id:
                p = parse_stamp(sh.property(STAMP_ATTR))
                if p is not None:
                    return p
    return None


# -- the cache -----------------------------------------------------------------

def versions_fields(kmp_versions):
    from klayout_magic_pcells.cache import versions_fields as kmp_fields
    f = kmp_fields(kmp_versions, PDK)
    f.update({"power_format": FORMAT, "power_code": code_digest(full=True)})
    return f


def make_cache(cfg, kmp_versions):
    """GdsCache under <cache>/power, or a session-only one (KMP_CACHE=0, or a
    cache directory that can't be written)."""
    from klayout_magic_pcells import _cache_dir_problem, _log_warn
    from klayout_magic_pcells.cache import GdsCache
    root = os.path.join(cfg.cache_dir, "power")
    enabled = cfg.cache_enabled
    if enabled:
        why = _cache_dir_problem(root)
        if why:
            _log_warn("sky130_power: the cache directory %s can't be used (%s); continuing without "
                      "the disk cache. Set KMP_CACHE_DIR to a writable directory, or KMP_CACHE=0."
                      % (root, why))
            enabled = False
    return GdsCache(root, versions_fields(kmp_versions), enabled=enabled,
                    server_code=code_digest(full=True))


class Result:
    def __init__(self, key, gds_path, sidecar, source):
        self.key, self.gds_path, self.sidecar, self.source = key, gds_path, sidecar, source

    @property
    def stamp(self):
        return self.sidecar.get("stamp", "")

    @property
    def info(self):
        return self.sidecar.get("result", {})


class HWGenerator:
    """Memo, then disk cache, then the generator. Thread-safe enough for
    KLayout, which calls produce from one thread."""

    def __init__(self, cache, kmp_versions):
        self.cache = cache
        self.versions = kmp_versions
        self.fresh = False      # audit --regen: every get() draws again
        self.replaced = {}      # key -> copy of the disk entry a fresh get() replaced
        self._memo = {}
        self.stats = {"memo": 0, "disk": 0, "drawn": 0}

    def key(self, params):
        return self.cache.key(CELL, FORM, request_of(params))

    def peek(self, params):
        return self._memo.get(self.key(params))

    def evict(self, params):
        key = self.key(params)
        self._memo.pop(key, None)
        self.cache.evict(key, CELL)

    def clear_memo(self):
        self._memo.clear()

    def get(self, params):
        """Result for ``params``; raises HWParamError for refused values and
        RuntimeError (or what Magic raised) for failures."""
        import shutil
        from klayout_magic_pcells.importer import gds_grid_nm
        from .hybrid_waffle import write_gds
        key = self.key(params)
        hit = self._memo.get(key)
        if hit is not None and not os.path.isfile(hit.gds_path):
            del self._memo[key]
            hit = None
        if hit is not None and (not self.fresh or hit.source == "drawn"):
            self.stats["memo"] += 1
            return Result(hit.key, hit.gds_path, hit.sidecar, "memo")
        entry = self.cache.lookup(key, CELL)
        if entry is not None and not self.fresh:
            self.stats["disk"] += 1
            res = Result(key, entry[0], entry[1], "disk")
            self._memo[key] = res
            return res
        if entry is not None and key not in self.replaced:
            old = self.cache.tmp_path(key) + ".old"
            try:
                shutil.copyfile(entry[0], old)
                self.replaced[key] = old
            except OSError:
                pass
        tmp = self.cache.tmp_path(key)
        t0 = time.time()
        try:
            r = write_gds(params, tmp, name=CELL)
            grid = gds_grid_nm(tmp)
            sidecar = {
                "key": key, "request": request_of(params),
                "result": {"pitch": r.pitch, "strap_w": r.strap_w, "blocks": r.blocks,
                           "devices": r.devices, "w": r.w, "l": r.l, "nf": r.nf,
                           "total_w": r.total_w, "summary": r.summary(),
                           "magic_values": {k: str(v) for k, v in r.magic_values.items()
                                            if k != "kmp_dialog"}},
                "stamp": make_stamp(self.versions, key, grid), "grid_nm": grid,
                "versions": versions_fields(self.versions), "gen_s": round(time.time() - t0, 3),
                "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            gds = self.cache.store(key, CELL, tmp, sidecar)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        self.stats["drawn"] += 1
        res = Result(key, gds, sidecar, "drawn")
        self._memo[key] = res
        return res


# -- the package state -----------------------------------------------------------

class PowerState:
    def __init__(self):
        self.cfg = None
        self.versions = None
        self.cache = None
        self.generator = None
        self.library = None
        self.created_stamp = ""
        self.stamp_dict = {}
        self.last_error = None


state = PowerState()


def start(cfg=None):
    """Register klayout-magic-pcells' sky130A library if needed, and set up
    the generator. Returns the state; raises RuntimeError with the reason
    when sky130A's Magic can't start."""
    import klayout_magic_pcells as kmp
    lib = kmp.register(PDK, cfg=cfg) if cfg is not None else kmp.register(PDK)
    kst = kmp.state_for(PDK)
    if lib is None or kst.versions is None:
        raise RuntimeError("klayout-magic-pcells could not register sky130A (%s)" % (kst.last_error or "no reason given"))
    if state.generator is not None and state.versions is kst.versions:
        return state
    state.cfg = kst.cfg
    state.versions = kst.versions
    state.cache = make_cache(kst.cfg, kst.versions)
    state.generator = HWGenerator(state.cache, kst.versions)
    state.created_stamp = make_stamp(kst.versions)
    state.stamp_dict = parse_stamp(state.created_stamp)
    return state
