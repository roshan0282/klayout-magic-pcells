"""How good a common-centroid pattern is. Pure Python.

All lengths are in unit pitches (x and y pitch taken as 1 unless given).

* ``centroid``  each device's centroid offset from the array centre
  (exact; zero for every pattern pattern.build makes).
* ``sigma``     random mismatch under a spatially correlated field: each
  unit deviates by e_u, unit variance, correlation rho ** distance
  (Huang/Wey 2013; Lin 2011). For each device pair, the standard deviation
  of (mean of k) - (mean of m), relative to one unit's sigma. Lower is
  better; it falls as units of the two devices interleave and as each
  device spreads out. ``score`` is the mean variance over pairs, which the
  optimizer minimizes.
* ``dispersion`` the first-pass score from plan/centroid.md: for each
  device, the mean distance from a unit to its nearest same-device unit
  (higher = better spread), summed over devices.
* ``adjacency`` how often two devices are next to each other, per
  direction (h = left/right, v = above/below).
* ``gradient``  device-mean mismatch under a synthetic gradient across the
  array: linear (cancels for any common centroid) and quadratic terms x^2,
  y^2 and x*y, which a common centroid does not cancel (Sharma 2021). The
  value is the largest pair difference of the device means for a unit
  coefficient, e.g. g(x, y) = x^2.
"""

import math

from .pattern import DUMMY, centroid_offsets


def _pos(grid, px=1.0, py=1.0):
    R, C = len(grid), len(grid[0])
    out = {}
    for i, r in enumerate(grid):
        for j, k in enumerate(r):
            out.setdefault(k, []).append(((j - (C - 1) / 2.0) * px, ((R - 1) / 2.0 - i) * py))
    return out


def sigma_pairs(grid, devices, rho=0.9, px=1.0, py=1.0):
    pos = _pos(grid, px, py)
    names = [n for n, _ in devices]

    def S(a, b):
        return sum(rho ** math.hypot(u[0] - v[0], u[1] - v[1]) for u in pos[a] for v in pos[b])

    out = {}
    if len(names) == 1:
        k = names[0]
        out[(k,)] = math.sqrt(S(k, k)) / len(pos[k])
        return out
    s = {k: S(k, k) for k in names}
    for i, k in enumerate(names):
        for m in names[i + 1:]:
            nk, nm = len(pos[k]), len(pos[m])
            var = s[k] / nk ** 2 + s[m] / nm ** 2 - 2 * S(k, m) / (nk * nm)
            out[(k, m)] = math.sqrt(max(var, 0.0))
    return out


def dispersion(grid, devices, px=1.0, py=1.0):
    pos = _pos(grid, px, py)
    per = {}
    for name, _ in devices:
        p = pos.get(name, [])
        if len(p) < 2:
            per[name] = 0.0
            continue
        per[name] = sum(min(math.hypot(u[0] - v[0], u[1] - v[1]) for v in p if v is not u) for u in p) / len(p)
    return sum(per.values()), per


def adjacency(grid):
    """{"AB": (h, v)} for each unordered pair of symbols, AA included."""
    out = {}
    R, C = len(grid), len(grid[0])

    def add(a, b, d):
        key = "".join(sorted(a + b))
        h, v = out.get(key, (0, 0))
        out[key] = (h + 1, v) if d == "h" else (h, v + 1)

    for i in range(R):
        for j in range(C):
            if j + 1 < C:
                add(grid[i][j], grid[i][j + 1], "h")
            if i + 1 < R:
                add(grid[i][j], grid[i + 1][j], "v")
    return out


GRADIENTS = {
    "linear x+y": lambda x, y: x + y,
    "x^2": lambda x, y: x * x,
    "y^2": lambda x, y: y * y,
    "x*y": lambda x, y: x * y,
}


def gradient(grid, devices, px=1.0, py=1.0):
    pos = _pos(grid, px, py)
    names = [n for n, _ in devices]
    out = {}
    for gname, f in GRADIENTS.items():
        means = {k: sum(f(*u) for u in pos[k]) / len(pos[k]) for k in names}
        vals = list(means.values())
        out[gname] = max(vals) - min(vals) if len(vals) > 1 else 0.0
    return out


