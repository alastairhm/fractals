#!/usr/bin/env python3
"""
citymap.py - generate random minimalist city-map posters.

    python citymap.py                      # random city, random name
    python citymap.py --seed 42 --name Dishforth --out dishforth.png
    python citymap.py --palette night --count 4
    python citymap.py --align 0.6              # lower = more patchwork of grid angles

Needs: numpy, matplotlib, shapely  (pip install numpy matplotlib shapely)
"""
import argparse
import math
import random

import matplotlib.pyplot as plt
import numpy as np
from shapely import affinity
from shapely.geometry import LineString, MultiPoint, Point, Polygon, box
from shapely.ops import unary_union, voronoi_diagram

PALETTES = {
    "classic": dict(bg="#dccb9c", road="#353b3c", water="#e2432b", block="#1d1d1d", park="#e2432b", text="#353b3c"),
    "night":   dict(bg="#1f2a36", road="#c9d1d9", water="#f2b134", block="#0d1218", park="#f2b134", text="#c9d1d9"),
    "mint":    dict(bg="#e6efe9", road="#2f3e46", water="#2a9d8f", block="#2f3e46", park="#e76f51", text="#2f3e46"),
    "blush":   dict(bg="#f4e1d2", road="#3d3b40", water="#3a6ea5", block="#3d3b40", park="#d1495b", text="#3d3b40"),
}

# Map area in map units. Matches the axes box below, so 1 unit is the same size in x and y.
W, H = 100.0, 139.0
BOUNDS = box(-15, -15, W + 15, H + 15)


# --------------------------------------------------------------------------- helpers
def lines_of(geom):
    """Yield every LineString inside any shapely geometry."""
    if geom.is_empty:
        return
    if geom.geom_type == "LineString":
        yield geom
    elif hasattr(geom, "geoms"):
        for g in geom.geoms:
            yield from lines_of(g)


def polys_of(geom):
    if geom.is_empty:
        return
    if geom.geom_type == "Polygon":
        yield geom
    elif hasattr(geom, "geoms"):
        for g in geom.geoms:
            yield from polys_of(g)


def meander(rng, start, target, step=0.4, amp=(0.6, 1.3), wavelength=(16, 30), max_len=400):
    """A Kinoshita-style meandering curve that drifts from start towards target."""
    x, y = start
    pts = [(x, y)]
    phase = rng.uniform(0, 2 * math.pi)
    a = rng.uniform(*amp)
    k = 2 * math.pi / rng.uniform(*wavelength)
    s = 0.0
    while s < max_len:
        base = math.atan2(target[1] - y, target[0] - x)
        a = float(np.clip(a + rng.normal(0, 0.02), *amp))
        k = float(np.clip(k + rng.normal(0, 0.0008), 2 * math.pi / wavelength[1], 2 * math.pi / wavelength[0]))
        phase += k * step
        theta = base + a * math.sin(phase)
        x += step * math.cos(theta)
        y += step * math.sin(theta)
        s += step
        pts.append((x, y))
        if math.hypot(target[0] - x, target[1] - y) < 2:
            break
    return LineString(pts)


def warp(line, rng, amp, wl):
    """Bend a straight line gently so districts feel less ruler-drawn."""
    if amp == 0:
        return line
    n = max(int(line.length / 0.8), 2)
    pts = [line.interpolate(i / n, normalized=True) for i in range(n + 1)]
    (x0, y0), (x1, y1) = pts[0].coords[0], pts[-1].coords[0]
    nx, ny = -(y1 - y0) / line.length, (x1 - x0) / line.length
    ph = rng.uniform(0, 2 * math.pi)
    out = []
    for i, p in enumerate(pts):
        d = amp * math.sin(2 * math.pi * i * 0.8 / wl + ph)
        out.append((p.x + nx * d, p.y + ny * d))
    return LineString(out)


def blob(rng, cx, cy, r, n=9, jag=0.35):
    angs = np.sort(rng.uniform(0, 2 * math.pi, n))
    poly = Polygon([(cx + r * (1 + rng.uniform(-jag, jag)) * math.cos(t),
                     cy + r * (1 + rng.uniform(-jag, jag)) * math.sin(t)) for t in angs]).buffer(0)
    return max(polys_of(poly), key=lambda q: q.area) if poly.geom_type != "Polygon" else poly


