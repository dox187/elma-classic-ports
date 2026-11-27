"""Exact wheel contacts in eight-by-four strips on Gravity Ride's braking slope."""
from corner_samples import POINTER, cell_records, contacts
from head_clearance import write_if_changed
from projection_tables import byte_lines
from wheel_terrain import RECORD

# The position selects only the strip. Every result is rebuilt independently
# from all packed edges in their original order. Positions use solver units.
STRIPS = {
    59: (169, 2, (
        (43296, 31597, 8), (43304, 31597, 8), (43312, 31596, 8),
        (43320, 31596, 8), (43328, 31596, 8), (43336, 31596, 8),
        (43344, 31596, 8), (43352, 31595, 8), (43360, 31595, 8),
        (43368, 31595, 8), (43376, 31595, 8), (43384, 31594, 8),
        (43392, 31594, 8), (43400, 31594, 8), (43408, 31594, 8),
        (43416, 31594, 8), (43424, 31594, 8), (43432, 31594, 8),
        (43440, 31594, 8), (43448, 31594, 8), (43456, 31593, 8),
        (43464, 31593, 8), (43472, 31592, 8), (43480, 31591, 8),
        (43488, 31592, 8), (43496, 31589, 8), (43528, 31580, 4),
        (43536, 31578, 4), (43616, 31549, 4), (43624, 31545, 4),
        (43672, 31519, 4), (43728, 31472, 4), (43768, 31418, 4))),
    76: (174, 1, (
        (44560, 31593, 8), (44568, 31597, 8), (44584, 31597, 8),
        (44592, 31597, 8), (44624, 31596, 4), (44632, 31596, 4),
        (44656, 31599, 4), (44664, 31599, 4), (44688, 31597, 4),
        (44696, 31598, 4))),
    80: (171, 1, (
        (43816, 31367, 8), (43824, 31360, 4), (43840, 31336, 4),
        (43856, 31325, 4), (43864, 31315, 4), (43872, 31303, 4),
        (43888, 31295, 4), (43896, 31289, 4), (43904, 31280, 4))),
}


def terrain_ends(levels, banks):
    """Highest referenced byte in each packed collision bank, including directories."""
    ends = {}
    for level in levels:
        base = level['base_bank']
        bank = level['directory_bank']
        offset = level['directory_address'] - 0x4000
        width, height = level['grid']
        end = offset + width * height * POINTER.size
        ends[bank] = max(ends.get(bank, 0), end)
        leaves = []
        for address, relative, count in POINTER.iter_unpack(banks[bank][offset:end]):
            if count == 255:
                child = base + relative
                start = address - 0x4000
                limit = start + 16 * POINTER.size
                ends[child] = max(ends.get(child, 0), limit)
                leaves.extend(POINTER.iter_unpack(banks[child][start:limit]))
            elif count:
                leaves.append((address, relative, count))
        for address, relative, count in leaves:
            if count:
                target = base + relative
                limit = address - 0x4000 + count * RECORD.size
                ends[target] = max(ends.get(target, 0), limit)
    return ends


def generate(gen, template, levels, banks):
    ends = terrain_ends(levels, banks)
    outputs = {}
    for bank, (page, pages, regions) in STRIPS.items():
        end = ends[bank]
        if any(value != 255 for value in banks[bank][end:]):
            raise ValueError(f'Extra data after terrain in bank {bank}')
        source = [f'.module gravity_terrain_{bank}', f'.area _CODE_{bank}',
                  f'_physics_bank_{bank}::', *byte_lines(banks[bank][:end]),
                  f'_riding_gravity_strip_{bank}::', f'GRAVITY_X_PAGE = {page}',
                  template.read_text(), 'gravity_columns:']
        # A null row-directory pointer rejects every position in a missing column.
        columns = [' .dw 65535,0'] * (pages * 32)
        indices = bytearray()
        rows, dictionary, palette = {}, {}, {}
        for x, y, height in regions:
            index = (x - page * 256) // 8
            if x % 8 or not 0 <= index < len(columns) or columns[index] != ' .dw 65535,0':
                raise ValueError(f'Invalid or duplicate strip at {x}, {y}')
            if height not in (4, 8):
                raise ValueError(f'Invalid strip height at {x}, {y}')
            columns[index] = f' .dw {y},gravity_entries+{len(indices)}'
            for yy in range(y, y + height):
                row = bytearray()
                for xx in range(x, x + 8):
                    edges = cell_records(levels[10], banks, xx, yy)
                    hit = contacts(edges, xx & 4095, yy & 4095)
                    if len(hit) == 1:
                        code = dictionary.setdefault(hit[0], len(dictionary)+1)
                    else:
                        code = 255 if hit else 0
                    row.append(code)
                indices.append(rows.setdefault(bytes(row), len(rows)))
            indices.extend([255] * (8 - height))
        if len(dictionary) >= 255 or len(rows) >= 255:
            raise ValueError(f'Strip index exceeds one byte in bank {bank}')
        values = bytearray()
        for nx, ny, length in dictionary:
            high = bytes((v >> 8) & 255 for v in (nx, ny, length))
            values.extend((nx & 255, ny & 255, length & 255,
                           palette.setdefault(high, len(palette))))
        source.extend([*columns, 'gravity_entries:', *byte_lines(indices),
                       'gravity_rows:', *byte_lines(b''.join(rows)),
                       'gravity_contacts:', *byte_lines(values),
                       'gravity_high:', *byte_lines(b''.join(palette)),
                       f'_riding_gravity_end_{bank}::'])
        path = gen / f'gravity_terrain_{bank}.s'
        write_if_changed(path, '\n'.join(source) + '\n')
        outputs[bank] = path
    return outputs
