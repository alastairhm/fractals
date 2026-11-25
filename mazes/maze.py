#!/usr/bin/env python3
"""
maze.py - random-walk maze posters, in the same style as citymap.py.

    python maze.py                                   # backtracker, 30x45, flood style
    python maze.py --algo wilson --size 40 60 --seed 3
    python maze.py --algo all --style flood          # one poster per algorithm
    python maze.py --palette night --no-solution

Algorithms (all make "perfect" mazes: exactly one route between any two cells)
  backtracker   random walk that backs up when stuck -> long twisty corridors
  aldous        pure random walk, carve on first visit -> unbiased, slow
  wilson        loop-erased random walks -> unbiased, quicker than aldous

Styles
  lines   walls drawn as lines, solution in red
  flood   corridors coloured by distance from the entrance

Needs: numpy, matplotlib
"""
import argparse
from collections import deque

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap

PALETTES = {
    "classic": dict(bg="#dccb9c", wall="#353b3c", path="#e2432b", text="#353b3c"),
    "night":   dict(bg="#1f2a36", wall="#c9d1d9", path="#f2b134", text="#c9d1d9"),
    "mint":    dict(bg="#e6efe9", wall="#2f3e46", path="#e76f51", text="#2f3e46"),
    "blush":   dict(bg="#f4e1d2", wall="#3d3b40", path="#3a6ea5", text="#3d3b40"),
}
DIRS = [(0, 1), (1, 0), (0, -1), (-1, 0)]  # (dx, dy): N, E, S, W