# --------------------------------------------------------------------------- city pieces
def make_rivers(rng):
    # main river enters top, leaves bottom
    sx = rng.uniform(0.35, 0.75) * W
    ex = rng.uniform(0.3, 0.7) * W
    main = meander(rng, (sx, H + 10), (ex, -12), amp=(0.8, 1.45), wavelength=(24, 38))
    main_poly = main.buffer(rng.uniform(0.9, 1.3), cap_style="flat")

    # tributary from a side edge into the main river
    join = main.interpolate(rng.uniform(0.3, 0.55), normalized=True)
    side = rng.choice([-12, W + 12])
    trib = meander(rng, (side, rng.uniform(0.35, 0.65) * H), (join.x, join.y),
                   amp=(0.3, 0.8), wavelength=(10, 20))
    trib_poly = trib.buffer(0.65, cap_style="flat")

    # thin squiggly creeks
    creeks = []
    for _ in range(rng.integers(1, 4)):
        a = (rng.uniform(0, W), rng.uniform(H * 0.5, H + 5))
        b = (a[0] + rng.uniform(-30, 30), rng.uniform(-5, H * 0.4))
        creeks.append(meander(rng, a, b, step=0.15, amp=(0.9, 1.3), wavelength=(1.5, 3.5)))

    water = unary_union([main_poly.buffer(0), trib_poly.buffer(0)]).buffer(0)
    return water, creeks, join


def make_grids(rng):
    """The city's shared street lattices: a main one and one skewed one.
    Districts borrow one of these, so their streets line up across boundaries."""
    base = rng.uniform(-20, 20)
    sp = rng.uniform(3.2, 4.6)
    origin = Point(W / 2 + rng.uniform(-sp, sp), H / 2 + rng.uniform(-sp, sp))
    main = dict(angle=base, spacing=sp, origin=origin)
    skew = dict(angle=base + rng.choice([-1, 1]) * rng.uniform(30, 40), spacing=sp * rng.uniform(0.9, 1.15), origin=origin)
    return main, skew


def make_districts(rng, downtown, grids, align=0.9):
    """Two big halves, split by a line through downtown: one half on the main grid,
    the other on the skewed grid (the Belmouth look). `align` is the chance a
    district follows its half's grid rather than the other one."""
    main, skew = grids
    seeds = [downtown] + [Point(rng.uniform(0, W), rng.uniform(0, H)) for _ in range(rng.integers(5, 9))]
    split = rng.uniform(0, math.pi)
    nx, ny = math.cos(split), math.sin(split)

    def half_grid(p):
        side = (p.x - downtown.x) * nx + (p.y - downtown.y) * ny > 0
        own, other = (main, skew) if side else (skew, main)
        return own if rng.random() < align else other

    cells = list(polys_of(voronoi_diagram(MultiPoint(seeds), envelope=BOUNDS)))
    districts = []
    for i, s in enumerate(seeds):
        cell = next((c for c in cells if c.contains(s)), None)
        if cell is None:
            continue
        cell = cell.intersection(BOUNDS)
        grid = half_grid(s)
        if i == 0:
            core = s.buffer(rng.uniform(9, 15))
            districts.append(dict(cell=cell.difference(core), center=s, style="grid", grid=main))
            cell, style = cell.intersection(core), "downtown"
            grid = skew if rng.random() < 0.5 else main
        else:
            edge = min(s.x, W - s.x, s.y, H - s.y) < 25
            style = rng.choice(["suburb", "organic", "organic"] if edge
                               else ["organic", "organic", "grid", "long"])
        districts.append(dict(cell=cell, center=s, style=style, grid=grid, angle=grid["angle"]))
    for d in districts:
        d.setdefault("angle", d["grid"]["angle"])
    return districts


