"""Certify wheel contacts in 16-unit tiles along two Bumpy Journey landings."""
from collections import Counter
from functools import lru_cache

from corner_samples import cell_records, contacts, normalize, q14, record_contact
from head_clearance import packed_inputs
from projection_tables import byte_lines
from wheel_terrain import RADIUS

COURSE = 33
# Scan the upper face in vertical columns, and the next face in horizontal rows.
STRIPS = ((65024, 67584, False), (63488, 62720, True))
MISS = 15
TABLE_OFFSET = 3584


def geometry(gen):
    levels, banks, _ = packed_inputs(gen)

    @lru_cache(None)
    def records(cx, cy):
        return cell_records(levels[COURSE], banks, cx*1024, cy*1024)

    def ordered(x, y):
        return contacts(records(x//1024, y//1024), x & 4095, y & 4095)

    vertices, planes = Counter(), Counter()
    columns = []
    for along, across, vertical in STRIPS:
        for i in range(64):
            left = along + 16*i
            search = range(0, 2048, 8) if vertical else range(2040, -1, -8)
            def position(u, v):
                return (v, u) if vertical else (u, v)
            edge = next((n for n in search if ordered(*position(left+8, across+n))), None)
            base = max(0, edge//16 - (2 if vertical else 3)) if edge is not None else 255
            columns.append((left, across, vertical, base))
            if base == 255:
                continue
            # Rank the actual endpoint vertices and interior planes in these six
            # tiles. An unselected expression can only reduce lookup coverage.
            for tile in range(6):
                x, y = position(left+8, across+16*(base+tile)+8)
                qx, qy = x & 4095, y & 4095
                for rec in records(x//1024, y//1024):
                    if record_contact(rec, qx, qy) is None:
                        continue
                    px, py, dx, dy, ex, ey, flags, *_ = rec
                    tangent = q14(ex*(qx-px) + ey*(qy-py))
                    px += x-qx
                    py += y-qy
                    if tangent < 0:
                        vertices[px, py] += 1
                    elif tangent > (flags & 16383):
                        vertices[px+dx, py+dy] += 1
                    else:
                        planes[px, py, ex, ey] += 1

    vertex = {i: key for i, (key, _) in enumerate(vertices.most_common(3), 1)}
    plane = {i: key for i, (key, _) in enumerate(planes.most_common(2), 4)}

    def evaluate(code, x, y):
        if code == 0:
            return ()
        if code in vertex:
            px, py = vertex[code]
            dx, dy = x-px, y-py
            if dx*dx + dy*dy >= RADIUS*RADIUS:
                return ()
            nx, ny, length = normalize(dx, dy)
            return (normalize(q14(nx*length), q14(ny*length)),)
        px, py, ex, ey = plane[code]
        distance = q14(-ey*(x-px) + ex*(y-py))
        if abs(distance) >= RADIUS:
            return ()
        return ((-ey, ex, distance) if distance >= 0 else (ey, -ex, -distance),)

    data = bytearray()
    for left, across, vertical, base in columns:
        if base == 255:
            data.extend([255]*4)
            continue
        codes = []
        for tile in range(6):
            top = across + 16*(base+tile)
            allowed = [0, *vertex, *plane]
            for u in range(left, left+16):
                for v in range(top, top+16):
                    x, y = (v, u) if vertical else (u, v)
                    hit = ordered(x, y)
                    allowed = [code for code in allowed if evaluate(code, x, y) == hit]
                    if not allowed:
                        break
                if not allowed:
                    break
            codes.append(allowed[0] if allowed else MISS)
        data.extend([base, *(codes[i] | codes[i+1]<<4 for i in (0, 2, 4))])
    return vertex, plane, data


def directory(gen, src, directory_source, bank):
    vertex, plane, data = geometry(gen)
    template = (src/'bumpy_strip.inc').read_text()
    reader = [directory_source.replace(' .bndry 256', ' bumpy_resolver\n .bndry 256'),
              ' bumpy_reader', ' bumpy_hit_kernel', 'bumpy_vertices:']
    reader.extend(f' .dw {x & 65535},{y & 65535}' for x, y in vertex.values())
    reader.append('bumpy_planes:')
    reader.extend(f' .dw {x & 65535},{y & 65535},{ex},{-ey}' for x, y, ex, ey in plane.values())
    reader.append(f'bumpy_bank == {bank}')
    return template + '\n' + '\n'.join(reader), data


def payload(original, skip, tiles):
    if len(tiles) != 512 or original[TABLE_OFFSET:TABLE_OFFSET+512] != bytes(512):
        raise ValueError('Wheel strip tiles need the unused last page pair of the rolling directory')
    return [*byte_lines(original[skip:TABLE_OFFSET]), 'bumpy_tiles::', *byte_lines(tiles),
            'bumpy_tiles_end::', *byte_lines(original[TABLE_OFFSET+512:])]
