"""Pixel-resolve Mandelbrot: an 8-bit style animation that starts as one
giant pixel and splits into 4, 16, 64 ... until it reaches full 1024x1024.

Each level's blocks are the true average of the detail underneath them,
snapped to a 16-colour retro palette, so every stage is an honest
low-res picture of the set (not just a centre sample). New levels are
drawn over the old one block by block in raster order, like a BBC Micro
filling the screen, then held for a beat.

Examples
  python3 pixel_resolve.py                          # full set -> pixel_resolve.mp4
  python3 pixel_resolve.py --cx -0.7436 --cy 0.1318 --mag 60 -o seahorse.mp4
  python3 pixel_resolve.py --no-hud --hold 20 --fps 25
  python3 pixel_resolve.py --shape circle -o pixel_resolve_circles.mp4
  python3 pixel_resolve.py --mode quadtree -o pixel_resolve_quadtree.mp4
  python3 pixel_resolve.py --order random -o pixel_resolve_dissolve.mp4
  python3 pixel_resolve.py --order spiral -o pixel_resolve_spiral.mp4

--mode quadtree only splits blocks that still hide detail (pixels of more
than one palette colour), so flat areas stay as big outlined blocks and
the boundary shatters into fine pixels. --order random reveals each
level's blocks in shuffled order - the classic pixel-dissolve wipe.

Needs numpy, numba, Pillow and ffmpeg on the PATH.
"""
import argparse
import subprocess

import numpy as np
from numba import njit, prange
from PIL import Image, ImageDraw, ImageFont

SIZE = 1024          # final resolution; must be a power of two
LEVELS = 11          # 1x1, 2x2, ... 1024x1024

# 16-colour ramp: interior black, then deep blue -> purple -> red -> gold -> white
PALETTE = np.array([
    (0, 0, 0), (17, 12, 46), (30, 24, 92), (43, 45, 140),
    (60, 70, 180), (95, 60, 190), (140, 50, 170), (185, 45, 130),
    (220, 60, 90), (240, 95, 60), (250, 135, 40), (252, 175, 35),
    (253, 210, 70), (255, 235, 130), (255, 248, 200), (255, 255, 255),
], dtype=np.uint8)


# ---------------------------------------------------------------- fractal
@njit(parallel=True, fastmath=True)
def mandel(size, cx, cy, span, max_iter):
    """Smooth iteration count per pixel; -1 for points inside the set."""
    out = np.empty((size, size), dtype=np.float64)
    step = span / size
    for j in prange(size):
        y0 = cy + (size / 2 - j - 0.5) * step
        for i in range(size):
            x0 = cx + (i - size / 2 + 0.5) * step
            # skip main cardioid and period-2 bulb
            q = (x0 - 0.25) ** 2 + y0 * y0
            if q * (q + (x0 - 0.25)) <= 0.25 * y0 * y0 or (x0 + 1) ** 2 + y0 * y0 <= 0.0625:
                out[j, i] = -1.0
                continue
            x = y = 0.0
            n = 0
            while n < max_iter and x * x + y * y <= 256.0:
                x, y = x * x - y * y + x0, 2 * x * y + y0
                n += 1
            if n == max_iter:
                out[j, i] = -1.0
            else:
                out[j, i] = n + 1 - np.log(np.log(np.sqrt(x * x + y * y))) / np.log(2.0)
    return out


def brightness(it):
    """0..1 per pixel: 0 inside the set, log-scaled escape speed outside."""
    v = np.zeros_like(it)
    out = it >= 0
    s = np.log1p(it[out])
    lo, hi = np.percentile(s, 1), np.percentile(s, 99.5)
    v[out] = 0.08 + 0.92 * np.clip((s - lo) / (hi - lo + 1e-9), 0, 1)
    return v


# ---------------------------------------------------------------- levels
def level_image(v, level):
    """Average v over (SIZE/res)^2 blocks, snap to palette, upscale."""
    res = 1 << level
    b = SIZE // res
    avg = v.reshape(res, b, res, b).mean(axis=(1, 3))
    idx = np.rint(avg * (len(PALETTE) - 1)).astype(np.intp)
    small = PALETTE[idx]                                  # res x res x 3
    return small, b


def circle_mask(b, res):
    """Hard-edged disc per block (pixel centres inside radius), tiled res x res."""
    c = (np.arange(b) + 0.5 - b / 2) ** 2
    disc = (c[:, None] + c[None, :]) <= (b / 2) ** 2
    return np.tile(disc, (res, res))[..., None]


