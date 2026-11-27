"""Prove empty and planar wheel queries on Bowling from its ordered terrain."""
from functools import lru_cache

from corner_samples import cell_records, contacts, normalize, q14
from gravity_strips import terrain_ends
from head_clearance import write_if_changed
from projection_tables import byte_lines
from wheel_terrain import RADIUS

BANK = 86
COURSE = 45
FLAT_Y = 66496
SHARED_CAP = 1
CAP_VERTEX = (173205, 66135)
# Half-open X runs covering all 64 rows. Zero is empty and one selects
# the shared vertex. Codes 106..109 give the first planar distance minus 256.
FLAT_RUNS = (
    (172032, 173011, 0), (173011, 173208, SHARED_CAP),
    (173400, 173687, 106), (173687, 174014, 107),
    (174014, 174342, 108), (174342, 174649, 109),
)


def slope_contains(x, y):
    if 171776 <= x < 172288 and 65344 <= y < 65792:
        return True
    if 171776 <= x < 171984 and 65280 <= y < 65344:
        return True
    return 171888 <= x < 171984 and 65024 <= y < 65280 and y-x >= -106691


def certify(level, banks):
    @lru_cache(maxsize=None)
    def records(subx, suby):
        return cell_records(level, banks, subx*1024, suby*1024)

    def matches(x, y, expected):
        return contacts(records(x//1024, y//1024), x & 4095, y & 4095) == expected

    for lo, hi, code in FLAT_RUNS:
        for x in range(lo, hi):
            for dy in range(64):
                expected = ()
                if code == SHARED_CAP:
                    dx, vy = x - CAP_VERTEX[0], FLAT_Y + dy - CAP_VERTEX[1]
                    if dx*dx + vy*vy < RADIUS*RADIUS:
                        nx, ny, d = normalize(dx, vy)
                        expected = (normalize(q14(nx*d), q14(ny*d)),)
                elif code:
                    length = 256 + code + dy
                    if length < RADIUS:
                        expected = ((50, 16384, length),)
                if not matches(x, FLAT_Y+dy, expected):
                    return False
    for x in range(171776, 172288):
        for y in range(65024, 65792):
            if slope_contains(x, y):
                # The solver rounds the original inward distance before negating.
                length = -q14(13546*(x-172885) - 9217*(y-65934))
                expected = ((-13546, 9217, length),) if 0 <= length < RADIUS else ()
                if not matches(x, y, expected):
                    return False
    return True


def generate(gen, template, levels, banks):
    end = terrain_ends(levels, banks)[BANK]
    if any(value != 255 for value in banks[BANK][end:]):
        raise ValueError('Unexpected data after packed terrain in bank 86')
    source = ['.module bowling_terrain', '.area _CODE_86', '_physics_bank_86::',
              *byte_lines(banks[BANK][:end]), '_bowling_wheel_select::']
    if len(levels) > COURSE and certify(levels[COURSE], banks):
        start_x = FLAT_RUNS[0][0]
        stop_x = (FLAT_RUNS[-1][1]+255) & ~255
        assert start_x % 256 == 0 and start_x >> 16 == (stop_x-1) >> 16
        source.extend([f'bowling_start_page = {(start_x >> 8) & 255}',
                       f'bowling_page_count = {(stop_x-start_x) >> 8}',
                       f'bowling_cap_x = {CAP_VERTEX[0] & 4095}',
                       f'bowling_cap_y = {CAP_VERTEX[1] & 4095}',
                       f'bowling_first_y = {FLAT_Y & 4095}',
                       template.read_text(), 'bowling_ranges:'])
        end_x = FLAT_RUNS[0][0]
        for lo, hi, code in FLAT_RUNS:
            if lo != end_x:
                source.extend([f' .dw {lo & 65535}', ' .db 255'])
            source.extend([f' .dw {hi & 65535}', f' .db {code}'])
            end_x = hi
        source.extend([f' .dw {stop_x & 65535}', ' .db 255'])
    else:
        source.extend([' ld hl,#_riding_corner_select', ' ld e,#32', ' jp ___sdcc_bcall_ehl'])
    source.append('_bowling_terrain_end::')
    path = gen/'bowling_terrain.s'
    write_if_changed(path, '\n'.join(source) + '\n')
    return path
