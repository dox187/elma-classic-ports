"""Generate the exact rounded seat projection and a narrow band of the rider ellipse."""
import math
import re

from head_clearance import write_if_changed


def generate(gen):
    header = (gen / 'riding_constants.h').read_text()
    constants = {name: int(value) for name, value in
                 re.findall(r'^#define (\w+) (-?\d+)$', header, re.M)}

    def coefficient(name):
        full, partial = map(int, re.search(
            rf'q24_C_{name}\[2\]\s*=\s*\{{(\d+),(\d+)\}}', header).groups())
        return full if full == partial else None

    nx, ny, ellipse = (coefficient(name) for name in ('SEAT_NX', 'SEAT_NY', 'ELLIPSE'))
    left, right, top = (constants[name] for name in ('RIDER_LEFT', 'RIDER_RIGHT', 'RIDER_TOP'))
    if None in (nx, ny, ellipse) or not (-512 <= left < 0 < right < 512 and 0 < top < 768):
        return False

    def rounded(value, scale):
        return (value * scale + (1 << 23)) >> 24

    columns = [rounded(x - constants['SEAT_X'], nx) for x in range(-512, 512)]
    rows = [rounded(y - constants['SEAT_Y'], ny) for y in range(768)]
    if min(rows) - max(columns) < -512 or max(rows) - min(columns) > 32767:
        return False
    # The original also has a seat rectangle generated from its compact
    # coefficient. Check its worst corner for the actual Q24 profile.
    if constants['RIDING_SEAT_FAST_ENABLED']:
        greatest_x = min(511, constants['RIDING_SEAT_FAST_X'])
        least_y = max(0, constants['RIDING_SEAT_FAST_Y'])
        if (greatest_x >= -512 and least_y <= top and
                rows[least_y] < columns[greatest_x + 512]):
            return False
    # The shipped limiter first tests its bucket edge, generated from the
    # compact coefficient. A few buckets admit one or more extra y values
    # beyond the Q24 ellipse. Preserve that comparison before the exact square.
    bucket_edges = list(map(int, re.search(
        r'^#define RIDING_ELLIPSE_INSIDE_Y_VALUES ([0-9,]+)$', header, re.M)[1].split(',')))
    bucket_shift = constants['RIDING_ELLIPSE_BUCKET_SHIFT']
    heights, capped_x, capped_y, band = [], [], [], []
    for x in range(right + 1):
        xs = rounded(x, ellipse)
        height = max(bucket_edges[x >> bucket_shift],
                     math.isqrt(max(0, top * top - xs * xs)))
        heights.append(height)

        def correction(y):
            denominator = math.isqrt(xs * xs + y * y)
            return x * top // denominator, y * top // denominator

        tx, ty = correction(top)
        capped_x.append(tx)
        capped_y.append(ty)
        for offset in range(1, 17):
            y = min(top, height + offset)
            px, py = correction(y)
            dx, dy = x - px, y - py
            if not (0 <= dx < 16 and 0 <= dy < 16):
                return False
            band.append((dx << 4) | dy)

    lines = []
    def array(type_name, name, data):
        lines.append(f'static const {type_name} {name}[] = {{')
        lines.extend(','.join(map(str, data[i:i+32])) + ',' for i in range(0, len(data), 32))
        lines.append('};')

    array('int16_t', 'seat_column', columns)
    array('int16_t', 'seat_row', rows)
    array('int16_t', 'seat_push_x', [rounded(-i-1, nx) for i in range(512)])
    array('int16_t', 'seat_push_y', [rounded(-i-1, ny) for i in range(512)])
    array('int16_t', 'ellipse_height', heights)
    array('int16_t', 'ellipse_top_x', capped_x)
    array('int16_t', 'ellipse_top_y', capped_y)
    array('uint8_t', 'ellipse_edge', band)
    write_if_changed(gen / 'physics_seat_tables.h', '\n'.join(lines) + '\n')
    return True
