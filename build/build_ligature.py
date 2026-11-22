#!/usr/bin/env python3
"""
Mochi Mono Ligature build script.

Starts from the already-built MochiMono-*.otf and produces a name-keyed OTF that adds

  * programming ligatures (GSUB calt + liga): -> => == != >= <= <-> ... drawn with
    round-capped strokes that match the font's weight
  * Powerline + Powerline Extra shapes (U+E0A0..E0A3, U+E0B0..E0BF)
  * a hand-drawn set of common icons at Nerd Font code points (folder, file, git
    branch, check, cross, warning, home, search, gear, ...). This is NOT the full
    Nerd Fonts icon library, which cannot be redistributed from here.

Usage:
    python3 build_ligature.py --src ../fonts --out ../fonts
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

from build import contours_from_recording, signed_area

FAMILY = "Mochi Mono Ligature"
VERSION = "1.000"
ASC, DESC = 960, -240          # line box used by Powerline shapes and hhea
K = 0.5522847498               # circle -> cubic bezier constant
CELL = 500


# --------------------------------------------------------------------------
# path helpers. A contour is a list of ("L", (p0, p1)) / ("C", (p0, c1, c2, p1))
# --------------------------------------------------------------------------
def reverse(contour):
    out = []
    for kind, p in reversed(contour):
        out.append((kind, tuple(reversed(p))))
    return out


class Shape:
    def __init__(self):
        self.contours = []

    def solid(self, contour):
        if signed_area(contour) < 0:
            contour = reverse(contour)
        self.contours.append(contour)

    def hole(self, contour):
        if signed_area(contour) > 0:
            contour = reverse(contour)
        self.contours.append(contour)

    # -- primitives ---------------------------------------------------------
    def polygon(self, pts, hole=False):
        seg = [("L", (pts[i], pts[(i + 1) % len(pts)])) for i in range(len(pts))]
        (self.hole if hole else self.solid)(seg)

    def ellipse(self, cx, cy, rx, ry, hole=False):
        pts = [(cx + rx, cy), (cx, cy + ry), (cx - rx, cy), (cx, cy - ry)]
        seg = []
        for i in range(4):
            a, b = pts[i], pts[(i + 1) % 4]
            if i == 0:
                c1, c2 = (a[0], a[1] + K * ry), (b[0] + K * rx, b[1])
            elif i == 1:
                c1, c2 = (a[0] - K * rx, a[1]), (b[0], b[1] + K * ry)
            elif i == 2:
                c1, c2 = (a[0], a[1] - K * ry), (b[0] - K * rx, b[1])
            else:
                c1, c2 = (a[0] + K * rx, a[1]), (b[0], b[1] - K * ry)
            seg.append(("C", (a, c1, c2, b)))
        (self.hole if hole else self.solid)(seg)

    def ring(self, cx, cy, r_out, width):
        self.ellipse(cx, cy, r_out, r_out)
        self.ellipse(cx, cy, r_out - width, r_out - width, hole=True)

    def capsule(self, p1, p2, w):
        h = w / 2.0
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        n = math.hypot(dx, dy)
        d = (dx / n, dy / n)
        nv = (-d[1], d[0])

        def add(p, v, k):
            return (p[0] + v[0] * k, p[1] + v[1] * k)

        a1, b1 = add(p1, nv, h), add(p1, nv, -h)
        a2, b2 = add(p2, nv, h), add(p2, nv, -h)
        e1 = add(p1, d, -h)
        e2 = add(p2, d, h)
        seg = [
            ("C", (a1, add(a1, d, -K * h), add(e1, nv, K * h), e1)),
            ("C", (e1, add(e1, nv, -K * h), add(b1, d, -K * h), b1)),
            ("L", (b1, b2)),
            ("C", (b2, add(b2, d, K * h), add(e2, nv, -K * h), e2)),
            ("C", (e2, add(e2, nv, K * h), add(a2, d, K * h), a2)),
            ("L", (a2, a1)),
        ]
        self.solid(seg)

    def polyline(self, pts, w):
        for a, b in zip(pts, pts[1:]):
            self.capsule(a, b, w)

    def chevron(self, tip, dx, dy, w):
        """A '>'-like head whose tip is at `tip`; dx > 0 opens to the left."""
        self.capsule(tip, (tip[0] - dx, tip[1] + dy), w)
        self.capsule(tip, (tip[0] - dx, tip[1] - dy), w)

    def glyph_outline(self, glyph_set, name, sx, sy, dx, dy):
        rec = RecordingPen()
        glyph_set[name].draw(TransformPen(rec, (sx, 0, 0, sy, dx, dy)))
        for c in contours_from_recording(rec.value):
            self.solid(c) if signed_area(c) > 0 else self.hole(c)

    def to_charstring(self, width):
        pen = T2CharStringPen(width, None)
        for c in self.contours:
            pen.moveTo(c[0][1][0])
            for kind, p in c:
                if kind == "L":
                    pen.lineTo(p[1])
                else:
                    pen.curveTo(p[1], p[2], p[3])
            pen.closePath()
        return pen.getCharString()

    def xmin(self):
        xs = []
        for c in self.contours:
            for _, p in c:
                xs.extend(q[0] for q in p)
        return int(round(min(xs))) if xs else 0


# --------------------------------------------------------------------------
# ligatures
# --------------------------------------------------------------------------
def uname(ch):
    return "uni%04X" % ord(ch)


def build_ligatures(metrics):
    """Returns {sequence: (glyph_name, Shape, width)}."""
    t = metrics["t"]
    hy = metrics["hy"]                       # hyphen centre line
    eq_lo, eq_hi = metrics["eq_lo"], metrics["eq_hi"]
    yb, yt = eq_lo + t / 2.0, eq_hi - t / 2.0   # centres of the two '=' bars
    ym = (yb + yt) / 2.0
    t3 = t * 0.8
    head = 150 + (t - 73) * 0.6
    m = 62                                   # side margin inside the ligature
    out = {}

    def new(seq, ncell=None):
        n = ncell or len(seq)
        s = Shape()
        out[seq] = ("lig_" + "_".join("%04X" % ord(c) for c in seq), s, CELL * n)
        return s, CELL * n

    def arrow_right(s, W, y, x_end):
        s.chevron((x_end, y), head, head, t)

    # hyphen arrows -----------------------------------------------------------
    for seq in ("->", "-->"):
        s, W = new(seq)
        s.capsule((m, hy), (W - m, hy), t)
        arrow_right(s, W, hy, W - m)
    for seq in ("<-", "<--"):
        s, W = new(seq)
        s.capsule((m, hy), (W - m, hy), t)
        s.chevron((m, hy), -head, head, t)
    s, W = new("<->")
    s.capsule((m, hy), (W - m, hy), t)
    arrow_right(s, W, hy, W - m)
    s.chevron((m, hy), -head, head, t)

    # equals arrows -----------------------------------------------------------
    for seq in ("=>", "==>"):
        s, W = new(seq)
        s.capsule((m, yb), (W - m - head * 0.6, yb), t)
        s.capsule((m, yt), (W - m - head * 0.6, yt), t)
        s.chevron((W - m, ym), head + 25, head + 45, t)
    for seq in ("<==",):
        s, W = new(seq)
        s.capsule((m + head * 0.6, yb), (W - m, yb), t)
        s.capsule((m + head * 0.6, yt), (W - m, yt), t)
        s.chevron((m, ym), -(head + 25), head + 45, t)
    s, W = new("<=>")
    s.capsule((m + head * 0.6, yb), (W - m - head * 0.6, yb), t)
    s.capsule((m + head * 0.6, yt), (W - m - head * 0.6, yt), t)
    s.chevron((W - m, ym), head + 25, head + 45, t)
    s.chevron((m, ym), -(head + 25), head + 45, t)

    # comparison --------------------------------------------------------------
    s, W = new("==")
    for y in (yb, yt):
        s.capsule((m - 20, y), (W - m + 20, y), t)
    s, W = new("===")
    for y in (eq_lo + t3 / 2, ym, eq_hi - t3 / 2):
        s.capsule((m - 20, y), (W - m + 20, y), t3)
    s, W = new("!=")
    for y in (yb, yt):
        s.capsule((m - 20, y), (W - m + 20, y), t)
    s.capsule((W / 2 - 62, eq_lo - 78), (W / 2 + 62, eq_hi + 78), t * 0.95)
    s, W = new("/=")
    for y in (yb, yt):
        s.capsule((m - 20, y), (W - m + 20, y), t)
    s.capsule((W / 2 - 62, eq_lo - 78), (W / 2 + 62, eq_hi + 78), t * 0.95)
    s, W = new("!==")
    for y in (eq_lo + t3 / 2, ym, eq_hi - t3 / 2):
        s.capsule((m - 20, y), (W - m + 20, y), t3)
    s.capsule((W / 2 - 62, eq_lo - 78), (W / 2 + 62, eq_hi + 78), t * 0.95)

    for seq, left in ((">=", False), ("<=", True)):
        s, W = new(seq)
        dxh, dyh = 330, 170
        cy = ym + 85
        if left:
            s.chevron((m + 20, cy), -dxh, dyh, t)
        else:
            s.chevron((W - m - 20, cy), dxh, dyh, t)
        bar_y = cy - dyh - t - 30   # leave a clear gap under the chevron
        s.capsule((m + 20, bar_y), (W - m - 20, bar_y), t)

    # chevrons and dashes -----------------------------------------------------
    s, W = new(">>")
    for tip in (480, 980):
        s.chevron((tip - 20, ym + 20), 230, 190, t)
    s, W = new("<<")
    for tip in (20, 520):
        s.chevron((tip + 20, ym + 20), -230, 190, t)
    s, W = new("--")
    s.capsule((m, hy), (W - m, hy), t)
    s, W = new("---")
    s.capsule((m, hy), (W - m, hy), t)
    return out


# --------------------------------------------------------------------------
# powerline + icons (all width 500)
# --------------------------------------------------------------------------
def build_powerline(t):
    Y0, Y1, W = DESCENT_Y, ASCENT_Y, CELL
    yc = (Y0 + Y1) / 2.0
    ts = 70
    g = {}

    def mirror(pts):
        return [(W - x, y) for x, y in pts]

    def poly(cp, pts):
        s = Shape()
        s.polygon(pts)
        g[cp] = s
        return s

    # E0B0..E0B3 triangle / chevron arrows
    poly(0xE0B0, [(0, Y0), (W, yc), (0, Y1)])
    poly(0xE0B1, [(0, Y1), (ts, Y1), (W, yc), (ts, Y0), (0, Y0), (W - ts, yc)])
    poly(0xE0B2, mirror([(0, Y0), (W, yc), (0, Y1)]))
    poly(0xE0B3, mirror([(0, Y1), (ts, Y1), (W, yc), (ts, Y0), (0, Y0), (W - ts, yc)]))

    # E0B4..E0B7 half circles
    def half(cp, thin, left):
        s = Shape()
        rx, ry = W, (Y1 - Y0) / 2.0
        seg = [
            ("C", ((0, Y1), (K * rx, Y1), (rx, yc + K * ry), (rx, yc))),
            ("C", ((rx, yc), (rx, yc - K * ry), (K * rx, Y0), (0, Y0))),
        ]
        if thin:
            ix, iy = rx - ts, ry - ts
            seg += [
                ("L", ((0, Y0), (0, Y0 + ts))),
                ("C", ((0, Y0 + ts), (K * ix, Y0 + ts), (ix, yc - K * iy), (ix, yc))),
                ("C", ((ix, yc), (ix, yc + K * iy), (K * ix, Y1 - ts), (0, Y1 - ts))),
                ("L", ((0, Y1 - ts), (0, Y1))),
            ]
        else:
            seg.append(("L", ((0, Y0), (0, Y1))))
        if left:
            seg = [(k, tuple((W - x, y) for x, y in p)) for k, p in seg]
        s.solid(seg)
        g[cp] = s

    half(0xE0B4, False, False)
    half(0xE0B5, True, False)
    half(0xE0B6, False, True)
    half(0xE0B7, True, True)

    # E0B8..E0BF corner triangles and diagonals
    poly(0xE0B8, [(0, Y0), (W, Y0), (0, Y1)])
    poly(0xE0B9, [(0, Y1), (ts, Y1), (W, Y0), (W - ts, Y0)])
    poly(0xE0BA, [(0, Y0), (W, Y0), (W, Y1)])
    poly(0xE0BB, [(0, Y0), (ts, Y0), (W, Y1), (W - ts, Y1)])
    poly(0xE0BC, [(0, Y0), (0, Y1), (W, Y1)])
    poly(0xE0BD, [(0, Y0), (ts, Y0), (W, Y1), (W - ts, Y1)])
    poly(0xE0BE, [(W, Y0), (W, Y1), (0, Y1)])
    poly(0xE0BF, [(0, Y1), (ts, Y1), (W, Y0), (W - ts, Y0)])
    return g


def build_icons(t, glyph_set, cmap):
    """Simple icons on a 440-unit box centred on the x-height line."""
    S, X0, Y0 = 440.0, 30.0, 110.0
    w = max(46.0, t * 0.75)            # icon stroke
    g = {}

    def P(x, y):                        # unit coords -> font units
        return (X0 + x * S, Y0 + y * S)

    def poly(pts, hole=False, shape=None):
        shape.polygon([P(*p) for p in pts], hole=hole)

    def cap(s, a, b, k=1.0):
        s.capsule(P(*a), P(*b), w * k)

    def ring(s, cx, cy, r, k=1.0):
        c = P(cx, cy)
        s.ring(c[0], c[1], r * S, w * k)

    def disc(s, cx, cy, r, hole=False):
        c = P(cx, cy)
        s.ellipse(c[0], c[1], r * S, r * S, hole=hole)

    def add(cps, builder):
        s = Shape()
        builder(s)
        for cp in cps:
            g[cp] = s

    # git branch (powerline, octicons, devicons, font-awesome fork)
    def branch(s):
        ring(s, 0.25, 0.86, 0.14)
        ring(s, 0.25, 0.14, 0.14)
        ring(s, 0.76, 0.62, 0.14)
        cap(s, (0.25, 0.28), (0.25, 0.72))
        cap(s, (0.25, 0.40), (0.76, 0.48))

    add((0xE0A0, 0xF418, 0xE725, 0xF126), branch)

    # LN and CN badges
    def letters(a, b):
        def build(s):
            s.glyph_outline(glyph_set, cmap[ord(a)], 0.5, 0.5, 5, 150)
            s.glyph_outline(glyph_set, cmap[ord(b)], 0.5, 0.5, 250, 150)
        return build

    add((0xE0A1,), letters("L", "N"))
    add((0xE0A3,), letters("C", "N"))

    # lock
    def lock(s):
        ring(s, 0.5, 0.62, 0.30, 0.8)
        poly([(0.12, 0.0), (0.88, 0.0), (0.88, 0.50), (0.12, 0.50)], shape=s)
        disc(s, 0.5, 0.28, 0.07, hole=True)

    add((0xE0A2, 0xF023), lock)

    # folder / open folder / file
    def folder(s):
        poly([(0.04, 0.08), (0.96, 0.08), (0.96, 0.76), (0.48, 0.76), (0.40, 0.92),
              (0.04, 0.92)], shape=s)

    add((0xF07B, 0xE5FF), folder)

    def folder_open(s):
        poly([(0.04, 0.08), (0.80, 0.08), (0.98, 0.48), (0.98, 0.60), (0.80, 0.60),
              (0.80, 0.72), (0.46, 0.72), (0.38, 0.88), (0.04, 0.88)], shape=s)

    add((0xF07C,), folder_open)

    def file_(s):
        poly([(0.14, 0.04), (0.86, 0.04), (0.86, 0.68), (0.54, 1.0), (0.14, 1.0)], shape=s)
        poly([(0.54, 0.96), (0.54, 0.70), (0.82, 0.70)], hole=True, shape=s)

    add((0xF15B, 0xF016), file_)

    # check / cross / plus / minus / bars
    add((0xF00C,), lambda s: s.polyline([P(0.08, 0.48), P(0.36, 0.14), P(0.94, 0.86)], w * 1.15))

    def cross(s):
        cap(s, (0.12, 0.12), (0.88, 0.88), 1.1)
        cap(s, (0.12, 0.88), (0.88, 0.12), 1.1)

    add((0xF00D,), cross)

    def plus(s):
        cap(s, (0.1, 0.5), (0.9, 0.5), 1.1)
        cap(s, (0.5, 0.1), (0.5, 0.9), 1.1)

    add((0xF067,), plus)
    add((0xF068,), lambda s: cap(s, (0.1, 0.5), (0.9, 0.5), 1.1))

    def bars(s):
        for y in (0.2, 0.5, 0.8):
            cap(s, (0.1, y), (0.9, y), 1.0)

    add((0xF0C9,), bars)

    # warning triangle
    def warning(s):
        poly([(0.5, 0.96), (0.02, 0.06), (0.98, 0.06)], shape=s)
        # exclamation mark cut out of the triangle
        bar = Shape()
        bar.capsule(P(0.5, 0.34), P(0.5, 0.62), w * 0.9)
        for c in bar.contours:
            s.hole(c)
        c = P(0.5, 0.20)
        s.ellipse(c[0], c[1], w * 0.55, w * 0.55, hole=True)

    add((0xF071,), warning)

    # clock
    def clock(s):
        ring(s, 0.5, 0.5, 0.46, 0.9)
        cap(s, (0.5, 0.5), (0.5, 0.78), 0.8)
        cap(s, (0.5, 0.5), (0.72, 0.38), 0.8)

    add((0xF017,), clock)

    # home
    def home(s):
        poly([(0.5, 1.0), (0.02, 0.52), (0.16, 0.52), (0.16, 0.04), (0.40, 0.04),
              (0.40, 0.34), (0.60, 0.34), (0.60, 0.04), (0.84, 0.04), (0.84, 0.52),
              (0.98, 0.52)], shape=s)

    add((0xF015,), home)

    # search
    def search(s):
        ring(s, 0.42, 0.58, 0.34, 1.0)
        cap(s, (0.68, 0.32), (0.94, 0.06), 1.2)

    add((0xF002,), search)

    # star
    def star(s):
        pts = []
        for i in range(10):
            r = 0.5 if i % 2 == 0 else 0.21
            a = math.pi / 2 + i * math.pi / 5
            pts.append((0.5 + r * math.cos(a) * 1.0, 0.5 + r * math.sin(a)))
        poly(pts, shape=s)

    add((0xF005,), star)

    # heart
    def heart(s):
        seg = [
            ("C", (P(0.5, 0.06), P(0.30, 0.22), P(0.02, 0.46), P(0.02, 0.70))),
            ("C", (P(0.02, 0.70), P(0.02, 0.92), P(0.40, 1.04), P(0.5, 0.74))),
            ("C", (P(0.5, 0.74), P(0.60, 1.04), P(0.98, 0.92), P(0.98, 0.70))),
            ("C", (P(0.98, 0.70), P(0.98, 0.46), P(0.70, 0.22), P(0.5, 0.06))),
        ]
        s.solid(seg)

    add((0xF004,), heart)

    # bolt
    def bolt(s):
        poly([(0.62, 1.0), (0.16, 0.46), (0.45, 0.46), (0.36, 0.0), (0.86, 0.60),
              (0.56, 0.60)], shape=s)

    add((0xF0E7,), bolt)

    # code </>  and terminal
    def code(s):
        s.chevron(P(0.04, 0.5), -0.30 * S, 0.30 * S, w)
        s.chevron(P(0.96, 0.5), 0.30 * S, 0.30 * S, w)
        cap(s, (0.58, 0.82), (0.42, 0.18), 0.9)

    add((0xF121,), code)

    def terminal(s):
        s.chevron(P(0.50, 0.5), 0.36 * S, 0.30 * S, w)
        cap(s, (0.58, 0.14), (0.96, 0.14), 1.0)

    add((0xF120,), terminal)

    # gear
    def gear(s):
        c = P(0.5, 0.5)
        s.ellipse(c[0], c[1], 0.34 * S, 0.34 * S)
        for i in range(8):
            a = i * math.pi / 4
            p1 = (c[0] + 0.30 * S * math.cos(a), c[1] + 0.30 * S * math.sin(a))
            p2 = (c[0] + 0.46 * S * math.cos(a), c[1] + 0.46 * S * math.sin(a))
            tooth = Shape()
            tooth.capsule(p1, p2, 0.17 * S)
            s.contours.extend(tooth.contours)
        s.ellipse(c[0], c[1], 0.14 * S, 0.14 * S, hole=True)

    add((0xF013,), gear)
    return g


# --------------------------------------------------------------------------
# font assembly
# --------------------------------------------------------------------------
ASCENT_Y, DESCENT_Y = ASC, DESC


def measure(font):
    cm = font.getBestCmap()
    gs = font.getGlyphSet()

    def bounds(ch):
        bp = BoundsPen(gs)
        gs[cm[ord(ch)]].draw(bp)
        return bp.bounds

    hy = bounds("-")
    eq = bounds("=")
    return {"t": hy[3] - hy[1], "hy": (hy[1] + hy[3]) / 2.0, "eq_lo": eq[1], "eq_hi": eq[3]}


def build(src_path, style, out_dir):
    print("[%s] reading %s" % (style, src_path))
    src = TTFont(src_path)
    cmap = src.getBestCmap()
    gs = src.getGlyphSet()
    hmtx = src["hmtx"]
    metrics = measure(src)
    print("[%s] stroke %.1f, hyphen y %.1f, '=' %.1f..%.1f"
          % (style, metrics["t"], metrics["hy"], metrics["eq_lo"], metrics["eq_hi"]))

    # --- rename glyphs to uniXXXX and copy outlines ------------------------
    old_order = src.getGlyphOrder()
    notdef = old_order[0]
    rename = {notdef: ".notdef"}
    new_cmap = {}
    for cp in sorted(cmap):
        old = cmap[cp]
        if old not in rename:
            rename[old] = "uni%04X" % cp if cp <= 0xFFFF else "u%X" % cp
        new_cmap[cp] = rename[old]
    order = [".notdef"] + [rename[o] for o in old_order[1:] if o in rename]
    charstrings, advance, lsb = {}, {}, {}
    for old, new in rename.items():
        pen = T2CharStringPen(hmtx[old][0], None)
        gs[old].draw(pen)
        charstrings[new] = pen.getCharString()
        bp = BoundsPen(gs)
        gs[old].draw(bp)
        advance[new] = hmtx[old][0]
        lsb[new] = int(round(bp.bounds[0])) if bp.bounds else 0

    # --- new glyphs ----------------------------------------------------------
    t = metrics["t"]
    ligs = build_ligatures(metrics)
    for seq, (gname, shape, width) in ligs.items():
        charstrings[gname] = shape.to_charstring(width)
        advance[gname], lsb[gname] = width, shape.xmin()
        order.append(gname)

    extra = {}
    extra.update(build_powerline(t))
    extra.update(build_icons(t, gs, cmap_old_to_glyph(cmap)))
    for cp, shape in sorted(extra.items()):
        gname = "uni%04X" % cp
        charstrings[gname] = shape.to_charstring(CELL)
        advance[gname], lsb[gname] = CELL, shape.xmin()
        new_cmap[cp] = gname
        order.append(gname)

    # --- font tables -----------------------------------------------------------
    bold = style == "Bold"
    ps = "%s-%s" % (FAMILY.replace(" ", ""), style)
    full = "%s %s" % (FAMILY, style)
    fb = FontBuilder(1000, isTTF=False)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(new_cmap)
    fb.setupCFF(ps, {"FullName": full, "FamilyName": FAMILY, "Weight": style}, charstrings, {})
    fb.setupHorizontalMetrics({n: (advance[n], lsb[n]) for n in order})
    fb.setupHorizontalHeader(ascent=ASC, descent=DESC, lineGap=0)
    src_names = src["name"]
    fb.setupNameTable({
        "copyright": src_names.getDebugName(0),
        "familyName": FAMILY,
        "styleName": style,
        "uniqueFontIdentifier": "%s;%s" % (VERSION, ps),
        "fullName": full,
        "version": "Version " + VERSION,
        "psName": ps,
        "licenseDescription": src_names.getDebugName(13),
        "licenseInfoURL": src_names.getDebugName(14),
    })
    fb.setupOS2(
        sTypoAscender=880, sTypoDescender=-120, sTypoLineGap=ASC - DESC - 1000,
        usWinAscent=ASC, usWinDescent=-DESC,
        sxHeight=543, sCapHeight=733,
        usWeightClass=700 if bold else 400,
        achVendID="UKWN", fsType=0,
    )
    os2 = fb.font["OS/2"]
    os2.panose.bProportion = 9
    os2.fsSelection = (0x20 if bold else 0x40)
    fb.font["head"].macStyle = 1 if bold else 0
    fb.setupPost(isFixedPitch=1)

    # --- ligature feature -------------------------------------------------------
    seqs = sorted(ligs, key=lambda s: (-len(s), s))
    lines = ["languagesystem DFLT dflt;", "languagesystem latn dflt;", "lookup MOCHI_LIGS {"]
    for seq in seqs:
        lines.append("  sub %s by %s;" % (" ".join(uname(c) for c in seq), ligs[seq][0]))
    lines += ["} MOCHI_LIGS;", "feature calt { lookup MOCHI_LIGS; } calt;",
              "feature liga { lookup MOCHI_LIGS; } liga;"]
    addOpenTypeFeaturesFromString(fb.font, "\n".join(lines))

    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "MochiMonoLigature-%s.otf" % style)
    fb.save(out)
    print("[%s] wrote %s (%.1f MB, %d glyphs, %d ligatures, %d icon/powerline glyphs)"
          % (style, out, os.path.getsize(out) / 1e6, len(order), len(ligs), len(extra)))


def cmap_old_to_glyph(cmap):
    """cp -> original glyph name, for outlines borrowed from the source font."""
    return cmap


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="folder with MochiMono-*.otf")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    for style in ("Regular", "Bold"):
        build(os.path.join(args.src, "MochiMono-%s.otf" % style), style, args.out)


if __name__ == "__main__":
    main()
