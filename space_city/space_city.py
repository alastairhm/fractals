#!/usr/bin/env python3
"""Procedural 'radial space city' pen-and-ink generator.

Usage: python3 space_city.py [seed] [out.png]
With no seed, the current UTC time (YYYYMMDDHHMMSS) is used.
"""
import math
import random
import sys
from datetime import datetime, timezone

import cairo

W, H = 1400, 2300
BLACK = (0, 0, 0)
WHITE = (1, 1, 1)


def setc(ctx, c):
    ctx.set_source_rgb(*c)


# ---------------------------------------------------------------- primitives
def hatch_rect(ctx, x, y, w, h, gap=4, vertical=None):
    """Solar-panel style hatched rectangle."""
    if vertical is None:
        vertical = w < h
    setc(ctx, WHITE)
    ctx.rectangle(x, y, w, h)
    ctx.fill()
    setc(ctx, BLACK)
    ctx.set_line_width(1.6)
    ctx.rectangle(x, y, w, h)
    ctx.stroke()
    ctx.set_line_width(1.1)
    if vertical:
        yy = y + gap
        while yy < y + h:
            ctx.move_to(x, yy)
            ctx.line_to(x + w, yy)
            yy += gap
    else:
        xx = x + gap
        while xx < x + w:
            ctx.move_to(xx, y)
            ctx.line_to(xx, y + h)
            xx += gap
    ctx.stroke()


def detail_block(ctx, x, y, w, h, rng):
    """Black building with random white detailing (axis-aligned, local coords)."""
    style = rng.random()
    if style < 0.12:
        hatch_rect(ctx, x, y, w, h, gap=rng.choice([3, 4, 5]))
        return
    setc(ctx, BLACK)
    ctx.rectangle(x, y, w, h)
    ctx.fill()
    if w < 6 or h < 6:
        return
    setc(ctx, WHITE)
    ctx.set_line_width(1.2)
    if style < 0.35:  # inner outline
        ctx.rectangle(x + 2.5, y + 2.5, w - 5, h - 5)
        ctx.stroke()
    elif style < 0.55:  # windows / dots
        n = max(1, int(max(w, h) / 7))
        for i in range(n):
            t = (i + 0.5) / n
            cx = x + w * (t if w > h else 0.5)
            cy = y + h * (t if h >= w else 0.5)
            ctx.arc(cx, cy, 1.4, 0, 2 * math.pi)
            ctx.fill()
    elif style < 0.75:  # split cells
        if w > h:
            k = rng.randint(1, 3)
            for i in range(1, k + 1):
                xx = x + w * i / (k + 1)
                ctx.move_to(xx, y + 2)
                ctx.line_to(xx, y + h - 2)
        else:
            k = rng.randint(1, 3)
            for i in range(1, k + 1):
                yy = y + h * i / (k + 1)
                ctx.move_to(x + 2, yy)
                ctx.line_to(x + w - 2, yy)
        ctx.stroke()
    elif style < 0.88:  # small white inset box
        iw, ih = w * rng.uniform(0.3, 0.6), h * rng.uniform(0.3, 0.6)
        ctx.rectangle(x + (w - iw) / 2, y + (h - ih) / 2, iw, ih)
        ctx.fill()
    # else: plain black


def dish(ctx, cx, cy, r):
    setc(ctx, WHITE)
    ctx.arc(cx, cy, r, 0, 2 * math.pi)
    ctx.fill()
    setc(ctx, BLACK)
    ctx.set_line_width(1.6)
    ctx.arc(cx, cy, r, 0, 2 * math.pi)
    ctx.stroke()
    ctx.arc(cx, cy, r * 0.35, 0, 2 * math.pi)
    ctx.fill()
    ctx.set_line_width(1)
    for i in range(12):
        a = i * math.pi / 6
        ctx.move_to(cx + r * 0.35 * math.cos(a), cy + r * 0.35 * math.sin(a))
        ctx.line_to(cx + r * math.cos(a), cy + r * math.sin(a))
    ctx.stroke()


