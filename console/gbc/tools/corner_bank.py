"""Link sparse corner lookup data into unused ranges of packed scenery banks."""
from head_clearance import write_if_changed
from head_lane_tables import verify_graphics_range
from projection_tables import byte_lines


# Offsets within the original level_bank arrays. The normal atlas follows
# these arrays at $7c00, so each replacement must keep the original length.
RANGES = {283: (0x3600, 0x3c00), 447: (0x27f0, 0x3c00),
          472: (0x0e00, 0x3c00), 473: (0, 0x3c00),
          474: (0, 0x3c00), 475: (0x2c00, 0x3c00)}
CODE_BYTES = 256


def generate(gen, bank, data, dest=None, *, prefix_asm=None):
    """Return an assembly source that replaces level_bank_<bank>.c in link order."""
    start, limit = RANGES[bank]
    data_start = start + (CODE_BYTES if prefix_asm is not None else 0)
    end = data_start + len(data)
    if not data or end > limit:
        raise ValueError(f'Corner lookup requires 1..{limit-data_start} bytes in bank {bank}')
    verify_graphics_range(gen, end-start, bank, start)
    original = (gen / f'level_bank_{bank}.c').read_text()
    values = original.split('{', 1)[1].split('}', 1)[0].strip().rstrip(',')
    payload = bytes(map(int, values.split(',')))
    if end > len(payload):
        raise ValueError(f'Corner lookup exceeds original scenery array in bank {bank}')
    source = [f'.module corner_bank_{bank}', f'.area _CODE_{bank}', f'_level_bank_{bank}::',
              *byte_lines(payload[:start])]
    if prefix_asm is not None:
        source.extend([f'_riding_corner_code_{bank}::', prefix_asm, f'_riding_corner_code_end_{bank}::',
                       f' .ds {CODE_BYTES}-(.-_riding_corner_code_{bank})'])
    source.extend([f'_riding_corner_data_{bank}::', *byte_lines(data),
                   f'_riding_corner_end_{bank}::', *byte_lines(payload[end:])])
    target = (dest or gen) / f'corner_bank_{bank}.s'
    write_if_changed(target, '\n'.join(source) + '\n')
    return target


def after_numeric_prefix(table, earlier, bank, end_label):
    # The earlier assembly owns everything through its end label, including
    # leaf data or scenery ahead of the numeric table. Keep that prefix exact.
    prefix, tail = earlier.read_text().split(end_label + '::\n')
    amount = sum(len(line[5:].split(',')) for line in prefix.splitlines() if line.startswith(' .db '))
    if amount != RANGES[bank][0] or any(line and not line.startswith(' .db ') for line in tail.splitlines()):
        raise ValueError(f'Numeric prefix in bank {bank} no longer abuts corner data')
    label = f'_riding_corner_data_{bank}::\n'
    write_if_changed(table, prefix + end_label + '::\n' + label + table.read_text().split(label)[1])


def matches_rom(rom, source, bank):
    """Compare literal bytes before and after any assembled reader page."""
    asm = source.read_text()
    before, literals = asm.split(f'_riding_corner_data_{bank}::\n')
    code = f'_riding_corner_code_{bank}::\n'
    has_code = code in before
    before = before.partition(code)[0]
    def db_values(section):
        return bytes(int(value) for line in section.splitlines() if line.startswith(' .db ')
                     for value in line[5:].split(','))
    prefix, suffix = db_values(before), db_values(literals)
    base = bank * 16384
    pos = base + len(prefix) + (CODE_BYTES if has_code else 0)
    return bool(suffix and rom[base:base+len(prefix)] == prefix and rom[pos:pos+len(suffix)] == suffix)


def validate_layout(symbols, bank, size, *, with_code=False):
    """Verify the extent and address used by the reader in the linked ROM."""
    start, limit = RANGES[bank]
    base = (bank << 16) + 0x4000
    data_start = base + start + (CODE_BYTES if with_code else 0)
    end = data_start + size
    if (size <= 0 or end > base + limit or symbols.get(f'_level_bank_{bank}') != base or
            symbols.get(f'_riding_corner_data_{bank}') != data_start or
            symbols.get(f'_riding_corner_end_{bank}') != end):
        raise ValueError(f'Corner lookup moved outside its assigned range in bank {bank}')
    if with_code and (symbols.get(f'_riding_corner_code_{bank}') != base + start or
                      not base + start < symbols.get(f'_riding_corner_code_end_{bank}', 0) <= data_start):
        raise ValueError(f'Corner reader must fit its {CODE_BYTES}-byte page in bank {bank}')
    for prefix in ('_normal_atlas_tail_', '_wheel_terrain_tail_'):
        if symbols.get(f'{prefix}{bank}', base + 0x4000) < end:
            raise ValueError(f'Corner lookup overlaps {prefix}{bank}')
