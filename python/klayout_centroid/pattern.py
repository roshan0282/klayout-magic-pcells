"""Common-centroid pattern core: device unit counts -> a letter grid.

Pure Python, no KLayout. Every pattern built here has all device centroids
exactly at the array centre, by construction:

* Units are placed in point-symmetric pairs: a cell (i, j) and its 180
  degree mirror (R-1-i, C-1-j) always hold the same device.
* A device with an odd count needs one cell whose own centroid is the
  centre. The first such device gets the centre cell (only an odd x odd
  grid has one). Every further odd device gets a *triad*: three cells
  {a, b, -(a+b)} (offsets from the centre) whose centroid is the centre.
  Triads come in mirrored pairs (T for one odd device, -T for another), so
  the cells left over still pair up. This makes counts like 3:5 possible,
  which pure point symmetry can't do.
* Cells not used by a device are dummies (``.``), also placed in pairs, on
  the outermost cells.

The styles differ only in how the pairs are ordered and assigned:

``interdigitated``  half the cells in raster order, devices spread evenly
                    (1 x N rows give ABBA-like interdigitation)
``checkerboard``    cells of one checkerboard colour first, devices in
                    blocks: two equal devices give the AB/BA cross-coupled quad
``symmetric``       half-cells by distance from the centre, devices spread
                    evenly (spiral-like; suits ratioed capacitor arrays)
``optimized``       ``symmetric``, then simulated annealing over swaps of
                    symmetric pairs, lowering the correlated-mismatch score
                    (see metrics.py). Every swap keeps the common centroid.

``override`` takes a hand-written grid ("ABBA/BAAB") and only checks it.
"""

import math
import random
from fractions import Fraction

DUMMY = "."
STYLES = ("interdigitated", "checkerboard", "symmetric", "optimized")


class PatternError(ValueError):
    """A pattern can't be built; ``param`` names the input to blame."""

    def __init__(self, msg, param=None):
        super().__init__(msg)
        self.param = param


# ---------------------------------------------------------------- inputs

def parse_devices(text):
    """[(name, count)] from "A:4,B:4", "A:4 B:4" or a bare ratio "1:2:4:8"
    (named A, B, C, ...). Names are single letters or digits, so that a
    pattern prints as a letter grid."""
    text = (text or "").strip()
    if not text:
        raise PatternError("no devices given (e.g. A:4,B:4 or 1:2:4:8)", "devices")
    toks = [t for t in text.replace(",", " ").replace(";", " ").split() if t]
    if len(toks) == 1 and all(p.strip().isdigit() for p in toks[0].split(":")) and ":" in toks[0]:
        counts = [int(p) for p in toks[0].split(":")]
        if len(counts) > 26:
            raise PatternError("at most 26 devices", "devices")
        out = [(chr(ord("A") + i), n) for i, n in enumerate(counts)]
    else:
        out = []
        for t in toks:
            if ":" not in t:
                raise PatternError("%r is not name:count" % t, "devices")
            name, n = t.split(":", 1)
            name = name.strip()
            if len(name) != 1 or not name.isalnum():
                raise PatternError("device name %r: use one letter or digit (it is the grid symbol)" % name,
                                   "devices")
            try:
                out.append((name, int(n)))
            except ValueError:
                raise PatternError("%r: the count is not a whole number" % t, "devices")
    names = [n for n, _ in out]
    if len(set(names)) != len(names):
        raise PatternError("device names repeat: %s" % " ".join(names), "devices")
    for name, n in out:
        if n < 1:
            raise PatternError("device %s: count %d, needs at least 1" % (name, n), "devices")
    return out


def parse_grid(text):
    """Rows of a hand-written grid: "ABBA/BAAB", or one row per line.
    ``.``, ``-`` and ``_`` are dummies."""
    rows = [r.strip() for r in (text or "").replace("\n", "/").replace("|", "/").split("/")]
    rows = ["".join(c for c in r if not c.isspace()) for r in rows if r.strip()]
    if not rows:
        raise PatternError("the pattern override is empty", "override")
    if len({len(r) for r in rows}) != 1:
        raise PatternError("the override's rows differ in length: %s" % "/".join(rows), "override")
    return tuple(r.replace("-", DUMMY).replace("_", DUMMY) for r in rows)


# --------------------------------------------------------------- geometry

