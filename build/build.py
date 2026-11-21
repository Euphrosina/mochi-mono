#!/usr/bin/env python3
"""
Mochi Mono build script.

Takes Noto Sans Mono CJK SC (SIL OFL 1.1), keeps a useful character set
(ASCII / Latin / pinyin / symbols / kana / GB2312 / Big5 hanzi), and rounds
every sharp outline corner into a soft, puffy one.

Usage:
    python3 build.py --regular NotoSansCJK-Regular.ttc --bold NotoSansCJK-Bold.ttc --out ../fonts
"""
import argparse
import math
import os

from fontTools import subset
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTCollection

FAMILY = "Mochi Mono"
VERSION = "1.000"
SOURCE_NAME = "Noto Sans Mono CJK SC"

# corner radii (font units, em = 1000): convex corners, concave corners
PARAMS = {
    "Regular": dict(r_convex=46.0, r_concave=22.0),
    "Bold": dict(r_convex=58.0, r_concave=28.0),
}
MIN_TURN_DEG = 15.0   # gentler turns are treated as smooth and left alone
MAX_TURN_DEG = 172.0


# --------------------------------------------------------------------------
# character set
# --------------------------------------------------------------------------
def wanted_codepoints():
    cps = set()
    ranges = [
        (0x20, 0x7E), (0xA0, 0xFF),            # ASCII, Latin-1
        (0x100, 0x17F), (0x1CD, 0x1DC),        # Latin Ext-A, pinyin vowels
        (0x251, 0x251), (0x261, 0x261),        # ɑ ɡ
        (0x2C6, 0x2C7), (0x2C9, 0x2CB),        # modifier letters (bopomofo tones)
        (0x2010, 0x2027), (0x2030, 0x203E),    # general punctuation
        (0x20AC, 0x20AC),                      # euro
        (0x2190, 0x21FF), (0x2200, 0x22FF),    # arrows, math
        (0x2500, 0x259F), (0x25A0, 0x25FF),    # box drawing, blocks, shapes
        (0x2605, 0x2606), (0x2660, 0x2667), (0x266A, 0x266B),
        (0x3000, 0x303F),                      # CJK symbols and punctuation
        (0x3040, 0x30FF),                      # hiragana, katakana
        (0x3105, 0x312F),                      # bopomofo
        (0xFF01, 0xFF5E), (0xFFE0, 0xFFE5),    # fullwidth forms
    ]
    for lo, hi in ranges:
        cps.update(range(lo, hi + 1))

    # GB2312 hanzi (simplified, levels 1+2)
    for hi in range(0xB0, 0xF8):
        for lo in range(0xA1, 0xFF):
            try:
                ch = bytes([hi, lo]).decode("gb2312")
            except UnicodeDecodeError:
                continue
            cps.add(ord(ch))
    # Big5 hanzi (traditional, levels 1+2)
    for hi in range(0xA4, 0xFA):
        for lo in list(range(0x40, 0x7F)) + list(range(0xA1, 0xFF)):
            try:
                ch = bytes([hi, lo]).decode("big5")
            except UnicodeDecodeError:
                continue
            if 0x4E00 <= ord(ch) <= 0x9FFF:
                cps.add(ord(ch))
    return cps


# --------------------------------------------------------------------------
# small vector helpers
# --------------------------------------------------------------------------
def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def mul(a, k):
    return (a[0] * k, a[1] * k)


def norm(a):
    return math.hypot(a[0], a[1])


def unit(a):
    n = norm(a)
    return (a[0] / n, a[1] / n) if n > 1e-9 else (0.0, 0.0)


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


# --------------------------------------------------------------------------
# outline model: a contour is a list of segments
#   ("L", (p0, p1))  or  ("C", (p0, c1, c2, p1))
# --------------------------------------------------------------------------
def contours_from_recording(rec):
    out, cur, start, pos = [], None, None, None
    for op, args in rec:
        if op == "moveTo":
            cur, start, pos = [], args[0], args[0]
        elif op == "lineTo":
            if args[0] != pos:
                cur.append(("L", (pos, args[0])))
            pos = args[0]
        elif op == "curveTo":
            if len(args) != 3:
                raise ValueError("unexpected curveTo arity")
            cur.append(("C", (pos, args[0], args[1], args[2])))
            pos = args[2]
        elif op in ("closePath", "endPath"):
            if cur is not None:
                if pos != start:
                    cur.append(("L", (pos, start)))
                if cur:
                    out.append(cur)
            cur = None
        else:
            raise ValueError("unsupported op %s" % op)
    return out


def bez(p, t):
    p0, c1, c2, p1 = p
    a, b, c = lerp(p0, c1, t), lerp(c1, c2, t), lerp(c2, p1, t)
    d, e = lerp(a, b, t), lerp(b, c, t)
    return lerp(d, e, t)


def split_cubic(p, t):
    p0, c1, c2, p1 = p
    a, b, c = lerp(p0, c1, t), lerp(c1, c2, t), lerp(c2, p1, t)
    d, e = lerp(a, b, t), lerp(b, c, t)
    m = lerp(d, e, t)
    return (p0, a, d, m), (m, e, c, p1)


