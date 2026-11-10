#!/usr/bin/env python3
"""Render a program's ANSI truecolor terminal output to a PNG.

Runs the command, parses its 24-bit SGR colour codes (38;2 / 48;2 / 0) and
draws each character cell with a monospace font. Upper half block cells
(U+2580) are drawn as two solid rectangles so half-block output stays crisp.

usage: ansi2png.py [--font PATH] [--size PX] OUT.png -- command [args...]

Requires Pillow (python-pillow on Arch).
"""
import argparse
import re
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

DEFAULT_FONT = "/usr/share/fonts/TTF/JetBrainsMono-Regular.ttf"
BG = (24, 24, 32)        # terminal background
FG = (205, 214, 244)     # default foreground
PAD = 16
HALF = "▀"


def parse(text):
    """Split ANSI text into rows of (char, fg, bg) cells."""
    token = re.compile(r"\x1b\[([0-9;]*)m|(.)", re.S)
    rows = []
    for line in text.split("\n"):
        if line == "":
            continue
        fg, bg = FG, None
        cells = []
        for m in token.finditer(line):
            if m.group(2) is not None:
                cells.append((m.group(2), fg, bg))
                continue
            p = [int(x) for x in m.group(1).split(";") if x] or [0]
            i = 0
            while i < len(p):
                if p[i] == 0:
                    fg, bg = FG, None
                    i += 1
                elif p[i] in (38, 48) and i + 4 < len(p) and p[i + 1] == 2:
                    c = tuple(p[i + 2:i + 5])
                    if p[i] == 38:
                        fg = c
                    else:
                        bg = c
                    i += 5
                else:
                    i += 1
        rows.append(cells)
    return rows


def render(rows, font):
    asc, desc = font.getmetrics()
    cw = round(font.getlength("M"))
    ch = asc + desc + 2

    w = max(len(r) for r in rows)
    img = Image.new("RGB", (w * cw + 2 * PAD, len(rows) * ch + 2 * PAD), BG)
    d = ImageDraw.Draw(img)
    for y, row in enumerate(rows):
        for x, (c, fg, bg) in enumerate(row):
            x0, y0 = PAD + x * cw, PAD + y * ch
            if c == HALF:
                mid = y0 + ch // 2
                d.rectangle([x0, y0, x0 + cw - 1, mid - 1], fill=fg)
                d.rectangle([x0, mid, x0 + cw - 1, y0 + ch - 1], fill=bg or BG)
            else:
                if bg:
                    d.rectangle([x0, y0, x0 + cw - 1, y0 + ch - 1], fill=bg)
                if c != " ":
                    d.text((x0, y0 + 1), c, font=font, fill=fg)
    return img


def main():
    if "--" not in sys.argv:
        sys.exit("usage: ansi2png.py [--font PATH] [--size PX] OUT.png -- command [args...]")
    split = sys.argv.index("--")
    ap = argparse.ArgumentParser(description="Render ANSI terminal output to PNG.")
    ap.add_argument("out", help="output PNG path")
    ap.add_argument("--font", default=DEFAULT_FONT, help="monospace TTF/OTF font")
    ap.add_argument("--size", type=int, default=15, help="font size in pixels")
    args = ap.parse_args(sys.argv[1:split])
    cmd = sys.argv[split + 1:]
    if not cmd:
        sys.exit("ansi2png.py: no command given after --")

    text = subprocess.run(cmd, capture_output=True, check=True).stdout.decode("utf-8")
    rows = parse(text)
    if not rows:
        sys.exit("ansi2png.py: command produced no output")

    img = render(rows, ImageFont.truetype(args.font, args.size))
    img.save(args.out, optimize=True)
    print(f"{args.out} {img.size[0]}x{img.size[1]}")


if __name__ == "__main__":
    main()
