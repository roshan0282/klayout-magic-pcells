"""PCell declarations built from the manifest, one class per device.

``PCellDeclarationHelper.param()`` installs a descriptor on the class, so each
device gets its own subclass; sharing one class would mix up parameters.
"""

import hashlib
import json
import logging

from ._kl import db, warn, error
from .importer import insert_gds_flat
from .manifest import DISPLAY_PARAMS, InvalidValue
from .stamp import apply_stamp, parse_stamp, same_versions

log = logging.getLogger("klayout_magic_pcells")

PLACEHOLDER_LAYER = (255, 0)
CREATED_PARAM = "kmp_created"


class PCellNameError(Exception):
    pass


def _ktype(helper, ptype):
    return {
        "float": helper.TypeDouble,
        "int": helper.TypeInt,
        "bool01": helper.TypeBoolean,
        "signed": helper.TypeString,
        "string": helper.TypeString,
    }[ptype]


def _num_equal(a, b):
    if a == b:
        return True
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return False


def changed_params(request, checked):
    """Parameters whose value ``_check`` changed (numerically, for numbers)."""
    out = {}
    for k, v in request.items():
        if k in checked and not _num_equal(v, checked[k]):
            out[k] = checked[k]
    return out


def reserved_names():
    return set(dir(db.PCellDeclarationHelper))


def check_names(spec):
    bad = [p.name for p in spec.params if p.name in reserved_names() or p.name == CREATED_PARAM]
    if bad:
        raise PCellNameError("%s: parameter name(s) %s collide with PCellDeclarationHelper "
                             "attributes" % (spec.name, ", ".join(bad)))


def draw_placeholder(layout, cell, device, reason):
    li = layout.layer(*PLACEHOLDER_LAYER)
    cell.shapes(li).insert(db.DBox(-0.5, -0.5, 0.5, 0.5))
    text = "KMP_ERROR %s: %s" % (device, " ".join(str(reason).split())[:400])
    cell.shapes(li).insert(db.DText(text, db.DTrans()))