def seg_len(seg):
    kind, p = seg
    if kind == "L":
        return norm(sub(p[1], p[0]))
    total, prev = 0.0, p[0]
    for i in range(1, 17):
        cur = bez(p, i / 16.0)
        total += norm(sub(cur, prev))
        prev = cur
    return total


def tan_start(seg):
    kind, p = seg
    if kind == "L":
        return unit(sub(p[1], p[0]))
    for q in (p[1], p[2], p[3]):
        v = sub(q, p[0])
        if norm(v) > 1e-6:
            return unit(v)
    return (0.0, 0.0)


def tan_end(seg):
    kind, p = seg
    if kind == "L":
        return unit(sub(p[1], p[0]))
    for q in (p[2], p[1], p[0]):
        v = sub(p[3], q)
        if norm(v) > 1e-6:
            return unit(v)
    return (0.0, 0.0)


def trim_start(seg, d):
    """Remove the first d units (chord distance) of a segment."""
    kind, p = seg
    if kind == "L":
        v = unit(sub(p[1], p[0]))
        return ("L", (add(p[0], mul(v, d)), p[1]))
    lo, hi = 0.0, 1.0
    for _ in range(30):
        mid = (lo + hi) / 2
        if norm(sub(bez(p, mid), p[0])) < d:
            lo = mid
        else:
            hi = mid
    return ("C", split_cubic(p, (lo + hi) / 2)[1])


def trim_end(seg, d):
    """Remove the last d units (chord distance) of a segment."""
    kind, p = seg
    if kind == "L":
        v = unit(sub(p[0], p[1]))
        return ("L", (p[0], add(p[1], mul(v, d))))
    lo, hi = 0.0, 1.0
    for _ in range(30):
        mid = (lo + hi) / 2
        if norm(sub(bez(p, mid), p[3])) < d:
            hi = mid
        else:
            lo = mid
    return ("C", split_cubic(p, (lo + hi) / 2)[0])


def seg_start(seg):
    return seg[1][0]


def seg_end(seg):
    return seg[1][-1]


def signed_area(contour):
    pts = []
    for kind, p in contour:
        pts.extend(p[:-1])
    s = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return s / 2.0


# --------------------------------------------------------------------------
# the actual rounding
# --------------------------------------------------------------------------
def round_contour(segs, fill_left, r_convex, r_concave):
    n = len(segs)
    if n < 2:
        return segs, []
    lens = [seg_len(s) for s in segs]
    cuts = [None] * n  # cut at the vertex that STARTS segment i
    for i in range(n):
        a, b = segs[i - 1], segs[i]
        t1, t2 = tan_end(a), tan_start(b)
        dot = max(-1.0, min(1.0, t1[0] * t2[0] + t1[1] * t2[1]))
        turn = math.degrees(math.acos(dot))
        if turn < MIN_TURN_DEG:
            continue
        turn = min(turn, MAX_TURN_DEG)
        cross = t1[0] * t2[1] - t1[1] * t2[0]
        convex = (cross > 0) == fill_left
        r = r_convex if convex else r_concave
        theta = math.radians(turn)
        d = r * math.tan(theta / 2.0)
        d = min(d, 0.5 * lens[i - 1], 0.5 * lens[i])
        if d < 1.0:
            continue
        cuts[i] = (d, theta, t1, t2)

    trimmed = []
    for i, s in enumerate(segs):
        if cuts[i] is not None:
            s = trim_start(s, cuts[i][0])
        nxt = cuts[(i + 1) % n]
        if nxt is not None:
            s = trim_end(s, nxt[0])
        trimmed.append(s)

    out = []
    for i in range(n):
        # a segment that was trimmed down to nothing (thin stroke ends) is dropped
        if seg_len(trimmed[i]) > 0.05:
            out.append(trimmed[i])
        nxt = (i + 1) % n
        if cuts[nxt] is not None:
            d, theta, o1, o2 = cuts[nxt]
            p_s, p_e = seg_end(trimmed[i]), seg_start(trimmed[nxt])
            # use the trimmed segments' own tangents when they still have length,
            # otherwise fall back to the tangents measured at the original corner
            t1 = tan_end(trimmed[i]) if seg_len(trimmed[i]) > 0.5 else o1
            t2 = tan_start(trimmed[nxt]) if seg_len(trimmed[nxt]) > 0.5 else o2
            k = (4.0 / 3.0) * math.tan(theta / 4.0) / math.tan(theta / 2.0)
            h = d * k
            out.append(("C", (p_s, add(p_s, mul(t1, h)), sub(p_e, mul(t2, h)), p_e)))
    return out, cuts


def mono_fit(width):
    """Return (target_width, x_scale, x_shift) that snaps a proportional glyph
    onto the 500/1000 monospace grid (zero-width marks and grid glyphs are kept)."""
    if width in (0, 500, 1000):
        return width, 1.0, 0.0
    target = 1000 if width >= 700 else 500
    sx = max(0.8, min(1.25, target / float(width)))
    return target, sx, (target - width * sx) / 2.0


