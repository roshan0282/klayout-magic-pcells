"""report.json and report.md for the parity harness."""

import json
import os
from collections import Counter, OrderedDict

FAMILY_ORDER = ("mos", "varactor", "res", "mim_cap", "diode", "photodiode", "fixed")
MAX_DETAIL = 150


def point_failures(pt, r):
    """The checks this point failed, in a fixed order."""
    f = []
    if "error" in r:
        return ["error"]
    if not r.get("sent", {}).get("equal", False):
        f.append("request")
    if not r.get("geometry", {}).get("identical", False):
        f.append("geometry")
    if not r.get("texts", {}).get("identical", False):
        f.append("texts")
    if not r.get("bbox", {}).get("equal", False):
        f.append("bbox")
    if not r.get("magic_cell", {}).get("equal", False):
        f.append("magic_cell")
    if not r.get("checked", {}).get("equal", False):
        f.append("checked")
    if r.get("cache") != "identical":
        f.append("cache")
    if r.get("placeholder") != "none":
        f.append("placeholder")
    st = r.get("stamp", "")
    if not (st == "ok" or st.startswith("n/a")):
        f.append("stamp")
    rt = r.get("roundtrip")
    if rt is not None and any(not (v == "ok" or str(v).startswith("n/a"))
                              for k, v in rt.items() if k != "traceback"):
        f.append("roundtrip")
    d = r.get("drc")
    if d is not None:
        if not d.get("equal") or d.get("single_matches_sheet") is False:
            f.append("drc")
        if d.get("baseline") not in (None, "ok", "updated"):
            f.append("drc_baseline")
    e = r.get("extract")
    if e is not None:
        if not e.get("equal"):
            f.append("extract")
        ident = e.get("identity", "")
        if not (ident == "ok" or ident.startswith("known Magic behaviour")):
            f.append("extract_identity")
    return f