# ---------------------------------------------------------------- background
def make_skyline(rng):
    """Return land(x, y) -> True where the city exists; a jagged edge to open sky."""
    waves = [(rng.uniform(0.002, 0.02), rng.uniform(0, 6.3), rng.uniform(15, 70)) for _ in range(5)]
    base_l = H * rng.uniform(0.17, 0.25)   # sky depth at left edge
    reach = W * rng.uniform(0.4, 0.6)      # how far right the sky bay extends

    def edge(x):
        t = max(0.0, 1 - x / reach)
        d = base_l * (t ** 0.7)
        return d + sum(a * math.sin(f * x + p) for f, p, a in waves) * (0.3 + t)

    def land(x, y):
        if x < reach * 1.15 and y < edge(x):
            return False
        if x > W * 0.86 and y < (x - W * 0.86) * 2.2 + rng.uniform(-25, 25):
            return False
        return True
    return land, edge


def background_grid(ctx, rng, land):
    """City blocks by recursive subdivision: nothing lines up across the page."""
    leaves = []

    def split(x, y, w, h, depth):
        small = max(w, h) < rng.uniform(14, 48) or depth > 14
        if small:
            leaves.append((x, y, w, h))
            return
        g = rng.choice([2.5, 3, 3, 4, 5, 8]) if depth < 6 else rng.choice([2.5, 3, 3.5])
        if (w > h and rng.random() < 0.8) or (w <= h and rng.random() < 0.2):
            t = w * rng.uniform(0.25, 0.75)
            split(x, y, t - g / 2, h, depth + 1)
            split(x + t + g / 2, y, w - t - g / 2, h, depth + 1)
        else:
            t = h * rng.uniform(0.25, 0.75)
            split(x, y, w, t - g / 2, depth + 1)
            split(x, y + t + g / 2, w, h - t - g / 2, depth + 1)

    # coarse irregular districts first
    split(-10, -10, W + 20, H + 20, 0)
    for (x, y, w, h) in leaves:
        if w < 3 or h < 3:
            continue
        cxm, cym = x + w / 2, y + h / 2
        if not land(cxm, cym):
            # occasional stragglers / towers poking into the sky
            if land(cxm, cym + 60) and rng.random() < 0.35:
                tall = rng.uniform(1.0, 3.5)
                detail_block(ctx, x, y - h * (tall - 1), w * rng.uniform(0.4, 1), h * tall, rng)
            continue
        if rng.random() < 0.07:
            continue
        # jitter so edges don't align
        jx, jy = rng.uniform(-1, 1), rng.uniform(-1, 1)
        detail_block(ctx, x + jx, y + jy, w * rng.uniform(0.8, 1), h * rng.uniform(0.8, 1), rng)


# ---------------------------------------------------------------- hub
def annular_segment(ctx, cx, cy, r0, r1, a0, a1):
    ctx.new_path()
    ctx.arc(cx, cy, r1, a0, a1)
    ctx.arc_negative(cx, cy, r0, a1, a0)
    ctx.close_path()


