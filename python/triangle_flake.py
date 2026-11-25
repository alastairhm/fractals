#!/usr/bin/env python3
"""Seeded triangle flakes: a triangle sprouts a smaller triangle from the
midpoint of each side, and each new triangle does the same on its two outer
sides. Same retro style as koch_riff.py / pythagoras_tree.py.

usage:
  triangle_flake.py [seed ...]            one PNG per seed
  triangle_flake.py --gif [seed ...]      one growth GIF per seed
  triangle_flake.py --sheet [seed ...]    animated 3x3 sheet (sheet_flake.gif + .png)
"""
import sys, math, random, hashlib
from PIL import Image, ImageDraw

W = H = 360
SCALE = 3
BG = (0, 0, 0)

# (core colour, tip colour) - lines fade from one to the other by depth
PALETTES = [
    ((120, 90, 60), (150, 160, 120)),   # bark -> sage
    ((60, 80, 140), (120, 200, 255)),   # ice
    ((140, 70, 0), (255, 176, 0)),      # amber CRT
    ((20, 110, 50), (80, 255, 120)),    # green phosphor
    ((110, 40, 120), (255, 110, 200)),  # synthwave
    ((110, 110, 110), (235, 228, 210)), # chalk
]


def seed_from(s):
    try:
        return int(s)
    except ValueError:
        return int(hashlib.sha256(s.encode()).hexdigest()[:8], 16)


def build(seed):
    """Return list of (depth, triangle) plus metadata."""
    rng = random.Random(seed)
    ratio = rng.uniform(0.33, 0.55)        # child side / parent side
    peak = rng.choice([60, 60, 60, rng.uniform(35, 80)])   # child apex height angle
    twist = rng.choice([0, 0, 0, rng.uniform(-0.25, 0.25)])  # slide child along edge
    jitter = rng.choice([0, 0, 0.05, 0.12])  # random wobble in ratio per child
    depth = rng.choice([4, 5, 5, 6, 6, 7])
    sides = rng.choice([3, 3, 3, 3, 4, 5, 6])
    shapes = []

    def grow(p, q, d):
        """Sprout a triangle on the outer (right-hand) side of edge p->q."""
        if d > depth:
            return
        dx, dy = q[0] - p[0], q[1] - p[1]
        L = math.hypot(dx, dy)
        ux, uy = dx / L, dy / L
        nx, ny = uy, -ux                                  # outward normal
        r = max(0.15, ratio + rng.uniform(-jitter, jitter))
        s = r * L
        mx = p[0] + dx * (0.5 + twist * (1 - r))
        my = p[1] + dy * (0.5 + twist * (1 - r))
        b0 = (mx - ux * s / 2, my - uy * s / 2)
        b1 = (mx + ux * s / 2, my + uy * s / 2)
        h = (s / 2) * math.tan(math.radians(peak))
        apex = (mx + nx * h, my + ny * h)
        shapes.append((d, [b0, apex, b1]))
        grow(b0, apex, d + 1)
        grow(apex, b1, d + 1)

    start = math.pi / 2
    core = [(math.cos(start + 2 * math.pi * i / sides),
             math.sin(start + 2 * math.pi * i / sides)) for i in range(sides)]
    shapes.append((0, core))
    for i in range(sides):
        grow(core[i], core[(i + 1) % sides], 1)

    meta = dict(seed=seed, sides=sides, ratio=round(ratio, 2), peak=round(peak),
                twist=round(twist, 2), jitter=jitter, depth=depth,
                palette=rng.randrange(len(PALETTES)))
    return shapes, meta


def lerp(c0, c1, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c0, c1))


def frame(shapes, meta, upto=None, label=True):
    xs = [x for _, poly in shapes for x, _ in poly]
    ys = [y for _, poly in shapes for _, y in poly]
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    k = (W * 0.84) / max(max(xs) - min(xs), max(ys) - min(ys))
    core, tip = PALETTES[meta["palette"]]
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    upto = meta["depth"] if upto is None else upto
    for depth, poly in shapes:
        if depth > upto:
            continue
        col = lerp(core, tip, depth / meta["depth"])
        xy = [(W / 2 + (x - cx) * k, H / 2 - (y - cy) * k) for x, y in poly]
        d.line(xy + [xy[0]], fill=col, width=1)
    if label:
        d.text((6, H - 14),
               f"flake #{meta['seed']} r={meta['ratio']} d={min(upto, meta['depth'])}", fill=tip)
    return img


def up(img, s=SCALE):
    return img.resize((img.width * s, img.height * s), Image.NEAREST)


def save_gif(frames, maxd, path):
    durations = [600] * maxd + [3000]
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=durations, loop=0)


def main():
    args = sys.argv[1:]
    mode = "png"
    for flag in ("--gif", "--sheet"):
        if flag in args:
            mode = flag[2:]
            args.remove(flag)
    n = 9 if mode == "sheet" else 1
    seeds = [seed_from(a) for a in args] or [random.randrange(2**31) for _ in range(n)]

    if mode == "sheet":
        built = [build(s) for s in seeds]
        maxd = max(m["depth"] for _, m in built)
        cols, rows = 3, math.ceil(len(built) / 3)
        frames = []
        for t in range(maxd + 1):
            sheet = Image.new("RGB", (cols * W, rows * H), BG)
            for i, (shapes, m) in enumerate(built):
                sheet.paste(frame(shapes, m, t), ((i % cols) * W, (i // cols) * H))
            frames.append(sheet)
        frames[-1].save("sheet_flake.png")
        save_gif(frames, maxd, "sheet_flake.gif")
        for _, m in built:
            print(m)
        return

    for s in seeds:
        shapes, m = build(s)
        if mode == "gif":
            frames = [up(frame(shapes, m, t), 2) for t in range(m["depth"] + 1)]
            save_gif(frames, m["depth"], f"flake_{s}.gif")
        else:
            up(frame(shapes, m)).save(f"flake_{s}.png")
        print(m)


if __name__ == "__main__":
    main()
