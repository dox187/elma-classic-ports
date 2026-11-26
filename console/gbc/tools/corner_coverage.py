"""Rank wheel-contact tiles around original polygon vertices in a packed course."""

from collections import defaultdict
from itertools import combinations
from math import isqrt

from corner_samples import MERGE, POINTER, TILE, cell_records, contacts, record_contact
from wheel_terrain import RADIUS, RECORD

UNIT = 1 << 14


def _vertices(level, banks):
    """Collect incident rays, skipping piece boundaries introduced by the packer."""
    width, height = level['grid']
    directory = banks[level['directory_bank']]
    start = level['directory_address'] - 0x4000
    vertices = defaultdict(set)
    for i in range(width * height):
        ptr = POINTER.unpack_from(directory, start + i * POINTER.size)
        address, relative, count = ptr
        if count == 255:
            bank = banks[level['base_bank'] + relative]
            offset = address - 0x4000
            leaves = sorted(set(POINTER.iter_unpack(bank[offset:offset + 16*POINTER.size])))
        else:
            leaves = (ptr,)
        cx, cy = i % width * 4096, i // width * 4096
        for address, relative, count in leaves:
            if not count:
                continue
            bank = banks[level['base_bank'] + relative]
            offset = address - 0x4000
            for px, py, dx, dy, ex, ey, flags, *_ in RECORD.iter_unpack(
                    bank[offset:offset + count*RECORD.size]):
                ax, ay = cx + px, cy + py
                length = flags & 0x3fff
                if not flags & 0x4000:
                    vertices[ax, ay].add((ex, ey, length))
                if not flags & 0x8000:
                    vertices[ax + dx, ay + dy].add((-ex, -ey, length))
    return vertices


