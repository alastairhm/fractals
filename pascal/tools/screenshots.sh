#!/bin/sh
# Rebuild every program and regenerate the README screenshots.
# Run from anywhere: tools/screenshots.sh
# Extra arguments are passed to ansi2png.py, e.g. --font /path/to/Mono.ttf
set -eu

cd "$(dirname "$0")/.."
mkdir -p screenshots

make -s all > /dev/null   # fpc prints mandelbrot5's harmless crtbeginS.o warnings on stdout

RENDER_OPTS="$*"

# shot OUT.png command [args...]
shot() {
    out=$1; shift
    # RENDER_OPTS is deliberately unquoted so it splits into separate options
    python3 tools/ansi2png.py $RENDER_OPTS "screenshots/$out" -- "$@"
}

shot mandelbrot.png           ./mandelbrot  100 36
shot mandelbrot2.png          ./mandelbrot2 100 36
shot mandelbrot3.png          ./mandelbrot3 100 36 500
shot mandelbrot4.png          ./mandelbrot4 120 36 1000
shot mandelbrot4-seahorse.png ./mandelbrot4 120 36 2000 -0.7436 0.1318 200
# Piped output, so mandelbrot5 draws one frame instead of going interactive
shot mandelbrot5-filaments.png ./mandelbrot5 120 36 3000 -0.1011 0.9563 300