def spiral_order(res):
    """Flat block indices in a clockwise spiral from the outer edge inwards."""
    parts = []
    for k in range((res + 1) // 2):
        lo, hi = k, res - 1 - k
        if lo == hi:
            parts.append([lo * res + lo])
            break
        r = np.arange(lo, hi)
        parts += [lo * res + r,                 # top, left -> right
                  r * res + hi,                 # right, top -> bottom
                  hi * res + (hi - r + lo),     # bottom, right -> left
                  (hi - r + lo) * res + lo]     # left, bottom -> top
    return np.concatenate(parts)


def hud(frame, text):
    """Chunky pixel-font label, bottom left."""
    font = ImageFont.load_default()
    tmp = Image.new("RGB", (len(text) * 7 + 4, 14), (0, 0, 0))
    ImageDraw.Draw(tmp).text((2, 1), text, font=font, fill=(255, 255, 255))
    big = np.asarray(tmp.resize((tmp.width * 3, tmp.height * 3), Image.NEAREST))
    h, w = big.shape[:2]
    frame[SIZE - h - 12:SIZE - 12, 12:12 + w] = big
    return frame


# ---------------------------------------------------------------- video
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cx", type=float, default=-0.65)
    ap.add_argument("--cy", type=float, default=0.0)
    ap.add_argument("--mag", type=float, default=1.0, help="zoom; 1 = whole set")
    ap.add_argument("--iter", type=int, default=512)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--draw", type=int, default=30, help="max frames to draw a level")
    ap.add_argument("--hold", type=int, default=12, help="frames to hold each level")
    ap.add_argument("--final", type=int, default=75, help="frames to hold the last level")
    ap.add_argument("--shape", choices=["square", "circle"], default="square",
                    help="draw each pixel as a square block or a round dot")
    ap.add_argument("--mode", choices=["grid", "quadtree"], default="grid",
                    help="grid: every block splits; quadtree: only blocks with detail split")
    ap.add_argument("--order", choices=["raster", "random", "spiral", "spiral-out"],
                    default="raster",
                    help="raster: left-to-right; random: pixel dissolve; "
                         "spiral: edges inwards; spiral-out: centre outwards")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--no-grid", action="store_true", help="quadtree without block outlines")
    ap.add_argument("--no-hud", action="store_true")
    ap.add_argument("-o", "--out", default="pixel_resolve.mp4")
    a = ap.parse_args()

    print("rendering fractal...")
    v = brightness(mandel(SIZE, a.cx, a.cy, 3.0 / a.mag, a.iter))

    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{SIZE}x{SIZE}", "-r", str(a.fps), "-i", "-",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", a.out],
        stdin=subprocess.PIPE)

    canvas = np.zeros((SIZE, SIZE, 3), dtype=np.uint8)
    frames = 0

    def emit(label):
        nonlocal frames
        f = canvas.copy()
        if not a.no_hud:
            hud(f, label)
        ff.stdin.write(f.tobytes())
        frames += 1

    rng = np.random.default_rng(a.seed)
    idx_full = np.rint(v * (len(PALETTE) - 1)).astype(np.int8)
    outline = a.mode == "quadtree" and a.shape == "square" and not a.no_grid
    clean = canvas.copy()                       # same picture without grid lines

    def busy(level):
        """Blocks at this level whose pixels don't all share one colour."""
        res = 1 << level
        b = SIZE // res
        blk = idx_full.reshape(res, b, res, b)
        return blk.max(axis=(1, 3)) != blk.min(axis=(1, 3))

    for level in range(LEVELS):
        small, b = level_image(v, level)
        res = small.shape[0]
        full = np.repeat(np.repeat(small, b, axis=0), b, axis=1)
        if a.shape == "circle":
            full = full * circle_mask(b, res)
        lined = full
        if outline and b >= 4:
            edge = np.zeros((b, b), dtype=bool)
            edge[0, :] = edge[:, 0] = True
            lined = np.where(np.tile(edge, (res, res))[..., None],
                             (full * 0.45).astype(np.uint8), full)

        # which blocks get drawn this level
        if a.mode == "quadtree" and level > 0:
            new = np.repeat(np.repeat(busy(level - 1), 2, axis=0), 2, axis=1)
        else:
            new = np.ones((res, res), dtype=bool)
        order = np.flatnonzero(new)
        if a.order == "random":
            order = rng.permutation(order)
        elif a.order in ("spiral", "spiral-out"):
            sp = spiral_order(res)
            if a.order == "spiral-out":
                sp = sp[::-1]
            order = sp[new.ravel()[sp]]
        if len(order) == 0:
            break
        label = f"{res}x{res}" if a.mode == "grid" else f"{b}px  {len(order)} new"

        steps = min(len(order), a.draw)
        shown = np.zeros(res * res, dtype=bool)
        for s in range(1, steps + 1):
            shown[order[:len(order) * s // steps]] = True
            m = shown.reshape(res, res)
            m = np.repeat(np.repeat(m, b, axis=0), b, axis=1)
            canvas[m] = lined[m]
            clean[m] = full[m]
            emit(label)
        last = level == LEVELS - 1
        for i in range(a.final if last else a.hold):
            if last and outline and i == a.final // 3:
                canvas[:] = clean               # drop the grid for the finish
            emit(label)
        print(f"  level {level:2d}  {label:>14}  ({frames} frames)")

    ff.stdin.close()
    ff.wait()
    print(f"wrote {a.out}: {frames} frames, {frames / a.fps:.1f}s")


if __name__ == "__main__":
    main()
