"""Zoom video from the whole Mandelbrot set to the Andromeda Research spot,
in the edge-band style of andromeda_zoom.py.

Usage:
    python3 zoom_video.py                 # full render -> mandel_zoom.mp4
    python3 zoom_video.py --turns 1 -o mandel_zoom_spin.mp4   # one clockwise turn
    python3 zoom_video.py --turns 1 --roundtrip -o mandel_roundtrip.mp4  # in and out, loops
    python3 zoom_video.py --preview 0 0.5 0.8 1   # PNG stills at those points

ZOOM_WORKERS=N sets the colouring/stats thread count (default: CPU count);
the fractal itself is rendered by numba across all cores.
"""
import argparse
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from numba import njit, prange

from andromeda_zoom import colour_for  # noqa: F401  (palette() mirrors it)

W, H, SCALE = 640, 480, 2          # render size, upscaled 2x -> 1280x960
FPS, SECONDS = 30, 20

START = (-0.65, 0.0, 0.9)                          # cx, cy, mag
END = (-1.74747070750, 0.00087953063, 11.1e6)


TURNS = 0.0                       # clockwise turns over the whole video
WORKERS = int(os.environ.get("ZOOM_WORKERS", os.cpu_count() or 4))


@njit(parallel=True, fastmath=True, nogil=True)
def mandel(w, h, cx, cy, span, max_iter, angle):
    """Escape-time counts with the view rotated by `angle` radians.

    Sampling the plane rotated anticlockwise makes the picture appear to
    turn clockwise on screen.
    """
    out = np.zeros((h, w), np.int32)
    sx = span / w
    ca, sa = np.cos(angle), np.sin(angle)
    for j in prange(h):
        dy = (h / 2 - j) * sx
        for i in range(w):
            dx = (i - w / 2) * sx
            cr = cx + dx * ca - dy * sa
            ci = cy + dx * sa + dy * ca
            zr = zi = 0.0
            n = 0
            while n < max_iter and zr * zr + zi * zi <= 4.0:
                zr, zi = zr * zr - zi * zi + cr, 2.0 * zr * zi + ci
                n += 1
            out[j, i] = n
    return out


def ease(u):
    """Smooth start and stop (smootherstep)."""
    return u * u * u * (u * (6 * u - 15) + 10)


def view(u):
    """Camera at progress u in [0, 1].

    Magnification grows exponentially; the centre glides onto the target
    during the first 30% of the zoom and then stays locked on it.
    """
    s = ease(u)
    m0, m1 = START[2], END[2]
    mag = m0 * (m1 / m0) ** s
    # Offset from target shrinks with the zoom, and is also eased to zero
    # over the first 30% so the target is centred for the rest of the dive
    g = 1 - ease(min(s / 0.3, 1.0))
    k = (m0 / mag) * g
    cx = END[0] + (START[0] - END[0]) * k
    cy = END[1] + (START[1] - END[1]) * k
    return cx, cy, mag


def max_iter_for(mag):
    return int(min(3000, 300 + 150 * np.log10(max(mag, 1.0))))


def render_iters(u, angle=None):
    cx, cy, mag = view(u)
    mi = max_iter_for(mag)
    if angle is None:
        angle = 2 * np.pi * TURNS * u  # constant angular speed
    return mandel(W, H, cx, cy, 3.0 / mag, mi, angle), mi


def stats(it, mi):
    esc = it[it < mi]
    return float(esc.min()), float(np.percentile(esc, 99.5))


def palette(n, n0, n1):
    """Vectorised andromeda_zoom.colour_for (linear mode) over an array of n.

    Same float operations in the same order as colour_for + colorsys, so the
    result is bit-identical; it just runs in numpy instead of a Python loop
    that holds the GIL.
    """
    t = np.clip((n - n0) / max(n1 - n0, 1), 0.0, 1.0)
    h = (0.88 + 1.0 * t) % 1.0
    s = 1.0 - 0.6 * np.maximum(t - 0.6, 0.0) / 0.4
    v = 1.0
    i = (h * 6.0).astype(np.int64)
    f = (h * 6.0) - i
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    u = v * (1.0 - s * (1.0 - f))
    i %= 6
    vv = np.full_like(h, v)
    r = np.choose(i, [vv, q, p, p, u, vv])
    g = np.choose(i, [u, vv, vv, q, p, p])
    b = np.choose(i, [p, p, u, vv, vv, q])
    rgb = np.stack([r, g, b], axis=-1) * 255
    return rgb.astype(np.int64).astype(np.uint8)