class Grid:
    """Index helpers for an R x C grid; cell (i, j) is row i, column j,
    row 0 printed first (the top row)."""

    def __init__(self, rows, cols):
        self.R, self.C = rows, cols

    def cells(self):
        return [(i, j) for i in range(self.R) for j in range(self.C)]

    def mirror(self, u):
        return (self.R - 1 - u[0], self.C - 1 - u[1])

    def idx(self, u):
        return u[0] * self.C + u[1]

    def offset2(self, u):
        """Doubled offset from the centre (integers): (2x, 2y)."""
        return (2 * u[1] - (self.C - 1), (self.R - 1) - 2 * u[0])

    def from_offset2(self, o):
        x2, y2 = o
        j2, i2 = x2 + (self.C - 1), (self.R - 1) - y2
        if j2 % 2 or i2 % 2:
            return None
        i, j = i2 // 2, j2 // 2
        if 0 <= i < self.R and 0 <= j < self.C:
            return (i, j)
        return None

    def center(self):
        if self.R % 2 and self.C % 2:
            return ((self.R - 1) // 2, (self.C - 1) // 2)
        return None

    def half_cells(self, reserved=()):
        res = set(reserved)
        return [u for u in self.cells() if u not in res and self.idx(u) < self.idx(self.mirror(u))]

    def radius2(self, u):
        x2, y2 = self.offset2(u)
        return x2 * x2 + y2 * y2

    def angle(self, u):
        x2, y2 = self.offset2(u)
        return math.atan2(y2, x2) % (2 * math.pi)


def _find_triad_pairs(g, n_pairs, taken):
    """``n_pairs`` mirrored triad pairs (T, -T) of free cells, compact first.
    Returns [(T, -T)] as lists of cells, or None."""
    if n_pairs == 0:
        return []
    taken = set(taken)
    free = sorted((u for u in g.cells() if u not in taken and u != g.center()),
                  key=lambda u: (g.radius2(u), g.angle(u)))
    out = []
    for _ in range(n_pairs):
        found = None
        for ia, a in enumerate(free):
            if a in taken:
                continue
            oa = g.offset2(a)
            for b in free[ia + 1:]:
                if b in taken:
                    continue
                ob = g.offset2(b)
                c = g.from_offset2((-oa[0] - ob[0], -oa[1] - ob[1]))
                if c is None or c in taken or c in (a, b):
                    continue
                tri = [a, b, c]
                mir = [g.mirror(u) for u in tri]
                cells = set(tri) | set(mir)
                if len(cells) != 6 or cells & taken:
                    continue
                found = (tri, mir)
                break
            if found:
                break
        if not found:
            return None
        out.append(found)
        taken |= set(found[0]) | set(found[1])
    return out


def _skeleton(g, counts):
    """Cells fixed before pairing: {cell: label} for the centre and the
    triads, or raises PatternError. ``counts`` includes the dummies."""
    odd = [k for k, n in counts.items() if n % 2]
    if not odd:
        if g.center() is not None and sum(counts.values()) % 2:
            raise PatternError("internal: odd cell count without an odd device")
        return {}
    if g.center() is None:
        names = ", ".join("%s:%d" % (k if k != DUMMY else "dummies", counts[k]) for k in odd)
        raise PatternError("%d x %d has no centre cell, so every count must be even (odd: %s)"
                           % (g.R, g.C, names), "rows")
    ones = [k for k in odd if counts[k] == 1]
    if len(ones) > 1:
        raise PatternError("%s each have one unit; only one unit can sit on the centre. "
                           "Double the counts (e.g. 2:2)" % " and ".join(k for k in ones), "devices")
    if ones:
        centre = ones[0]
    elif DUMMY in odd:
        centre = DUMMY
    else:
        centre = min(odd, key=lambda k: (counts[k], k))
    rest = [k for k in odd if k != centre]
    sk = {g.center(): centre}
    if rest:
        pairs = _find_triad_pairs(g, len(rest) // 2, sk)
        if pairs is None:
            raise PatternError("%d x %d is too small for %d odd counts (each extra odd count "
                               "needs a triad of 3 cells)" % (g.R, g.C, len(odd)), "rows")
        for (tri, mir), (ka, kb) in zip(pairs, zip(rest[0::2], rest[1::2])):
            for u in tri:
                sk[u] = ka
            for u in mir:
                sk[u] = kb
    return sk


def feasible(devices, rows, cols):
    """(True, "") or (False, reason) for these devices on rows x cols."""
    try:
        _layout_counts(devices, rows, cols)
        g = Grid(rows, cols)
        _skeleton(g, _layout_counts(devices, rows, cols))
        return True, ""
    except PatternError as e:
        return False, str(e)


def _layout_counts(devices, rows, cols):
    if rows < 1 or cols < 1:
        raise PatternError("rows and cols must be at least 1", "rows")
    n = sum(c for _, c in devices)
    if rows * cols < n:
        raise PatternError("%d x %d = %d cells, fewer than the %d units" % (rows, cols, rows * cols, n), "rows")
    counts = dict(devices)
    if rows * cols > n:
        counts[DUMMY] = rows * cols - n
    return counts


def auto_shape(devices, rows=0, cols=0, aspect=1.0, max_extra=None):
    """(rows, cols) trading dummies against squareness in um (``aspect`` =
    unit pitch x / pitch y): cost 8 * dummies / units + |ln(width/height)|.
    A given rows or cols is kept."""
    n = sum(c for _, c in devices)
    ones = [k for k, c in devices if c == 1]
    if len(ones) > 1:
        raise PatternError("%s each have one unit, and only one unit can sit on the centre cell; "
                           "double all counts" % " and ".join(ones), "devices")
    if max_extra is None:
        max_extra = max(4, n // 2)
    best, first_why = None, None
    rr = [rows] if rows > 0 else range(1, n + max_extra + 1)
    for r in rr:
        cc = [cols] if cols > 0 else range(max(1, -(-n // r)), -(-(n + max_extra) // r) + 1)
        for c in cc:
            if r * c < n or r * c - n > max_extra and not (rows and cols):
                continue
            ok, why = feasible(devices, r, c)
            if not ok:
                if first_why is None or r * c < first_why[0]:
                    first_why = (r * c, "%d x %d: %s" % (r, c, why))
                continue
            squareness = abs(math.log((c * aspect) / r))
            # a dummy costs 8/n (as a fraction of the units); a factor e off square costs 1
            key = (round(8.0 * (r * c - n) / n + squareness, 6), r * c, r)
            if best is None or key < best[0]:
                best = (key, (r, c))
    if best is None:
        if rows and cols:
            ok, why = feasible(devices, rows, cols)
            raise PatternError(why, "rows")
        raise PatternError("no array shape with up to %d dummies gives these counts a common centroid "
                           "(smallest tried: %s)" % (max_extra, first_why[1] if first_why else "-"), "devices")
    return best[1]


# ----------------------------------------------------------- construction

def spread(pairs):
    """An evenly spread sequence of labels with ``pairs[k]`` copies each."""
    items = []
    order = {k: i for i, k in enumerate(pairs)}
    for k, p in pairs.items():
        for t in range(p):
            items.append(((t + 0.5) / p, order[k], k))
    return [k for _, _, k in sorted(items)]


def _order(g, half, style):
    if style == "interdigitated":
        return sorted(half, key=g.idx)
    if style == "checkerboard":
        return sorted(half, key=lambda u: ((u[0] + u[1]) % 2, g.idx(u)))
    return sorted(half, key=lambda u: (g.radius2(u), g.angle(u), g.idx(u)))


def _construct(devices, rows, cols, style):
    g = Grid(rows, cols)
    counts = _layout_counts(devices, rows, cols)
    lab = dict(_skeleton(g, counts))
    used = {k: 0 for k in counts}
    for k in lab.values():
        used[k] += 1
    half = g.half_cells(lab)
    pairs = {k: (counts[k] - used[k]) // 2 for k in counts}
    # dummies on the outermost half-cells, corners first
    if pairs.get(DUMMY):
        outer = sorted(half, key=lambda u: (-g.radius2(u), g.idx(u)))[:pairs[DUMMY]]
        for u in outer:
            lab[u] = lab[g.mirror(u)] = DUMMY
        half = [u for u in half if u not in set(outer)]
    dev_pairs = {k: p for k, p in pairs.items() if k != DUMMY}
    half = _order(g, half, style)
    seq = [k for k, p in dev_pairs.items() for _ in range(p)] if style == "checkerboard" else spread(dev_pairs)
    assert len(seq) == len(half), (len(seq), len(half))
    for u, k in zip(half, seq):
        lab[u] = lab[g.mirror(u)] = k
    return tuple("".join(lab[(i, j)] for j in range(cols)) for i in range(rows))


class Pattern:
    """A letter grid plus how it was made. ``grid[0]`` is the top row."""

    def __init__(self, grid, devices, style, notes=()):
        self.grid = tuple(grid)
        self.devices = list(devices)
        self.style = style
        self.notes = list(notes)

    @property
    def rows(self):
        return len(self.grid)

    @property
    def cols(self):
        return len(self.grid[0])

    def text(self, sep="\n"):
        return sep.join(" ".join(r) for r in self.grid)

    def cells_of(self, name):
        return [(i, j) for i, r in enumerate(self.grid) for j, c in enumerate(r) if c == name]

    def __repr__(self):
        return "Pattern(%s, %s)" % (self.style, "/".join(self.grid))


def centroid_offsets(grid):
    """{label: (dx, dy)} exact Fractions, in pitches, of each label's
    centroid from the array centre (dummies included)."""
    R, C = len(grid), len(grid[0])
    sums = {}
    for i, r in enumerate(grid):
        for j, k in enumerate(r):
            s = sums.setdefault(k, [0, 0, 0])
            s[0] += Fraction(2 * j - (C - 1), 2)
            s[1] += Fraction((R - 1) - 2 * i, 2)
            s[2] += 1
    return {k: (s[0] / s[2], s[1] / s[2]) for k, s in sums.items()}


def check_centroid(grid, devices=None):
    """Raises PatternError unless every device's centroid is the centre and,
    when ``devices`` is given, the unit counts match."""
    if devices is not None:
        have = {}
        for r in grid:
            for k in r:
                have[k] = have.get(k, 0) + 1
        for name, n in devices:
            if have.get(name, 0) != n:
                raise PatternError("device %s has %d units in the grid, %d asked for"
                                   % (name, have.get(name, 0), n), "override")
        extra = sorted(set(have) - {n for n, _ in devices} - {DUMMY})
        if extra:
            raise PatternError("the grid has symbols that aren't devices: %s" % " ".join(extra), "override")
    off = centroid_offsets(grid)
    bad = ["%s (%s, %s)" % (k, v[0], v[1]) for k, v in sorted(off.items()) if k != DUMMY and v != (0, 0)]
    if bad:
        raise PatternError("not common-centroid; centroid offsets in pitches: %s" % ", ".join(bad), "override")


def build(devices, rows=0, cols=0, style="symmetric", aspect=1.0, seed=1, override=None, iterations=None,
          rho=0.9):
    """A Pattern for ``devices`` ([(name, count)] or "A:4,B:4"). rows/cols
    0 = automatic. Raises PatternError."""
    if isinstance(devices, str):
        devices = parse_devices(devices)
    if override:
        grid = parse_grid(override)
        check_centroid(grid, devices)
        return Pattern(grid, devices, "override")
    if style not in STYLES:
        raise PatternError("style %r: one of %s" % (style, ", ".join(STYLES)), "style")
    r, c = auto_shape(devices, rows, cols, aspect)
    notes = []
    if style == "checkerboard" and (r + c) % 2:
        notes.append("rows + cols is odd, so the mirror flips the checkerboard colour: "
                     "the pattern is common-centroid but not a pure checkerboard")
    if style == "optimized":
        # start from the best constructive pattern, so annealing can only improve on it
        starts = [_construct(devices, r, c, s) for s in ("checkerboard", "interdigitated", "symmetric")]
        grid = min(starts, key=lambda gr: corr_score(gr, devices, rho))
        grid = optimize(grid, devices, seed=seed, iterations=iterations, rho=rho)
    else:
        grid = _construct(devices, r, c, style)
    check_centroid(grid, devices)
    return Pattern(grid, devices, style, notes)


# ------------------------------------------------------------ optimizing

def _rho_table(R, C, rho):
    """rho ** distance (in pitches) for every cell pair, as a flat list."""
    cells = [(i, j) for i in range(R) for j in range(C)]
    return [[rho ** math.hypot(a[0] - b[0], a[1] - b[1]) for b in cells] for a in cells]


class _Corr:
    """S[k][m] = sum of rho(u, v) over u in k, v in m, kept up to date as
    cells change label."""

    def __init__(self, labels, names, table):
        self.t = table
        self.names = names
        self.lab = list(labels)
        n = len(labels)
        self.r = [{k: 0.0 for k in names} for _ in range(n)]
        for u in range(n):
            ru, tu = self.r[u], table[u]
            for v in range(n):
                ru[labels[v]] += tu[v]
        self.S = {k: {m: 0.0 for m in names} for k in names}
        for u in range(n):
            for m in names:
                self.S[labels[u]][m] += self.r[u][m]

    def relabel(self, u, b):
        a = self.lab[u]
        if a == b:
            return
        S, ru, tu = self.S, self.r[u], self.t[u]
        for m in self.names:
            if m != a:
                S[a][m] -= ru[m]
                S[m][a] -= ru[m]
        S[a][a] -= 2 * ru[a] - 1.0
        for w, rw in enumerate(self.r):
            rw[a] -= tu[w]
        self.lab[u] = b
        for w, rw in enumerate(self.r):
            rw[b] += tu[w]
        for m in self.names:
            if m != b:
                S[b][m] += ru[m]
                S[m][b] += ru[m]
        S[b][b] += 2 * ru[b] - 1.0

    def score(self, devs, n):
        """Mean over device pairs of Var(mean_k - mean_m), unit variance
        per cell; single device: Var(mean_k)."""
        S = self.S
        if len(devs) == 1:
            k = devs[0]
            return S[k][k] / n[k] ** 2
        tot, cnt = 0.0, 0
        for i, k in enumerate(devs):
            for m in devs[i + 1:]:
                tot += S[k][k] / n[k] ** 2 + S[m][m] / n[m] ** 2 - 2 * S[k][m] / (n[k] * n[m])
                cnt += 1
        return tot / cnt


def corr_score(grid, devices, rho=0.9):
    """The optimizer's objective for a grid (lower is better)."""
    R, C = len(grid), len(grid[0])
    flat = [grid[i][j] for i in range(R) for j in range(C)]
    corr = _Corr(flat, sorted(set(flat)), _rho_table(R, C, rho))
    return corr.score([n for n, _ in devices], dict(devices))


def optimize(grid, devices, seed=1, iterations=None, rho=0.9):
    """Anneal swaps of symmetric pairs (a half-cell and its mirror trade
    labels with another such pair). Centre, triads and dummies stay put,
    so the common centroid survives every move."""
    R, C = len(grid), len(grid[0])
    g = Grid(R, C)
    lab = {(i, j): grid[i][j] for i in range(R) for j in range(C)}
    counts = _layout_counts(devices, R, C)
    fixed = set(_skeleton(g, counts))
    half = [u for u in g.half_cells(fixed) if lab[u] != DUMMY]
    devs = [n for n, _ in devices]
    if len({lab[u] for u in half}) < 2:
        return grid
    names = sorted(set(lab.values()))
    flat = [lab[u] for u in g.cells()]
    corr = _Corr(flat, names, _rho_table(R, C, rho))
    n = dict(devices)
    rnd = random.Random(seed)
    if iterations is None:
        iterations = min(6000, 80 * len(half))
    cur = corr.score(devs, n)
    best, best_lab = cur, list(corr.lab)
    t0 = max(cur * 0.05, 1e-12)
    for it in range(iterations):
        a, b = rnd.sample(half, 2)
        ia, ib = g.idx(a), g.idx(b)
        la, lb = corr.lab[ia], corr.lab[ib]
        if la == lb:
            continue
        ma, mb = g.idx(g.mirror(a)), g.idx(g.mirror(b))
        for u, k in ((ia, lb), (ma, lb), (ib, la), (mb, la)):
            corr.relabel(u, k)
        new = corr.score(devs, n)
        temp = t0 * (1.0 - it / iterations) + 1e-15
        if new <= cur or rnd.random() < math.exp((cur - new) / temp):
            cur = new
            if cur < best - 1e-15:
                best, best_lab = cur, list(corr.lab)
        else:
            for u, k in ((ia, la), (ma, la), (ib, lb), (mb, lb)):
                corr.relabel(u, k)
    return tuple("".join(best_lab[i * C + j] for j in range(C)) for i in range(R))