def _wheel_arc(radius):
    # Walk the shorter coordinate in each octant at one tile per step.
    offsets = set()
    for u in range(0, isqrt(radius*radius // 2) + 1, TILE):
        v = isqrt(radius*radius - u*u)
        for x, y in ((u, v), (v, u)):
            for dx in (-x, x):
                for dy in (-y, y):
                    offsets.add((dx, dy))
    return tuple(sorted(offsets))


SUPPORT_RADIUS = RADIUS - TILE // 4
ARC = _wheel_arc(SUPPORT_RADIUS)


def _centers(a, b):
    # Sample the wheel's outer contact band as it rolls between a planar
    # face and the radial cap. Positions straddling that transition can use
    # both records even when the projected terrain points merge into one.
    radius = SUPPORT_RADIUS
    for ex, ey, _ in (a, b):
        for side in (-radius, radius):
            for along in range(-MERGE // TILE * TILE, MERGE + TILE, TILE):
                yield ((along*ex - side*ey) // UNIT,
                       (along*ey + side*ex) // UNIT)

    # An outside corner also has an arc where both records supply caps.
    # On the inside the center of a wheel touching both planes lies farther
    # along the opposite bisector, at radius / sin(half the opening angle).
    yield from ARC
    sx, sy = a[0] + b[0], a[1] + b[1]
    length = isqrt(sx*sx + sy*sy)
    if length:
        yield -sx*radius // length, -sy*radius // length
        sine = abs(sx*a[1] - sy*a[0]) // length
        if sine >= UNIT // 2:
            yield sx*radius*UNIT // (length*sine), sy*radius*UNIT // (length*sine)


def _projection(ray, x, y):
    ex, ey, length = ray
    along = max(0, min(length, (ex*x + ey*y + UNIT//2) // UNIT))
    return (ex*along + UNIT//2) // UNIT, (ey*along + UNIT//2) // UNIT


def has_merge(level, banks, tx, ty, cache):
    x, y = tx*TILE, ty*TILE
    key = x >> 10, y >> 10
    if key not in cache:
        cache[key] = cell_records(level, banks, x, y)
    records = cache[key]
    # The wheel silhouette often cuts a tile diagonally. Checking four
    # quadrants also finds merges when the center sample is airborne.
    for dx, dy in ((8, 8), (2, 2), (13, 13), (2, 13), (13, 2)):
        qx, qy = (x & 4095) + dx, (y & 4095) + dy
        if sum(record_contact(record, qx, qy) is not None for record in records) >= 2:
            if len(contacts(records, qx, qy)) == 1:
                return True
    return False


def ranked_tiles(level, banks):
    """Return (integer score, tile_x, tile_y), best first, for one packed level.

    Coordinates are level-local 16-unit tiles, as used by cell_samples at
    (16*tile_x, 16*tile_y). The directory and segment records are the only
    terrain inputs. Initial wheel position, support direction and wheelbase
    also contribute to the score. Ties sort by tile address.
    """
    width, height = level['grid']
    start_x, start_y = (q // 64 - m*1024 for q, m in
                        zip(level['start_q16'], level['origin_m']))
    scores = {}
    slopes = {}
    for (vx, vy), rays in _vertices(level, banks).items():
        spawn_distance = isqrt((vx-start_x)**2 + (vy-start_y)**2)
        proximity = 256*4096 // (4096 + spawn_distance)
        for a, b in combinations(sorted(rays), 2):
            # Both rays point away from the vertex. Opposite, collinear rays
            # describe a straight edge even if the source contains a vertex.
            turn = UNIT + (a[0]*b[0] + a[1]*b[1]) // UNIT
            if turn < UNIT // 256:
                continue
            for x, y in _centers(a, b):
                tx, ty = (vx+x) // TILE, (vy+y) // TILE
                if not (0 <= tx < width*4096//TILE and 0 <= ty < height*4096//TILE):
                    continue
                ax, ay = _projection(a, x, y)
                bx, by = _projection(b, x, y)
                da = isqrt((x-ax)**2 + (y-ay)**2)
                db = isqrt((x-bx)**2 + (y-by)**2)
                if max(da, db) >= RADIUS or min(da, db) < RADIUS - MERGE:
                    continue
                apart = isqrt((ax-bx)**2 + (ay-by)**2)
                # A merged cap and plane needs both projections and a new
                # normal. Prefer this over a duplicated cap or separate hits.
                merge = 0
                if apart < MERGE:
                    merge = 192 if apart else 96
                upward = max(0, 2*y - ay - by) * 128 // (2*RADIUS)
                score = (proximity + merge + upward + min(turn, UNIT)*48//UNIT
                         + min(da, db) - (RADIUS - MERGE))
                key = tx, ty
                if score > scores.get(key, -1):
                    scores[key] = score
                    # Two simultaneous changes of support can involve four
                    # records. Keep the slope direction for a wheelbase check.
                    nx, ny = 2*x - ax - bx, 2*y - ay - by
                    slopes[key] = (nx // (RADIUS//2) if ny > RADIUS//2
                                   and abs(nx) > RADIUS//2 and apart < MERGE else None)
    # A mostly level bike can load two short inclined faces at once. Match
    # their support directions across the 1.7 m unloaded wheelbase. Bins of
    # 8 tiles (0.125 m) allow for wheel travel and unequal loads.
    support = {(x//8, y//8, slope) for (x, y), slope in slopes.items() if slope is not None}
    wheelbase = round(1.7*1024/TILE)
    for (x, y), slope in slopes.items():
        if slope is not None and any(((x+offset)//8, (y+rise)//8, slope) in support
                                     for offset in (-wheelbase, wheelbase)
                                     for rise in (-8, 0, 8)):
            scores[x, y] += 192
    order = sorted(scores, key=lambda p: (-scores[p], p[1], p[0]))
    # Use the packed query order to confirm the strongest geometric leads.
    # Beyond this bound, the vertex estimate alone ranks remaining locations.
    cache = {}
    for x, y in order[:256]:
        if has_merge(level, banks, x, y, cache):
            scores[x, y] += 384
    return sorted(((v, x, y) for (x, y), v in scores.items()),
                  key=lambda entry: (-entry[0], entry[2], entry[1]))
