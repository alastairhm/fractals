#!/usr/bin/env python3
"""Seeded strange attractors (Clifford / de Jong) as glowing density plots,
in the same retro style as koch_riff.py and pythagoras_tree.py.

  Clifford:  x' = sin(a*y) + c*cos(a*x)      y' = sin(b*x) + d*cos(b*y)
  de Jong:   x' = sin(a*y) - cos(b*x)        y' = sin(c*x) - cos(d*y)

usage:
  attractor.py [seed ...]            one PNG per seed
  attractor.py --gif [seed ...]      one GIF per seed, points piling up
  attractor.py --sheet [seed ...]    3x3 contact sheet, animated and still
                                     (sheet_attractor_<seeds>.gif + .png)

  --size WxH|N   output image size in pixels (default 1080x1080); for --sheet
                 this is the whole sheet, split evenly between tiles
"""
import sys, math, random, hashlib
import numpy as np
from PIL import Image, ImageDraw

SIZE = (1080, 1080)    # default output size
SCALE = 3              # single images are drawn at 1/SCALE and upscaled (nearest)
WALKERS = 20000        # independent points iterated in parallel
STEPS = 300            # iterations per walker  (=> 6M points)
WARMUP = 20

# (mid colour, hot colour): density ramps black -> mid -> hot
PALETTES = [
    ((90, 100, 70), (225, 235, 190)),   # sage
    ((30, 70, 160), (170, 225, 255)),   # ice
    ((150, 60, 0), (255, 215, 120)),    # amber CRT
    ((10, 120, 50), (170, 255, 190)),   # green phosphor
    ((120, 20, 110), (255, 170, 230)),  # synthwave
    ((100, 100, 100), (250, 246, 235)), # chalk
]


def seed_from(s):
    try:
        return int(s)
    except ValueError:
        return int(hashlib.sha256(s.encode()).hexdigest()[:8], 16)


def step(kind, x, y, a, b, c, d):
    if kind == "clifford":
        return np.sin(a * y) + c * np.cos(a * x), np.sin(b * x) + d * np.cos(b * y)
    return np.sin(a * y) - np.cos(b * x), np.sin(c * x) - np.cos(d * y)


def params(rng):
    kind = rng.choice(["clifford", "dejong"])
    if kind == "clifford":
        a, b = rng.uniform(-2.5, 2.5), rng.uniform(-2.5, 2.5)
        c, d = rng.uniform(-1.5, 1.5), rng.uniform(-1.5, 1.5)
    else:
        a, b, c, d = (rng.uniform(-3, 3) for _ in range(4))
    return kind, a, b, c, d


def coverage(kind, p, rng_np):
    """Fraction of a coarse grid touched: rejects seeds that collapse to dots."""
    x, y = rng_np.uniform(-1, 1, 2000), rng_np.uniform(-1, 1, 2000)
    for _ in range(WARMUP):
        x, y = step(kind, x, y, *p)
    xs, ys = [], []
    for _ in range(60):
        x, y = step(kind, x, y, *p)
        xs.append(x); ys.append(y)
    xs, ys = np.concatenate(xs), np.concatenate(ys)
    if not np.all(np.isfinite(xs)) or np.ptp(xs) < 1e-3 or np.ptp(ys) < 1e-3:
        return 0.0
    h, _, _ = np.histogram2d(xs, ys, bins=40)
    return (h > 0).mean()


