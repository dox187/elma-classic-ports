"""Compare the linked two-wheel grid predicate to signed, exclusive 32-bit limits."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import random
import re
import struct

from pyboy import PyBoy


def vectors():
    low, high = -(1 << 31), (1 << 31) - 1
    edges = (low, low + 1, -0x1000000, -0x10000, -1, 0, 1, 0xffff,
             0x10000, 0x123456, 0xffffff, 0x1000000, high - 1, high)
    for limit in edges:
        near = sorted({max(low, min(high, limit + d))
                       for d in (-0x10001, -0x10000, -2, -1, 0, 1, 0x10000)})
        for a in near:
            for b in (*near, low, high):
                yield (limit, 1), ((a, 0), (b, -1))
                yield (1, limit), ((0, b), (-1, a))
    rng = random.Random(0x9623)
    for _ in range(4096):
        limit = tuple(rng.randint(low, high) for _ in range(2))
        yield limit, [[rng.randint(low, high) for _ in range(2)] for _ in range(2)]
        yield limit, [[max(low, min(high, lim + rng.randint(-0x1ffff, 0x1ffff)))
                       for lim in limit] for _ in range(2)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    args = parser.parse_args()
    sy = {name: int(addr, 16) for name, addr in re.findall(
        r'^DEF (\S+) 0x(\w+)', args.rom.with_suffix('.noi').read_text(), re.M)}
    image = bytearray(args.rom.read_bytes())
    image[0x100:0x102] = bytes([0x18, 0xfe])
    emu = PyBoy(BytesIO(image), window='null', cgb=True, sound_emulated=False)
    emu.set_emulation_speed(0)
    try:
        emu.tick(120, False)
        mem, reg = emu.memory, emu.register_file
        mem[0xffff] = 0
        addr = sy['_wheels_in_grid']
        mem[0x3000] = 0
        mem[0x2000] = mem[sy['__current_bank']] = addr >> 16
        code, stack = 0xc900, 0xcff0
        mem[code:code+5] = [0xcd, addr & 255, (addr >> 8) & 255, 0x18, 0xfe]
        count = 0
        for limits, wheels in vectors():
            dest = sy['_riding_level'] + 24
            mem[dest:dest+8] = struct.pack('<ii', *limits)
            for index, point in enumerate(wheels):
                dest = sy['_Bike'] + 24 * (index+1)
                mem[dest:dest+8] = struct.pack('<ii', *point)
            reg.SP, reg.PC = stack, code
            emu.tick(1, False)
            expected = all(x < limits[0] and y < limits[1] for x,y in wheels)
            assert (reg.A, reg.SP, reg.PC) == (expected, stack, code+3), (limits, wheels, expected, reg.A)
            count += 1
        print(json.dumps({'passed': True, 'vectors': count}))
    finally:
        emu.stop(save=False)


if __name__ == '__main__':
    main()
