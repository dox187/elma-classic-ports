"""Compile complete wheel contacts on Haircut's closely spaced sloping faces."""
from functools import lru_cache
from itertools import chain, product

from corner_samples import cell_records, contacts, normalize, q14
from head_clearance import packed_inputs
from projection_tables import byte_lines
from wheel_terrain import RADIUS, classify

COURSE = 38
X, Y = 153600, 25600
WIDTH, HEIGHT, TILE = 72, 64, 32
MISS = 15
VERTEX = (154144, 27204)
# World-space origins and packed Q14 tangent components. Changing a course
# can only reduce coverage: the complete ordered result must still agree.
PLANES = ((155271, 26075, -11575, 11596), (154435, 25639, -14975, -6647),
          (154144, 27204, 2995, -16108), (159540, 28574, -14140, -8277))


def expression(code, x, y):
    if code == 0:
        return ()
    if code == 1:
        dx, dy = x - VERTEX[0], y - VERTEX[1]
        if dx*dx + dy*dy >= RADIUS*RADIUS:
            return ()
        nx, ny, d = normalize(dx, dy)
        return (normalize(q14(nx*d), q14(ny*d)),)
    px, py, ex, ey = PLANES[code-2]
    d = q14(-ey*(x-px) + ex*(y-py))
    if abs(d) >= RADIUS:
        return ()
    return ((-ey, ex, d) if d >= 0 else (ey, -ex, -d),)


def tile_code(records, x, y):
    # Each aligned tile lies in a single packed leaf. A conservative empty
    # proof needs no enumeration. A potential plane may still clip its AABB.
    broad, _ = classify(records, x & 4095, y & 4095, TILE)
    if broad == 0:
        return 0
    allowed = list(range(2 + len(PLANES)))
    if 0 < broad < 64:
        px, py, _, _, ex, ey, *_ = records[broad-1]
        plane = (x - (x & 4095) + px, y - (y & 4095) + py, ex, ey)
        if plane in PLANES:
            allowed = [0, 2 + PLANES.index(plane)]
    # Try the extremes first, then prove every remaining integer center.
    probes = ((16, 16), (0, 0), (0, 31), (31, 0), (31, 31))
    for dx, dy in chain(probes, product(range(TILE), repeat=2)):
        answer = contacts(records, (x & 4095) + dx, (y & 4095) + dy)
        allowed = [code for code in allowed if expression(code, x+dx, y+dy) == answer]
        if not allowed:
            return MISS
    return allowed[0]


def tile_map(gen):
    levels, banks, _ = packed_inputs(gen)
    if COURSE >= len(levels):
        return [[MISS]*WIDTH for _ in range(HEIGHT)]
    level = levels[COURSE]

    @lru_cache(None)
    def leaf(cx, cy):
        return cell_records(level, banks, 1024*cx, 1024*cy)

    return [[tile_code(leaf(x//1024, y//1024), x, y) for x in range(X, X+WIDTH*TILE, TILE)]
            for y in range(Y, Y+HEIGHT*TILE, TILE)]


def packed_pages(grid):
    pages, blocks, directory = {}, {}, []
    fallback = bytes(WIDTH*HEIGHT//64), [bytes(8)], [bytes([255])*4]
    # A 256u page has eight 4x2 blocks of 32u tiles. Both the page's block
    # indices and the blocks' packed contact codes are shared across pages.
    for y in range(0, HEIGHT, 8):
        for x in range(0, WIDTH, 8):
            ids = []
            for row in range(y, y+8, 2):
                for col in range(x, x+8, 4):
                    block = bytes(grid[j][i] | grid[j][i+1] << 4
                                  for j in (row, row+1) for i in (col, col+2))
                    if block not in blocks and len(blocks) == 64:
                        return fallback
                    ids.append(blocks.setdefault(block, len(blocks)))
            page = bytes(ids)
            # The fixed rolling-table gaps bound both dictionaries. A larger
            # alternate course pack falls back to the hand-held iterator.
            if page not in pages and len(pages) == 38:
                return fallback
            directory.append(pages.setdefault(page, len(pages)))
    return bytes(directory), list(pages), list(blocks)


def bank_sections(gen):
    directory, pages, blocks = packed_pages(tile_map(gen))

    def data(name, records):
        return [name+':', *byte_lines(b''.join(records))]

    planes = ['haircut_planes:']
    for x, y, ex, ey in PLANES:
        planes.append(f' .dw {x & 65535},{y & 65535},{ex},{-ey}')
    return {
        (29, 7): [' wheel_rect_query'],
        (29, 8): [' wheel_rect_plane'],
        (29, 9): [' wheel_rect_cap', *planes],
        (29, 10): ['haircut_directory:', *byte_lines(directory)],
        (30, 4): data('haircut_pages0', pages[:16]),
        (30, 5): data('haircut_pages1', pages[16:32]),
        (30, 6): [*data('haircut_pages2', pages[32:]), ' wheel_rect_tile_code'],
        (30, 7): data('haircut_blocks0', blocks[:32]),
        (30, 8): data('haircut_blocks1', blocks[32:]),
    }
