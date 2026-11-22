"""Round trips of saved PCell files, with and without the library.

Two modes, chosen by ``KMP_RT_MODE``:

``nolib`` (plain python3, library not registered):
    each pcell/<id>.gds and .oas must open as a cold proxy (``is_proxy()``
    true, ``is_pcell_variant()`` false, title ``<defunct><library>.…``)
    whose stored geometry compares identical to ref/<id>.gds and whose stamp
    reads back; the GDS is saved again as resaved/<id>.gds.

``lib`` (``klayout -b -rm pymacros/klayout_magic_pcells.lym -r roundtrip.py``):
    each file must open as a live PCell variant whose stored parameters are
    the manifest defaults overridden by the request, plus ``kmp_created``,
    and whose regenerated geometry compares identical to the ref;
    resaved/<id>.gds must come back live and identical; on ``default``
    points the variant is also placed in host layouts with dbu 0.0005 and
    0.005 and compared.

Inputs come from environment variables (``klayout -b -r`` owns argv):
KMP_RT_MODE, KMP_RT_POINTS (JSON list), KMP_RT_PCELL, KMP_RT_REF,
KMP_RT_RESAVED, KMP_RT_OUT.
"""

import json
import os
import sys
import traceback

import klayout.db as db

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
for p in (HERE, os.path.join(REPO, "python")):
    if p not in sys.path:
        sys.path.insert(0, p)

from compare import compare_layouts  # noqa: E402
from klayout_magic_pcells.stamp import read_stamp  # noqa: E402

sys.path.insert(0, os.path.join(REPO, "python"))
from klayout_magic_pcells.config import LIBRARY_NAMES  # noqa: E402

PDK = os.environ.get("KMP_PDK") or "sky130A"
LIB = LIBRARY_NAMES[PDK]
DEFUNCT = "<defunct>" + LIB + "."


def read(path):
    ly = db.Layout()
    ly.read(path)
    return ly


def device_cells(ly, top_name):
    """Cells other than the T<id> top and KLayout's context cell."""
    return [c for c in ly.each_cell()
            if c.name != top_name and not c.name.startswith("$$$CONTEXT")]


def identical(ref_ly, ref_top, ly, cell, text_attrs=True, text_dupes=True):
    r = compare_layouts(ref_ly, ref_ly.cell(ref_top), ly, cell, text_attrs=text_attrs,
                        text_dupes=text_dupes)
    if r["identical"]:
        return "ok"
    return "differs: " + ", ".join(l["layer"] for l in r["layers"] if l["status"] != "same")


def nolib(pt, env):
    res = {}
    ref_ly = read(os.path.join(env["ref"], pt["id"] + ".gds"))
    for fmt in ("gds", "oas"):
        path = os.path.join(env["pcell"], "%s.%s" % (pt["id"], fmt))
        ly = read(path)
        cells = device_cells(ly, "T" + pt["id"])
        if len(cells) != 1:
            res[fmt + "_nolib"] = "expected one device cell, found %d" % len(cells)
            continue
        c = cells[0]
        problems = []
        if not c.is_proxy():
            problems.append("not a proxy")
        if c.is_pcell_variant():
            problems.append("is a live PCell variant")
        if not c.display_title().startswith(DEFUNCT):
            problems.append("title %r" % c.display_title())
        # A KLayout 0.30.11 OASIS file keeps neither a text's size and
        # justification nor the second of two identical texts at one place.
        g = identical(ref_ly, pt["ref_top"], ly, c, text_attrs=(fmt != "oas"),
                      text_dupes=(fmt != "oas"))
        if g != "ok":
            problems.append("geometry " + g)
        if pt.get("expect_stamp", True):
            st = read_stamp(c)
            if st is None:
                problems.append("no stamp")
            elif st.get("key") != pt["key"][:16]:
                problems.append("stamp key %s" % st.get("key"))
        res[fmt + "_nolib"] = "ok" if not problems else "; ".join(problems)
        if fmt == "gds":
            os.makedirs(env["resaved"], exist_ok=True)
            ly.write(os.path.join(env["resaved"], pt["id"] + ".gds"))
    return res


def params_equal(spec, stored, expected):
    """Stored parameters against the expected ones.

    Doubles may come back one ULP off (KLayout writes and parses them with
    about 15 digits), so floats are compared to a relative 1e-12, and the
    request built from them must equal the original request exactly.
    """
    diffs = []
    for k in sorted(set(stored) | set(expected)):
        a, b = stored.get(k), expected.get(k)
        if isinstance(a, float) or isinstance(b, float):
            try:
                if abs(float(a) - float(b)) <= 1e-12 * max(1.0, abs(float(b))):
                    continue
            except (TypeError, ValueError):
                pass
        if a != b:
            diffs.append("%s=%r (expected %r)" % (k, a, b))
    ra = spec.build_request({k: v for k, v in stored.items() if spec.param(k)})
    rb = spec.build_request({k: v for k, v in expected.items() if spec.param(k)})
    for k in sorted(ra):
        if ra[k] != rb.get(k):
            diffs.append("request %s=%r (expected %r)" % (k, ra[k], rb.get(k)))
    return diffs


