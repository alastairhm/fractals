"""Turn a Mandelbrot view into a 3D-printable tile (binary STL).

Modes
  relief : terraced height map - each iteration band is a step, the set
           itself is the highest plateau. Prints as a tactile contour map.
  lines  : the edge-band line art from andromeda_zoom.py, raised off a flat
           base. Swap filament at the top of the base for a two-colour print.
  litho  : lithophane - thin where the image is bright, thick where dark.
           Print in white, stand it upright and backlight it.

Examples
  python3 fractal_tile.py                                  # Andromeda, relief
  python3 fractal_tile.py --mode lines -o andromeda_lines.stl
  python3 fractal_tile.py --cx -0.65 --cy 0 --mag 0.75 --mode lines -o full_set.stl
  python3 fractal_tile.py --mode litho --size 100 -o andromeda_litho.stl

Only needs numpy, numba (and Pillow for --preview). The mesh is closed
(top surface, side walls, flat bottom), so slicers accept it as-is.
"""
import argparse

import numpy as np

from andromeda_zoom import mandel


# ---------------------------------------------------------------- heights
def iterations(cx, cy, mag, res, max_iter):
    return mandel(res, res, cx, cy, 3.0 / mag, max_iter)


def norm_log(it, max_iter):
    """0..1 per pixel: log-scaled iteration count, set interior = 1."""
    esc = it < max_iter
    n0 = it[esc].min()
    n1 = np.percentile(it[esc], 99.5)
    t = np.log1p(np.clip(it - n0, 0, None)) / np.log1p(max(n1 - n0, 1))
    t = np.clip(t, 0, 1)
    t[~esc] = 1.0
    return t


def edge_mask(it, max_iter, thicken=1):
    p = np.pad(it, 1, mode="edge")
    e = ((p[1:-1, 1:-1] != p[:-2, 1:-1]) | (p[1:-1, 1:-1] != p[2:, 1:-1]) |
         (p[1:-1, 1:-1] != p[1:-1, :-2]) | (p[1:-1, 1:-1] != p[1:-1, 2:]))
    e &= it < max_iter
    for _ in range(thicken):                      # widen lines for the nozzle
        q = np.pad(e, 1)
        e = (q[1:-1, 1:-1] | q[:-2, 1:-1] | q[2:, 1:-1] |
             q[1:-1, :-2] | q[1:-1, 2:])
    return e


def heights(mode, it, max_iter, base, relief):
    if mode == "relief":
        return base + relief * norm_log(it, max_iter)
    if mode == "lines":
        return base + relief * edge_mask(it, max_iter).astype(float)
    if mode == "litho":
        # bright image = thin. Use the edge-band picture as brightness.
        bright = edge_mask(it, max_iter).astype(float) * 0.85
        bright = np.maximum(bright, 0.15 * norm_log(it, max_iter))
        return base + relief * (1.0 - bright)
    raise ValueError(mode)


# ---------------------------------------------------------------- mesh
def heightfield_triangles(h, size):
    """Closed triangle soup for a square height field. h[r, c], row 0 = top
    (north) of the image. Returns (n, 3, 3) float32 array of triangles."""
    ny, nx = h.shape
    d = size / (nx - 1)
    xs = np.arange(nx) * d
    ys = (ny - 1 - np.arange(ny)) * d             # image row 0 at the back
    X, Y = np.meshgrid(xs, ys)
    V = np.stack([X, Y, h], axis=-1)              # (ny, nx, 3)

    # top: for rows r (north) and r+1 (south)
    a = V[1:, :-1]   # south-west
    b = V[1:, 1:]    # south-east
    c = V[:-1, 1:]   # north-east
    dd = V[:-1, :-1]  # north-west
    top = np.concatenate([np.stack([a, b, c], -2).reshape(-1, 3, 3),
                          np.stack([a, c, dd], -2).reshape(-1, 3, 3)])

    # boundary loop, anticlockwise seen from above
    south = V[-1, :]
    east = V[::-1, -1][1:]
    north = V[0, ::-1][1:]
    west = V[:, 0][1:]
    loop = np.concatenate([south, east, north, west])  # last == first
    p_top, q_top = loop[:-1], loop[1:]
    p_bot, q_bot = p_top.copy(), q_top.copy()
    p_bot[:, 2] = 0
    q_bot[:, 2] = 0
    walls = np.concatenate([np.stack([p_bot, q_bot, q_top], 1),
                            np.stack([p_bot, q_top, p_top], 1)])

    centre = np.array([size / 2, size / 2, 0.0])
    cen = np.broadcast_to(centre, p_bot.shape)
    bottom = np.stack([cen, q_bot, p_bot], 1)     # faces downwards

    return np.concatenate([top, walls, bottom]).astype(np.float32)


def write_stl(path, tris):
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    rec = np.zeros(len(tris), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)),
                                     ("attr", "<u2")])
    rec["n"] = n
    rec["v"] = tris
    with open(path, "wb") as f:
        f.write(b"fractal_tile".ljust(80, b" "))
        f.write(np.uint32(len(tris)).tobytes())
        f.write(rec.tobytes())


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cx", type=float, default=-1.74747070750)
    ap.add_argument("--cy", type=float, default=0.00087953063)
    ap.add_argument("--mag", type=float, default=11.1e6 * 1.33,
                    help="1 = 3 units wide (whole set ~0.75)")
    ap.add_argument("--iter", type=int, default=3000)
    ap.add_argument("--mode", choices=["relief", "lines", "litho"], default="relief")
    ap.add_argument("--size", type=float, default=100.0, help="tile width, mm")
    ap.add_argument("--res", type=int, default=400, help="grid points per side")
    ap.add_argument("--base", type=float, default=None, help="base thickness, mm")
    ap.add_argument("--relief", type=float, default=None, help="relief height, mm")
    ap.add_argument("--preview", action="store_true", help="also save a PNG height map")
    ap.add_argument("-o", "--out", default=None)
    a = ap.parse_args()

    # sensible defaults per mode
    base = a.base if a.base is not None else {"relief": 1.6, "lines": 2.0, "litho": 0.8}[a.mode]
    relief = a.relief if a.relief is not None else {"relief": 3.0, "lines": 1.2, "litho": 2.4}[a.mode]
    out = a.out or f"fractal_{a.mode}.stl"

    it = iterations(a.cx, a.cy, a.mag, a.res, a.iter)
    h = heights(a.mode, it, a.iter, base, relief)
    tris = heightfield_triangles(h, a.size)
    write_stl(out, tris)
    print(f"{out}: {len(tris):,} triangles, {a.size:.0f} x {a.size:.0f} x "
          f"{h.max():.1f} mm")

    if a.preview:
        from PIL import Image
        img = ((h - h.min()) / max(np.ptp(h), 1e-9) * 255).astype(np.uint8)
        Image.fromarray(img).save(out[:-4] + "_heights.png")


if __name__ == "__main__":
    main()