def hub(ctx, cx, cy, R, rng):
    # protruding modules / towers first so the hub disc covers their roots
    n_out = rng.randint(6, 16)
    for _ in range(n_out):
        a = rng.uniform(0, 2 * math.pi)
        length = rng.uniform(R * 0.12, R * 0.4)
        ctx.save()
        ctx.translate(cx, cy)
        ctx.rotate(a)
        r = R - 5
        bw = rng.choice([10, 14, 18])
        while r < R + length:
            seg = rng.choice([8, 12, 16, 22])
            detail_block(ctx, r, -bw / 2, seg, bw, rng)
            r += seg + 3
        end = rng.random()
        if end < 0.35:
            pw, ph = rng.uniform(25, 60), rng.uniform(40, 90)
            hatch_rect(ctx, r, -ph / 2, pw, ph, vertical=False)
        elif end < 0.6:
            dish(ctx, r + 12, 0, rng.uniform(9, 16))
        ctx.restore()

    # white backing disc
    setc(ctx, WHITE)
    ctx.new_path()
    steps = 90
    for i in range(steps + 1):
        a = i * 2 * math.pi / steps
        rr = R * rng.uniform(0.86, 0.93)
        ctx.line_to(cx + rr * math.cos(a), cy + rr * math.sin(a))
    ctx.close_path()
    ctx.fill()

    # core
    core = rng.uniform(0.09, 0.15) * R
    setc(ctx, BLACK)
    ctx.arc(cx, cy, core, 0, 2 * math.pi)
    ctx.fill()
    setc(ctx, WHITE)
    ctx.set_line_width(2)
    ctx.arc(cx, cy, core * 0.65, 0, 2 * math.pi)
    ctx.stroke()
    ctx.arc(cx, cy, core * 0.25, 0, 2 * math.pi)
    ctx.fill()
    for i in range(8):
        a = i * math.pi / 4
        ctx.arc(cx + core * 0.82 * math.cos(a), cy + core * 0.82 * math.sin(a), 1.8, 0, 2 * math.pi)
        ctx.fill()

    # main spokes (kept white across all rings)
    n_spokes = rng.choice([3, 4, 5, 6, 8])
    off = rng.uniform(0, 2 * math.pi)
    spokes = [off + i * 2 * math.pi / n_spokes for i in range(n_spokes)]
    spoke_half = 7 / R

    def on_spoke(a, half_width):
        for s in spokes:
            d = (a - s + math.pi) % (2 * math.pi) - math.pi
            if abs(d) < half_width:
                return True
        return False

    # rings
    r = core + 6
    while r < R:
        rw = min(rng.choice([12, 16, 20, 26, 32]), R - r)
        if rw < 6:
            break
        r_out = r + rw
        kind = rng.random()
        if kind < 0.12:
            # thin ring road with beads
            setc(ctx, BLACK)
            ctx.set_line_width(1.4)
            ctx.arc(cx, cy, r + rw / 2, 0, 2 * math.pi)
            ctx.stroke()
            for i in range(int(r / 6)):
                a = i * 2 * math.pi / int(r / 6)
                ctx.arc(cx + (r + rw / 2) * math.cos(a), cy + (r + rw / 2) * math.sin(a), 2, 0, 2 * math.pi)
                ctx.fill()
        else:
            target = rng.choice([10, 14, 20, 30, 45])
            n = max(6, int(2 * math.pi * r / target))
            gap = 3.0 / ((r + r_out) / 2)
            for i in range(n):
                a0 = i * 2 * math.pi / n + gap / 2
                a1 = (i + 1) * 2 * math.pi / n - gap / 2
                if on_spoke((a0 + a1) / 2, 8.0 / r):
                    continue
                if rng.random() < 0.08:
                    continue
                style = rng.random()
                ro = r_out + (rw * rng.uniform(-0.5, 0.6) if r_out > R * 0.85 else 0)
                annular_segment(ctx, cx, cy, r, ro, a0, a1)
                if style < 0.12:  # hatched (radial lines)
                    setc(ctx, BLACK)
                    ctx.set_line_width(1.4)
                    ctx.stroke()
                    ctx.set_line_width(1)
                    k = max(2, int((a1 - a0) * r / 4))
                    for j in range(1, k):
                        a = a0 + (a1 - a0) * j / k
                        ctx.move_to(cx + r * math.cos(a), cy + r * math.sin(a))
                        ctx.line_to(cx + ro * math.cos(a), cy + ro * math.sin(a))
                    ctx.stroke()
                else:
                    setc(ctx, BLACK)
                    ctx.fill()
                    setc(ctx, WHITE)
                    ctx.set_line_width(1.2)
                    if style < 0.4 and rw > 10:
                        annular_segment(ctx, cx, cy, r + 3, ro - 3, a0 + 2.5 / r, a1 - 2.5 / r)
                        ctx.stroke()
                    elif style < 0.6:
                        am = (a0 + a1) / 2
                        rm = (r + ro) / 2
                        ctx.arc(cx + rm * math.cos(am), cy + rm * math.sin(am), 1.6, 0, 2 * math.pi)
                        ctx.fill()
                    elif style < 0.75:
                        ctx.arc(cx, cy, (r + ro) / 2, a0 + 2 / r, a1 - 2 / r)
                        ctx.stroke()
        r = r_out + rng.choice([3, 3, 4, 7])

    # spoke centre lines
    setc(ctx, BLACK)
    ctx.set_line_width(1)
    for s in spokes:
        ctx.move_to(cx + core * math.cos(s), cy + core * math.sin(s))
        ctx.line_to(cx + R * math.cos(s), cy + R * math.sin(s))
    ctx.stroke()


