"""Check the linked drive cutoff, brake latch and torque fields at signed boundaries."""
import argparse
from pathlib import Path
import random
import re
import struct

from check_corner_results import WheelQueries


def check(rom, reference, gen):
    constants = (gen / 'riding_constants.h').read_text()
    limit = int(re.search(r'^#define WHEEL_MAXW (\d+)$', constants, re.M)[1])
    torque = int(re.search(r'^#define GAS_TQ (\d+)$', constants, re.M)[1])
    bounds = (1 << 31) - 1
    centers = (-bounds-1, -16777216, -65536, -32768, -limit, -256, 0,
               256, limit, 32768, 65536, 16777216, bounds)
    speeds = sorted({base+d for base in centers for d in range(-2, 3)
                     if -bounds-1 <= base+d <= bounds})
    carts = [WheelQueries(path) for path in (rom, reference)]
    rng = random.Random(611)
    checked = 0
    try:
        for speed in speeds:
            for facing in (0, 1, 255):
                for controls in range(4):
                    for previous_brake in (0, 2):
                        bike = bytearray(rng.randbytes(119))
                        bike[96], bike[98] = facing, previous_brake
                        active = 44 if facing else 68
                        struct.pack_into('<i', bike, active, speed)
                        fields = (('_Bike', bike), ('_riding_suspension_state', rng.randbytes(52)),
                                  ('_riding_subphase', bytes((checked % 2,))))
                        results = []
                        for cart in carts:
                            for name, data in fields:
                                start = cart.sym[name]
                                cart.m[start:start+len(data)] = data
                            cart.invoke('_riding_step_controls', a=controls)
                            results.append(tuple(cart.read(n, len(v)) for n, v in fields))
                        case = (speed, facing, controls, previous_brake)
                        assert results[0] == results[1], case
                        if not (controls & 2):
                            state = results[0][1]
                            left, right = (struct.unpack_from('<i', state, off)[0] for off in (18, 32))
                            assert left == (-torque if facing and controls & 1 and speed > -limit else 0), case
                            assert right == (torque if not facing and controls & 1 and speed < limit else 0), case
                        checked += 1
    finally:
        for cart in carts:
            cart.p.stop(save=False)
    print(f'{checked} drive cutoff, signed boundary and brake control cases matched.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('rom', 'reference', 'gen'):
        parser.add_argument('--'+option, type=Path, required=True)
    args = parser.parse_args()
    check(args.rom, args.reference, args.gen)
