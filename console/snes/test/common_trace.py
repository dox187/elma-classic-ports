#!/usr/bin/env python3
"""Sample the SNES production fixed-point physics model for the common benchmark."""

import argparse
import ctypes
from fractions import Fraction
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parents[1] / 'tests/console_physics'))
from sampling import sample_30hz

PHYS_HZ = 80
SAMPLE_HZ = 30
PH_DEAD = 1
PH_FINISH = 2


def build_solver(resource, work):
    gen = work / 'gen'
    library = work / 'physplay.so'
    subprocess.run([
        sys.executable, str(ROOT / 'tools/gen_phys.py'), str(resource), str(gen),
        '--hz', str(PHYS_HZ),
    ], check=True)
    subprocess.run([
        os.environ.get('HOSTCC', 'cc'), '-O2', '-Wall', '-shared', '-fPIC',
        '-I', str(gen), '-o', str(library), str(ROOT / 'test/physplay.c'),
        str(ROOT / 'test/phys_spec.c'),
    ], check=True)

    solver = ctypes.CDLL(str(library))
    solver.pp_level.argtypes = [ctypes.c_char_p]
    solver.pp_level.restype = ctypes.c_int
    solver.pp_run.argtypes = [
        ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(ctypes.c_uint16),
    ]
    solver.pp_run.restype = ctypes.c_int
    solver.pp_view.argtypes = [ctypes.POINTER(ctypes.c_int32)]
    solver.pp_view.restype = None
    return gen, solver


def trace_case(solver, level, inputs):
    if solver.pp_level(os.fsencode(level)):
        raise RuntimeError(f'Cannot load SNES level {level}')

    # Common masks put Left on bit 2. The SNES puts Right there.
    keys = [(mask & 3) | ((mask & 4) << 1) | ((mask & 8) >> 1) for mask in inputs]
    def native():
        step = 0
        terminal = None
        event = ctypes.c_uint16()
        view = (ctypes.c_int32 * 9)()
        while True:
            solver.pp_view(view)
            yield Fraction(step, PHYS_HZ), dict(x=view[0] / (1 << 16), y=view[1] / (1 << 16),
                                                 angle=view[4] / (1 << 28), event=terminal)
            mask = keys[step * SAMPLE_HZ // PHYS_HZ]
            step += solver.pp_run(bytes([mask]), 1, ctypes.byref(event))
            if event.value & PH_FINISH:
                terminal = 'finish'
            elif event.value & PH_DEAD:
                terminal = 'dead'

    return sample_30hz(native(), len(inputs))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--res', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()

    cases = json.loads(args.cases.read_text())
    gen, solver = build_solver(args.res.resolve(), args.work.resolve())
    traces = {
        case['id']: trace_case(solver, gen / 'phys' / f"lev{case['level']:02d}.bin",
                               case['inputs'])
        for case in cases
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(traces, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
