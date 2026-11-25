"""Generation, cache and stamps for the sky130_power library.

``HWGenerator.get(params)`` looks in an in-memory memo, then in the disk
cache, and only then draws the FET (``waffle.write_gds``). Drawing needs
only KLayout: the FET is drawn from raw layers with the rule table in
rules.py. Magic and netgen are used for verification only (verify.py).

The disk cache is klayout-magic-pcells' ``GdsCache`` under
``<KMP_CACHE_DIR>/power``: ``v1/<versions digest>/HW_FET/<key>.gds`` plus a
JSON sidecar with the request, the generator's report (gates, W, areas,
diffusion-to-tap distance), the stamp and the SHA-256 of the GDS. The key
covers the request, the generator's source (waffle.py, rules.py) and the
cache format, so a changed generator or rule starts new entries.

Stamps: ``hw2;version=0.9.0;code=<12 hex>;pdk=sky130A;rules=<12 hex>``,
``code`` a digest of the generator's source and ``rules`` of the PDK's rule
table. The generated-by stamp adds ``;key=<16 hex>;grid=<nm>`` and is a GDS
property (attribute 100) on one shape of the cell; the created-with stamp
is the hidden PCell parameter ``hw_created``.
"""

import hashlib
import json
import logging
import os
import time

CELL = "HW_FET"
FORM = "flat"
STAMP_PREFIX = "hw2"
STAMP_ATTR = 100
FORMAT = 2          # cache format of this package's entries

log = logging.getLogger("klayout_power_pcells")

_HERE = os.path.dirname(os.path.abspath(__file__))
_CODE_FILES = ("waffle.py", "rules.py")


def code_digest(full=False):
    """SHA-256 over the generator's source: what decides the geometry."""
    h = hashlib.sha256()
    for name in _CODE_FILES:
        with open(os.path.join(_HERE, name), "rb") as f:
            h.update(name.encode() + b"\0" + f.read() + b"\0")
    d = h.hexdigest()
    return d if full else d[:12]


def rules_digest(pdk="sky130A"):
    from .rules import PDKS
    text = json.dumps(PDKS[pdk], sort_keys=True, separators=(",", ":"), default=list)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _version():
    from . import __version__
    return __version__


def request_of(params):
    """The request text of a WaffleParams: every value as text, floats at
    12 significant digits (KLayout reopens a saved double up to one ULP off;
    see klayout-magic-pcells' README), None as ''."""
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
    """The WaffleParams of a request (inverse of request_of)."""
    from .waffle import WaffleParams
    r = request

    def f(k):
        return float(r[k]) if r.get(k) else None
    return WaffleParams(device=r["device"], nx=int(r["nx"]), ny=int(r["ny"]), P=f("P"), L=f("L"),
                        N=f("N"), gate_strap=r["gate_strap"], runners=tuple(r["runners"].split(",")),
                        runner_style=r["runner_style"], bus=r["bus"], bus_w=f("bus_w"),
                        guard_ring=r["guard_ring"] == "1", frame_w=f("frame_w"), pdk=r["pdk"],
                        source_taps=r.get("source_taps", "1") == "1", tap_w=f("tap_w"),
                        deep_nwell=r.get("deep_nwell", "1") == "1",
                        bottom_net=r.get("bottom_net", "S"), runner_w=f("runner_w"))


# -- stamps ----------------------------------------------------------------------

def make_stamp(pdk="sky130A", key=None, grid=None):
    parts = [STAMP_PREFIX, "version=%s" % _version(), "code=%s" % code_digest(), "pdk=%s" % pdk,
             "rules=%s" % rules_digest(pdk)]
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
    """Same generator code, PDK and rule table. The package version alone
    doesn't count: it changes without the geometry."""
    return all(a.get(k) == b.get(k) for k in ("code", "pdk", "rules"))


def describe(st):
    return " ".join("%s=%s" % (k, st.get(k)) for k in ("version", "code", "pdk", "rules") if st.get(k))


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

def versions_fields(pdk="sky130A"):
    return {"power_format": FORMAT, "pdk": pdk, "power_code": code_digest(full=True), "rules": rules_digest(pdk)}


def make_cache(cfg):
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
    return GdsCache(root, versions_fields(), enabled=enabled, server_code=code_digest(full=True))


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
    """Memo, then disk cache, then the generator."""

    def __init__(self, cache):
        self.cache = cache
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
        """Result for ``params``; raises WaffleError for values the generator
        refuses (``param`` names the parameter)."""
        import shutil
        from klayout_magic_pcells.importer import gds_grid_nm
        from .waffle import summary, write_gds
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
            w = write_gds(params, tmp, name=CELL)
            grid = gds_grid_nm(tmp)
            result = dict(w.report)
            result["summary"] = summary(w)
            sidecar = {
                "key": key, "request": request_of(params), "result": result,
                "stamp": make_stamp(params.pdk, key, grid), "grid_nm": grid,
                "versions": versions_fields(params.pdk), "gen_s": round(time.time() - t0, 3),
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
        self.cache = None
        self.generator = None
        self.library = None
        self.created_stamp = ""
        self.stamp_dict = {}
        self.last_error = None


state = PowerState()


def start(cfg=None):
    """Set up the cache and the generator (idempotent). Uses
    klayout-magic-pcells' settings (KMP_CACHE_DIR, KMP_CACHE, KMP_LAZY);
    needs no Magic."""
    if state.generator is not None and (cfg is None or cfg is state.cfg):
        return state
    if cfg is None:
        from klayout_magic_pcells.config import Config
        cfg = Config.load(pdk="sky130A")
    state.cfg = cfg
    state.cache = make_cache(cfg)
    state.generator = HWGenerator(state.cache)
    state.created_stamp = make_stamp()
    state.stamp_dict = parse_stamp(state.created_stamp)
    return state
