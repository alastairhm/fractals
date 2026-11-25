#!/usr/bin/env python3
"""
Random hand-drawn "alien script" glyph generator.

Each glyph is split into vertical columns, and each column is stacked with
segments: pinched bars, (optionally notched) blocks, and ovals with spiral
cut-outs. Everything is wobbled and drawn as a filled marker shape with white
"streak" gaps, like felt-tip on paper.

Each glyph gets a random hue; its shapes vary in shade.

Output is plain SVG (stdlib only). PNG too if cairosvg is installed.

  python3 glyphs.py                      # 3x4 sheet -> glyphs.svg
  python3 glyphs.py --rows 1 --cols 1 --size 400 --seed 42
  python3 glyphs.py --color "#1e8c2b" --png glyphs.png   # all shades of green
"""
import argparse
import colorsys
import math
import random

PAPER = "#e8e3e5"
RULE = "#5a4f52"


# ---------- geometry helpers ----------

def catmull_rom(pts, closed=True):
    """Turn a point list into a smooth SVG path (Catmull-Rom -> cubic Bezier)."""
    n = len(pts)
    if n < 2:
        return ""
    def P(i):
        return pts[i % n] if closed else pts[max(0, min(n - 1, i))]
    d = [f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"]
    rng = range(n) if closed else range(n - 1)
    for i in rng:
        p0, p1, p2, p3 = P(i - 1), P(i), P(i + 1), P(i + 2)
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d.append(f"C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}")
    if closed:
        d.append("Z")
    return " ".join(d)


def _flip_path(d, y, h):
    """Mirror an SVG path (M/C/Z with absolute coords) vertically about y + h/2."""
    out = []
    for tok in d.split():
        cmd = tok[0] if tok[0].isalpha() else ""
        body = tok[len(cmd):]
        if "," in body:
            px, py = body.split(",")
            body = f"{px},{2 * y + h - float(py):.1f}"
        out.append(cmd + body)
    return " ".join(out)


def wobble(pts, amt, rng):
    return [(x + rng.uniform(-amt, amt), y + rng.uniform(-amt, amt)) for x, y in pts]


# ---------- shape primitives ----------

class Pen:
    def __init__(self, rng, color, scale):
        self.rng, self.color, self.s = rng, color, scale
        self.outline = False   # True: thick outlines only, no fill or streaks
        self.out = []

    def shape(self, pts, inner_paths):
        r, s = self.rng, self.s
        body = catmull_rom(wobble(pts, 1.2 * s, r))
        if self.outline:
            self.out.append(f'<path d="{body}" fill="none" stroke="{self.color}" '
                            f'stroke-width="{7*s:.1f}" stroke-linejoin="round"/>')
            return
        self.out.append(f'<path d="{body}" fill="{self.color}" stroke="{self.color}" '
                        f'stroke-width="{3*s:.1f}" stroke-linejoin="round"/>')
        for p, w in inner_paths:
            self.out.append(f'<path d="{p}" fill="none" stroke="{PAPER}" stroke-opacity="0.92" '
                            f'stroke-width="{w:.1f}" stroke-linecap="round"/>')

    def block(self, x, y, w, h, pinch=0.0, taper=0.0, notch_top=0.0, notch_bot=0.0):
        """Rectangle-ish block; pinch narrows the middle, notches bite the ends."""
        r, s = self.rng, self.s
        cx = x + w / 2

        def half(t):
            # never wider than the column: margin covers stroke + wobble, taper only narrows
            base = w / 2 - 3.5 * s
            shrink = abs(taper) * (t if taper > 0 else 1 - t)
            return base * (1 - pinch * math.sin(math.pi * t)) * (1 - shrink)

        def notch(u, depth):
            k = 1 - ((u - 0.5) / 0.32) ** 2
            return depth * h * math.sqrt(k) if k > 0 else 0.0

        n_h = max(6, int(h / (20 * s)))
        n_w = max(4, int(w / (20 * s)))
        pts = []
        for i in range(n_w + 1):                       # top, left -> right
            u = i / n_w
            pts.append((cx + (2 * u - 1) * half(0), y + notch(u, notch_top)))
        for i in range(1, n_h):                        # right side, down
            t = i / n_h
            pts.append((cx + half(t), y + t * h))
        for i in range(n_w, -1, -1):                   # bottom, right -> left
            u = i / n_w
            pts.append((cx + (2 * u - 1) * half(1), y + h - notch(u, notch_bot)))
        for i in range(n_h - 1, 0, -1):                # left side, up
            t = i / n_h
            pts.append((cx - half(t), y + t * h))

        # inner white streaks that follow the body's profile
        inner = []
        t0 = notch_top + 0.07 + r.uniform(0, 0.05)
        t1 = 1 - notch_bot - 0.07 - r.uniform(0, 0.05)
        style = r.choice(["streaks", "streaks", "frame"])
        if style == "frame" and w > 30 * s:
            # inset outline, sometimes with a diagonal like the 3rd column of the sketch
            fx = 0.62
            frame = ([(cx - fx * half(t0), y + t0 * h), (cx + fx * half(t0), y + t0 * h)] +
                     [(cx + fx * half(t), y + t * h) for t in (0.5, t1)] +
                     [(cx - fx * half(t1), y + t1 * h), (cx - fx * half(0.5), y + 0.5 * h)])
            inner.append((catmull_rom(wobble(frame, 1.5 * s, r)), 2.5 * s))
            if r.random() < 0.6:
                diag = [(cx - 0.3 * half(t0), y + (t0 + 0.05) * h),
                        (cx + 0.2 * half(0.5), y + 0.5 * h),
                        (cx + 0.35 * half(t1), y + (t1 - 0.05) * h)]
                inner.append((catmull_rom(wobble(diag, 2 * s, r), closed=False), 3.5 * s))
        n_lines = 1 if w < 25 * s else r.randint(2, 4)
        for k in range(n_lines):
            f = -0.55 + 1.1 * (k + 0.5) / n_lines + r.uniform(-0.08, 0.08)
            a, b = t0 + r.uniform(0, 0.15), t1 - r.uniform(0, 0.15)
            line = [(cx + f * half(t), y + t * h)
                    for t in (a + (b - a) * j / 4 for j in range(5))]
            inner.append((catmull_rom(wobble(line, 1.2 * s, r), closed=False),
                          r.uniform(3.5, 7) * s))
        self.shape(pts, inner)

    def ell(self, x, y, sw, h, reach, fh, top=False):
        """L shape: a stem `sw` wide and `h` tall, with a foot `fh` tall that runs
        `reach` px to the right (across the gap into the next column).
        top=True flips it so the foot is at the top (a Γ shape)."""
        r, s = self.rng, self.s
        m = 3.5 * s
        x0, x1, x2 = x + m, x + sw - m, x + reach - m        # stem left/right, foot end
        yb, yk = y + h, y + h - fh                           # bottom, knee (foot top)
        step = 20 * s

        def edge(a, b):
            n = max(2, int(math.dist(a, b) / step))
            return [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n)]

        corners = [(x0, y), (x1, y), (x1, yk), (x2, yk), (x2, yb), (x0, yb)]
        pts = []
        for i in range(len(corners)):
            pts += edge(corners[i], corners[(i + 1) % len(corners)])

        # nested L-shaped streaks: lines nearer the left edge sit nearer the bottom
        inner = []
        n_lines = r.randint(2, 3)
        for k in range(n_lines):
            f = (k + 0.5) / n_lines + r.uniform(-0.06, 0.06)
            lx = x0 + (x1 - x0) * (0.2 + 0.6 * f)
            ly = yb - fh * (0.25 + 0.5 * f)
            top_y = y + h * r.uniform(0.07, 0.15)
            end_x = x2 - (x2 - x1) * r.uniform(0.08, 0.2)
            line = [(lx, top_y), (lx, (top_y + ly) / 2), (lx, ly - 0.3 * fh),
                    (lx + 0.3 * fh, ly), ((lx + end_x) / 2, ly), (end_x, ly)]
            inner.append((catmull_rom(wobble(line, 1.2 * s, r), closed=False),
                          r.uniform(3.5, 6) * s))

        if top:  # mirror vertically about the shape's middle
            flip = lambda p: (p[0], 2 * y + h - p[1])
            pts = [flip(p) for p in pts]
            inner = [(_flip_path(d, y, h), w) for d, w in inner]
        self.shape(pts, inner)

    def oval(self, cx, cy, rx, ry, rot=None):
        r, s = self.rng, self.s
        n = 28
        if rot is None:
            rot = r.uniform(-0.08, 0.08)
        cr, sr = math.cos(rot), math.sin(rot)

        def place(ex, ey, ox=cx, oy=cy):  # local ellipse coords -> page, with tilt
            return ox + ex * cr - ey * sr, oy + ex * sr + ey * cr

        pts = [place(rx * math.cos(2 * math.pi * i / n), ry * math.sin(2 * math.pi * i / n))
               for i in range(n)]
        # spiral-ish concentric arcs, drifting toward one side
        inner = []
        dx, dy = r.uniform(-0.25, 0.25) * rx, r.uniform(-0.25, 0.25) * ry
        start = r.uniform(0, 2 * math.pi)
        rings = r.randint(2, 3)
        for k in range(rings):
            f = 0.72 - k * 0.22
            ox, oy = dx * (k + 1) / rings, dy * (k + 1) / rings
            sweep = r.uniform(3.6, 5.4)
            arc = [place(ox + f * rx * math.cos(start + sweep * j / 10),
                         oy + f * ry * math.sin(start + sweep * j / 10)) for j in range(11)]
            inner.append((catmull_rom(wobble(arc, 1.0 * s, r), closed=False),
                          r.uniform(4, 6.5) * s))
        self.shape(pts, inner)