def district_streets(rng, d):
    cell, c, a = d["cell"], d["center"], d["angle"]
    sp, style = d["grid"]["spacing"], d["style"]
    R = 220.0
    streets = []

    if style == "suburb":
        # a few collector roads + curly loops and crescents
        o = d["grid"]["origin"]  # collector roads continue the neighbouring grid lines
        for k in np.arange(-R, R + 1e-9, sp * 2):
            streets.append(affinity.rotate(LineString([(o.x - R, o.y + k), (o.x + R, o.y + k)]), a, origin=o))
            streets.append(affinity.rotate(LineString([(o.x + k, o.y - R), (o.x + k, o.y + R)]), a, origin=o))
        minx, miny, maxx, maxy = cell.bounds
        for _ in range(int(cell.area / 160)):
            p = Point(rng.uniform(minx, maxx), rng.uniform(miny, maxy))
            if not cell.contains(p):
                continue
            r = rng.uniform(1.2, 2.6)
            f1, f2 = rng.uniform(0, 6.3, 2)
            t0 = rng.uniform(0, 2 * math.pi)
            span = 2 * math.pi if rng.random() < 0.45 else rng.uniform(2.2, 4.2)  # loop or crescent
            ts = np.linspace(t0, t0 + span, 60)
            rr = r * (1 + 0.15 * np.sin(2 * ts + f1) + 0.08 * np.sin(3 * ts + f2))
            crv = LineString(np.c_[p.x + rr * np.cos(ts), p.y + rr * np.sin(ts) * rng.uniform(0.55, 1.0)])
            streets.append(affinity.rotate(crv, rng.uniform(0, 180), origin=p))
            if rng.random() < 0.4:  # cul-de-sac stub into the loop
                t = rng.uniform(0, 2 * math.pi)
                streets.append(LineString([(p.x + 0.3 * r * math.cos(t), p.y + 0.3 * r * math.sin(t)),
                                           (p.x + r * 1.7 * math.cos(t), p.y + r * 1.7 * math.sin(t))]))
        return [g.intersection(cell) for g in streets]

    # Every district draws from the same lattice (same origin, spacing and angle),
    # so neighbouring districts on the same grid share street lines.
    o = d["grid"]["origin"]
    mult = {"downtown": (0.5, 0.5), "long": (1, int(rng.choice([2, 3]))), "organic": (1, 1)}
    mx, my = mult.get(style, (1, int(rng.choice([1, 1, 2]))))
    sx, sy = sp * mx, sp * my
    amp = rng.uniform(0.15, 0.35) if style == "organic" else 0
    wl = rng.uniform(25, 45)
    for k in np.arange(-R, R + 1e-9, sx):
        streets.append(warp(LineString([(o.x + k, o.y - R), (o.x + k, o.y + R)]), rng, amp, wl))
    for k in np.arange(-R, R + 1e-9, sy):
        streets.append(warp(LineString([(o.x - R, o.y + k), (o.x + R, o.y + k)]), rng, amp, wl))

    out = []
    for g in streets:
        g = affinity.rotate(g, a, origin=o).intersection(cell)
        for seg in lines_of(g):
            # break into pieces and randomly drop some so the grid isn't perfect
            L = seg.length
            pos = 0.0
            while pos < L:
                step = rng.uniform(sp * 1.5, sp * 6)
                piece = LineString([seg.interpolate(pos), seg.interpolate(min(pos + step, L))])
                if rng.random() > 0.12:
                    out.append(piece)
                pos += step
    return out


def make_arterials(rng, grids):
    """Main roads mostly sit on a grid line, so they read as part of the street pattern."""
    roads = []
    for i in range(rng.integers(3, 6)):
        g = grids[0] if rng.random() < 0.7 else grids[1]
        o, sp = g["origin"], g["spacing"]
        k = sp * rng.integers(-14, 15)
        line = LineString([(o.x + k, o.y - 250), (o.x + k, o.y + 250)])
        roads.append(affinity.rotate(line, g["angle"] + rng.choice([0, 90]), origin=o))
    # one or two off-grid diagonals, the old trails the grid grew around
    for _ in range(rng.integers(1, 3)):
        p = Point(rng.uniform(0, W), rng.uniform(0, H))
        roads.append(affinity.rotate(LineString([(p.x - 250, p.y), (p.x + 250, p.y)]),
                                     rng.uniform(0, 180), origin=p))
    # a sweeping ring road segment
    if rng.random() < 0.7:
        cx, cy, r = rng.uniform(0, W), rng.uniform(0, H), rng.uniform(45, 80)
        t0 = rng.uniform(0, 2 * math.pi)
        ts = np.linspace(t0, t0 + rng.uniform(1.2, 2.2), 60)
        roads.append(LineString([(cx + r * math.cos(t), cy + r * math.sin(t)) for t in ts]))
    return roads


def make_railway(rng):
    """A bundle of thin parallel tracks (a rail yard) running off the edge."""
    a = rng.uniform(0, 180)
    c = Point(rng.uniform(0.2, 0.8) * W, rng.uniform(0.2, 0.8) * H)
    tracks = []
    for i in range(rng.integers(3, 7)):
        L = LineString([(c.x - 200, c.y + i * 0.35), (c.x + rng.uniform(5, 25), c.y + i * 0.35)])
        tracks.append(affinity.rotate(L, a, origin=c))
    return tracks


