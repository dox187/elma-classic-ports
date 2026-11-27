"""Exact wheel contacts in eight-unit-wide strips on Gravity Ride's braking slope."""
from corner_samples import POINTER, cell_records, contacts
from head_clearance import write_if_changed
from projection_tables import byte_lines
from wheel_terrain import RECORD

# The position selects only the strip. Every result is rebuilt independently
# from all packed edges in their original order. Each (x, y, mask) covers
# eight X units on the selected rows within the next eight Y units.
STRIPS = {
    59: (169, 2, (
        (43296, 31597, 0xfd), (43304, 31597, 0xfd), (43312, 31596, 0xf9),
        (43320, 31596, 0xfd), (43328, 31596, 0xfd), (43336, 31596, 0xfd),
        (43344, 31595, 0xf9), (43352, 31595, 0xfd), (43360, 31595, 0xfd),
        (43368, 31595, 0xfd), (43376, 31595, 0xfd), (43384, 31594, 0xf9),
        (43392, 31594, 0xfd), (43400, 31594, 0xfd), (43408, 31594, 0xfd),
        (43416, 31594, 0xfd), (43424, 31594, 0xfd), (43432, 31594, 0xff),
        (43440, 31594, 0xff), (43448, 31594, 0xff), (43456, 31589, 0xd1),
        (43464, 31589, 0xd1), (43472, 31589, 0xf9), (43480, 31588, 0xd9),
        (43488, 31587, 0xf9), (43496, 31589, 0xf9), (43528, 31579, 0x93),
        (43536, 31578, 0xcf), (43544, 31578, 0xf1), (43560, 31609, 0xff),
        (43584, 31609, 0xff), (43600, 31608, 0xff), (43616, 31549, 0x83),
        (43624, 31545, 0x85), (43632, 31568, 0xff), (43640, 31608, 0xff),
        (43648, 31575, 0xff), (43656, 31608, 0xff), (43664, 31581, 0xff),
        (43672, 31519, 0xe1), (43688, 31590, 0xff), (43696, 31608, 0xff),
        (43704, 31608, 0xff), (43712, 31597, 0xff), (43728, 31472, 0xe1),
        (43736, 31600, 0xff), (43744, 31608, 0xff), (43752, 31603, 0xff),
        (43760, 31604, 0xff), (43768, 31417, 0x1d))),
    76: (174, 1, (
        (44544, 31589, 0xff), (44552, 31597, 0xff), (44560, 31593, 0xff),
        (44568, 31597, 0xff), (44576, 31597, 0xff), (44584, 31597, 0xfd),
        (44592, 31597, 0xf9), (44600, 31597, 0xf1), (44608, 31597, 0xe1),
        (44616, 31598, 0xe5), (44624, 31598, 0xc1), (44632, 31599, 0xe5),
        (44640, 31599, 0xe1), (44648, 31599, 0xe1), (44656, 31599, 0xe5),
        (44664, 31599, 0xe1), (44672, 31599, 0xe1), (44680, 31598, 0xc7),
        (44688, 31598, 0xc1), (44696, 31598, 0xc3), (44792, 31599, 0xe1))),
    80: (171, 1, (
        (43816, 31367, 0x41), (43824, 31360, 0x01), (43832, 31348, 0x01),
        (43840, 31336, 0x01), (43856, 31325, 0x01), (43864, 31317, 0x01),
        (43872, 31306, 0x01), (43888, 31295, 0x01), (43896, 31289, 0x01),
        (43904, 31273, 0x81), (43920, 31282, 0xff), (43944, 31295, 0xff),
        (43976, 31308, 0xff), (43992, 31316, 0xff), (44016, 31329, 0xff))),
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
        for x, y, mask in regions:
            index = (x - page * 256) // 8
            if x % 8 or not 0 <= index < len(columns) or columns[index] != ' .dw 65535,0':
                raise ValueError(f'Invalid or duplicate strip at {x}, {y}')
            if not 0 < mask <= 255:
                raise ValueError(f'Invalid strip row mask at {x}, {y}')
            columns[index] = f' .dw {y},gravity_entries+{len(indices)}'
            for dy in range(8):
                if not mask & (1 << dy):
                    indices.append(255)
                    continue
                yy = y + dy
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
