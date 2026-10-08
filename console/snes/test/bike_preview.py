"""Pictures of the bike as the SNES draws it (bikefix.py) next to the
original game's look at 0.4 (bikemodel.py), for states of the bike from a
DUMP of the PC reference tool (pcref) or for test poses.

  bike_preview.py LGR GEN_DIR OUT.png [DUMP FRAME...]

Without a DUMP it draws the poses of test/snes_bike.c (bike_poses.py).
Prints how many pixels differ.
"""

import math
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))

import bikefix
import bikemodel as bm
from lgr import Lgr

PPM = 4915 / 256
BG = (110, 140, 200)


def read_dump(path):
    rows, cols = {}, None
    for line in open(path):
        if line.startswith('#'):
            cols = line[1:].split()
            continue
        d = dict(zip(cols, [float(x) for x in line.split()]))
        rows[int(d['frame'])] = d
    return rows


def state_of(d):
    return bm.State(body=(d['body_x'], d['body_y']), body_a=d['body_a'],
                    wheel0=(d['wheel2_x'], d['wheel2_y']), wheel0_a=d['wheel2_a'],
                    wheel1=(d['wheel4_x'], d['wheel4_y']), wheel1_a=d['wheel4_a'],
                    rider=(d['rider_x'], d['rider_y']), head=(d['head_x'], d['head_y']),
                    turned=bool(d['hatra_f']), turn=d['turn_f'], volt=d['volt'],
                    volt1=bool(d['volt1']))


def place(st, w=96, h=96):
    """An origin and a camera that show the bike in the middle of a w x h
    picture."""
    org = (int(math.floor(st.body[0]) - 50) * 65536, int(math.ceil(st.body[1]) + 50) * 65536)
    cx = int((st.body[0] - org[0] / 65536) * PPM) - w // 2
    cy = int((org[1] / 65536 - st.body[1]) * PPM) - h // 2
    return org, (cx, cy)


def pair(pics, data, st, w=96, h=96, bike=None):
    org, cam = place(st, w, h)
    x0 = org[0] / 65536 + cam[0] / PPM
    y1 = org[1] / 65536 - cam[1] / PPM
    ref = bm.render_reference(pics, bm.kibike(st), x0, y1, w, h, bg=BG)
    fx = bikefix.State.from_model(st, org, cam)
    if bike is None:
        bike = bikefix.Bike(data)
        bike.frame(fx)              # all parts loaded
        bike.frame(fx)
    oam, _, _ = bike.frame(fx)
    sn = bikefix.preview(data, oam, (w, h))
    out = np.empty((h, w, 3), np.uint8)
    out[:] = BG
    m = sn[..., 3] > 0
    out[m] = sn[m][:, :3]
    return ref, out


def main():
    lgr = Lgr(sys.argv[1])
    pics = bm.Pictures(lgr)
    data = bikefix.Data(sys.argv[2])
    states = []
    if len(sys.argv) > 4:
        dump = read_dump(sys.argv[4])
        frames = [int(f) for f in sys.argv[5:]] or sorted(dump)
        states = [state_of(dump[f]) for f in frames]
    else:
        import bike_poses
        states = bike_poses.model_states()
    w = h = 80
    cols = 6
    rows = (len(states) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * (2 * w + 8), rows * (h + 4)), (40, 40, 40))
    for n, st in enumerate(states):
        ref, sn = pair(pics, data, st, w, h)
        im = np.concatenate([ref, np.zeros((h, 4, 3), np.uint8), sn], axis=1)
        sheet.paste(Image.fromarray(im), ((n % cols) * (2 * w + 8), (n // cols) * (h + 4)))
    sheet = sheet.resize((sheet.width * 3, sheet.height * 3), Image.NEAREST)
    sheet.save(sys.argv[3])


if __name__ == '__main__':
    main()
