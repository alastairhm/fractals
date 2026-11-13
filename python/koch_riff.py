#!/usr/bin/env python3
"""Seeded Koch-curve riffs in a low-res, thin-line retro style.

usage: koch_riff.py [--sheet] [--gif] [--size WxH|N] [seed ...]
       (seeds can be ints or any text)

  --gif         animate the curve growing depth by depth (.gif instead of .png)
  --sheet       3-column contact sheet of all seeds (9 random if none given),
                saved as sheet_<seed>-<seed>-....png/.gif
  --size WxH    output image size in pixels, or N for NxN (default 1080x1080);
                for --sheet this is the whole sheet, split evenly between tiles
"""
import sys, math, random, hashlib
from PIL import Image, ImageDraw

SIZE = (1080, 1080)   # default output size
SCALE = 3             # single images are drawn at 1/SCALE and upscaled (nearest)

PALETTES = [
    ((0, 0, 0), (150, 160, 120)),   # sage
    ((0, 0, 0), (120, 200, 255)),   # ice
    ((0, 0, 0), (255, 176, 0)),     # amber CRT
    ((0, 0, 0), (80, 255, 120)),    # green phosphor
    ((0, 0, 0), (255, 110, 200)),   # synthwave pink
    ((0, 0, 0), (235, 228, 210)),   # chalk
]


def seed_from(s):
    try:
        return int(s)
    except ValueError:
        return int(hashlib.sha256(s.encode()).hexdigest()[:8], 16)


def rot(vx, vy, a):
    c, s = math.cos(a), math.sin(a)
    return vx * c - vy * s, vx * s + vy * c


def subdivide(p, q, rule, rng):
    """Replace segment p->q by a generator, flipping in/out at random."""
    (x0, y0), (x1, y1) = p, q
    dx, dy = x1 - x0, y1 - y0
    sign = rng.choice((-1, 1)) if rule["flip"] > rng.random() else 1
    pts = []
    for gx, gy in rule["gen"]:
        gy *= sign
        pts.append((x0 + gx * dx - gy * dy, y0 + gx * dy + gy * dx))
    return pts


def koch_generator(angle):
    """Classic 4-segment bump with adjustable peak angle (Cesàro style)."""
    a = math.radians(angle)
    # side pieces of length t, peak sides of length t too
    t = 1 / (2 + 2 * math.cos(a))
    peak = (0.5, t * math.sin(a))
    return [(0, 0), (t, 0), peak, (1 - t, 0)]


def quad_generator():
    return [(0, 0), (1/3, 0), (1/3, 1/3), (2/3, 1/3), (2/3, 0)]


def build(seed):
    rng = random.Random(seed)
    sides = rng.choice([3, 3, 3, 4, 5, 6, 8])
    style = rng.choice(["koch", "koch", "cesaro", "quad"])
    if style == "koch":
        gen, depth = koch_generator(60), rng.choice([3, 4, 4, 5])
    elif style == "cesaro":
        ang = rng.uniform(70, 86)
        gen, depth = koch_generator(ang), rng.choice([4, 5])
    else:
        gen, depth = quad_generator(), rng.choice([3, 3, 4])
    rule = {"gen": gen, "flip": rng.choice([0.0, 0.25, 0.5, 0.5, 1.0])}
    outward = rng.random() < 0.8

    r = 1.0
    start = rng.uniform(0, 2 * math.pi)
    poly = [(r * math.cos(start + 2 * math.pi * i / sides),
             r * math.sin(start + 2 * math.pi * i / sides)) for i in range(sides)]
    if outward:
        poly.reverse()

    pts = poly
    stages = [poly]
    for _ in range(depth):
        nxt = []
        for i in range(len(pts)):
            nxt += subdivide(pts[i], pts[(i + 1) % len(pts)], rule, rng)
        pts = nxt
        stages.append(pts)

    meta = dict(seed=seed, sides=sides, style=style, depth=depth,
                flip=rule["flip"], outward=outward,
                palette=rng.randrange(len(PALETTES)), stages=stages)
    return pts, meta


