#!/usr/bin/env python3
"""
cat_maze.py - random black-cat meander patterns.

Blocky black cats (sitting, lying, hanging upside down) hidden in a
thick-lined maze of right-angle meanders and spiral hooks.

Everything sits on a grid of nodes. Every free node is drawn as a black
square; joining two neighbouring nodes fills the gap between them. The
white channels are the gaps that are never joined, so they all have the
same width, which gives the hand-cut lino look. Cats are solid blocks of
nodes with a strip kept clear on one side for their ears.

Usage:
    python cat_maze.py                       # cats.svg, random seed
    python cat_maze.py -o cats.png --seed 7  # PNG (needs Pillow)
    python cat_maze.py -W 24 -H 42 --cats 16 -o wallpaper.png
    python cat_maze.py --count 5 -o cats.png # cats_1.png ... cats_5.png
    python cat_maze.py --fg "#f2f0ea" --bg "#161616"   # inverted
"""
import argparse
import math
import random
import sys

DIRS = [(1, 0), (0, 1), (-1, 0), (0, -1)]  # right, down, left, up
ORIENTS = ["up", "down", "left", "right"]  # which way the ears point


class CatMaze:
    def __init__(self, w, h, rng, thickness=0.62):
        self.w, self.h, self.rng, self.t = w, h, rng, thickness
        self.grid = {}      # (i, j) -> ("cat", k) | "X" (ear clearance)
        self.cats = []      # dicts
        self.nodes = set()  # maze nodes
        self.edges = set()  # frozenset({a, b})

    # ---------------------------------------------------------------- cats
    def place_cats(self, n):
        rng = self.rng
        tries = 0
        while len(self.cats) < n and tries < n * 200:
            tries += 1
            o = rng.choices(ORIENTS, weights=[5, 2, 2, 2])[0]
            if o in ("up", "down"):
                bw, bh = rng.choice([2, 2, 3]), rng.randint(3, 5)
            else:
                bw, bh = rng.randint(3, 5), rng.choice([2, 2, 3])
            i0 = rng.randint(0, self.w - bw)
            j0 = rng.randint(0, self.h - bh)
            body = [(i, j) for i in range(i0, i0 + bw) for j in range(j0, j0 + bh)]
            if o == "up":
                strip = [(i, j0 - 1) for i in range(i0, i0 + bw)]
            elif o == "down":
                strip = [(i, j0 + bh) for i in range(i0, i0 + bw)]
            elif o == "left":
                strip = [(i0 - 1, j) for j in range(j0, j0 + bh)]
            else:
                strip = [(i0 + bw, j) for j in range(j0, j0 + bh)]
            strip = [c for c in strip if self.inside(c)]
            if any(c in self.grid for c in body + strip):
                continue
            # keep a one-cell gap from other cats so they don't merge
            ring = {(i + dx, j + dy) for i, j in body + strip
                    for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
            if any(self.grid.get(c) not in (None,) for c in ring):
                continue
            k = len(self.cats)
            for c in body:
                self.grid[c] = ("cat", k)
            for c in strip:
                self.grid[c] = "X"
            self.cats.append(dict(
                orient=o, i0=i0, j0=j0, i1=i0 + bw - 1, j1=j0 + bh - 1,
                eyes=rng.choice(["dot", "dot", "sleepy", "lid", "almond", "side"]),
                ear_h=rng.uniform(0.62, 0.85),
                ear_b=rng.uniform(0.45, 0.6),
                eye_v=rng.uniform(0.42, 0.62),
            ))

    def inside(self, c):
        return 0 <= c[0] < self.w and 0 <= c[1] < self.h

    # ---------------------------------------------------------------- maze
    def grow_maze(self):
        rng = self.rng
        free = [(i, j) for j in range(self.h) for i in range(self.w)
                if (i, j) not in self.grid]
        unvisited = set(free)
        rng.shuffle(free)
        for start in free:
            if start not in unvisited:
                continue
            unvisited.discard(start)
            self.nodes.add(start)
            cur, d = start, rng.randrange(4)
            spin = rng.choice([1, -1])          # which way it likes to curl
            for _ in range(rng.randint(3, 30)):
                opts = []
                for nd, wt in ((d, 9), ((d + spin) % 4, 4), ((d - spin) % 4, 1)):
                    nxt = (cur[0] + DIRS[nd][0], cur[1] + DIRS[nd][1])
                    if nxt in unvisited:
                        opts.append((nd, nxt, wt))
                if not opts:
                    break
                nd, nxt, _ = rng.choices(opts, weights=[o[2] for o in opts])[0]
                self.edges.add(frozenset((cur, nxt)))
                unvisited.discard(nxt)
                self.nodes.add(nxt)
                cur, d = nxt, nd

        self._fix_fragments()
        self._add_legs()

    def _neighbours(self, c):
        for dx, dy in DIRS:
            yield (c[0] + dx, c[1] + dy)

    def _components(self):
        parent = {n: n for n in self.nodes}

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        for e in self.edges:
            a, b = tuple(e)
            if a in parent and b in parent:
                parent[find(a)] = find(b)
        comps = {}
        for n in self.nodes:
            comps.setdefault(find(n), []).append(n)
        return list(comps.values())

    def _fix_fragments(self):
        """Join tiny bits (dots, stubs) on to something next to them, and
        add the odd extra joint so walks branch into T-junctions."""
        rng = self.rng
        for comp in self._components():
            if len(comp) <= 2 or rng.random() < 0.12:
                cands = []
                for n in comp:
                    for nb in self._neighbours(n):
                        if nb in comp:
                            continue
                        if nb in self.nodes or (
                                isinstance(self.grid.get(nb), tuple)):
                            cands.append((n, nb))
                if cands:
                    self.edges.add(frozenset(rng.choice(cands)))
                elif len(comp) == 1:
                    self.nodes.discard(comp[0])     # lone dot, drop it

    def _add_legs(self):
        """Connect a few maze lines to each cat body (legs / tails)."""
        rng = self.rng
        for k, cat in enumerate(self.cats):
            touch = []
            for i in range(cat["i0"], cat["i1"] + 1):
                for j in range(cat["j0"], cat["j1"] + 1):
                    for nb in self._neighbours((i, j)):
                        if nb in self.nodes:
                            touch.append(((i, j), nb))
            rng.shuffle(touch)
            for e in touch[:rng.randint(0, 2)]:
                self.edges.add(frozenset(e))

    # ---------------------------------------------------------------- shapes
    def shapes(self):
        """Return [(colour_key, [(x, y), ...]), ...] in grid units."""
        t2 = self.t / 2
        out = []

        def sq(c):
            x, y = c[0] + 0.5, c[1] + 0.5
            return (x - t2, y - t2, x + t2, y + t2)

        def rect(b):
            x0, y0, x1, y1 = b
            return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

        degree = {}
        for e in self.edges:
            for c in e:
                degree[c] = degree.get(c, 0) + 1
        for n in self.nodes:
            if degree.get(n, 0) <= 1:
                # line end: round cap, like the tip of a tail
                out.append(("fg", circle(n[0] + 0.5, n[1] + 0.5, t2, t2, 32)))
            else:
                out.append(("fg", rect(sq(n))))
        for e in self.edges:
            a, b = tuple(e)
            ax, ay, bx, by = a[0] + 0.5, a[1] + 0.5, b[0] + 0.5, b[1] + 0.5
            px = t2 if ax == bx else 0     # widen across the line only
            py = t2 if ay == by else 0
            out.append(("fg", rect((min(ax, bx) - px, min(ay, by) - py,
                                    max(ax, bx) + px, max(ay, by) + py))))
        for cat in self.cats:
            out.extend(self._cat_shapes(cat, sq))
        return out

    def _cat_shapes(self, cat, sq):
        x0, y0 = sq((cat["i0"], cat["j0"]))[:2]
        x1, y1 = sq((cat["i1"], cat["j1"]))[2:]
        o = cat["orient"]
        # local frame: u runs across the head, v runs from the ear end
        # into the body (negative v = outwards, where the ears go)
        if o == "up":
            A, f = x1 - x0, lambda u, v: (x0 + u, y0 + v)
        elif o == "down":
            A, f = x1 - x0, lambda u, v: (x1 - u, y1 - v)
        elif o == "left":
            A, f = y1 - y0, lambda u, v: (x0 + v, y1 - u)
        else:
            A, f = y1 - y0, lambda u, v: (x1 - v, y0 + u)

        def poly(pts):
            return [f(u, v) for u, v in pts]

        res = [("fg", [(x0, y0), (x1, y0), (x1, y1), (x0, y1)])]

        eb = min(cat["ear_b"], A / 2 - 0.15)
        eh = cat["ear_h"]
        res.append(("fg", poly([(0, 0.05), (eb, 0.05), (eb * 0.2, -eh)])))
        res.append(("fg", poly([(A, 0.05), (A - eb, 0.05), (A - eb * 0.2, -eh)])))

        ex = min(0.3, A * 0.19)
        ev = cat["eye_v"]
        for side in (-1, 1):
            cu = A / 2 + side * ex
            style = cat["eyes"]
            if style in ("dot", "side"):
                du = 0.1 if style == "side" else 0
                res.append(("bg", poly(circle(cu + du, ev, 0.1, 0.1))))
            elif style == "sleepy":    # flat top, round bottom
                res.append(("bg", poly(arc(cu, ev - 0.04, 0.13, 0, math.pi))))
            elif style == "lid":       # flat bottom, round top
                res.append(("bg", poly(arc(cu, ev + 0.04, 0.13, math.pi, 2 * math.pi))))
            elif style == "almond":
                res.append(("bg", poly(lens(cu, ev, 0.15, 0.085))))
                res.append(("fg", poly(circle(cu, ev, 0.03, 0.07))))
        return res


def circle(cx, cy, rx, ry, n=18):
    return [(cx + rx * math.cos(2 * math.pi * k / n),
             cy + ry * math.sin(2 * math.pi * k / n)) for k in range(n)]


def arc(cx, cy, r, a0, a1, n=14):
    return [(cx + r * math.cos(a0 + (a1 - a0) * k / n),
             cy + r * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]


def lens(cx, cy, hw, hh, n=10):
    top = [(cx - hw + 2 * hw * k / n, cy - hh * math.sin(math.pi * k / n)) for k in range(n + 1)]
    bot = [(cx + hw - 2 * hw * k / n, cy + hh * math.sin(math.pi * k / n)) for k in range(1, n)]
    return top + bot


# -------------------------------------------------------------------- output
def to_svg(pattern, scale, fg, bg):
    W, H = pattern.w * scale, pattern.h * scale
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
             f'viewBox="0 0 {W} {H}">',
             f'<rect width="100%" height="100%" fill="{bg}"/>']
    cols = {"fg": fg, "bg": bg}
    for key, pts in pattern.shapes():
        p = " ".join(f"{x * scale:.2f},{y * scale:.2f}" for x, y in pts)
        lines.append(f'<polygon points="{p}" fill="{cols[key]}"/>')
    lines.append("</svg>")
    return "\n".join(lines)


def to_png(pattern, scale, fg, bg, path, ss=3):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        sys.exit("PNG output needs Pillow:  pip install pillow  (or use .svg)")
    s = scale * ss
    img = Image.new("RGB", (pattern.w * s, pattern.h * s), bg)
    d = ImageDraw.Draw(img)
    cols = {"fg": fg, "bg": bg}
    for key, pts in pattern.shapes():
        d.polygon([(x * s, y * s) for x, y in pts], fill=cols[key])
    img = img.resize((pattern.w * scale, pattern.h * scale), Image.LANCZOS)
    img.save(path)


def main():
    ap = argparse.ArgumentParser(description="Random black-cat meander pattern")
    ap.add_argument("-W", "--width", type=int, default=20, help="grid columns (default 20)")
    ap.add_argument("-H", "--height", type=int, default=36, help="grid rows (default 36)")
    ap.add_argument("--cats", type=int, default=None, help="number of cats (default: by area)")
    ap.add_argument("--scale", type=int, default=40, help="pixels per grid cell (default 40)")
    ap.add_argument("--thickness", type=float, default=0.62,
                    help="line thickness as a fraction of a cell (default 0.62)")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--fg", default="#1a1a1a")
    ap.add_argument("--bg", default="#f2f0ea")
    ap.add_argument("--count", type=int, default=1, help="how many images to make")
    ap.add_argument("-o", "--out", default="cats.svg", help="output .svg or .png")
    a = ap.parse_args()

    base_seed = a.seed if a.seed is not None else random.randrange(1 << 30)
    ncats = a.cats if a.cats is not None else max(1, a.width * a.height // 55)

    for n in range(a.count):
        seed = base_seed + n
        rng = random.Random(seed)
        p = CatMaze(a.width, a.height, rng, a.thickness)
        p.place_cats(ncats)
        p.grow_maze()

        out = a.out
        if a.count > 1:
            stem, dot, ext = out.rpartition(".")
            out = f"{stem}_{n + 1}.{ext}" if dot else f"{out}_{n + 1}"
        if out.lower().endswith(".png"):
            to_png(p, a.scale, a.fg, a.bg, out)
        else:
            with open(out, "w") as fh:
                fh.write(to_svg(p, a.scale, a.fg, a.bg))
        print(f"{out}  (seed {seed}, {len(p.cats)} cats)")


if __name__ == "__main__":
    main()