def round_glyph(glyph, width, params, private, gsubrs):
    """Returns (charstring, new_advance_width, xMin)."""
    target, sx, dx = mono_fit(width)
    rec = RecordingPen()
    glyph.draw(TransformPen(rec, (sx, 0, 0, 1, dx, 0)))
    width = target
    contours = contours_from_recording(rec.value)
    pen = T2CharStringPen(width, None)
    if contours:
        big = max(contours, key=lambda c: abs(signed_area(c)))
        fill_left = signed_area(big) > 0  # CCW outer contour -> fill on the left
        for c in contours:
            new, _ = round_contour(c, fill_left, params["r_convex"], params["r_concave"])
            pen.moveTo(seg_start(new[0]))
            for kind, p in new:
                if kind == "L":
                    pen.lineTo(p[1])
                else:
                    pen.curveTo(p[1], p[2], p[3])
            pen.closePath()
    charstring = pen.getCharString(private, gsubrs)
    bounds = BoundsPen(None)
    charstring.draw(bounds)
    xmin = int(round(bounds.bounds[0])) if bounds.bounds else 0
    return charstring, width, xmin


# --------------------------------------------------------------------------
# font building
# --------------------------------------------------------------------------
def load_face(ttc_path):
    ttc = TTCollection(ttc_path)
    for f in ttc.fonts:
        if f["name"].getDebugName(1) == SOURCE_NAME:
            return f
    raise SystemExit("face %r not found in %s" % (SOURCE_NAME, ttc_path))


def set_names(font, style):
    ps = "%s-%s" % (FAMILY.replace(" ", ""), style)
    full = "%s %s" % (FAMILY, style)
    orig = font["name"].getDebugName(0) or ""
    copyright_ = (
        "%s Mochi Mono is a modified version of Noto Sans Mono CJK SC "
        "(rounded corners, reduced character set)." % orig
    ).strip()
    lic = font["name"].getDebugName(13)
    lic_url = font["name"].getDebugName(14)
    name = font["name"]
    name.names = []

    def put(i, s):
        if s:
            name.setName(s, i, 3, 1, 0x409)
            name.setName(s, i, 1, 0, 0)

    put(0, copyright_)
    put(1, FAMILY)
    put(2, style)
    put(3, "%s;%s" % (VERSION, ps))
    put(4, full)
    put(5, "Version " + VERSION)
    put(6, ps)
    put(13, lic)
    put(14, lic_url)

    cff = font["CFF "].cff
    cff.fontNames = [ps]
    top = cff.topDictIndex[0]
    top.FullName = full
    top.FamilyName = FAMILY
    top.Notice = ""
    if hasattr(top, "Copyright"):
        top.Copyright = ""
    os2 = font["OS/2"]
    os2.achVendID = "UKWN"


def build(ttc_path, style, out_dir):
    print("[%s] loading %s" % (style, ttc_path))
    font = load_face(ttc_path)

    # drop Unicode Variation Sequence maps (cmap format 14): they drag in tens of
    # thousands of regional glyph variants we do not want
    cmap = font["cmap"]
    cmap.tables = [t for t in cmap.tables if t.format != 14]

    opts = subset.Options()
    opts.hinting = False
    opts.desubroutinize = True
    opts.notdef_outline = True
    opts.glyph_names = False
    # 'locl' / 'ccmp' pull in ~15k regional (JP/KR/TC) glyph variants; keep only
    # vertical-writing punctuation forms
    opts.layout_features = ["vert", "vrt2"]
    opts.name_IDs = ["*"]
    opts.name_languages = ["*"]
    sub_ = subset.Subsetter(opts)
    sub_.populate(unicodes=wanted_codepoints())
    print("[%s] subsetting ..." % style)
    sub_.subset(font)

    cff = font["CFF "].cff
    top = cff.topDictIndex[0]
    cs = top.CharStrings
    glyph_set = font.getGlyphSet()
    order = font.getGlyphOrder()
    hmtx = font["hmtx"]
    params = PARAMS[style]
    print("[%s] rounding %d glyphs ..." % (style, len(order)))
    new = {}
    for gid, gname in enumerate(order):
        if hasattr(top, "FDSelect") and top.FDSelect is not None:
            private = top.FDArray[top.FDSelect[gid]].Private
        else:
            private = top.Private
        new[gname] = round_glyph(glyph_set[gname], hmtx[gname][0], params, private, cff.GlobalSubrs)
    for gname, (charstring, adv, xmin) in new.items():
        cs[gname] = charstring
        hmtx[gname] = (adv, xmin)

    font["post"].isFixedPitch = 1
    font["OS/2"].panose.bProportion = 9  # monospaced

    set_names(font, style)
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "MochiMono-%s.otf" % style)
    font.save(out)
    print("[%s] wrote %s (%.1f MB)" % (style, out, os.path.getsize(out) / 1e6))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regular", required=True)
    ap.add_argument("--bold", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    build(args.regular, "Regular", args.out)
    build(args.bold, "Bold", args.out)


if __name__ == "__main__":
    main()