def build(seed, nx, ny):
    """Pick parameters (re-rolling dull ones), return nx x ny histogram snapshots."""
    rng = random.Random(seed)
    rng_np = np.random.default_rng(seed)
    for tries in range(200):
        kind, *p = params(rng)
        if coverage(kind, p, rng_np) > 0.18:
            break
    x, y = rng_np.uniform(-1, 1, WALKERS), rng_np.uniform(-1, 1, WALKERS)
    for _ in range(WARMUP):
        x, y = step(kind, x, y, *p)

    # first pass on a sample to fix the bounds
    sx, sy = x[:2000].copy(), y[:2000].copy()
    bx, by = [], []
    for _ in range(80):
        sx, sy = step(kind, sx, sy, *p)
        bx.append(sx); by.append(sy)
    bx, by = np.concatenate(bx), np.concatenate(by)
    x0, x1 = np.percentile(bx, [0.1, 99.9])
    y0, y1 = np.percentile(by, [0.1, 99.9])
    span = max(x1 - x0, y1 - y0) * 1.12
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    # widen the longer axis so pixels stay square on non-square images
    sx, sy = span * max(1, nx / ny), span * max(1, ny / nx)
    rng_range = [[cx - sx / 2, cx + sx / 2], [cy - sy / 2, cy + sy / 2]]

    hist = np.zeros((nx, ny))
    snaps = []
    snap_at = set(int(STEPS * f) for f in (0.004, 0.012, 0.03, 0.07, 0.15, 0.3, 0.55, 1.0))
    for i in range(1, STEPS + 1):
        x, y = step(kind, x, y, *p)
        h, _, _ = np.histogram2d(x, y, bins=[nx, ny], range=rng_range)
        hist += h
        if i in snap_at:
            snaps.append(hist.copy())

    meta = dict(seed=seed, kind=kind, a=round(p[0], 3), b=round(p[1], 3),
                c=round(p[2], 3), d=round(p[3], 3), rerolls=tries,
                palette=rng.randrange(len(PALETTES)))
    return snaps, meta


def robust_norm(hist):
    """Log-scale ceiling from the 99.7th percentile, so hot spots don't dim the rest."""
    nz = hist[hist > 0]
    return np.log1p(np.percentile(nz, 99.7)) if nz.size else 1.0


def colourise(hist, meta, norm=None, label=True):
    mid, hot = (np.array(c, float) for c in PALETTES[meta["palette"]])
    norm = norm if norm is not None else robust_norm(hist)
    t = np.clip(np.log1p(hist) / norm, 0, 1).T[::-1]     # rows = y, flip up
    t = t ** 0.8
    lo = np.clip(t * 2, 0, 1)[..., None]
    hi = np.clip(t * 2 - 1, 0, 1)[..., None]
    rgb = lo * mid + hi * (hot - mid)
    img = Image.fromarray(rgb.clip(0, 255).astype(np.uint8), "RGB")
    if label:
        ImageDraw.Draw(img).text(
            (6, img.height - 14),
            f"{meta['kind']} #{meta['seed']}  {meta['a']} {meta['b']} {meta['c']} {meta['d']}",
            fill=tuple(int(v) for v in hot))
    return img


def frames_for(snaps, meta):
    norm = robust_norm(snaps[-1])      # fixed scale so it brightens as it fills
    return [colourise(s, meta, norm) for s in snaps]


def native(size):
    """Native drawing resolution for an output size."""
    return max(1, round(size[0] / SCALE)), max(1, round(size[1] / SCALE))


def save_gif(frames, path):
    durations = [450] * (len(frames) - 1) + [3000]
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
    sys.exit(f"attractor.py: bad --size {s!r} (want WxH or N, e.g. 1080x1080)")


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
        # tiles are drawn at full resolution (no upscale), size // grid each
        cols, rows = 3, math.ceil(len(seeds) / 3)
        tw, th = max(1, size[0] // cols), max(1, size[1] // rows)
        built = [build(s, tw, th) for s in seeds]
        tiles = [frames_for(sn, m) for sn, m in built]
        frames = []
        for f in range(len(tiles[0])):
            sheet_img = Image.new("RGB", size)
            for i, t in enumerate(tiles):
                sheet_img.paste(t[f], ((i % cols) * tw, (i // cols) * th))
            frames.append(sheet_img)
        tag = "-".join(map(str, seeds))
        frames[-1].save(f"sheet_attractor_{tag}.png")
        save_gif(frames, f"sheet_attractor_{tag}.gif")
        for _, m in built:
            print(m)
        return

    for s in seeds:
        snaps, m = build(s, *native(size))
        if gif:
            save_gif([f.resize(size, Image.NEAREST) for f in frames_for(snaps, m)],
                     f"attractor_{s}.gif")
        else:
            colourise(snaps[-1], m).resize(size, Image.NEAREST).save(f"attractor_{s}.png")
        print(m)


if __name__ == "__main__":
    main()
