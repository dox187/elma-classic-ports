"""Prove stationary two-contact decisions over finite boxes of wheel impulses."""
import re

from head_clearance import write_if_changed

# Frequent ordered pairs from 54 neutral starts and the later braking routes.
# Match all four signed coefficients at runtime. Positions and lengths can vary.
NORMALS = ((-5937, 15270, 856, 16362), (-4523, 15747, 16105, 3013),
           (-412, 16379, 16367, -737), (-8277, 14140, 11596, 11575),
           (-9789, 13138, 104, 16384))
X_MIN, Y_MIN, SIDE = -65536, -81920, 4096
Y_CELLS = 20
COLUMNS = tuple((X_MIN + i*SIDE, SIDE) for i in range(24)) + tuple(
    (-4096 + i*1024, 1024) for i in range(8))


def cell(normals, x, width, y, coefficients):
    """A signed byte certifies both supports and the first pivot moment."""
    nx, ny, px, py = normals
    tangents = []
    for dx in (x, x + width - 1):
        for dy in (y, y + SIDE - 1):
            # A rounded dot <= 0 supports a wheel at rest. The extrema
            # of each linear numerator occur at corners; rounding is monotone.
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
    output = [reader.read_text(), 'stopped_match:']
    if len({normal[0] & 255 for normal in NORMALS}) != len(NORMALS):
        raise ValueError('Stopped pair tags must have distinct low bytes')
    for i, (nx, _, _, _) in enumerate(NORMALS):
        output += [f' ld de,#stopped_key_{i}', f' cp #{nx & 255}', ' jp z,stopped_check']
    output += [' xor a', ' ret']
    for i, normal in enumerate(NORMALS):
        output += [f'stopped_key_{i}:', ' .dw ' + ','.join(map(str, normal)),
                   f' .dw stopped_grid_{i}', f'stopped_grid_{i}:']
        for y in range(Y_CELLS):
            row = [cell(normal, x, width, Y_MIN + y*SIDE, scales)
                   for x, width in COLUMNS]
            output.append(' .db ' + ','.join(map(str, row)))
    destination = gen / 'physics_stopped_pair_game.s'
    write_if_changed(destination, '\n'.join(output) + '\n')
    return destination
