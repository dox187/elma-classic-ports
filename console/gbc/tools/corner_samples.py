"""Evaluate every integer wheel center in selected 16-unit terrain squares.

cell_samples() consumes the same packed records and record order as seg_query.
The optional CLI compares the complete ordered geometry against a linked ROM.
"""
from functools import lru_cache
from math import isqrt
from pathlib import Path
import struct

from wheel_terrain import RADIUS, RECORD

MERGE = 102
TILE = 16
POINTER = struct.Struct('<HBB')


@lru_cache(maxsize=1)
def reciprocal_roots():
    path = Path(__file__).resolve().parents[2] / 'nes/src/rsqrt.inc'
    entries = path.read_text().split('\n', 1)[1].strip().rstrip(',')
    return tuple(map(int, entries.split(',')))


def q14(product):
    return max(-32768, min(32767, (product + 8192) >> 14))


def normalize(x, y):
    squared = x*x + y*y
    if squared < 16384:
        length = isqrt(squared)
        if length == 0:
            return 0, 16384, 0
        # Signed division on the cartridge truncates toward zero.
        nx = (abs(x) << 14) // length
        ny = (abs(y) << 14) // length
        return -nx if x < 0 else nx, -ny if y < 0 else ny, length
    roots = reciprocal_roots()
    factor = roots[min((squared - 16384) >> 9, len(roots) - 1)]
    nx, ny = x*factor >> 4, y*factor >> 4
    return nx, ny, q14(nx*x + ny*y)


def cell_records(level, banks, x, y):
    """Ordered records for a level-local center in integer solver units."""
    width, height = level['grid']
    cx, cy = x >> 12, y >> 12
    if not (0 <= cx < width and 0 <= cy < height):
        return ()
    base = level['base_bank']
    offset = level['directory_address'] - 0x4000 + 4*(cy*width + cx)
    address, relative, count = POINTER.unpack_from(banks[level['directory_bank']], offset)
    if count == 255:
        subcell = ((y >> 8) & 12) | ((x >> 10) & 3)
        address, relative, count = POINTER.unpack_from(
            banks[base + relative], address - 0x4000 + 4*subcell)
    if not count:
        return ()
    offset = address - 0x4000
    return tuple(RECORD.unpack_from(banks[base + relative], offset + i*RECORD.size)
                 for i in range(count))


def record_contact(record, qx, qy):
    px, py, dx, dy, ex, ey, flags, bx0, bx1, by0, by1 = record
    if not (bx0 <= (qx >> 6) + 128 <= bx1 and by0 <= (qy >> 6) + 128 <= by1):
        return None
    x, y = qx - px, qy - py
    distance = q14(-ey*x + ex*y)
    if abs(distance) >= RADIUS:
        return None
    pos = q14(ex*x + ey*y)
    end = flags & 0x3fff
    if 0 <= pos <= end:
        if pos == end and flags & 0x8000:
            return None
        return (-ey, ex, distance) if distance >= 0 else (ey, -ex, -distance)
    if pos < 0:
        if flags & 0x4000:
            return None
    else:
        if flags & 0x8000:
            return None
        x, y = x - dx, y - dy
    return normalize(x, y) if x*x + y*y < RADIUS*RADIUS else None


def contacts(records, qx, qy):
    first = None
    for record in records:
        new = record_contact(record, qx, qy)
        if new is None:
            continue
        if first is None:
            first = new
            continue
        # Work in offsets from the wheel center. The cartridge takes the
        # signed, floored half-difference of the two projected terrain points.
        ax, ay = q14(first[0]*first[2]), q14(first[1]*first[2])
        dx, dy = ax - q14(new[0]*new[2]), ay - q14(new[1]*new[2])
        if dx*dx + dy*dy >= MERGE*MERGE:
            return first, new
        first = normalize(ax - (dx >> 1), ay - (dy >> 1))
    return () if first is None else (first,)


def cell_samples(level, banks, x, y):
    """Return 256 y-major tuples of active (nx, ny, length) records."""
    if x % TILE or y % TILE:
        raise ValueError(f'Unaligned 16-unit square ({x}, {y})')
    records = cell_records(level, banks, x, y)
    qx, qy = x & 4095, y & 4095
    return tuple(contacts(records, qx + dx, qy + dy)
                 for dy in range(TILE) for dx in range(TILE))


def verify(gen, rom, cells):
    """Compare every active geometry record to the cartridge's raw contacts()."""
    import sys
    from collections import Counter

    from head_clearance import packed_inputs
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'test'))
    from check_normal_atlas import Cartridge

    levels, banks, _ = packed_inputs(gen)
    cart = Cartridge(rom)
    try:
        mem, reg, symbols = cart.m, cart.reg, cart.sym
        def call(address, pop_bytes=0):
            mem[cart.code:cart.code+5] = bytes([0xcd, address & 255, address >> 8, 0x18, 0xfe])
            reg.SP, reg.PC = cart.stack, cart.code
            for _ in range(16):
                cart.p.tick(1, False)
                if reg.PC == cart.code + 3:
                    break
            if (reg.PC, reg.SP) != (cart.code + 3, cart.stack + pop_bytes):
                raise RuntimeError(f'Cartridge did not return from {address:#x}')
            return reg.A

        # The linker exports the iterator but omits its static C caller.
        # Identify contacts() by its assembly entry and the two calls it makes.
        bank = symbols['_riding_contacts_loop'] >> 16
        image = cart.image[bank*16384:(bank+1)*16384]
        prefix = bytes.fromhex('78 e6 0f 67 69 e5 cd')
        def call_opcode(name):
            return b'\xcd' + struct.pack('<H', symbols[name] & 65535)
        tail = (call_opcode('_seg_query') + bytes.fromhex('c1 d1 d1')
                + call_opcode('_riding_contacts_loop') + bytes.fromhex('e1 e8 04 e9'))
        entries = [i for i in range(len(image)) if image.startswith(prefix, i)
                   and image[i+9:i+11] == b'\x4f\xc5' and tail in image[i:i+80]]
        if len(entries) != 1:
            raise ValueError('Cannot identify the linked contacts() entry and its two callees')
        entry = entries[0]
        ct = symbols['_Ct']
        counts = Counter()
        for level, x, y in cells:
            reg.A = level
            if call(symbols['_physics_collision_select']) != 1:
                raise ValueError(f'Unknown level {level}')
            for i, sample in enumerate(cell_samples(levels[level], banks, x, y)):
                qx, qy = x + i % TILE, y + i // TILE
                reg.D, reg.E, reg.B, reg.C = struct.pack('>i', qx)
                mem[cart.stack:cart.stack+4] = struct.pack('<i', qy)
                n = call(entry+0x4000, 4)
                actual = tuple(struct.unpack('<3h', bytes(mem[ct+10*j:ct+10*j+6]))
                               for j in range(n)) if n <= 2 else None
                if sample != actual:
                    raise ValueError(f'Level {level} at ({qx}, {qy}): generated {sample}, ROM {actual}')
                counts[n] += 1
        return counts
    finally:
        cart.p.stop(save=False)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gen', type=Path, required=True, help='packed collision asset directory')
    parser.add_argument('--rom', type=Path, required=True, help='reference ROM with matching .noi')
    parser.add_argument('--cell', type=int, nargs=3, action='append', required=True,
                        metavar=('LEVEL', 'X', 'Y'), help='zero-based course and aligned origin')
    args = parser.parse_args()
    result = verify(args.gen, args.rom, args.cell)
    print(f'Verified {sum(result.values())} centers. Contact count frequencies {dict(sorted(result.items()))}')
