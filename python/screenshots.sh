#!/bin/sh
# Regenerate the README example images for the Python scripts, in
# python/screenshots/ and the screenshots/ folders of mazes/, glyphs/,
# space_city/ and City Map Generator/.
# Run from anywhere: python/screenshots.sh
# Needs python3 with Pillow and NumPy, plus ffmpeg. Everything from the zoom
# stills onwards needs the packages in requirements.txt,
# taken from python/.venv if it exists.
set -eu

cd "$(dirname "$0")"
mkdir -p screenshots
cd screenshots

# run SCRIPT OUTPUT-PATTERN NEW-NAME [args...]: render, then rename the output
run() {
    script=$1 out=$2 name=$3; shift 3
    python3 "../$script" "$@" > /dev/null
    mv "$out" "$name"
    echo "screenshots/$name"
}

run koch_riff.py       koch_17.png                   koch.png        --size 720 17
run koch_riff.py       sheet_1-2-3-4-5-6-7-8-9.png   koch-sheet.png  --sheet --size 1080 1 2 3 4 5 6 7 8 9
run pythagoras_tree.py tree_6.png                    tree.png        --size 720 6
run pythagoras_tree.py tree_9.gif                    tree-grow.gif   --gif --size 540 9
run attractor.py       attractor_14.png              attractor.png   --size 720 14

# attractor.py --sheet always writes a .gif as well; keep only the still
python3 ../attractor.py --sheet --size 720 11 13 14 15 17 18 2 5 6 > /dev/null
mv sheet_attractor_11-13-14-15-17-18-2-5-6.png attractor-sheet.png
rm sheet_attractor_11-13-14-15-17-18-2-5-6.gif
echo "screenshots/attractor-sheet.png"

run attractor.py       attractor_11.gif              attractor-grow.gif --gif --size 540 11

# zoom_video.py needs Numba, so prefer the venv's python
zpy=python3
venv="$(cd .. && pwd)/.venv/bin/python"
if [ -x "$venv" ]; then zpy=$venv; fi
"$zpy" ../zoom_video.py --preview 0 0.35 0.8 1 > /dev/null
for u in 0.00 0.35 0.80 1.00; do
    mv "preview_$u.png" "zoom-$u.png"
    echo "screenshots/zoom-$u.png"
done

# The rest also need packages from requirements.txt, so use the same python.
# shrink FILE WIDTH: scale an image down to WIDTH pixels wide, in place
shrink() {
    "$zpy" - "$1" "$2" <<'PY'
import sys
from PIL import Image
path, w = sys.argv[1], int(sys.argv[2])
im = Image.open(path)
im.resize((w, round(im.height * w / im.width)), Image.LANCZOS).save(path, optimize=True)
PY
}

"$zpy" ../triangle_flake.py 3 > /dev/null
mv flake_3.png flake.png
"$zpy" ../triangle_flake.py --gif 8 > /dev/null
mv flake_8.gif flake-grow.gif
"$zpy" ../mandelbrot_numba.py > /dev/null
mv mandelbrot.png mandelbrot-numba.png
shrink mandelbrot-numba.png 960
for mode in relief lines litho; do
    "$zpy" ../fractal_tile.py --mode $mode --preview -o tile.stl > /dev/null
    mv tile_heights.png "tile-$mode.png"
    rm tile.stl
done

# pixel_resolve.py writes MP4s; turn short ones into GIFs for the README
pixel_gif() {
    name=$1; shift
    "$zpy" ../pixel_resolve.py --fps 8 --draw 4 --hold 4 --final 24 "$@" -o tmp.mp4 > /dev/null
    ffmpeg -y -loglevel error -i tmp.mp4 -vf "scale=400:-1:flags=area,split[a][b];[a]palettegen=max_colors=64[p];[b][p]paletteuse=dither=none" "$name.gif"
    rm tmp.mp4
}
pixel_gif pixel-resolve
pixel_gif pixel-resolve-quadtree --mode quadtree
for f in flake.png flake-grow.gif mandelbrot-numba.png tile-relief.png tile-lines.png \
         tile-litho.png pixel-resolve.gif pixel-resolve-quadtree.gif; do
    echo "screenshots/$f"
done

# Generative art in the sibling folders, each with its own screenshots/
cd ../..
mkdir -p mazes/screenshots glyphs/screenshots space_city/screenshots "City Map Generator/screenshots"

for algo in backtracker aldous wilson; do
    "$zpy" mazes/maze.py --algo $algo --seed 3 --dpi 60 --out mazes/screenshots/maze-$algo.png
done
"$zpy" mazes/maze.py --style lines --palette night --seed 3 --dpi 60 --out mazes/screenshots/maze-lines.png
"$zpy" mazes/cat_maze.py --seed 11 --scale 20 -o mazes/screenshots/cat-maze.png

city="City Map Generator"
"$zpy" "$city/citymap.py" --seed 42 --name Dishforth --dpi 60 --out "$city/screenshots/city.png"
"$zpy" "$city/citymap.py" --seed 7 --name Ravenhythe --palette night --dpi 60 --out "$city/screenshots/city-night.png"

g=glyphs/screenshots
"$zpy" glyphs/glyphs.py --seed 42 --lines --out $g/tmp.svg --png $g/glyphs.png
"$zpy" glyphs/glyphs.py --seed 7 --outline --out $g/tmp.svg --png $g/glyphs-outline.png
rm $g/tmp.svg
shrink $g/glyphs.png 800
shrink $g/glyphs-outline.png 800

"$zpy" space_city/space_city.py 42 space_city/screenshots/space-city.png
shrink space_city/screenshots/space-city.png 800
