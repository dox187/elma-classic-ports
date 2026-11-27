"""Certify Hang Tight's planar and shared-vertex wheel contacts by 32-unit column."""
from functools import lru_cache

from corner_samples import cell_records, contacts, normalize, q14
from gravity_strips import terrain_ends
from head_clearance import write_if_changed
from projection_tables import byte_lines
from wheel_terrain import RADIUS

BANK = 87
COURSE = 51
X_BASE = 65536
Y_BASE = 24576
# For each 32-unit X column starting at x=65792, the first 16-unit Y band
# and the exclusive end select one verified terrain expression. Y is measured
# from the top of its 4096-unit terrain cell.
BANDS = (
    (3, 214, 223), (1, 215, 222), (1, 216, 224), (1, 217, 226),
    (1, 217, 228), (1, 218, 230), (1, 218, 231), (1, 223, 233),
    (1, 228, 235), (3, 231, 236), (3, 233, 239), (3, 235, 241),
    (3, 233, 243), (3, 231, 244), (3, 230, 245), (3, 231, 246),
    (3, 232, 247), (3, 232, 247), (3, 233, 248), (3, 233, 248),
    (3, 233, 248), (3, 233, 248), (3, 233, 248), (3, 232, 247),
    (3, 232, 247), (3, 231, 246), (3, 230, 245), (3, 232, 243),
    (3, 235, 242), (3, 234, 240), (2, 232, 238), (2, 230, 236),
    (2, 226, 234), (2, 219, 232), (2, 217, 231), (2, 217, 229),
    (2, 216, 227), (2, 216, 225), (2, 215, 223), (2, 214, 221),
    (4, 213, 219), (4, 202, 207), (4, 200, 215), (4, 198, 213),
    (4, 194, 209), (4, 187, 202), (4, 183, 198), (4, 183, 198),
)


def expected(kind, x, y):
    px, py = ((905, 3443) if kind in (1, 3) else (1312, 3055))
    dx, dy = x - px, y - py
    if kind <= 2:
        nx, ny = (11292, -11872) if kind == 1 else (-11305, -11859)
        length = -q14(nx * dx + ny * dy)
        return ((-nx, -ny, length),) if 0 <= length < RADIUS else ()
    if dx*dx + dy*dy >= RADIUS*RADIUS:
        return ()
    nx, ny, length = normalize(dx, dy)
    return (normalize(q14(nx*length), q14(ny*length)),)


def certify(level, banks):
    @lru_cache(maxsize=None)
    def records_at(sx, sy):
        return cell_records(level, banks, X_BASE + sx*1024, Y_BASE + sy*1024)

    for column, (kind, lower, upper) in enumerate(BANDS, 8):
        for y in range(lower*16, upper*16):
            for x in range(column*32, (column+1)*32):
                records = records_at(x//1024, y//1024)
                if contacts(records, x, y) != expected(kind, x, y):
                    return False
    return True


def generate(gen, template, levels, banks):
    end = terrain_ends(levels, banks)[BANK]
    if any(value != 255 for value in banks[BANK][end:]):
        raise ValueError('Unexpected data following packed terrain in bank 87')
    source = ['.module hang_terrain', '.area _CODE_87', '_physics_bank_87::',
              *byte_lines(banks[BANK][:end])]
    if len(levels) > COURSE and certify(levels[COURSE], banks):
        source.extend([template.read_text(), 'hang_bounds:'])
        for kind, lower, upper in BANDS:
            source.append(f' .db {lower},{((kind-1) << 6) | (upper-lower)}')
    else:
        source.extend(['_hang_wheel_select::', ' ld hl,#_bowling_wheel_select',
                       ' ld e,#86', ' jp ___sdcc_bcall_ehl'])
    path = gen/'hang_terrain.s'
    write_if_changed(path, '\n'.join(source)+'\n')
    return path