class Maze:
    """Grid of w x h cells. open_[x, y, d] is True when there's no wall that way."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.open_ = np.zeros((w, h, 4), dtype=bool)

    def inside(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h

    def neighbours(self, x, y):
        for d, (dx, dy) in enumerate(DIRS):
            if self.inside(x + dx, y + dy):
                yield d, x + dx, y + dy

    def carve(self, x, y, d):
        dx, dy = DIRS[d]
        self.open_[x, y, d] = True
        self.open_[x + dx, y + dy, (d + 2) % 4] = True


# --------------------------------------------------------------------------- algorithms
def backtracker(m, rng):
    seen = np.zeros((m.w, m.h), bool)
    stack = [(int(rng.integers(m.w)), int(rng.integers(m.h)))]
    seen[stack[0]] = True
    while stack:
        x, y = stack[-1]
        options = [(d, nx, ny) for d, nx, ny in m.neighbours(x, y) if not seen[nx, ny]]
        if not options:
            stack.pop()
            continue
        d, nx, ny = options[rng.integers(len(options))]
        m.carve(x, y, d)
        seen[nx, ny] = True
        stack.append((nx, ny))


def aldous_broder(m, rng):
    seen = np.zeros((m.w, m.h), bool)
    x, y = int(rng.integers(m.w)), int(rng.integers(m.h))
    seen[x, y] = True
    left = m.w * m.h - 1
    while left:
        opts = list(m.neighbours(x, y))
        d, nx, ny = opts[rng.integers(len(opts))]
        if not seen[nx, ny]:
            m.carve(x, y, d)
            seen[nx, ny] = True
            left -= 1
        x, y = nx, ny


def wilson(m, rng):
    in_maze = np.zeros((m.w, m.h), bool)
    in_maze[rng.integers(m.w), rng.integers(m.h)] = True
    cells = [(x, y) for x in range(m.w) for y in range(m.h)]
    rng.shuffle(cells)
    for start in cells:
        if in_maze[start]:
            continue
        # random walk until we hit the maze, remembering only the last exit
        # from each cell - that is the loop erasure
        exit_dir = {}
        x, y = start
        while not in_maze[x, y]:
            opts = list(m.neighbours(x, y))
            d, nx, ny = opts[rng.integers(len(opts))]
            exit_dir[(x, y)] = d
            x, y = nx, ny
        x, y = start
        while not in_maze[x, y]:
            d = exit_dir[(x, y)]
            m.carve(x, y, d)
            in_maze[x, y] = True
            x, y = x + DIRS[d][0], y + DIRS[d][1]


ALGOS = {"backtracker": backtracker, "aldous": aldous_broder, "wilson": wilson}
ALGO_TITLES = {"backtracker": "Backtracker", "aldous": "Aldous–Broder", "wilson": "Wilson"}


# --------------------------------------------------------------------------- solving
def distances(m, start):
    dist = np.full((m.w, m.h), -1)
    prev = {}
    dist[start] = 0
    q = deque([start])
    while q:
        x, y = q.popleft()
        for d, nx, ny in m.neighbours(x, y):
            if m.open_[x, y, d] and dist[nx, ny] < 0:
                dist[nx, ny] = dist[x, y] + 1
                prev[(nx, ny)] = (x, y)
                q.append((nx, ny))
    return dist, prev


def solve(m, start, end):
    _, prev = distances(m, start)
    path = [end]
    while path[-1] != start:
        path.append(prev[path[-1]])
    return path[::-1]


# --------------------------------------------------------------------------- render
def render(m, title, pal, out, style="lines", solution=True, dpi=200):
    start, end = (0, m.h - 1), (m.w - 1, 0)  # top-left in, bottom-right out
    m.open_[start[0], start[1], 0] = True     # gap in top wall
    m.open_[end[0], end[1], 2] = True         # gap in bottom wall

    fig = plt.figure(figsize=(8, 12), facecolor=pal["bg"])
    # keep cells square inside the poster's map box
    box_w, box_h = 0.84 * 8, 0.78 * 12
    s = min(box_w / m.w, box_h / m.h)
    aw, ah = m.w * s / 8, m.h * s / 12
    ax = fig.add_axes([0.5 - aw / 2, 0.17 + (0.78 - ah) / 2, aw, ah])
    ax.set_xlim(-0.05, m.w + 0.05)
    ax.set_ylim(-0.05, m.h + 0.05)
    ax.set_aspect("equal")
    ax.axis("off")

    lw = max(0.7, 70 / max(m.w, m.h))  # thinner walls for bigger mazes

    if style == "flood":
        dist, _ = distances(m, start)
        cmap = LinearSegmentedColormap.from_list("p", [pal["path"], pal["bg"], pal["wall"]])
        ax.imshow(dist.T, origin="lower", extent=(0, m.w, 0, m.h), cmap=cmap,
                  interpolation="nearest", zorder=0)

    walls = []
    for x in range(m.w):
        for y in range(m.h):
            if not m.open_[x, y, 0]:
                walls.append([(x, y + 1), (x + 1, y + 1)])
            if not m.open_[x, y, 1]:
                walls.append([(x + 1, y), (x + 1, y + 1)])
            if y == 0 and not m.open_[x, y, 2]:
                walls.append([(x, 0), (x + 1, 0)])
            if x == 0:
                walls.append([(0, y), (0, y + 1)])
    ax.add_collection(LineCollection(walls, colors=pal["wall"], linewidths=lw,
                                     capstyle="round", zorder=2))

    if solution:
        path = solve(m, start, end)
        xs = [p[0] + 0.5 for p in path]
        ys = [p[1] + 0.5 for p in path]
        xs = [xs[0]] + xs + [xs[-1]]
        ys = [m.h + 0.4] + ys + [-0.4]
        ax.plot(xs, ys, color=pal["path"] if style == "lines" else pal["wall"],
                lw=lw * 2.6, solid_capstyle="round", solid_joinstyle="round", zorder=3)

    fig.text(0.5, 0.075, title, ha="center", va="center", fontsize=40,
             fontweight="bold", color=pal["text"], family="DejaVu Sans")
    fig.savefig(out, dpi=dpi, facecolor=pal["bg"])
    plt.close(fig)


def make_maze(algo, w, h, seed):
    rng = np.random.default_rng(seed)
    m = Maze(w, h)
    ALGOS[algo](m, rng)
    return m


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Random-walk maze posters")
    ap.add_argument("--algo", default="backtracker", choices=[*ALGOS, "all"])
    ap.add_argument("--size", type=int, nargs=2, default=[30, 45], metavar=("W", "H"))
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--palette", default="classic", choices=PALETTES)
    ap.add_argument("--style", default="flood", choices=["lines", "flood"])
    ap.add_argument("--no-solution", action="store_true")
    ap.add_argument("--title", default=None)
    ap.add_argument("--out", default="maze.png")
    ap.add_argument("--dpi", type=int, default=200)
    a = ap.parse_args()

    algos = list(ALGOS) if a.algo == "all" else [a.algo]
    for algo in algos:
        m = make_maze(algo, *a.size, a.seed)
        out = a.out if len(algos) == 1 else a.out.replace(".png", f"_{algo}.png")
        render(m, a.title or ALGO_TITLES[algo], PALETTES[a.palette], out,
               a.style, not a.no_solution, a.dpi)
        print(f"{algo} -> {out}")
