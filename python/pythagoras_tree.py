#!/usr/bin/env python3
"""Seeded Pythagoras trees (squares + right triangles) in the koch_riff style.

usage:
  pythagoras_tree.py [seed ...]                 one PNG per seed
  pythagoras_tree.py --gif [seed ...]           one growth GIF per seed
  pythagoras_tree.py --sheet [seed ...]         3x3 contact sheet (sheet_tree_<seeds>.png)
  pythagoras_tree.py --sheet --gif [seed ...]   animated contact sheet (sheet_tree_<seeds>.gif)

  --size WxH|N   output image size in pixels (default 1080x1080); for --sheet
                 this is the whole sheet, split evenly between tiles
"""
import sys, math, random, hashlib
from PIL import Image, ImageDraw

SIZE = (1080, 1080)   # default output size
SCALE = 3             # single images are drawn at 1/SCALE and upscaled (nearest)
BG = (0, 0, 0)

# (trunk colour, leaf colour) - lines fade from one to the other by depth
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
    """Return list of (depth, polygon) plus metadata."""
    rng = random.Random(seed)
    base_angle = rng.uniform(25, 65)          # 45 = the classic symmetric tree
    jitter = rng.choice([0, 0, 4, 8, 14])     # per-node angle wobble (degrees)
    lean = rng.choice([0, 0, 1.5, -1.5, 3])   # drift in angle with depth (wind)
    depth = rng.choice([8, 9, 10, 10, 11])
    draw_tri = rng.random() < 0.6
    shapes = []

    def grow(p0, p1, d):
        vx, vy = p1[0] - p0[0], p1[1] - p0[1]
        nx, ny = -vy, vx                                  # left normal (up)
        p2, p3 = (p1[0] + nx, p1[1] + ny), (p0[0] + nx, p0[1] + ny)
        shapes.append((d, [p0, p1, p2, p3]))
        if d == depth:
            return
        a = math.radians(base_angle + lean * d + rng.uniform(-jitter, jitter))
        a = min(max(a, math.radians(10)), math.radians(80))
        L = math.cos(a)
        c, s = math.cos(a), math.sin(a)
        apex = (p3[0] + L * (vx * c - vy * s), p3[1] + L * (vx * s + vy * c))
        if draw_tri:
            shapes.append((d + 0.5, [p3, apex, p2]))
        grow(p3, apex, d + 1)
        grow(apex, p2, d + 1)

    grow((-0.5, 0.0), (0.5, 0.0), 0)
    meta = dict(seed=seed, angle=round(base_angle, 1), jitter=jitter, lean=lean,
                depth=depth, triangles=draw_tri,
                palette=rng.randrange(len(PALETTES)))
    return shapes, meta


def lerp(c0, c1, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c0, c1))


def frame(shapes, meta, w, h, upto=None, label=True):
    """w x h native-res image showing shapes with depth <= upto (scaled to full tree)."""
    xs = [x for _, poly in shapes for x, _ in poly]
    ys = [y for _, poly in shapes for _, y in poly]
    cx = (max(xs) + min(xs)) / 2
    k = min((w * 0.86) / (max(xs) - min(xs)), (h * 0.82) / (max(ys) - min(ys)))
    base_y = h * 0.06 + (h * 0.82 - (max(ys) - min(ys)) * k) / 2 + (max(ys) - min(ys)) * k
    trunk, leaf = PALETTES[meta["palette"]]
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    upto = meta["depth"] if upto is None else upto
    for depth, poly in shapes:
        if depth > upto:
            continue
        col = lerp(trunk, leaf, depth / meta["depth"])
        xy = [(w / 2 + (x - cx) * k, base_y - (y - min(ys)) * k) for x, y in poly]
        d.line(xy + [xy[0]], fill=col, width=1)
    if label:
        d.text((6, h - 14), f"tree #{meta['seed']} a={meta['angle']} d={min(int(upto), meta['depth'])}",
               fill=leaf)
    return img


def scaled(shapes, meta, size, upto=None):
    """Frame drawn at 1/SCALE of size, upscaled nearest-neighbour to size."""
    w, h = max(1, round(size[0] / SCALE)), max(1, round(size[1] / SCALE))
    return frame(shapes, meta, w, h, upto).resize(size, Image.NEAREST)


def sheet_frame(built, t, size, cols=3):
    """Tiles are drawn at full resolution (no upscale), size // grid each."""
    rows = math.ceil(len(built) / cols)
    tw, th = max(1, size[0] // cols), max(1, size[1] // rows)
    sheet = Image.new("RGB", size, BG)
    for i, (shapes, m) in enumerate(built):
        sheet.paste(frame(shapes, m, tw, th, t), ((i % cols) * tw, (i // cols) * th))
    return sheet


def save_gif(frames, maxd, path):
    durations = [500] * maxd + [3000]
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=durations, loop=0)


def parse_size(s):
    try:
        w, _, h = s.lower().partition("x")
        w, h = int(w), int(h or w)
        if w > 0 and h > 0:
            return w, h
    except ValueError:
        pass
    sys.exit(f"pythagoras_tree.py: bad --size {s!r} (want WxH or N, e.g. 1080x1080)")


def main():
    args, size, gif, sheet = [], SIZE, False, False
    it = iter(sys.argv[1:])
    for a in it:
        if a == "--gif":
            gif = True
        elif a == "--sheet":
            sheet = True
        elif a == "--size":
            size = parse_size(next(it, ""))
        elif a.startswith("--size="):
            size = parse_size(a.split("=", 1)[1])
        else:
            args.append(a)
    n = 9 if sheet else 1
    seeds = [seed_from(a) for a in args] or [random.randrange(2**31) for _ in range(n)]

    if sheet:
        built = [build(s) for s in seeds]
        maxd = max(m["depth"] for _, m in built)
        tag = "-".join(map(str, seeds))
        if gif:
            frames = [sheet_frame(built, t, size) for t in range(maxd + 1)]
            save_gif(frames, maxd, f"sheet_tree_{tag}.gif")
        else:
            sheet_frame(built, maxd, size).save(f"sheet_tree_{tag}.png")
        for _, m in built:
            print(m)
        return

    for s in seeds:
        shapes, m = build(s)
        if gif:
            frames = [scaled(shapes, m, size, t) for t in range(m["depth"] + 1)]
            save_gif(frames, m["depth"], f"tree_{s}.gif")
        else:
            scaled(shapes, m, size).save(f"tree_{s}.png")
        print(m)


if __name__ == "__main__":
    main()