def longest_run(grid):
    """Longest horizontal or vertical run of one device (dummies ignored)."""
    best = 0
    R, C = len(grid), len(grid[0])
    for lines in (grid, ["".join(grid[i][j] for i in range(R)) for j in range(C)]):
        for line in lines:
            run, prev = 0, None
            for k in line:
                run = run + 1 if k == prev and k != DUMMY else 1
                prev = k
                if k != DUMMY:
                    best = max(best, run)
    return best


def evaluate(pattern, rho=0.9, px=1.0, py=1.0):
    grid, devices = pattern.grid, pattern.devices
    off = centroid_offsets(grid)
    sig = sigma_pairs(grid, devices, rho, px, py)
    dsum, dper = dispersion(grid, devices, px, py)
    return {
        "rows": pattern.rows, "cols": pattern.cols, "style": pattern.style,
        "units": sum(n for _, n in devices),
        "dummies": sum(r.count(DUMMY) for r in grid),
        "centroid": {k: (float(v[0]) * px, float(v[1]) * py) for k, v in off.items() if k != DUMMY},
        "common_centroid": all(v == (0, 0) for k, v in off.items() if k != DUMMY),
        "sigma": sig,
        "score": sum(s * s for s in sig.values()) / len(sig),
        "dispersion": dsum, "dispersion_per": dper,
        "adjacency": adjacency(grid),
        "gradient": gradient(grid, devices, px, py),
        "longest_run": longest_run(grid),
        "rho": rho,
    }


def summary_line(m):
    """One line for the PCell form."""
    sig = max(m["sigma"].values()) if m["sigma"] else 0.0
    quad = max(v for k, v in m["gradient"].items() if k != "linear x+y")
    return ("%dx%d %s, %d units + %d dummies; centroid %s; sigma %.3f; disp %.2f; quad grad %.3f; run %d"
            % (m["rows"], m["cols"], m["style"], m["units"], m["dummies"],
               "OK" if m["common_centroid"] else "OFF", sig, m["dispersion"], quad, m["longest_run"]))


def report_text(pattern, m=None, unit="pitch"):
    m = m or evaluate(pattern)
    lines = ["%s pattern, %d x %d (row 0 on top):" % (pattern.style, pattern.rows, pattern.cols), ""]
    lines += ["    " + " ".join(r) for r in pattern.grid]
    lines.append("")
    for n in pattern.notes:
        lines.append("note: " + n)
    lines.append("units %d, dummies %d (.)" % (m["units"], m["dummies"]))
    lines.append("centroid offset from the array centre (%s):" % unit)
    for name, _ in pattern.devices:
        dx, dy = m["centroid"][name]
        lines.append("    %s  n=%-3d  (%+.4g, %+.4g)" % (name, dict(pattern.devices)[name], dx, dy))
    lines.append("common centroid: %s" % ("yes" if m["common_centroid"] else "NO"))
    lines.append("correlated mismatch, sigma(mean_k - mean_m) / sigma_unit, rho=%g per pitch:" % m["rho"])
    for k, v in m["sigma"].items():
        lines.append("    %s  %.4f" % ("-".join(k), v))
    lines.append("dispersion (sum of mean nearest same-device distance): %.3f  %s"
                 % (m["dispersion"], " ".join("%s=%.2f" % kv for kv in m["dispersion_per"].items())))
    lines.append("adjacency (h, v): " + "  ".join("%s=%d,%d" % (k, h, v) for k, (h, v) in sorted(m["adjacency"].items())))
    lines.append("gradient mismatch (max pair difference of device means, unit coefficient):")
    lines.append("    " + "  ".join("%s=%.4g" % kv for kv in m["gradient"].items()))
    lines.append("longest same-device run: %d" % m["longest_run"])
    return "\n".join(lines)
