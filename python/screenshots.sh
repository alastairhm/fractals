#!/bin/sh
# Regenerate the README example images in python/screenshots/.
# Run from anywhere: python/screenshots.sh
# Needs python3 with Pillow and NumPy; the zoom stills also need Numba,
# taken from python/.venv if it exists (see requirements.txt).
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
