# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Four standalone Free Pascal programs that render the Mandelbrot set to the terminal. Each `mandelbrotN.pas` is a self-contained progression on the previous one (plain ASCII → log-scaled ASCII gradient → 24-bit coloured ASCII with smooth escape counts → truecolor `▀` half blocks with pan/zoom and auto contrast). The README has the full feature table, argument reference and an explanation of the algorithms.

## Commands

```sh
fpc -O2 mandelbrot4.pas                          # build one program (binary lands next to the source)
for f in mandelbrot*.pas; do fpc -O2 "$f"; done  # build all
./mandelbrot4 -h                                 # every program supports -h / --help
tools/screenshots.sh                             # rebuild all + regenerate screenshots/*.png
tools/ansi2png.py out.png -- ./mandelbrot4 160 50 3000 -0.1011 0.9563 300   # render any command to PNG
```

There is no test suite, linter or build system. Verify changes by building and running the program, including edge-case arguments (e.g. width/height of 1, zoom ≤ 0, non-numeric input — arguments fall back to defaults via `StrToIntDef`/`StrToFloatDef`). Binaries and `*.o`/`*.ppu` build output are gitignored.

The screenshot tools need Python with Pillow (`python-pillow`) and default to `/usr/share/fonts/TTF/JetBrainsMono-Regular.ttf`.

## Architecture notes

- **No shared unit.** Each program is deliberately self-contained: argument parsing (`IntArg`/`FloatArg`/`ArgOr`), `-h`/`--help` handling and the help text are duplicated in every file. A fix to common behaviour (argument validation, help, divide-by-zero guards) usually needs applying to all four files.
- All programs use `{$mode objfpc}{$H+}`, take positional arguments only, and clamp/default bad values rather than erroring. `FloatArg` forces `.` as the decimal separator regardless of locale.
- `mandelbrot3` and `mandelbrot4` share the smooth-colouring approach: escape radius 256 (`Bailout2`), fractional count `n + 1 − log₂(log|z|)`, cosine `Gradient`. `mandelbrot4` additionally does two passes — compute every pixel into `Values` (−1 = inside), then normalise between the min/max visible values before drawing — and only emits SGR codes when the fg/bg colour changes.
- `mandelbrot4` maps two vertical pixels per terminal cell (fg = top, bg = bottom of `U+2580`), so pixel height is `2 × rows` and pixels are square (`PixelSize` derived from width; `BaseSpan` = 3.5 real units at zoom 1).
- `tools/ansi2png.py` only understands the SGR codes these programs emit (`38;2;r;g;b`, `48;2;r;g;b`, `0`) and draws `▀` cells as two filled rectangles. If a program starts emitting other escape sequences, update the parser.

## Keeping docs in sync

The README's screenshot section shows the exact commands used in `tools/screenshots.sh`; if output or arguments change, regenerate the screenshots and keep the README commands, usage tables and each program's header comment / `ShowHelp` text consistent.
