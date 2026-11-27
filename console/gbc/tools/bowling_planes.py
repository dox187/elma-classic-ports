"""Prove empty and planar wheel queries on Bowling from its ordered terrain."""
from functools import lru_cache

from corner_samples import cell_records, contacts, q14
from gravity_strips import terrain_ends
from head_clearance import write_if_changed
from projection_tables import byte_lines
from wheel_terrain import RADIUS

BANK = 86
COURSE = 45
FLAT_Y = 66496
# Half-open X runs. Each covers all 64 rows. A zero code denotes empty;
# other codes give the initial distance minus 256 at the first row.
FLAT_RUNS = (
    (172032, 173011, 0),
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
                length = 256 + code + dy
                expected = ((50, 16384, length),) if code and length < RADIUS else ()
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
        source.extend([template.read_text(), 'bowling_ranges:'])
        for lo, hi, code in FLAT_RUNS:
            source.extend([f' .dw {lo & 65535},{hi & 65535}', f' .db {code}'])
        source.append(' .dw 0')
    else:
        source.extend([' ld hl,#_riding_corner_select', ' ld e,#32', ' jp ___sdcc_bcall_ehl'])
    source.append('_bowling_terrain_end::')
    path = gen/'bowling_terrain.s'
    write_if_changed(path, '\n'.join(source) + '\n')
    return path
