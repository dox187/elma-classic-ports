"""Prove stationary two-contact decisions over finite boxes of wheel impulses."""
from itertools import product
import re

from head_clearance import write_if_changed

# Frequent ordered pairs from 54 neutral starts and the later braking routes.
# Two families share a grid across a range of ordered normals. The remaining
# tuples use all four exact coefficients. Positions and lengths can vary.
NORMALS = ((-5937, 15270, 856, 16362), (-4523, 15747, 16105, 3013),
           (-412, 16379, 16367, -737), (-8277, 14140, 11596, 11575),
           (-9789, 13138, 104, 16384))
# Each pair of inclusive high bytes admits all 256 possible low bytes.
NORMAL_BANDS = {
    NORMALS[2]: ((-2, 1), (63, 64), (63, 64), (-3, 9)),
    NORMALS[4]: ((-39, -38), (51, 52), (0, 1), (63, 64)),
}


def normal_region(normal):
    for representative, bands in NORMAL_BANDS.items():
        if all(low <= value >> 8 <= high for value, (low, high) in zip(normal, bands)):
            return representative
    return normal if normal in NORMALS else None


def normal_corners(normal):
    bands = NORMAL_BANDS.get(normal)
    if bands is None:
        return (normal,)
    return product(*[(low * 256, high * 256 + 255) for low, high in bands])


X_MIN, Y_MIN, SIDE = -65536, -81920, 4096
Y_CELLS = 20
COLUMNS = tuple((X_MIN + i*SIDE, SIDE) for i in range(24)) + tuple(
    (-4096 + i*1024, 1024) for i in range(8))


def cell(normals, x, width, y, coefficients):
    """A signed byte certifies both supports and the first pivot moment."""
    tangents = []
    # Each unrounded numerator is affine in any one coordinate when the
    # others are fixed, even when both normals and impulses range over a box.
    # Its extrema occur at corners. Both fixed-point roundings are monotone.
    for nx, ny, px, py in normal_corners(normals):
        for dx, dy in product((x, x + width - 1), (y, y + SIDE - 1)):
            if max(dx*nx + dy*ny, dx*px + dy*py) >= 8192:
                return 0
            tangents.append((dy*px - dx*py + 8192) >> 14)
    moments = [((((v*length) >> 6)*coefficient + (1 << 23)) >> 24)
               for v in (min(tangents), max(tangents))
               for length in (384, 447) for coefficient in coefficients]
    # With a signed16 applied torque, neither Q24 saturation nor the
    # following signed32 moment addition may wrap anywhere in the box.
    if min(moments) <= -(1 << 31) + 32768 or max(moments) >= (1 << 31) - 32768:
        return 0
    if min(moments) > 0:
        return 1 + min(126, (min(moments) - 1) // 32)
    if max(moments) < 0:
        return -(1 + min(126, (-max(moments) - 1) // 32))
    return 0


def generate(gen, reader):
    constants = (gen / 'riding_constants.h').read_text()
    scales = tuple(map(int, re.search(r'q24_C_OLD\[2\]=\{(-?\d+),(-?\d+)\}', constants).groups()))
    new_scales = tuple(map(int, re.search(r'q24_C_NEW\[2\]=\{(-?\d+),(-?\d+)\}', constants).groups()))
    # For q >= 2, round((1640*q + 1) * C_NEW / 2**24) <= 17*q.
    # The added unit covers the signed floor in the contact length scale.
    bound_enabled = all(0 <= value <= 170000 for value in new_scales)
    output = [f'PAIR_TIGHT_BOUND = {int(bound_enabled)}',
              reader.read_text(), 'stopped_match:']
    for i, normal in enumerate(NORMALS):
        bands = NORMAL_BANDS.get(normal)
        if bands is None:
            continue
        for offset, (low, high) in zip((1, 3, 11, 13), bands):
            output += [f' ld a,(#_Ct+{offset})', f' sub #{low & 255}',
                       f' cp #{high - low + 1}', f' jr nc,stopped_next_{i}']
        output += [f' ld bc,#stopped_grid_{i}', ' jp stopped_table', f'stopped_next_{i}:']
    exact = [(i, normal) for i, normal in enumerate(NORMALS) if normal not in NORMAL_BANDS]
    if len({normal[0] & 255 for _, normal in exact}) != len(exact):
        raise ValueError('Exact stopped pair tags must have distinct low bytes')
    output.append(' ld a,(#_Ct)')
    for i, normal in exact:
        output += [f' ld de,#stopped_key_{i}', f' cp #{normal[0] & 255}', ' jp z,stopped_check']
    output += [' xor a', ' ret']
    for i, normal in enumerate(NORMALS):
        if normal not in NORMAL_BANDS:
            output += [f'stopped_key_{i}:', ' .dw ' + ','.join(map(str, normal)),
                       f' .dw stopped_grid_{i}']
        output.append(f'stopped_grid_{i}:')
        for y in range(Y_CELLS):
            row = [cell(normal, x, width, Y_MIN + y*SIDE, scales)
                   for x, width in COLUMNS]
            output.append(' .db ' + ','.join(map(str, row)))
    destination = gen / 'physics_stopped_pair_game.s'
    write_if_changed(destination, '\n'.join(output) + '\n')
    return destination
