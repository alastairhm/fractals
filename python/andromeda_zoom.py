"""Recreate the Andromeda Research-style Mandelbrot deep zoom.

Centre: -1.74747070750 + 0.00087953063i, magnification 11.1e6.

Look: plain escape-time Mandelbrot, but only the *boundaries* between
iteration bands are drawn (coloured by iteration count); band interiors are
black. Far from the set the bands are wide, so you see thin contour lines on
black; near the set the bands crowd together and the lines merge into solid
colour. Rendered at a low, DOS-like resolution and scaled up for the chunky feel.
"""
import colorsys

import numpy as np
from numba import njit, prange
from PIL import Image

import argparse

W, H = 640, 480            # VGA-era resolution
SCALE = 3                  # nearest-neighbour upscale for the retro look


@njit(parallel=True, fastmath=True)
def mandel(w, h, cx, cy, span, max_iter):
    out = np.zeros((h, w), np.int32)
    sx = span / w
    for j in prange(h):
        ci = cy + (h / 2 - j) * sx
        for i in range(w):
            cr = cx + (i - w / 2) * sx
            zr = zi = 0.0
            n = 0
            while n < max_iter and zr * zr + zi * zi <= 4.0:
                zr, zi = zr * zr - zi * zi + cr, 2.0 * zr * zi + ci
                n += 1
            out[j, i] = n
    return out


def colour_for(n, n0, n1, log=False):
    """Magenta/red far out -> orange -> yellow -> green -> blue -> violet -> pastel pink."""
    if log:   # spreads colours better when most pixels escape in a few steps
        t = np.log1p(max(n - n0, 0)) / np.log1p(max(n1 - n0, 1))
    else:
        t = (n - n0) / max(n1 - n0, 1)
    t = min(max(t, 0.0), 1.0)
    hue = (0.88 + 1.0 * t) % 1.0
    sat = 1.0 - 0.6 * max(t - 0.6, 0.0) / 0.4      # fade to pastel near the core
    r, g, b = colorsys.hsv_to_rgb(hue, sat, 1.0)
    return int(r * 255), int(g * 255), int(b * 255)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Edge-band Mandelbrot renderer")
    ap.add_argument("--cx", type=float, default=-1.74747070750)
    ap.add_argument("--cy", type=float, default=0.00087953063)
    ap.add_argument("--mag", type=float, default=11.1e6,
                    help="magnification; 1 = 3 units wide (whole set)")
    ap.add_argument("--iter", type=int, default=3000)
    ap.add_argument("--log", action="store_true",
                    help="log-scale palette (good for wide views)")
    ap.add_argument("-o", "--out", default="andromeda_zoom.png")
    a = ap.parse_args()
    MAX_ITER = a.iter
    it = mandel(W, H, a.cx, a.cy, 3.0 / a.mag, MAX_ITER)

    # A pixel is an "edge" if any 4-neighbour has a different iteration count
    p = np.pad(it, 1, mode="edge")
    edge = ((p[1:-1, 1:-1] != p[:-2, 1:-1]) | (p[1:-1, 1:-1] != p[2:, 1:-1]) |
            (p[1:-1, 1:-1] != p[1:-1, :-2]) | (p[1:-1, 1:-1] != p[1:-1, 2:]))
    edge &= it < MAX_ITER

    n0 = int(it.min())
    n1 = int(np.percentile(it[it < MAX_ITER], 99.5))  # ignore set interior
    lut = np.array([colour_for(n, n0, n1, a.log) for n in range(MAX_ITER + 1)], np.uint8)

    img = np.zeros((H, W, 3), np.uint8)
    img[edge] = lut[it[edge]]
    big = Image.fromarray(img).resize((W * SCALE, H * SCALE), Image.NEAREST)
    big.save(a.out)
    print("iterations:", n0, n1, it.max())