def make_lots(rng, districts, water, kind):
    shapes = []
    n = rng.integers(110, 170) if kind == "block" else rng.integers(35, 60)
    for _ in range(n):
        p = Point(rng.uniform(0, W), rng.uniform(0, H))
        d = min(districts, key=lambda d: d["center"].distance(p) if d["cell"].contains(p) else 1e9)
        if kind == "block":
            w, h = rng.uniform(0.5, 2.6), rng.uniform(0.5, 1.8)
            if rng.random() < 0.15:
                w *= 2
            shp = affinity.rotate(box(p.x - w / 2, p.y - h / 2, p.x + w / 2, p.y + h / 2), d["angle"], origin=p)
            if rng.random() < 0.1:  # L-shaped building
                shp = shp.difference(affinity.translate(shp, w / 2, h / 2))
        else:
            if rng.random() < 0.5:
                shp = blob(rng, p.x, p.y, rng.uniform(0.6, 2.0))
            else:
                w, h = rng.uniform(0.4, 1.2), rng.uniform(1.5, 4.5)
                shp = affinity.rotate(box(p.x - w / 2, p.y - h / 2, p.x + w / 2, p.y + h / 2),
                                      d["angle"] + rng.choice([0, 90]), origin=p)
        if shp.is_valid and not shp.intersects(water.buffer(0.4)):
            shapes.append(shp)
    # black ponds/oxbows hugging the river
    if kind == "block":
        for _ in range(rng.integers(2, 6)):
            p = water.exterior.interpolate(rng.random(), normalized=True) if water.geom_type == "Polygon" \
                else list(polys_of(water))[0].exterior.interpolate(rng.random(), normalized=True)
            shapes.append(blob(rng, p.x, p.y, rng.uniform(0.8, 2.0)).difference(water))
    return shapes


# --------------------------------------------------------------------------- name
def random_name(rng):
    a = ["Ash", "Brook", "Cal", "Dun", "Elm", "Fair", "Glen", "Har", "Kings", "Lan", "Mar", "North",
         "Ox", "Pen", "Red", "Stan", "Thorn", "Wake", "Whit", "York", "Bel", "Cor", "Riv", "Sel"]
    b = ["ford", "ton", "wick", "bury", "field", "mouth", "ham", "by", "dale", "port", "stead",
         "chester", "worth", "ley", "minster", "haven", "gate", "peg", "ville", "brook"]
    return rng.choice(a) + rng.choice(b)


# --------------------------------------------------------------------------- render
def draw_city(seed=None, name=None, palette="classic", out="city.png", dpi=200, align=0.9):
    rng = np.random.default_rng(seed)
    random.seed(seed)
    pal = PALETTES[palette]
    name = name or random_name(rng)

    water, creeks, confluence = make_rivers(rng)
    downtown = Point(confluence.x + rng.normal(0, 3), confluence.y + rng.normal(0, 3))
    grids = make_grids(rng)
    districts = make_districts(rng, downtown, grids, align)

    minor = []
    for d in districts:
        minor += [g for s in district_streets(rng, d) for g in lines_of(s)]
    # most small streets stop at the water; arterials are bridges
    no_go = water.buffer(0.35)
    minor = [g for s in minor for g in lines_of(s.difference(no_go)) if g.length > 0.3]
    arterials = make_arterials(rng, grids)
    rail = make_railway(rng) if rng.random() < 0.8 else []

    blocks = make_lots(rng, districts, water, "block")
    parks = make_lots(rng, districts, water, "park")

    fig = plt.figure(figsize=(8, 12), facecolor=pal["bg"])
    ax = fig.add_axes([0.08, 0.17, 0.84, 0.78])  # 6.72in x 9.36in -> matches W:H
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_facecolor(pal["bg"])

    def fill(polys, color, z):
        for p in polys:
            for q in polys_of(p):
                ax.fill(*q.exterior.xy, color=color, lw=0, zorder=z)

    def stroke(lines, color, lw, z, ls="-"):
        for line in lines:
            for seg in lines_of(line):
                ax.plot(*seg.xy, color=color, lw=lw, zorder=z, solid_capstyle="round", ls=ls)

    fill(parks, pal["park"], 1)
    fill(blocks, pal["block"], 2)
    stroke(rail, pal["road"], 0.35, 3)
    stroke(minor, pal["road"], 1.25, 3)
    stroke(arterials, pal["road"], 2.2, 4)
    stroke(creeks, pal["water"], 0.5, 5)
    fill([water], pal["water"], 6)

    fig.text(0.5, 0.075, name, ha="center", va="center", fontsize=40,
             fontweight="bold", color=pal["text"], family="DejaVu Sans")
    fig.savefig(out, dpi=dpi, facecolor=pal["bg"])
    plt.close(fig)
    return out, name


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Random city map poster")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--name", default=None)
    ap.add_argument("--palette", default="classic", choices=PALETTES)
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--out", default="city.png")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--align", type=float, default=0.9,
                    help="0-1: how strictly districts follow their half's grid (lower = more patchwork)")
    args = ap.parse_args()

    for i in range(args.count):
        seed = None if args.seed is None else args.seed + i
        out = args.out if args.count == 1 else args.out.replace(".png", f"_{i + 1}.png")
        path, name = draw_city(seed, args.name, args.palette, out, args.dpi, args.align)
        print(f"{name} -> {path}")