def make_pcell(spec, state):
    """Return a PCellDeclarationHelper instance for ``spec``.

    ``state`` is the package's runtime state: ``state.generator``,
    ``state.created_stamp``, ``state.stamp_dict`` and ``state.cfg``.
    """
    check_names(spec)
    lead = [n for n in DISPLAY_PARAMS.get(spec.family, ()) if spec.param(n)]

    class _DevicePCell(db.PCellDeclarationHelper):
        def __init__(self):
            super().__init__()
            for p in spec.params:
                kw = {"default": p.default_value(), "tooltip": p.label}
                if p.unit:
                    kw["unit"] = p.unit
                self.param(p.name, _ktype(self, p.type), p.description, **kw)
            self.param(CREATED_PARAM, self.TypeString, "Created with", hidden=True,
                       readonly=True, default=state.created_stamp)
            self._warned = set()

        # -- helpers ------------------------------------------------------

        def _values(self):
            return {p.name: getattr(self, p.name) for p in spec.params}

        def _request(self, check=True):
            # check=False only for names and labels, which never reach Magic
            # and must never fail (a failing cell name leaves an unreadable
            # file, K3).
            return spec.build_request(self._values(), check=check)

        # -- KLayout hooks ------------------------------------------------

        def display_text_impl(self):
            try:
                req = self._request(check=False)
                res = state.generator.peek(spec, req) if state.generator else None
                changed = changed_params(req, res.checked) if res else {}
                parts = []
                for n in lead:
                    v = req[n]
                    if n in changed:
                        v = "%s*" % changed[n]
                    parts.append("%s=%s" % (n, v))
                return "%s(%s)" % (spec.short_name, " ".join(parts))
            except Exception as e:  # never break the GUI over a label
                return "%s(?: %s)" % (spec.short_name, e)

        def cell_name_impl(self):
            # Hash the request strings, not the raw doubles: a double read back
            # from a saved file can be one ULP off (see ParamSpec.format).
            vals = self._request(check=False)
            vals[CREATED_PARAM] = getattr(self, CREATED_PARAM)
            text = json.dumps(vals, sort_keys=True, separators=(",", ":"))
            return "%s__kmp_%s" % (spec.name, hashlib.sha256(text.encode("utf-8")).hexdigest()[:8])

        def wants_lazy_evaluation(self):
            return bool(state.cfg.lazy)

        def produce_impl(self):
            try:
                req = self._request()
                if state.generator is None:
                    raise RuntimeError("the Magic backend is not running")
                res = state.generator.get(spec, req)
                try:
                    insert_gds_flat(self.layout, self.cell, res.gds_path)
                except Exception as e:
                    if res.source == "magic":
                        raise
                    # A remembered or cached GDS that KLayout can't read:
                    # forget it and ask Magic once.
                    warn("sky130_magic %s: the cached GDS %s can't be read (%s); regenerating it"
                         % (spec.short_name, res.gds_path, e))
                    state.generator.evict(spec, req)
                    self.cell.clear_shapes()
                    res = state.generator.get(spec, req)
                    insert_gds_flat(self.layout, self.cell, res.gds_path)
                if not apply_stamp(self.layout, self.cell, res.stamp):
                    # Magic wrote a cell with no shapes (for example resistor
                    # l=0, where _draw fails on the "1.0u" that _check puts
                    # in). Parity means drawing the same nothing; say so.
                    if ("empty", res.key) not in self._warned:
                        self._warned.add(("empty", res.key))
                        warn("sky130_magic %s: Magic drew nothing for these parameters: %s"
                             % (spec.short_name,
                                " | ".join(res.messages.strip().splitlines()) or "no message"))
                    return
                if res.messages.strip() and res.key not in self._warned:
                    self._warned.add(res.key)
                    warn("sky130_magic %s: Magic's _check: %s"
                         % (spec.short_name, " | ".join(res.messages.strip().splitlines())))
                created = parse_stamp(getattr(self, CREATED_PARAM) or "")
                if created and not same_versions(created, state.stamp_dict):
                    key = ("created", getattr(self, CREATED_PARAM))
                    if key not in self._warned:
                        self._warned.add(key)
                        warn("sky130_magic %s: instance created with %s, regenerated with %s"
                             % (spec.short_name, getattr(self, CREATED_PARAM), state.created_stamp))
            except Exception as e:
                log.debug("produce failed", exc_info=True)
                error("sky130_magic %s: generation failed, drawing a placeholder on %d/%d: %s"
                      % (spec.short_name, PLACEHOLDER_LAYER[0], PLACEHOLDER_LAYER[1], e))
                try:
                    self.cell.clear_shapes()
                except Exception:
                    pass
                draw_placeholder(self.layout, self.cell, spec.name, e)

        def callback_impl(self, name):
            # GUI form only: self.<p> is a PCellParameterState here.
            states = self._param_states
            if states is None or not spec.params:
                return
            try:
                values = {p.name: states.parameter(p.name).value for p in spec.params}
                req = spec.build_request(values)
                chk = state.generator.check(spec, req)
            except InvalidValue as e:
                st = states.parameter(e.param)
                st.icon = db.PCellParameterState.ErrorIcon
                st.tooltip = str(e)
                return
            except Exception as e:
                st = states.parameter(spec.params[0].name)
                st.icon = db.PCellParameterState.ErrorIcon
                st.tooltip = "Magic backend failed: %s" % e
                return
            changed = changed_params(req, chk.checked)
            msg = " ".join(chk.log.split())
            for p in spec.params:
                st = states.parameter(p.name)
                if p.name in changed:
                    st.icon = db.PCellParameterState.WarningIcon
                    st.tooltip = "Magic draws %s (entered %s)%s" % (
                        changed[p.name], req[p.name], (": " + msg) if msg else "")
                else:
                    st.icon = db.PCellParameterState.NoIcon
                    st.tooltip = p.label

    _DevicePCell.__name__ = "PCell_" + spec.name
    return _DevicePCell()