# ---------- colour ----------

def hex_to_hls(h):
    h = h.lstrip("#")
    return colorsys.rgb_to_hls(*(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)))


def hls_to_hex(hh, l, sat):
    return "#" + "".join(f"{round(c * 255):02x}" for c in colorsys.hls_to_rgb(hh % 1, l, sat))


def glyph_palette(rng, fixed=None):
    """Return a function giving shades of one hue: random hue per glyph, or a fixed base."""
    if fixed:
        hue, light, sat = hex_to_hls(fixed)
    else:
        hue, light, sat = rng.random(), rng.uniform(0.30, 0.42), rng.uniform(0.55, 0.85)
    def shade():
        return hls_to_hex(hue + rng.uniform(-0.02, 0.02),
                          min(0.55, max(0.18, light + rng.uniform(-0.12, 0.12))),
                          min(1.0, max(0.35, sat + rng.uniform(-0.15, 0.1))))
    return shade


# ---------- glyph layout ----------

def glyph(pen, x, y, W, H, fixed_color=None, l_chance=0.35, ellipse_chance=0.5):
    r, s = pen.rng, pen.s
    shade = glyph_palette(r, fixed_color)
    ncols = r.choice([3, 3, 4, 4])  # at least 3 columns per glyph
    weights = [r.uniform(0.6, 1.4) for _ in range(ncols)]
    gap_x = 0.09 * W
    gap_y = 0.05 * H
    usable = W - gap_x * (ncols - 1)
    widths = [usable * w / sum(weights) for w in weights]
    xs = [x + sum(widths[:i]) + gap_x * i for i in range(ncols)]

    reserved = {}  # column index -> ("top"|"bottom", height taken by an L's foot)
    for c in range(ncols):
        cx, cw = xs[c], widths[c]
        top, bot = y, y + H
        if c in reserved:
            side, fh = reserved[c]
            if side == "bottom":
                bot -= fh + gap_y
            else:
                top += fh + gap_y

        # maybe make this column an L whose foot runs under/over the next column
        if c < ncols - 1 and c not in reserved and r.random() < l_chance:
            fh = H * r.uniform(0.16, 0.26)
            is_top = r.random() < 0.35
            reach = xs[c + 1] + widths[c + 1] * r.uniform(0.6, 1.0) - cx
            pen.color = shade()
            pen.ell(cx, y, cw, H, reach, fh, top=is_top)
            reserved[c + 1] = ("top" if is_top else "bottom", fh)
            continue

        avail = bot - top
        nseg = r.choices([1, 2, 3], [3, 4, 3])[0]
        if avail < 0.5 * H:
            nseg = min(nseg, 2)
        hw = [r.uniform(0.5, 1.5) for _ in range(nseg)]
        usable_h = avail - gap_y * (nseg - 1)
        cy = top
        for i, hh in enumerate(hw):
            sh = usable_h * hh / sum(hw)
            aspect = sh / cw
            pen.color = shade()
            round_fit = aspect < 1.4 and r.random() < 0.65
            tall_fit = not round_fit and aspect < 2.6 and r.random() < ellipse_chance * 0.5
            if round_fit or tall_fit:
                maxw, maxh = cw / 2 - 4 * s, sh / 2 - 2 * s
                if tall_fit or r.random() < ellipse_chance:
                    # ellipse: stretched tall or wide, and tilted
                    if tall_fit or r.random() < 0.6:
                        ry = maxh * 0.95
                        rx = min(maxw, ry * r.uniform(0.4, 0.7))
                    else:
                        rx = maxw * 0.95
                        ry = min(maxh, rx * r.uniform(0.45, 0.65))
                    rot = r.uniform(-0.35, 0.35)
                    # shrink if the tilt pushes it past the column or segment
                    bw = math.hypot(rx * math.cos(rot), ry * math.sin(rot))
                    bh = math.hypot(rx * math.sin(rot), ry * math.cos(rot))
                    k = min(1.0, maxw / bw, maxh / bh)
                    pen.oval(cx + cw / 2, cy + sh / 2, rx * k, ry * k, rot)
                else:
                    rx, ry = maxw * r.uniform(0.75, 0.92), min(sh / 2, cw * 0.75) * 0.95
                    pen.oval(cx + cw / 2, cy + sh / 2, rx, ry)
            else:
                narrow = cw < 0.22 * W
                pen.block(
                    cx, cy, cw, sh,
                    pinch=r.uniform(0.25, 0.45) if (narrow and nseg == 1) else r.uniform(0, 0.08),
                    taper=r.uniform(-0.15, 0.15),
                    notch_top=r.uniform(0.06, 0.14) if (i > 0 or r.random() < 0.2) and r.random() < 0.5 else 0,
                    notch_bot=r.uniform(0.06, 0.14) if (i < nseg - 1) and r.random() < 0.5 else 0,
                )
            cy += sh + gap_y