def frame_rgb(it, mi, n0, n1, u):
    p = np.pad(it, 1, mode="edge")
    edge = ((p[1:-1, 1:-1] != p[:-2, 1:-1]) | (p[1:-1, 1:-1] != p[2:, 1:-1]) |
            (p[1:-1, 1:-1] != p[1:-1, :-2]) | (p[1:-1, 1:-1] != p[1:-1, 2:]))
    edge &= it < mi
    # Blend log palette (wide views) into linear palette (deep view)
    w = ease(u)
    ns = np.arange(mi + 1)
    t_lin = np.clip((ns - n0) / max(n1 - n0, 1), 0, 1)
    t_log = np.clip(np.log1p(np.maximum(ns - n0, 0)) / np.log1p(max(n1 - n0, 1)), 0, 1)
    t = (1 - w) * t_log + w * t_lin
    lut = palette(n0 + t * (n1 - n0), n0, n1)
    img = np.zeros((H, W, 3), np.uint8)
    img[edge] = lut[it[edge]]
    return img


def smooth(a, win=15):
    k = np.ones(win) / win
    pad = np.pad(a, win // 2, mode="edge")
    return np.convolve(pad, k, mode="valid")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=float, nargs="*")
    ap.add_argument("--turns", type=float, default=0.0,
                    help="clockwise turns over the video, e.g. 1")
    ap.add_argument("--roundtrip", action="store_true",
                    help="zoom in, then back out (twice as long); rotation "
                         "keeps going the same way, so the video loops")
    ap.add_argument("-o", "--out", default="mandel_zoom.mp4")
    a = ap.parse_args()
    global TURNS
    TURNS = a.turns

    if a.preview is not None:
        from PIL import Image
        for u in a.preview:
            it, mi = render_iters(u)
            n0, n1 = stats(it, mi)
            img = frame_rgb(it, mi, n0, n1, u)
            Image.fromarray(img).resize((W * SCALE, H * SCALE), Image.NEAREST) \
                .save(f"preview_{u:.2f}.png")
            print(u, view(u), mi, n0, n1)
        return

    n = FPS * SECONDS
    if a.roundtrip:
        # progress along the zoom path: 0 -> 1 -> 0; clock keeps running
        clock = np.arange(2 * n) / n                 # 0 .. 2 (end exclusive)
        us = np.where(clock <= 1, clock, 2 - clock)
    else:
        clock = np.linspace(0, 1, n)
        us = clock
    angles = 2 * np.pi * TURNS * clock

    # Pass 1: render every frame once, keeping the iteration counts in a
    # temporary file (int16: max_iter <= 3000) so pass 2 doesn't re-render.
    # mandel() is already parallel over rows and releases the GIL, so the
    # per-frame stats run in worker threads alongside the next render.
    cache = a.out[:-4] + ".iters.tmp"
    iters = np.lib.format.open_memmap(cache, mode="w+", dtype=np.int16,
                                      shape=(len(us), H, W))
    try:
        encode(a.out, us, angles, iters)
    finally:
        del iters
        os.remove(cache)


def encode(out, us, angles, iters):
    mis = [0] * len(us)

    def store(i, it, mi):
        iters[i] = it
        return stats(it, mi)

    with ThreadPoolExecutor(WORKERS) as pool:
        futs = []
        for i, (u, ang) in enumerate(zip(us, angles)):
            it, mis[i] = render_iters(u, ang)
            futs.append(pool.submit(store, i, it, mis[i]))
        s = np.array([f.result() for f in futs])
    # Palette range per frame, smoothed so colours don't flicker
    n0s, n1s = smooth(s[:, 0]), smooth(s[:, 1])

    def colour(i):
        return frame_rgb(iters[i], mis[i], n0s[i], n1s[i], us[i]).tobytes()

    tmp = out[:-4] + ".part.mp4"
    ff = subprocess.Popen([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
        "-i", "-",
        "-vf", f"scale={W * SCALE}:{H * SCALE}:flags=neighbor,format=yuv420p",
        "-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", tmp,
    ], stdin=subprocess.PIPE)
    # Pass 2: colour frames in parallel; map() yields them in order
    with ThreadPoolExecutor(WORKERS) as pool:
        for frame in pool.map(colour, range(len(us))):
            ff.stdin.write(frame)
    ff.stdin.close()
    if ff.wait() == 0:
        os.replace(tmp, out)
        print("wrote", out)


if __name__ == "__main__":
    main()
