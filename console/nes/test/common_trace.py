"""Run the NES host physics model on the common console benchmark cases.

Requires the NES level converter's NumPy dependency and a host C compiler.
Uses the ROM's fixed-point C model, packed level geometry, game rules and
nominal NTSC frame cadence. CPU overruns and controller polling are not emulated.
"""

import argparse
import ctypes
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import shlex
import subprocess
import sys

NES = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(NES.parents[1] / 'tests/console_physics'))
from sampling import sample_30hz

sys.path.insert(0, str(NES / 'tools'))
from elmadata import Resource, T_APPLE, T_FLOWER, T_KILLER, T_START, internal_levels
from levconv import Geometry, encode_grid_rows, encode_segments, grid_cells, le, objects, segments

PHYSICS_HZ = 50
FRAMES_PER_SECOND = 60
# physconst.py defines NTSC as 60.0988 scans per second.
NTSC_NUMERATOR = 600988
NTSC_DENOMINATOR = 10000
TRACE_HZ = 30
POSITION_SCALE = 262144
ANGLE_SCALE = math.tau / 16777216


class Level:
    def __init__(self, level):
        self.geo = geo = Geometry(level)
        lines = segments(geo)
        self.gw, self.gh, cells = grid_cells(lines, geo)
        self.objects = objects(geo)[:52]
        self.start = geo.to_u(*level.start())
        self.width = geo.w * 8
        self.height = geo.h * 8

        rows = encode_grid_rows(self.gw, self.gh, cells)
        row_offsets = bytearray()
        offset = 0
        for row in rows:
            row_offsets.extend(le(offset, 2))
            offset += len(row)
        packed_segments = encode_segments(lines)
        self.rows_address = len(packed_segments)
        self.grid_address = self.rows_address + len(row_offsets)
        self.data = ctypes.create_string_buffer(packed_segments + row_offsets + b''.join(rows))

    def load(self, model):
        model.trace_start(self.data, self.rows_address, self.grid_address, self.gw,
                          self.gh, self.width, self.height, *self.start)


class ObjectContacts:
    def __init__(self, packed_objects):
        self.active = [obj for obj in packed_objects if obj[0] != T_START]
        self.apples = sum(kind == T_APPLE for kind, *_ in self.active)

    def step(self, model, state):
        # These broad-phase bounds and squared thresholds come from game.c.
        bx, by = state[0] >> 14, state[1] >> 14
        points = [(state[i], state[i + 1], radius)
                  for i, radius in ((3, 819), (5, 819), (7, 653))]
        for index, obj in enumerate(self.active):
            if obj is None:
                continue
            kind, x, y, gravity = obj
            px, py = x >> 6, y >> 6
            if abs(px - bx) > 48 or abs(py - by) > 48:
                continue
            for qx, qy, radius in points:
                if abs(px - (qx >> 6)) > 14 or abs(py - (qy >> 6)) > 14:
                    continue
                if (x - qx)**2 + (y - qy)**2 >= radius**2:
                    continue
                if kind == T_KILLER:
                    return 'dead'
                if kind == T_APPLE:
                    self.active[index] = None
                    self.apples -= 1
                    model.trace_gravity(gravity)
                    break
                if kind == T_FLOWER and not self.apples:
                    return 'finish'
        return None


def build_model(work):
    work.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, NES / 'tools/physconst.py', work / 'physconst.h',
                    str(PHYSICS_HZ), 'ntsc'], check=True)
    # Bank registers are no-ops in the host's flat address space.
    (work / 'mapper.h').write_text(
        '#include <stdint.h>\n'
        '#ifdef __APPLE__\n'
        '#define section(name) section("__DATA,__nes_segs")\n'
        '#endif\n'
        'static inline uint8_t get_prg_8000(void) { return 0; }\n'
        'static inline void set_prg_8000(uint8_t bank) { (void)bank; }\n'
    )
    library = work / 'nes-common-trace.so'
    subprocess.run([*shlex.split(os.environ.get('HOSTCC', 'cc')),
                    '-O2', '-fwrapv', '-shared', '-fPIC',
                    '-I', work, '-I', NES / 'src', '-o', library,
                    NES / 'test/common_trace.c', NES / 'src/physics.c',
                    NES / 'src/fixmath.c', NES / 'src/segs.c', '-lm'], check=True)
    model = ctypes.CDLL(str(library.resolve()))
    model.trace_start.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                                  ctypes.c_uint8, ctypes.c_uint8, ctypes.c_uint16,
                                  ctypes.c_uint16, ctypes.c_int32, ctypes.c_int32]
    model.trace_start.restype = None
    model.trace_step.argtypes = [ctypes.c_uint8]
    model.trace_step.restype = ctypes.c_uint8
    model.trace_state.argtypes = [ctypes.POINTER(ctypes.c_int32)]
    model.trace_state.restype = None
    model.trace_gravity.argtypes = [ctypes.c_uint8]
    model.trace_gravity.restype = None
    return model


def trace(model, level, inputs):
    level.load(model)
    contacts = ObjectContacts(level.objects)
    state = (ctypes.c_int32 * 9)()
    model.trace_state(state)
    def native():
        frame, step = 0, 0
        event = None
        while True:
            time = Fraction(frame * NTSC_DENOMINATOR, NTSC_NUMERATOR)
            yield time, dict(x=state[0] / POSITION_SCALE + level.geo.x0,
                             y=state[1] / POSITION_SCALE + level.geo.ybot,
                             angle=state[2] * ANGLE_SCALE, event=event)
            mask = inputs[int(time * TRACE_HZ)]
            alive = model.trace_step(mask)
            model.trace_state(state)
            event = contacts.step(model, state) if alive else 'dead'
            step += 1
            frame = (step * FRAMES_PER_SECOND + PHYSICS_HZ - 1) // PHYSICS_HZ

    return sample_30hz(native(), len(inputs))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('res', 'work', 'cases', 'out'):
        parser.add_argument('--' + option, type=Path, required=True)
    args = parser.parse_args()

    cases = json.loads(args.cases.read_text())
    source = internal_levels(Resource(args.res))
    levels = {}
    model = build_model(args.work)
    traces = {}
    for case in cases:
        index = case['level']
        if not 0 <= index < len(source):
            raise ValueError(f"Unknown NES level index {index} in {case['id']}")
        if index not in levels:
            levels[index] = Level(source[index])
        traces[case['id']] = trace(model, levels[index], case['inputs'])
    args.out.write_text(json.dumps(traces, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
