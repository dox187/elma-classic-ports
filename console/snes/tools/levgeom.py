"""The pixels of a level on the SNES, shared by every converter and by the
program (build/gen/levels.h).

The physics keeps positions in meters, y up, as 16.16 fixed point. The
level is drawn in level pixels (LPX): x to the right, y down, from an
origin to the left of and above the level, PX_PER_M pixels a meter:

  px = (x - org_x) * PX_PER_M      py = (org_y - y) * PX_PER_M

PX_PER_M is 4915/256 (19.199...), 0.4 of the original game's 48, so that a
16.16 position becomes pixels with a multiplication by 4915 and a shift.
"""

import math

from config import SCREEN_W, SCREEN_H

PX_PER_M_NUM = 4915            # pixels a meter, times 256
PX_PER_M = PX_PER_M_NUM / 256.0
# Room around the level, in meters (a screen is 13.3 m wide):
MARGIN_M = 8.0


def bounds(lev):
    """min_x, min_y, max_x, max_y of the polygons, meters, y up."""
    xs = [p[0] for _, poly in lev.polygons for p in poly]
    ys = [p[1] for _, poly in lev.polygons for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def origin(lev):
    """org_x, org_y of the level in 16.16 fixed point: a whole number of
    meters, MARGIN_M or more outside the polygons."""
    x0, _, _, y1 = bounds(lev)
    ox = math.floor(x0 - MARGIN_M)
    oy = math.ceil(y1 + MARGIN_M)
    return ox * 65536, oy * 65536


def size_px(lev):
    """Width and height of the level in level pixels, margins included,
    rounded up to whole tiles (8 pixels)."""
    ox, oy = origin(lev)
    _, y0, x1, _ = bounds(lev)
    w = (x1 + MARGIN_M - ox / 65536.0) * PX_PER_M
    h = (oy / 65536.0 - (y0 - MARGIN_M)) * PX_PER_M
    return int(math.ceil(w / 8)) * 8, int(math.ceil(h / 8)) * 8


def to_px(lev, x, y):
    """Level pixels of a point in meters (floats), as the program computes
    them from 16.16."""
    ox, oy = origin(lev)
    fx = int(round(x * 65536)) - ox
    fy = oy - int(round(y * 65536))
    return (fx * PX_PER_M_NUM) / (256 * 65536.0), (fy * PX_PER_M_NUM) / (256 * 65536.0)