def sheet(rows, cols, size, seed, color, ruled, l_chance=0.35, ellipse_chance=0.5, outline=False):
    rng = random.Random(seed)
    s = size / 300
    pad = 0.25 * size
    Wd, Ht = cols * (size + pad) + pad, rows * (size * 1.25 + pad) + pad
    pen = Pen(rng, color, s)
    pen.outline = outline
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{Wd:.0f}" height="{Ht:.0f}" '
             f'viewBox="0 0 {Wd:.0f} {Ht:.0f}">',
             f'<rect width="100%" height="100%" fill="{PAPER}"/>']
    if ruled:
        step = size * 1.25 / 3
        yy = pad + step
        while yy < Ht:
            parts.append(f'<line x1="0" y1="{yy:.1f}" x2="{Wd:.0f}" y2="{yy+rng.uniform(-3,3):.1f}" '
                         f'stroke="{RULE}" stroke-width="{2*s:.1f}" opacity="0.7"/>')
            yy += step
    for rr in range(rows):
        for cc in range(cols):
            glyph(pen, pad + cc * (size + pad), pad + rr * (size * 1.25 + pad), size, size * 1.25, color, l_chance, ellipse_chance)
    parts += pen.out + ["</svg>"]
    return "\n".join(parts)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", type=int, default=3)
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--size", type=float, default=240, help="glyph width in px")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--color", default=None,
                    help="fix every glyph to shades of this colour (default: random hue per glyph)")
    ap.add_argument("--l-chance", type=float, default=0.35,
                    help="chance (0-1) a column becomes an L reaching into the next one")
    ap.add_argument("--ellipse-chance", type=float, default=0.5,
                    help="chance (0-1) a circle becomes a stretched, tilted ellipse")
    ap.add_argument("--outline", action="store_true", help="thick outlines only, no fill or streaks")
    ap.add_argument("--no-lines", action="store_true", help="skip the ruled-paper lines")
    ap.add_argument("--out", default="glyphs.svg")
    ap.add_argument("--png", help="also write a PNG (needs: pip install cairosvg)")
    a = ap.parse_args()

    svg = sheet(a.rows, a.cols, a.size, a.seed, a.color, not a.no_lines, a.l_chance, a.ellipse_chance, a.outline)
    with open(a.out, "w") as f:
        f.write(svg)
    print(f"wrote {a.out}")
    if a.png:
        import cairosvg
        cairosvg.svg2png(bytestring=svg.encode(), write_to=a.png)
        print(f"wrote {a.png}")
