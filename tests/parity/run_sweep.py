#!/usr/bin/env python3
"""Parity harness driver. Run it inside the pinned image (scripts/parity.sh).

    python3 tests/parity/run_sweep.py --out out/parity [--quick] [--devices GLOB ...]
        [--keep] [--update-baseline] [--no-unit] [--no-drc] [--no-extract] [--jobs N]

Steps, each writing under --out:
  0. unit and backend tests (tests/unit, tests/backend)
  1. versions.json
  2. sweep.json (gen_sweep.py)
  3. path A, Magic alone (magic_ref.tcl)        -> ref/
  4. path B, the PCell, empty cache (pcell_path.py) -> pcell/; again warm -> pcell_warm/
  5. per-point checks: the request path B sent, geometry, texts, bounding box,
     Magic cell name, checked dict, cache, placeholder, stamp
  6. round trips (roundtrip.py)
  7. DRC on sheets, both tools, both sides, plus the defaults one at a time
  8. extraction of the MOSFET points
  9. report.json, report.md

Exit status: 0 when every check passes, 1 when any check fails, 2 when the
harness itself fails.
"""

import argparse
import concurrent.futures as cf
import json
import multiprocessing
import os
import random
import re
import shutil
import subprocess
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "python"))

import report  # noqa: E402

LYM = os.path.join(REPO, "pymacros", "klayout_magic_pcells.lym")
MANIFEST = os.path.join(REPO, "python", "klayout_magic_pcells", "data", "manifest-sky130A.json")
BASELINE = os.path.join(HERE, "baseline", "drc-defaults.json")
PDK_ROOT = os.environ.get("PDK_ROOT", "/foss/pdks")
MAGICRC = os.path.join(PDK_ROOT, "sky130A", "libs.tech", "magic", "sky130A.magicrc")
SHEET_SIZE = 250
CHECKS = ("error", "request", "geometry", "texts", "bbox", "magic_cell", "checked", "cache",
          "placeholder", "stamp", "roundtrip", "drc", "drc_baseline", "extract")


class HarnessError(Exception):
    pass


def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def run(cmd, log_path, env=None, cwd=None, timeout=7200, shell=False):
    with open(log_path, "w") as lf:
        p = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                           env=env, cwd=cwd, timeout=timeout, shell=shell)
    return p.returncode


def tail(path, n=20):
    try:
        with open(path, errors="replace") as f:
            return "".join(f.readlines()[-n:])
    except OSError:
        return ""


# --- step 0: unit and backend tests ------------------------------------------

def step_unit(out):
    res = {}
    for suite in ("unit", "backend"):
        lp = os.path.join(out, "test_%s.log" % suite)
        env = dict(os.environ, KMP_CACHE_DIR=os.path.join(out, "cache-tests"))
        rc = run([sys.executable, "-m", "unittest", "discover", "-s", os.path.join("tests", suite),
                  "-t", ".", "-v"], lp, env=env, cwd=REPO)
        text = tail(lp, 400)
        m = re.search(r"Ran (\d+) tests?", text)
        skipped = re.search(r"skipped=(\d+)", text)
        fails = re.search(r"failures=(\d+)", text)
        errs = re.search(r"errors=(\d+)", text)
        res[suite] = {"rc": rc, "ran": int(m.group(1)) if m else 0,
                      "failures": int(fails.group(1)) if fails else 0,
                      "errors": int(errs.group(1)) if errs else 0,
                      "skipped": int(skipped.group(1)) if skipped else 0,
                      "ok": rc == 0, "log": os.path.relpath(lp, out)}
        log("tests/%s: %s" % (suite, res[suite]))
    return res


# --- step 1: versions -----------------------------------------------------------