# ---------------------------------------------------------------- spacecraft
def shuttle(ctx, x, y, s, a):
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(a)
    ctx.scale(s, s)
    setc(ctx, WHITE)
    ctx.move_to(-20, -5); ctx.line_to(15, -5); ctx.line_to(28, 0)
    ctx.line_to(15, 5); ctx.line_to(-20, 5); ctx.close_path()
    ctx.fill_preserve()
    setc(ctx, BLACK)
    ctx.set_line_width(1.5 / s)
    ctx.stroke()
    ctx.move_to(-15, -5); ctx.line_to(-22, -16); ctx.line_to(2, -5)
    ctx.move_to(-15, 5); ctx.line_to(-22, 16); ctx.line_to(2, 5)
    ctx.stroke()
    ctx.rectangle(-24, -3, 4, 6)
    ctx.fill()
    ctx.restore()


def station(ctx, x, y, s, rng):
    """ISS-style truss with panel wings."""
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(rng.uniform(-0.6, 0.6))
    L = 160 * s
    setc(ctx, BLACK)
    ctx.set_line_width(3)
    ctx.move_to(-L, 0); ctx.line_to(L, 0)
    ctx.stroke()
    for sx in (-L, -L * 0.55, L * 0.55, L):
        for sy in (-1, 1):
            hatch_rect(ctx, sx - 14 * s, sy * 8 - (60 * s if sy < 0 else 0), 28 * s, 60 * s, gap=3, vertical=True)
    detail_block(ctx, -18 * s, -10 * s, 36 * s, 20 * s, rng)
    ctx.restore()


# ---------------------------------------------------------------- main
def main():
    # default seed: current UTC time, e.g. 20261119215700
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else int(datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"))
    out = sys.argv[2] if len(sys.argv) > 2 else f"space_city_{seed}.png"
    rng = random.Random(seed)

    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, W, H)
    ctx = cairo.Context(surf)
    setc(ctx, WHITE)
    ctx.paint()

    land, edge = make_skyline(rng)
    background_grid(ctx, rng, land)

    # hubs: place with rejection sampling, big ones first
    hubs = []
    radii = sorted([rng.uniform(260, 420) for _ in range(3)] + [rng.uniform(90, 200) for _ in range(rng.randint(3, 6))], reverse=True)
    for R in radii:
        for _ in range(300):
            x, y = rng.uniform(-R * 0.3, W + R * 0.3), rng.uniform(R * 0.4, H + R * 0.2)
            if land(x, y - R * 0.3) and all(math.hypot(x - hx, y - hy) > (R + hr) * 0.8 for hx, hy, hr in hubs):
                hubs.append((x, y, R))
                break
    # draw small first so big ones overlap them
    for x, y, R in sorted(hubs, key=lambda h: h[2]):
        hub(ctx, x, y, R, rng)

    # spacecraft in the sky
    station(ctx, W * 0.17, H * 0.06, 1.0, rng)
    for _ in range(rng.randint(2, 4)):
        shuttle(ctx, rng.uniform(80, W * 0.35), rng.uniform(80, H * 0.18), rng.uniform(1.2, 2.2), rng.uniform(-1, 1))

    # border margin like a print
    setc(ctx, WHITE)
    m = 30
    ctx.rectangle(0, 0, W, m); ctx.rectangle(0, H - m, W, m)
    ctx.rectangle(0, 0, m, H); ctx.rectangle(W - m, 0, m, H)
    ctx.fill()

    surf.write_to_png(out)
    print(out)


if __name__ == "__main__":
    main()