def off_grid_layers(ly, cell, grid_dbu):
    """Layers of a flat cell with vertices or texts off a multiple of grid_dbu."""
    out = set()
    for li in ly.layer_indices():
        info = ly.get_info(li)
        it = cell.begin_shapes_rec(li)
        while not it.at_end():
            sh = it.shape()
            t = it.trans()
            if sh.is_text():
                pts = [sh.text.transformed(t).trans.disp]
            else:
                pol = sh.polygon
                pts = list(pol.transformed(t).each_point_hull()) if pol is not None else []
            if any(p.x % grid_dbu or p.y % grid_dbu for p in pts):
                out.add("%d/%d" % (info.layer, info.datatype))
                break
            it.next()
    return out


def lib(pt, env, st):
    res = {}
    spec = st.manifest[pt["device"]]
    expected = spec.defaults_values()
    # The typed values come from the sweep, not from the plugin's parser.
    expected.update(pt["value"])
    expected["kmp_created"] = st.created_stamp
    ref_ly = read(os.path.join(env["ref"], pt["id"] + ".gds"))
    files = [("gds_lib", os.path.join(env["pcell"], pt["id"] + ".gds")),
             ("oas_lib", os.path.join(env["pcell"], pt["id"] + ".oas")),
             ("resave_lib", os.path.join(env["resaved"], pt["id"] + ".gds"))]
    for name, path in files:
        if not os.path.isfile(path):
            res[name] = "missing file %s" % path
            continue
        ly = read(path)
        cells = device_cells(ly, "T" + pt["id"])
        if len(cells) != 1:
            res[name] = "expected one device cell, found %d" % len(cells)
            continue
        c = cells[0]
        problems = []
        if not c.is_pcell_variant():
            problems.append("not a live PCell variant (title %r)" % c.display_title())
        else:
            d = params_equal(spec, c.pcell_parameters_by_name(), expected)
            if d:
                problems.append("parameters: " + "; ".join(d[:5]))
        g = identical(ref_ly, pt["ref_top"], ly, c)
        if g != "ok":
            problems.append("geometry " + g)
        res[name] = "ok" if not problems else "; ".join(problems)
    if pt["kind"] == "default":
        for dbu in (0.0005, 0.005):
            name = "dbu_%g" % dbu
            try:
                ly = db.Layout()
                ly.dbu = dbu
                pc = ly.create_cell(pt["device"], LIB, pt["value"])
                v = identical(ref_ly, pt["ref_top"], ly, pc)
                if v != "ok":
                    # Exact only if Magic's own coordinates sit on the host grid.
                    ratio = int(round(dbu / ref_ly.dbu))
                    off = off_grid_layers(ref_ly, ref_ly.cell(pt["ref_top"]), ratio) if ratio > 1 else set()
                    diff = set(v.split(": ", 1)[1].split(", ")) if ": " in v else set()
                    if off and diff <= off:
                        v = "n/a: Magic's GDS has coordinates off the %g um grid on %s" % (
                            dbu, ", ".join(sorted(off)))
                res[name] = v
            except Exception as e:
                res[name] = "error: %s" % e
    return res


def main():
    mode = os.environ["KMP_RT_MODE"]
    env = {"pcell": os.environ["KMP_RT_PCELL"], "ref": os.environ["KMP_RT_REF"],
           "resaved": os.environ["KMP_RT_RESAVED"]}
    with open(os.environ["KMP_RT_POINTS"], encoding="utf-8") as f:
        points = json.load(f)
    st = None
    if mode == "lib":
        import klayout_magic_pcells as kmp
        st = kmp.state_for(PDK)
        if st.library is None:
            raise SystemExit("roundtrip: library not registered: %s" % st.last_error)
    out = {}
    for pt in points:
        try:
            out[pt["id"]] = nolib(pt, env) if mode == "nolib" else lib(pt, env, st)
        except Exception as e:
            out[pt["id"]] = {"error": "%s: %s" % (type(e).__name__, e),
                             "traceback": traceback.format_exc()}
    with open(os.environ["KMP_RT_OUT"], "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print("ROUNDTRIP %s: %d points" % (mode, len(out)))


main()