def finalize(rep, points, results, manifest, out):
    fam_of = {d["name"]: d["family"] for d in manifest.get("devices", [])}
    by_check = Counter()
    by_family = OrderedDict()
    by_device = OrderedDict()
    pts = []
    for pt in points:
        r = results.get(pt["id"], {"error": ["no result"]})
        fails = point_failures(pt, r)
        r["result"] = "pass" if not fails else "fail"
        r["failures"] = fails
        for c in fails:
            by_check[c] += 1
        fam = pt.get("family") or fam_of.get(pt["device"], "other")
        for key, table in ((fam, by_family), (pt["device"], by_device)):
            row = table.setdefault(key, {"points": 0, "pass": 0, "fail": 0, "checks": Counter()})
            row["points"] += 1
            row["pass" if not fails else "fail"] += 1
            for c in fails:
                row["checks"][c] += 1
        rec = {"id": pt["id"], "device": pt["device"], "family": fam, "kind": pt["kind"],
               "aliases": pt.get("aliases", []), "request": pt["request"]}
        rec.update(r)
        pts.append(rec)
    tests = rep["steps"].get("tests", {})
    tests_ok = all(t.get("ok") for t in tests.values())
    manifest_ok = rep["steps"].get("manifest", {}).get("ok", True)
    n_fail = sum(1 for p in pts if p["result"] == "fail")
    rep["summary"] = {
        "pass": len(pts) - n_fail, "fail": n_fail, "points": len(pts),
        "by_check": {c: {"fail": by_check[c]} for c in sorted(by_check)},
        "by_family": {k: {"points": v["points"], "pass": v["pass"], "fail": v["fail"],
                          "checks": dict(v["checks"])} for k, v in by_family.items()},
        "tests_ok": tests_ok,
        "manifest_ok": manifest_ok,
        "observations": observations(pts),
    }
    rep["by_device"] = {k: {"points": v["points"], "pass": v["pass"], "fail": v["fail"],
                            "checks": dict(v["checks"])} for k, v in by_device.items()}
    rep["points"] = pts
    if rep["harness_errors"]:
        status = 2
    elif n_fail or not tests_ok or not manifest_ok or not pts:
        status = 1
    else:
        status = 0
    rep["exit_status"] = status
    with open(os.path.join(out, "report.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=1, default=list)
        f.write("\n")
    with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as f:
        f.write(markdown(rep))
    return status


def observations(pts):
    """Magic behaviour seen in the sweep (recorded, not checked)."""
    msgs = Counter()
    with_msgs = 0
    empty = []
    second = []
    known_ext = []
    for p in pts:
        ident = (p.get("extract") or {}).get("identity", "")
        if ident.startswith("known Magic behaviour"):
            known_ext.append([p["id"], p["device"], p["kind"], p["extract"]["ref"]])
        m = (p.get("messages") or "").strip()
        if m:
            with_msgs += 1
            for line in m.splitlines():
                msgs[line.strip()] += 1
        if p.get("empty_output"):
            empty.append(p["id"])
        if p.get("second_check_changes"):
            second.append([p["id"], p["device"], p["kind"], p["second_check_changes"]])
    return {"points_with_check_messages": with_msgs,
            "messages": [[k, v] for k, v in msgs.most_common(40)],
            "empty_outputs": empty,
            "second_check_changes": second,
            "known_extraction": known_ext}


def summary_line(rep):
    s = rep.get("summary", {})
    if rep.get("harness_errors"):
        return "PARITY ERROR (harness failed: %s)" % rep["harness_errors"][0].splitlines()[0]
    if s.get("fail") or not s.get("tests_ok", True) or not s.get("manifest_ok", True):
        parts = ", ".join("%s %d" % (c, v["fail"]) for c, v in s.get("by_check", {}).items())
        if not s.get("tests_ok", True):
            parts = (parts + ", " if parts else "") + "unit/backend tests failed"
        if not s.get("manifest_ok", True):
            parts = (parts + ", " if parts else "") + "shipped manifest differs from Magic"
        return "PARITY FAIL %d/%d (%s)" % (s.get("fail", 0), s.get("points", 0), parts)
    return "PARITY PASS %d/%d" % (s.get("pass", 0), s.get("points", 0))


def _fmt_checks(c):
    return ", ".join("%s %d" % kv for kv in sorted(c.items())) or "-"


def markdown(rep):
    m = rep.get("meta", {})
    s = rep.get("summary", {})
    L = []
    L.append("# Parity report\n")
    L.append("**%s**\n" % summary_line(rep))
    L.append("| | |\n|---|---|")
    for k in ("image", "magic", "tech", "open_pdks", "klayout", "repo", "seed", "points", "seconds"):
        L.append("| %s | `%s` |" % (k, m.get(k, "")))
    L.append("")
    if rep.get("harness_errors"):
        L.append("## Harness errors\n")
        for e in rep["harness_errors"]:
            L.append("```\n%s\n```" % e.strip())
        L.append("")
    man = rep.get("steps", {}).get("manifest")
    if man:
        L.append("## Manifest\n")
        L.append("`tools/build_manifest.py --check`: %s\n" % man.get("summary", ""))
    tests = rep.get("steps", {}).get("tests")
    if tests:
        L.append("## Unit and backend tests\n")
        L.append("| suite | ran | failures | errors | skipped | result |\n|---|---|---|---|---|---|")
        for k, t in tests.items():
            L.append("| %s | %d | %d | %d | %d | %s |" % (k, t["ran"], t["failures"], t["errors"],
                                                       t["skipped"], "ok" if t["ok"] else "FAIL"))
        L.append("")
    L.append("## Results by device family\n")
    L.append("| family | points | pass | fail | failed checks |\n|---|---|---|---|---|")
    fam = s.get("by_family", {})
    for k in sorted(fam, key=lambda x: (FAMILY_ORDER.index(x) if x in FAMILY_ORDER else 99, x)):
        v = fam[k]
        L.append("| %s | %d | %d | %d | %s |" % (k, v["points"], v["pass"], v["fail"], _fmt_checks(v["checks"])))
    L.append("")
    L.append("## Results by device\n")
    L.append("| device | points | pass | fail | failed checks |\n|---|---|---|---|---|")
    for k, v in rep.get("by_device", {}).items():
        L.append("| `%s` | %d | %d | %d | %s |" % (k, v["points"], v["pass"], v["fail"], _fmt_checks(v["checks"])))
    L.append("")
    st = rep.get("steps", {})
    L.append("## Steps\n")
    for k, v in st.items():
        if k == "tests":
            continue
        vv = {a: b for a, b in v.items() if a not in ("unassigned_markers",)}
        L.append("- **%s**: `%s`" % (k, json.dumps(vv, default=str)))
    L.append("")
    fails = [p for p in rep.get("points", []) if p.get("result") == "fail"]
    if fails:
        L.append("## Failing points (%d%s)\n" % (len(fails), ", first %d shown" % MAX_DETAIL
                                                   if len(fails) > MAX_DETAIL else ""))
        for p in fails[:MAX_DETAIL]:
            L.append("### %s `%s` %s\n" % (p["id"], p["device"], p["kind"]))
            L.append("- request: `%s`" % json.dumps(p["request"]))
            L.append("- failed: %s" % ", ".join(p["failures"]))
            if "error" in p:
                L.append("- error: `%s`" % " | ".join(p["error"])[:600])
            g = p.get("geometry", {})
            if g.get("diff_layers"):
                L.append("- layers that differ: %s (XOR in `%s`)" % (", ".join(g["diff_layers"]), g.get("xor")))
            t = p.get("texts", {})
            if t.get("only_ref") or t.get("only_pcell"):
                L.append("- texts only in Magic: `%s`; only in the PCell: `%s`" % (t.get("only_ref"), t.get("only_pcell")))
            for key in ("sent", "bbox", "magic_cell", "checked", "cache", "stamp", "roundtrip", "drc",
                        "extract"):
                if key in p["failures"] or (key == "drc" and "drc_baseline" in p["failures"]) or \
                        (key == "extract" and "extract_identity" in p["failures"]) or \
                        (key == "sent" and "request" in p["failures"]):
                    L.append("- %s: `%s`" % (key, json.dumps(p.get(key), default=list)[:800]))
            if (p.get("messages") or "").strip():
                L.append("- Magic's messages: `%s`" % " | ".join(p["messages"].strip().splitlines())[:400])
            L.append("")
    obs = s.get("observations", {})
    if obs:
        L.append("## Magic behaviour seen in the sweep (recorded, not checked)\n")
        L.append("- points where `_check` or `_draw` printed a message: %d" % obs.get("points_with_check_messages", 0))
        if obs.get("empty_outputs"):
            L.append("- points where Magic wrote a cell with no shapes (the PCell reproduces them): %d (%s)"
                     % (len(obs["empty_outputs"]), ", ".join(obs["empty_outputs"][:40])))
        if obs.get("second_check_changes"):
            L.append("- `below:` points where a second `_check` would change Magic's checked values: %d"
                     % len(obs["second_check_changes"]))
            for pid, dev, kind, diff in obs["second_check_changes"][:30]:
                L.append("  - %s `%s` %s: `%s`" % (pid, dev, kind, json.dumps(diff)))
        if obs.get("known_extraction"):
            L.append("- MOSFET points whose Magic extraction differs from the checked values in a known "
                     "way (`baseline/extract-known.json`; both sides give the same netlist): %d"
                     % len(obs["known_extraction"]))
            for pid, dev, kind, devs in obs["known_extraction"][:20]:
                L.append("  - %s `%s` %s: `%s`" % (pid, dev, kind, json.dumps(devs)))
        if obs.get("messages"):
            L.append("\nMost frequent messages:\n")
            L.append("| count | message |\n|---|---|")
            for msg, n in obs["messages"][:25]:
                L.append("| %d | %s |" % (n, msg.replace("|", "\\|")))
        L.append("")
    exc = rep.get("exclusions", [])
    if exc:
        L.append("## Excluded from the sweep\n")
        L.append("Every `_draw` proc in sky130A.tcl that has a `_defaults` proc is a PCell and is swept. "
                 "These %d are not devices:\n" % len(exc))
        L.append("| proc | reason |\n|---|---|")
        for e in exc:
            L.append("| `%s` | %s |" % (e["proc"], e["reason"]))
        L.append("")
    return "\n".join(L) + "\n"
