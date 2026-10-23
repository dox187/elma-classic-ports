#!/usr/bin/env bash
# Reproduce the thumbnail from the cropped game frame and original splash title.
set -euo pipefail
assets="$(cd -- "$(dirname -- "$0")/../assets" && pwd)"
magick "$assets/icon-gameplay.png" -resize 320x176 \
    \( "$assets/icon-title.png" -resize 114x70 \) \
    -geometry +8+5 -composite -strip "PNG24:$assets/ICON0.PNG"