def frame(seed, meta, pts, d, w, h, label):
    """Draw stage d of a seed into a w x h native-res image, framed so the
    final (deepest) shape fills ~72% of the shorter side."""
    bg, fg = PALETTES[meta["palette"]]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    k = (min(w, h) * 0.72) / max(max(xs) - min(xs), max(ys) - min(ys))
    stage = meta["stages"][min(d, meta["depth"])]
    xy = [(w / 2 + (x - cx) * k, h / 2 - (y - cy) * k) for x, y in stage]
    img = Image.new("RGB", (w, h), bg)
    dr = ImageDraw.Draw(img)
    dr.line(xy + [xy[0]], fill=fg, width=1)
    dr.text((6, h - 14), label, fill=fg)
    return img


def native(size):
    """Native drawing resolution for an output size."""
    return max(1, round(size[0] / SCALE)), max(1, round(size[1] / SCALE))


def render(seed, path, size=SIZE):
    pts, meta = build(seed)
    label = f"koch #{seed}  {meta['style']} n={meta['sides']} d={meta['depth']} flip={meta['flip']}"
    img = frame(seed, meta, pts, meta["depth"], *native(size), label)
    img.resize(size, Image.NEAREST).save(path)
    return meta


def animate(seed, path, size=SIZE):
    """GIF: grow the curve one depth at a time, then pause on the final shape."""
    pts, meta = build(seed)
    frames, durations = [], []
    for d in range(meta["depth"] + 1):
        img = frame(seed, meta, pts, d, *native(size),
                    f"koch #{seed}  depth {d}/{meta['depth']}")
        frames.append(img.resize(size, Image.NEAREST))
        durations.append(700 if d < meta["depth"] else 2500)
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=durations, loop=0)
    return meta


def _sheet_frame(built, d, cols, size):
    """Tiles are drawn at full resolution (no upscale), size // grid each."""
    rows = math.ceil(len(built) / cols)
    tw, th = max(1, size[0] // cols), max(1, size[1] // rows)
    sheet = Image.new("RGB", size, (0, 0, 0))
    for i, (sd, m, pts) in enumerate(built):
        t = frame(sd, m, pts, d, tw, th, f"#{sd} {m['style']} d={min(d, m['depth'])}")
        sheet.paste(t, ((i % cols) * tw, (i // cols) * th))
    return sheet


def render_sheet(seeds, path, cols=3, size=SIZE):
    """Static contact sheet: every seed at its final depth."""
    built = [(sd, *build(sd)[::-1]) for sd in seeds]   # (seed, meta, pts)
    maxd = max(m["depth"] for _, m, _ in built)
    _sheet_frame(built, maxd, cols, size).save(path)


def animate_sheet(seeds, path, cols=3, size=SIZE):
    """Animated contact sheet: every tile grows in step, then all hold."""
    built = [(sd, *build(sd)[::-1]) for sd in seeds]   # (seed, meta, pts)
    maxd = max(m["depth"] for _, m, _ in built)
    frames = [_sheet_frame(built, d, cols, size) for d in range(maxd + 1)]
    durations = [700] * maxd + [3000]
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
    sys.exit(f"koch_riff.py: bad --size {s!r} (want WxH or N, e.g. 1080x1080)")


if __name__ == "__main__":
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
    if sheet:
        seeds = [seed_from(a) for a in args] or \
                [random.randrange(2**31) for _ in range(9)]
        tag = "-".join(map(str, seeds))
        if gif:
            animate_sheet(seeds, f"sheet_{tag}.gif", size=size)
        else:
            render_sheet(seeds, f"sheet_{tag}.png", size=size)
        sys.exit()
    for s in args or [str(random.randrange(2**31))]:
        sd = seed_from(s)
        if gif:
            m = animate(sd, f"koch_{sd}.gif", size)
        else:
            m = render(sd, f"koch_{sd}.png", size)
        m.pop("stages")
        print(m)
