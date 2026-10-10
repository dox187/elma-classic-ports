"""The poses of the bike and the objects of test/snes_bike.c: writes
build/gen/bike_poses.h and bike_poses.asm.

  bike_poses.py ELMA_RES build/gen/bike_poses

The bike stands at the same place of level 1 (Warm Up) in every pose: at
rest, turned, at many angles, while turning, volting, with the rider and
the wheels moved, and near the edges of the screen; objects of every kind
around it.

With BIKE_DUMP=FILE (a DUMP of the PC reference tool, pcref) and
BIKE_LEVEL=N (its level) the poses are the bike of every frame of that
ride instead, one frame each, with the camera of the original game and the
objects of the level.
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))

import bikemodel as bm
import bikefix

DUMP = os.environ.get('BIKE_DUMP')
HOLD = 1 if DUMP else 3      # frames a pose
LEVEL = int(os.environ.get('BIKE_LEVEL', '0')) if DUMP else 0
BASE = (30.0, -10.0)         # where the bike stands, meters from the origin
PPM = 4915 / 256

# Objects around the bike (type, anim, active, dx, dy meters):
OBJECTS = [
    (2, 0, 1, -4.0, 1.0), (2, 1, 1, 3.5, 2.0), (2, 0, 0, 1.0, 3.0),
    (3, 0, 1, 5.0, -2.0), (1, 0, 1, -5.5, -2.5), (4, 0, 1, 0.0, -1.5),
    (2, 1, 1, -6.4, 4.0), (2, 0, 1, 40.0, 0.0),
]


def level(res_path):
    import elmadata
    res = elmadata.Resource(res_path)
    return elmadata.internal_levels(res)[LEVEL]


def origin(res_path):
    import levgeom
    return levgeom.origin(level(res_path))


def dump_states():
    """(bikemodel.State, camera: the world point of the top left pixel)
    of every frame of the DUMP."""
    out = []
    cols = None
    for line in open(DUMP):
        if line.startswith('#'):
            cols = line[1:].split()
            continue
        d = dict(zip(cols, [float(x) for x in line.split()]))
        st = bm.State(body=(d['body_x'], d['body_y']), body_a=d['body_a'],
                      wheel0=(d['wheel2_x'], d['wheel2_y']), wheel0_a=d['wheel2_a'],
                      wheel1=(d['wheel4_x'], d['wheel4_y']), wheel1_a=d['wheel4_a'],
                      rider=(d['rider_x'], d['rider_y']), head=(d['head_x'], d['head_y']),
                      turned=bool(d['hatra_f']), turn=d['turn_f'], volt=d['volt'],
                      volt1=bool(d['volt1']))
        # The camera of kirakegyjatekost (Mo_bal 2 m, Mo_dx 9.33 m), the bike
        # in the middle vertically:
        x0 = d['body_x'] - (2.0 + d['baljobb_h'] * (640 / 48 - 4.0))
        y1 = d['body_y'] + 224 / PPM / 2
        out.append((st, (x0, y1)))
    first, last = [int(x) for x in os.environ.get('BIKE_FRAMES', '0:500').split(':')]
    return out[first:last]


def model_states():
    """(bikemodel.State, camera offset (pixels from centered)) of the
    poses, at the origin (0, 0)."""
    out = []
    rest = bm.State()

    def rotated(a, **kw):
        s = rest

        def R(p):
            return s.body + bm.rotate(p - s.body, a)
        return bm.State(body=s.body, body_a=a, wheel0=R(s.wheel[0]), wheel1=R(s.wheel[1]),
                        rider=R(s.rider), **kw)
    out.append((bm.State(), (0, 0)))
    out.append((bm.State(turned=True), (0, 0)))
    for k in range(24):
        a = k * 2 * math.pi / 24 + 0.05
        out.append((rotated(a, turned=bool(k & 1), wheel0_a=a * 3, wheel1_a=-a * 2), (0, 0)))
    for k in range(12):
        out.append((bm.State(turned=True, turn=k / 12 + 0.02), (0, 0)))
    for k in range(6):
        out.append((rotated(0.7, turned=False, turn=k / 6 + 0.04), (0, 0)))
    for v in (0.95, 0.8, 0.6, 0.4, 0.2):
        for v1 in (False, True):
            out.append((bm.State(volt=v, volt1=v1, turned=v1), (0, 0)))
    for dx, dy in ((0.1, 0.0), (-0.15, 0.05), (0.0, -0.1), (0.05, 0.1)):
        s = bm.State()
        out.append((bm.State(rider=(s.rider[0] + dx, s.rider[1] + dy)), (0, 0)))
    for d in (0.1, -0.08):
        s = bm.State()
        out.append((bm.State(wheel0=(s.wheel[0][0] + d, s.wheel[0][1] + d),
                             wheel1=(s.wheel[1][0] - d, s.wheel[1][1] + d)), (0, 0)))
    # Near the edges: the bike partly off the screen.
    for cam in ((115, 0), (-120, 0), (0, 100), (0, -96), (125, 95)):
        out.append((rotated(0.3, turned=True), cam))
    # Relative-pose cache coverage: absolute translation, fractional
    # quantization changes, wheel spin and camera motion remain visible.
    for step in range(12):
        st = bm.State(wheel0_a=step * 0.19, wheel1_a=-step * 0.23)
        st = st.moved(bm.v(step / 256.0, -step / 512.0))
        out.append((st, (step * 3 - 18, step % 3 - 1)))
    # Interpolation-like motion: each relative component changes separately
    # across subpixel boundaries, so a stale cached pose must never survive.
    for step in range(12):
        d = step / 512.0
        out.append((bm.State(body_a=step / 4096.0,
                             wheel0=(1.9 + d, 3.0 - d / 2),
                             wheel1=(3.6 - d / 3, 3.0 + d),
                             rider=(2.75 + d / 4, 4.04 - d / 3),
                             wheel0_a=step * 0.2, wheel1_a=-step * 0.1),
                    (step % 4 - 2, step % 3 - 1)))
    # Geometry samples turn/volt table indices, not the discarded low byte.
    for step in range(4):
        out.append((bm.State(turn=(0x4000 + step) / 65536.0,
                             volt=(0x8000 + step) / 65536.0,
                             volt1=True), (step, 0)))
    return out


def fixed_poses(org):
    """The poses as the program gets them (bikefix.State)."""
    out = []
    if DUMP:
        for st, (x0, y1) in dump_states():
            cam = (int(math.floor((x0 - org[0] / 65536) * PPM)),
                   int(math.floor((org[1] / 65536 - y1) * PPM)))
            out.append(bikefix.State.from_model(st, org, cam))
        return out
    for st, (cx, cy) in model_states():
        st = st.moved(bm.v(org[0] / 65536 + BASE[0], org[1] / 65536 + BASE[1]))
        px = int((st.body[0] - org[0] / 65536) * PPM)
        py = int((org[1] / 65536 - st.body[1]) * PPM)
        out.append(bikefix.State.from_model(st, org, (px - 128 + cx, py - 112 + cy)))
    return out


def objects(org, res_path=None):
    """phys_objs: (type, anim, gravity, active, x, y) in 16.16."""
    out = []
    if DUMP:
        for t, x, y, grav, anim in level(res_path).objects:
            out.append((t, anim, grav, 1, int(round(x * 65536)), int(round(y * 65536))))
        return out
    for t, anim, active, dx, dy in OBJECTS:
        x = org[0] + int(round((BASE[0] + 2.75 + dx) * 65536))
        y = org[1] + int(round((BASE[1] + 3.6 + dy) * 65536))
        out.append((t, anim, 0, active, x, y))
    return out


def view_bytes(p):
    """phys_view as 816-tcc lays out bike_view_t (52 bytes)."""
    import struct
    return struct.pack('<iiH2xiiiiHHiiiiBB2x', p.body[0], p.body[1], p.body_a,
                       p.wheel[0][0], p.wheel[1][0], p.wheel[0][1], p.wheel[1][1],
                       p.wheel_a[0], p.wheel_a[1], p.rider[0], p.rider[1],
                       p.head[0], p.head[1], p.turned, 1)


def main():
    import struct
    org = origin(sys.argv[1])
    poses = fixed_poses(org)
    objs = objects(org, sys.argv[1])
    out = sys.argv[2]
    h = ['// Generated by test/bike_poses.py.', '#define POSE_COUNT %d' % len(poses),
         '#define POSE_HOLD %d' % HOLD, '#define POSE_LEVEL %d' % LEVEL,
         '#define POSE_OBJS %d' % len(objs), '',
         'typedef struct {', '\tu8 view[52];        // bike_view_t',
         '\tu16 turn, volt, volt1;', '\ts16 cam_x, cam_y;', '} pose_t;', '',
         'typedef struct {', '\tu8 obj[12];         // phys_obj_t', '} pose_obj_t;', '',
         'extern const pose_t test_poses[];', 'extern const pose_obj_t test_objs[];']
    a = ['; Generated by test/bike_poses.py.', '.include "hdr.asm"', '',
         '.SECTION ".test_poses" SUPERFREE', 'test_poses:']
    for p in poses:
        b = view_bytes(p) + struct.pack('<HHHhh', p.turn, p.volt, p.volt1, p.cam[0], p.cam[1])
        a.append('\t.db ' + ','.join(str(x) for x in b))
    a += ['.ENDS', '', '.SECTION ".test_objs" SUPERFREE', 'test_objs:']
    for t, anim, grav, active, x, y in objs:
        a.append('\t.db ' + ','.join(str(v) for v in struct.pack('<BBBBii', t, anim, grav, active, x, y)))
    a += ['.ENDS', '']
    with open(out + '.h', 'w') as f:
        f.write('\n'.join(h) + '\n')
    with open(out + '.asm', 'w') as f:
        f.write('\n'.join(a) + '\n')


if __name__ == '__main__':
    main()