def step_versions(out):
    from klayout_magic_pcells.backend import MagicServer
    from klayout_magic_pcells.config import Config
    cfg = Config.load(env=dict(os.environ, KMP_CACHE_DIR=os.path.join(out, "cache-versions")))
    s = MagicServer(cfg)
    try:
        v = s.start()
    finally:
        s.close()
    shutil.rmtree(os.path.join(out, "cache-versions"), ignore_errors=True)
    kl = subprocess.run(["klayout", "-v"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    rev = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL)
    dirty = subprocess.run(["git", "-C", REPO, "status", "--porcelain", "--untracked-files=no"],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    rev_s = rev.stdout.decode().strip() or "unknown"
    if dirty.stdout.strip():
        rev_s += "-dirty"
    meta = v.as_dict()
    meta.update({"klayout": kl.stdout.decode().strip().replace("KLayout ", ""),
                 "image": os.environ.get("KMP_IMAGE", ""), "repo": rev_s,
                 "python": sys.version.split()[0]})
    with open(os.path.join(out, "versions.json"), "w") as f:
        json.dump(meta, f, indent=1)
    return meta


# --- steps 3 and 4: the two paths -------------------------------------------------

PATH_A_STALL = 300  # seconds without a finished point before path A counts as hung


def _count_lines(path):
    try:
        with open(path, "rb") as f:
            return sum(1 for line in f if line.endswith(b"\n"))
    except OSError:
        return 0


def path_a(out, sweep_path, cmd=None, stall=PATH_A_STALL):
    """Run magic_ref.tcl over the sweep.

    If Magic dies or stops making progress on a point (a segfault, or a
    generator loop that prints nothing), that point is recorded as a Magic
    error and Magic is started again on the next point, so one bad point
    can't hang or end the sweep.
    """
    cmd = cmd or ["magic", "-dnull", "-noconsole", "-rcfile", MAGICRC, os.path.join(HERE, "magic_ref.tcl")]
    with open(sweep_path, encoding="utf-8") as f:
        pts = json.load(f)["points"]
    ref_dir = os.path.join(out, "ref")
    ix = os.path.join(ref_dir, "index.jsonl")
    lp = os.path.join(out, "path_a.log")
    t = time.time()
    start, idle_runs, restarts = 0, 0, []
    with open(lp, "w") as lf:
        while start < len(pts):
            env = dict(os.environ, KMP_SWEEP=sweep_path, KMP_OUT=ref_dir, KMP_START=str(start))
            lf.flush()
            p = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                 env=env, cwd=out)
            last_n, last_t, status = -1, time.monotonic(), None
            while status is None:
                try:
                    status = p.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
                n = _count_lines(ix)
                if n != last_n:
                    last_n, last_t = n, time.monotonic()
                elif status is None and time.monotonic() - last_t > stall:
                    p.kill()
                    p.wait()
                    status = "hung"
            n = _count_lines(ix)
            if n >= len(pts):
                break
            if n <= start:
                idle_runs += 1
                if idle_runs >= 5:
                    raise HarnessError("path A made no progress in 5 runs; see %s:\n%s" % (lp, tail(lp)))
            else:
                idle_runs = 0
            bad = pts[n]
            why = ("no point finished for %d s" % stall) if status == "hung" else "Magic exited (status %s)" % status
            rec = {"id": bad["id"], "device": bad["device"], "rc": 1, "top": "", "magic_cell": "", "log": "",
                   "error": "path A watchdog: %s on this point; Magic restarted on the next one" % why,
                   "checked": {}}
            os.makedirs(ref_dir, exist_ok=True)
            with open(ix, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
            restarts.append(bad["id"])
            lf.write("\n[run_sweep] %s: %s; restarting at the next point\n" % (bad["id"], why))
            start = n + 1
    recs = {}
    with open(ix, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            recs[r["id"]] = r
    missing = [pt["id"] for pt in pts if pt["id"] not in recs]
    if missing:
        raise HarnessError("path A wrote no record for %d points (first %s); see %s" % (len(missing), missing[0], lp))
    if restarts:
        log("  path A restarted Magic after %s" % ", ".join(restarts))
    return recs, round(time.time() - t, 1)


def path_b(out, sweep_path, dirname):
    env = dict(os.environ, KMP_SWEEP=sweep_path, KMP_OUT=os.path.join(out, dirname),
               KMP_CACHE_DIR=os.path.join(out, "cache"))
    lp = os.path.join(out, "path_b_%s.log" % dirname)
    t = time.time()
    run(["klayout", "-b", "-rm", LYM, "-r", os.path.join(HERE, "pcell_path.py")], lp, env=env, cwd=out)
    ix = os.path.join(out, dirname, "index.json")
    if not os.path.isfile(ix):
        raise HarnessError("path B (%s) wrote no index; see %s:\n%s" % (dirname, lp, tail(lp)))
    with open(ix, encoding="utf-8") as f:
        data = json.load(f)
    if not data.get("registered"):
        raise HarnessError("path B: the library did not register: %s" % data.get("error"))
    return data, round(time.time() - t, 1)


# --- step 5: per-point checks ---------------------------------------------------

_CTX = {}


def _init_worker(ctx):
    _CTX.update(ctx)


def check_point(job):
    """Runs in a worker process; returns a dict of check results."""
    from compare import compare_cells
    from klayout_magic_pcells.stamp import read_stamp
    import klayout.db as db
    out, manifest_bbox = _CTX["out"], _CTX["bboxes"]
    pt, ra, pb, pw, cur = job["point"], job["ref"], job["pcell"], job["warm"], job["stamp"]
    pid = pt["id"]
    r = {}
    errs = []
    if ra is None or ra.get("rc"):
        errs.append("path A: %s" % ((ra or {}).get("error") or "no record").strip())
    if pb is None or pb.get("error"):
        errs.append("path B: %s" % ((pb or {}).get("error") or "no record"))
    if errs:
        r["error"] = errs
        return pid, r
    # What path B sent must be exactly what path A gave Magic: the point's
    # values over the manifest defaults.
    exp = dict(_CTX["req_defaults"][pt["device"]])
    exp.update(pt["request"])
    got = pb.get("request") or {}
    rdiff = {k: [exp.get(k), got.get(k)] for k in sorted(set(exp) | set(got)) if exp.get(k) != got.get(k)}
    r["sent"] = {"equal": not rdiff, "diff": rdiff}
    ref_gds = os.path.join(out, "ref", pid + ".gds")
    pc_gds = os.path.join(out, "pcell", pid + ".gds")
    xor = os.path.join(out, "xor", pid + ".gds")
    try:
        c = compare_cells(ref_gds, ra["top"], pc_gds, pb["variant"])
        if not c["identical"]:
            os.makedirs(os.path.dirname(xor), exist_ok=True)
            compare_cells(ref_gds, ra["top"], pc_gds, pb["variant"], xor_out=xor)
    except Exception as e:
        r["error"] = ["compare: %s" % e]
        return pid, r
    geo_diff = [l["layer"] for l in c["layers"] if l["xor_polygons"] or l["xor_area_um2"]]
    only_ref = [[l["layer"]] + t for l in c["layers"] for t in l["texts_only_a"]]
    only_pc = [[l["layer"]] + t for l in c["layers"] for t in l["texts_only_b"]]
    r["geometry"] = {"identical": not geo_diff, "diff_layers": geo_diff,
                     "xor": os.path.relpath(xor, out) if geo_diff or only_ref or only_pc else None}
    r["texts"] = {"identical": not only_ref and not only_pc, "only_ref": only_ref, "only_pcell": only_pc}
    bref, bpc = c["a"]["geometry_bbox_um"], c["b"]["geometry_bbox_um"]
    bb = {"ref": bref, "pcell": bpc, "equal": bref == bpc}
    if pt["kind"] == "default":
        mb = manifest_bbox.get(pt["device"])
        bb["manifest"] = mb
        bb["equal"] = bb["equal"] and (mb == bref)
    r["bbox"] = bb
    r["magic_cell"] = {"ref": ra["magic_cell"], "pcell": pb.get("magic_cell"),
                       "equal": ra["magic_cell"] == pb.get("magic_cell")}
    ca, cb = ra.get("checked") or {}, pb.get("checked") or {}
    r["checked"] = {"equal": ca == cb,
                    "diff": {k: [ca.get(k), cb.get(k)] for k in sorted(set(ca) | set(cb))
                             if ca.get(k) != cb.get(k)}}
    # cache: cold run went to Magic, warm run came from disk, same geometry
    cache = []
    if pb.get("source") != "magic":
        cache.append("cold source %s" % pb.get("source"))
    if pw is None or pw.get("error"):
        cache.append("warm run: %s" % ((pw or {}).get("error") or "no record"))
    else:
        if pw.get("source") != "disk":
            cache.append("warm source %s" % pw.get("source"))
        try:
            cw = compare_cells(pc_gds, pb["variant"], os.path.join(out, "pcell_warm", pid + ".gds"),
                               pw["variant"])
            if not cw["identical"]:
                cache.append("warm geometry differs")
        except Exception as e:
            cache.append("warm compare: %s" % e)
    r["cache"] = "identical" if not cache else "; ".join(cache)
    # placeholder and stamp, read without the library
    ly = db.Layout()
    ly.read(pc_gds)
    cell = ly.cell(pb["variant"])
    ph = ly.find_layer(255, 0)
    r["placeholder"] = "present" if ph is not None and not cell.shapes(ph).is_empty() else "none"
    empty = bref is None and not c["a"]["cells_below"] and not any(
        l["texts_a"] for l in c["layers"])
    st = read_stamp(cell)
    if empty:
        r["stamp"] = "n/a (Magic wrote no shapes)" if st is None else "unexpected stamp"
        r["empty_output"] = True
    elif st is None:
        r["stamp"] = "missing"
    else:
        bad = [k for k in ("magic", "tech", "pdk") if st.get(k) != cur.get(k)]
        if st.get("key") != (pb.get("key") or "")[:16]:
            bad.append("key")
        r["stamp"] = "ok" if not bad else "mismatch: " + ", ".join(bad)
    return pid, r


def step_checks(out, points, ref, pcell, warm, cur_stamp, manifest, jobs):
    from klayout_magic_pcells.manifest import Manifest
    bboxes = {d["name"]: d["defaults_run"].get("gds_bbox_um") for d in manifest["devices"]}
    req_defaults = {d.name: {p.name: p.default for p in d.params} for d in Manifest(manifest).devices}
    work = [{"point": pt, "ref": ref.get(pt["id"]), "pcell": pcell.get(pt["id"]),
             "warm": warm.get(pt["id"]), "stamp": cur_stamp} for pt in points]
    ctx = multiprocessing.get_context("fork")
    with ctx.Pool(jobs, initializer=_init_worker,
                  initargs=({"out": out, "bboxes": bboxes, "req_defaults": req_defaults},)) as pool:
        return dict(pool.map(check_point, work, chunksize=8))


def step_idempotence(points, pcell, cfg_env):
    """For below: points, would a second _check change Magic's checked dict?
    Recorded, not checked."""
    from klayout_magic_pcells.backend import MagicServer
    from klayout_magic_pcells.config import Config
    cfg = Config.load(env=cfg_env)
    s = MagicServer(cfg)
    s.start()
    out = {}
    try:
        for pt in points:
            if not pt["kind"].startswith("below:"):
                continue
            pb = pcell.get(pt["id"]) or {}
            chk = pb.get("checked")
            if not chk:
                continue
            again = s.check(pt["device"], chk).checked
            diff = {k: [chk.get(k), again.get(k)] for k in sorted(set(chk) | set(again))
                    if chk.get(k) != again.get(k)}
            out[pt["id"]] = {"second_check_changes": diff}
    finally:
        s.close()
    return out


# --- step 6: round trips ------------------------------------------------------------

def step_roundtrip(out, points, ref, pcell, results, seed):
    rng = random.Random(seed)
    chosen = []
    for pt in points:
        k = pt["kind"].split(":")[0]
        r = results.get(pt["id"], {})
        if "error" in r:
            continue
        if k in ("default", "min", "max") or rng.random() < 0.10:
            chosen.append({"id": pt["id"], "device": pt["device"], "kind": pt["kind"],
                           "request": pt["request"], "ref_top": ref[pt["id"]]["top"],
                           "key": pcell[pt["id"]].get("key") or "",
                           "expect_stamp": not r.get("empty_output")})
    rt = os.path.join(out, "roundtrip")
    os.makedirs(rt, exist_ok=True)
    pts_path = os.path.join(rt, "points.json")
    with open(pts_path, "w") as f:
        json.dump(chosen, f)
    env = dict(os.environ, KMP_RT_POINTS=pts_path, KMP_RT_PCELL=os.path.join(out, "pcell"),
               KMP_RT_REF=os.path.join(out, "ref"), KMP_RT_RESAVED=os.path.join(out, "resaved"),
               KMP_CACHE_DIR=os.path.join(out, "cache"))
    res = {}
    for mode in ("nolib", "lib"):
        e = dict(env, KMP_RT_MODE=mode, KMP_RT_OUT=os.path.join(rt, mode + ".json"))
        lp = os.path.join(rt, mode + ".log")
        if mode == "nolib":
            cmd = [sys.executable, os.path.join(HERE, "roundtrip.py")]
        else:
            cmd = ["klayout", "-b", "-rm", LYM, "-r", os.path.join(HERE, "roundtrip.py")]
        run(cmd, lp, env=e, cwd=out)
        if not os.path.isfile(e["KMP_RT_OUT"]):
            raise HarnessError("roundtrip %s wrote nothing; see %s:\n%s" % (mode, lp, tail(lp)))
        with open(e["KMP_RT_OUT"]) as f:
            for pid, d in json.load(f).items():
                res.setdefault(pid, {}).update(d)
    return res, len(chosen)


# --- steps 7 and 8: DRC and extraction ------------------------------------------------

def build_sheets(out, points, ref, pcell, results):
    from sheet import build_sheet, chunks
    d = os.path.join(out, "drc")
    os.makedirs(d, exist_ok=True)
    sheets = []
    ok = [pt for pt in points if "error" not in results.get(pt["id"], {})]
    # One device per sheet. On a sheet that mixed devices, Magic logged a unit
    # rescale when it read vendor cells with off-grid coordinates, and its DRC
    # result for an npn then differed from the npn checked alone.
    by_dev = {}
    for pt in ok:
        by_dev.setdefault(pt["device"], []).append(pt)
    for side in ("ref", "pcell"):
        for di, (dev, pts) in enumerate(sorted(by_dev.items())):
            ents = []
            for pt in pts:
                cell = ref[pt["id"]]["top"] if side == "ref" else pcell[pt["id"]]["variant"]
                ents.append((pt["id"], os.path.join(out, side, pt["id"] + ".gds"), cell))
            for k, ch in enumerate(chunks(ents, SHEET_SIZE)):
                path = os.path.join(d, "%s_%02d_%d.gds" % (side, di, k))
                placed, errors = build_sheet(ch, path)
                sheets.append({"side": side, "path": path, "placed": placed, "errors": errors,
                               "single": False, "device": dev})
    for pt in ok:
        if pt["kind"] != "default":
            continue
        path = os.path.join(d, "single_%s.gds" % pt["id"])
        placed, errors = build_sheet([(pt["id"], os.path.join(out, "pcell", pt["id"] + ".gds"),
                                       pcell[pt["id"]]["variant"])], path)
        sheets.append({"side": "pcell", "path": path, "placed": placed, "errors": errors,
                       "single": True})
    return sheets


def step_drc(out, sheets, jobs):
    import drc as drcmod
    from sheet import assign
    tasks = []
    for sh in sheets:
        for tool in ("klayout", "magic"):
            tasks.append((tool, sh))

    def work(t):
        tool, sh = t
        base = sh["path"][:-4]
        if tool == "klayout":
            m = drcmod.run_klayout_drc(sh["path"], "SHEET", base + ".klayout.xml", base + ".klayout.log")
        else:
            m = drcmod.run_magic_drc(sh["path"], "SHEET", base + ".magic.tsv", base + ".magic.log")
        got, unassigned = assign(m, sh["placed"])
        return tool, sh, got, unassigned

    sheet_sets, single_sets, unassigned_all = {}, {}, []
    t0 = time.time()
    # Big sheets first: they take longest.
    tasks.sort(key=lambda t: (t[1]["single"], -len(t[1]["placed"])))
    with cf.ThreadPoolExecutor(max_workers=jobs) as ex:
        for tool, sh, got, unassigned in ex.map(work, tasks):
            target = single_sets if sh["single"] else sheet_sets
            for pid in sh["placed"]:
                target.setdefault(pid, {}).setdefault(tool, {})[sh["side"]] = sorted(got.get(pid, ()))
            for u in unassigned:
                unassigned_all.append([tool, os.path.basename(sh["path"])] + u)
    return sheet_sets, single_sets, unassigned_all, round(time.time() - t0, 1)


def step_extract(out, sheets, points, jobs):
    import drc as drcmod
    mos = {pt["id"] for pt in points if pt["family"] == "mos"}
    tasks = []
    for sh in sheets:
        if sh["single"]:
            continue
        cells = ["D" + pid for pid, b in sh["placed"].items() if pid in mos and b]
        if cells:
            tasks.append((sh, cells))

    def work(t):
        sh, cells = t
        base = sh["path"][:-4]
        return sh, drcmod.run_magic_extract(sh["path"], cells, base + "_ext", base + ".extract.log")

    res = {}
    with cf.ThreadPoolExecutor(max_workers=jobs) as ex:
        for sh, got in ex.map(work, tasks):
            for cell, devs in got.items():
                res.setdefault(cell[1:], {})[sh["side"]] = devs
    return res


EXTRACT_KNOWN = os.path.join(HERE, "baseline", "extract-known.json")


def load_extract_known():
    try:
        with open(EXTRACT_KNOWN) as f:
            return json.load(f).get("known", [])
    except (OSError, ValueError):
        return []


def _wl_ok(d, w, l):
    return (isinstance(d[1], float) and isinstance(d[2], float)
            and abs(d[1] - w) <= 0.0051 and abs(d[2] - l) <= 0.0051)


def identity_problems(device, devs, w, l, nf, m):
    """Magic's extraction against the checked values: the model is the device,
    w and l match to the 0.01 um drawing grid, and there are nf*m devices."""
    problems = []
    models = {d[0] for d in devs}
    if models != {device}:
        problems.append("models %s" % sorted(models))
    bad = [d for d in devs if not _wl_ok(d, w, l)]
    if bad:
        problems.append("w/l %s vs checked w=%s l=%s" % (sorted(set((d[1], d[2]) for d in bad))[:3], w, l))
    if len(devs) != nf * m:
        problems.append("count %d != nf*m = %d" % (len(devs), nf * m))
    return problems


def known_extraction(device, devs, w, l, nf, m, known):
    """The entry in extract-known.json this result matches, or None."""
    for k in known:
        other = k.get("devices", {}).get(device)
        if other is None or nf < k.get("min_nf", 1):
            continue
        own = [d for d in devs if d[0] == device]
        rest = [d for d in devs if d[0] != device]
        if (len(devs) == nf * m and len(own) == -(-nf // 2) * m and all(_wl_ok(d, w, l) for d in own)
                and all(d[0] == other and isinstance(d[1], float) and abs(d[1] - w) <= 0.0051
                        for d in rest)):
            return k
    return None


def extract_verdict(pt, devs, checked, known=()):
    """Compare the two sides, and Magic's side with the checked values."""
    ref, pc = devs.get("ref"), devs.get("pcell")
    v = {"ref": summarize_devs(ref), "pcell": summarize_devs(pc)}
    v["equal"] = ref is not None and pc is not None and sorted(ref) == sorted(pc)
    if ref is None or not checked:
        v["identity"] = "no netlist"
        return v
    try:
        w, l = float(checked["w"]), float(checked["l"])
        nf, m = int(float(checked["nf"])), int(float(checked.get("m", "1")))
    except (KeyError, ValueError):
        v["identity"] = "checked values not numeric"
        return v
    problems = identity_problems(pt["device"], ref, w, l, nf, m)
    if not problems:
        v["identity"] = "ok"
    else:
        k = known_extraction(pt["device"], ref, w, l, nf, m, known)
        v["identity"] = ("known Magic behaviour: " + k["rule"]) if k else "; ".join(problems)
    return v


def summarize_devs(devs):
    if devs is None:
        return None
    from collections import Counter
    c = Counter(devs)
    return [[m, w, l, n] for (m, w, l), n in sorted(c.items(), key=lambda kv: str(kv[0]))]


# --- driver -----------------------------------------------------------------------------

def cleanup(out, points, results):
    for pt in points:
        r = results.get(pt["id"], {})
        if r.get("result") != "pass":
            continue
        for d in ("ref", "pcell", "pcell_warm", "resaved"):
            for ext in (".gds", ".oas"):
                p = os.path.join(out, d, pt["id"] + ext)
                if os.path.exists(p):
                    os.remove(p)
    for name in ("cache", "cache-tests"):
        shutil.rmtree(os.path.join(out, name), ignore_errors=True)
    d = os.path.join(out, "drc")
    if os.path.isdir(d):
        # Keep the raw DRC and extraction output only for sheets with a failing point.
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".gds.json"):
                continue
            base = fn[:-len(".gds.json")]
            with open(os.path.join(d, fn)) as f:
                placed = json.load(f).get("placed", {})
            if any(results.get(pid, {}).get("result") != "pass" for pid in placed):
                continue
            for ext in (".klayout.xml", ".klayout.log", ".magic.tsv", ".magic.log", ".extract.log"):
                p = os.path.join(d, base + ext)
                if os.path.exists(p):
                    os.remove(p)
        for fn in os.listdir(d):
            p = os.path.join(d, fn)
            if fn.endswith(".gds"):
                os.remove(p)
            elif fn.endswith("_ext") and os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.join(REPO, "out", "parity"))
    ap.add_argument("--quick", action="store_true", help="only the 60 default points")
    ap.add_argument("--devices", nargs="*", default=[], help="fnmatch patterns")
    ap.add_argument("--seed", type=int, default=1121)
    ap.add_argument("--random", type=int, default=5)
    ap.add_argument("--max-per-device", type=int, default=60)
    ap.add_argument("--keep", action="store_true", help="keep the GDS files of passing points")
    ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument("--no-unit", action="store_true")
    ap.add_argument("--no-drc", action="store_true")
    ap.add_argument("--no-extract", action="store_true")
    ap.add_argument("--jobs", type=int, default=max(1, min(6, os.cpu_count() or 1)))
    args = ap.parse_args(argv)

    out = os.path.abspath(args.out)
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    t0 = time.time()
    rep = {"meta": {"seed": args.seed, "quick": args.quick, "devices": args.devices,
                    "jobs": args.jobs}, "steps": {}, "harness_errors": []}
    points = []
    results = {}
    manifest = {}
    try:
        with open(MANIFEST, encoding="utf-8") as f:
            manifest = json.load(f)
        rep["exclusions"] = manifest.get("excluded", [])
        if not args.no_unit:
            log("step 0: unit and backend tests")
            rep["steps"]["tests"] = step_unit(out)
        log("step 1: versions and the manifest check")
        rep["meta"].update(step_versions(out))
        lp = os.path.join(out, "manifest_check.log")
        rc = run([sys.executable, os.path.join(REPO, "tools", "build_manifest.py"), "--check"], lp,
                 env=dict(os.environ, KMP_CACHE_DIR=os.path.join(out, "cache-manifest")))
        rep["steps"]["manifest"] = {"ok": rc == 0, "rc": rc,
                                    "summary": tail(lp, 1).strip(), "log": os.path.relpath(lp, out)}
        log("  " + rep["steps"]["manifest"]["summary"])
        log("step 2: sweep")
        sweep_path = os.path.join(out, "sweep.json")
        cmd = [sys.executable, os.path.join(HERE, "gen_sweep.py"), "--manifest", MANIFEST,
               "--out", sweep_path, "--seed", str(args.seed), "--random", str(args.random),
               "--max-per-device", str(args.max_per_device)]
        if args.quick:
            cmd.append("--quick")
        if args.devices:
            cmd += ["--devices"] + args.devices
        if run(cmd, os.path.join(out, "gen_sweep.log")) != 0:
            raise HarnessError("gen_sweep failed:\n" + tail(os.path.join(out, "gen_sweep.log")))
        with open(sweep_path) as f:
            sweep = json.load(f)
        points = sweep["points"]
        if not points:
            raise HarnessError("the sweep is empty (check --devices)")
        rep["meta"]["points"] = len(points)
        log("  %d points" % len(points))

        log("step 3+4: path A and path B (cold) in parallel")
        with cf.ThreadPoolExecutor(2) as ex:
            fa = ex.submit(path_a, out, sweep_path)
            fb = ex.submit(path_b, out, sweep_path, "pcell")
            ref, ta = fa.result()
            pb_data, tb = fb.result()
        pcell = pb_data["points"]
        log("  path A %.1f s, path B %.1f s %s" % (ta, tb, pb_data.get("generator_stats")))
        log("step 4: path B (warm)")
        pw_data, tw = path_b(out, sweep_path, "pcell_warm")
        warm = pw_data["points"]
        log("  warm %.1f s %s" % (tw, pw_data.get("generator_stats")))
        rep["steps"]["paths"] = {"a_seconds": ta, "b_seconds": tb, "b_warm_seconds": tw,
                                 "b_generator": pb_data.get("generator_stats"),
                                 "b_server": pb_data.get("server_stats"),
                                 "b_warm_generator": pw_data.get("generator_stats"),
                                 "b_warm_server": pw_data.get("server_stats")}

        log("step 5: per-point checks")
        from klayout_magic_pcells.stamp import parse_stamp
        cur = parse_stamp(pb_data["created_stamp"]) or {}
        t = time.time()
        results = step_checks(out, points, ref, pcell, warm, cur, manifest, args.jobs)
        rep["steps"]["checks"] = {"seconds": round(time.time() - t, 1)}
        for pt in points:
            r = results.setdefault(pt["id"], {})
            ra, pb = ref.get(pt["id"]) or {}, pcell.get(pt["id"]) or {}
            r.update({"messages": pb.get("messages", ra.get("log", "")),
                      "pcell_cell": pb.get("variant"), "stored": pb.get("stored"),
                      "checked_dict": pb.get("checked")})

        log("step 5b: second _check on below: points (recorded only)")
        idem = step_idempotence(points, pcell, dict(os.environ, KMP_CACHE_DIR=os.path.join(out, "cache-idem")))
        shutil.rmtree(os.path.join(out, "cache-idem"), ignore_errors=True)
        for pid, d in idem.items():
            results[pid].update(d)

        log("step 6: round trips")
        t = time.time()
        rt, n_rt = step_roundtrip(out, points, ref, pcell, results, args.seed)
        for pid, d in rt.items():
            results[pid]["roundtrip"] = d
        rep["steps"]["roundtrip"] = {"points": n_rt, "seconds": round(time.time() - t, 1)}

        sheets = None
        if not (args.no_drc and args.no_extract):
            log("building DRC sheets")
            sheets = build_sheets(out, points, ref, pcell, results)
        if not args.no_drc:
            log("step 7: DRC (%d sheets x 2 tools)" % len(sheets))
            sheet_sets, single_sets, unassigned, tdrc = step_drc(out, sheets, args.jobs)
            rep["steps"]["drc"] = {"sheets": sum(1 for s in sheets if not s["single"]),
                                   "singles": sum(1 for s in sheets if s["single"]),
                                   "seconds": tdrc, "unassigned_markers": unassigned[:50],
                                   "unassigned_count": len(unassigned)}
            apply_drc(points, results, sheet_sets, single_sets, args.update_baseline, rep)
            log("  DRC %.1f s, %d unassigned markers" % (tdrc, len(unassigned)))
        if not args.no_extract:
            log("step 8: extraction of MOSFET points")
            t = time.time()
            ex = step_extract(out, sheets, points, args.jobs)
            known = load_extract_known()
            for pt in points:
                if pt["family"] != "mos" or pt["id"] not in ex:
                    continue
                results[pt["id"]]["extract"] = extract_verdict(
                    pt, ex[pt["id"]], (pcell.get(pt["id"]) or {}).get("checked"), known)
            rep["steps"]["extract"] = {"points": len(ex), "seconds": round(time.time() - t, 1)}
    except Exception as e:
        rep["harness_errors"].append("%s: %s\n%s" % (type(e).__name__, e, traceback.format_exc()))
        log("HARNESS ERROR: %s" % e)

    rep["meta"]["seconds"] = round(time.time() - t0, 1)
    status = report.finalize(rep, points, results, manifest, out)
    if not args.keep and not rep["harness_errors"]:
        cleanup(out, points, results)
    print(report.summary_line(rep))
    return status


def apply_drc(points, results, sheet_sets, single_sets, update_baseline, rep):
    baseline = {}
    if os.path.isfile(BASELINE) and not update_baseline:
        with open(BASELINE) as f:
            baseline = json.load(f).get("devices", {})
    new_baseline = {}
    for pt in points:
        pid = pt["id"]
        if pid not in sheet_sets:
            continue
        s = sheet_sets[pid]
        d = {"klayout": {"ref": s.get("klayout", {}).get("ref"), "pcell": s.get("klayout", {}).get("pcell")},
             "magic": {"ref": s.get("magic", {}).get("ref"), "pcell": s.get("magic", {}).get("pcell")}}
        d["equal"] = all(d[t]["ref"] == d[t]["pcell"] for t in ("klayout", "magic"))
        if pt["kind"] == "default":
            single = single_sets.get(pid, {})
            d["single"] = {t: single.get(t, {}).get("pcell") for t in ("klayout", "magic")}
            d["single_matches_sheet"] = all(d["single"][t] == d[t]["pcell"] for t in ("klayout", "magic"))
            new_baseline[pt["device"]] = {t: d[t]["pcell"] for t in ("klayout", "magic")}
            b = baseline.get(pt["device"])
            if update_baseline:
                d["baseline"] = "updated"
            elif b is None:
                d["baseline"] = "missing"
            else:
                diff = [t for t in ("klayout", "magic") if sorted(b.get(t) or []) != (d[t]["pcell"] or [])
                        or sorted(b.get(t) or []) != (d[t]["ref"] or [])]
                d["baseline"] = "ok" if not diff else "differs (%s)" % ", ".join(diff)
        results[pid]["drc"] = d
    if update_baseline:
        if rep["meta"].get("quick") or rep["meta"].get("devices") or len(new_baseline) < 60:
            # A partial run would drop devices from the baseline; merge instead.
            if os.path.isfile(BASELINE):
                with open(BASELINE) as f:
                    old = json.load(f).get("devices", {})
                old.update(new_baseline)
                new_baseline = old
        doc = {"comment": "Rule IDs that each tool reports on each device's default point "
                          "(Magic drc(full) with catchup; KLayout sky130A_mr.drc with feol, beol "
                          "and offgrid on, floating_met and seal off). Written by "
                          "run_sweep.py --update-baseline.",
               "magic": rep["meta"].get("magic"), "tech": rep["meta"].get("tech"),
               "open_pdks": rep["meta"].get("open_pdks"), "klayout": rep["meta"].get("klayout"),
               "devices": {k: new_baseline[k] for k in sorted(new_baseline)}}
        os.makedirs(os.path.dirname(BASELINE), exist_ok=True)
        with open(BASELINE, "w") as f:
            json.dump(doc, f, indent=1)
            f.write("\n")


if __name__ == "__main__":
    sys.exit(main())
