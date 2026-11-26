"""Pack exact terrain contacts for geometry-selected and frequently visited corners."""
import json
import struct

import corner_bank
from corner_coverage import has_merge, ranked_tiles
from corner_samples import cell_samples
from head_clearance import packed_inputs, write_if_changed

# Tiles are ranked by visits to wheel/edge merges on the braking replay.
# Only their addresses are profile data. Every cell is evaluated anew from
# the packed course for all 256 integer centers, independently of that replay.
COURSE = 10
Y_ORIGIN = 1952
REGIONS = {
    473: (2608, (
        (2624, 1961), (2625, 1960), (2626, 1959), (2623, 1962), (2619, 1965),
        (2622, 1963), (2626, 1960), (2619, 1966), (2621, 1964), (2620, 1965),
        (2628, 1958), (2630, 1955), (2620, 1964), (2621, 1963), (2628, 1957),
        (2629, 1956), (2627, 1958), (2627, 1959), (2629, 1957), (2630, 1956),
        (2625, 1961), (2622, 1962), (2623, 1961), (2621, 1962))),
    474: (2712, (
        (2738, 1961), (2735, 1964), (2737, 1962), (2733, 1966), (2719, 1974),
        (2736, 1963), (2734, 1965), (2737, 1961), (2723, 1973), (2730, 1969),
        (2720, 1974), (2727, 1971), (2734, 1966), (2732, 1967), (2725, 1972),
        (2729, 1970), (2731, 1968), (2722, 1973), (2724, 1972), (2736, 1962),
        (2728, 1970), (2721, 1973), (2734, 1964), (2735, 1963), (2726, 1971),
        (2726, 1972), (2733, 1967), (2732, 1968), (2718, 1974), (2729, 1969),
        (2720, 1973), (2723, 1972), (2740, 1958), (2717, 1974), (2741, 1957),
        (2743, 1955), (2742, 1956), (2716, 1974))),
}


def pack_cell(samples, upper_bytes):
    indices = bytearray()
    dictionary = {}
    for contacts in samples:
        if len(contacts) == 1:
            index = dictionary.setdefault(contacts[0], len(dictionary) + 1)
            if index >= 255:
                return None
        else:
            index = 255 if contacts else 0
        indices.append(index)
    # Three low bytes and an index reconstruct the six original bytes.
    # Neighbouring positions share the upper bytes of their normals and distance.
    palette = dict(upper_bytes)
    for contact in dictionary:
        high = tuple((v >> 8) & 255 for v in contact)
        key = palette.setdefault(high, len(palette))
        if key >= 256:
            return None
        indices.extend((key, *(v & 255 for v in contact)))
    return indices, palette


SPARSE_BANKS = (283, 447, 472, 475)
# Reserve a table on every course before spending more on the two dense regions.
COURSE_BYTE_TARGET = 392


def sparse_payload(samples):
    # Identical rows share their 16 indices. 0 and 255 mean empty and defer.
    colors, rows = {}, {}
    row_ids = bytearray()
    for start in range(0, 256, 16):
        indices = bytearray()
        for hit in samples[start:start+16]:
            index = 255 if hit else 0
            if len(hit) == 1:
                index = colors.setdefault(hit[0], len(colors) + 1)
                if index >= 255:
                    return None
            indices.append(index)
        row = bytes(indices)
        row_ids.append(16 * rows.setdefault(row, len(rows)))
    indices = row_ids + b''.join(rows)
    return indices + b''.join(struct.pack('<hhh', *c) for c in colors), len(indices)


def pack_courses(levels, banks, gen):
    choices, counts = [], []
    for course, level in enumerate(levels):
        ranked = ranked_tiles(level, banks)
        counts.append(len(ranked))
        if course == COURSE:
            continue  # Two dense banks already cover this course.
        cache, smallest = {}, None
        for _, x, y in ranked[:256]:
            if not has_merge(level, banks, x, y, cache):
                continue
            payload = sparse_payload(cell_samples(level, banks, x*16, y*16))
            if payload is None:
                continue
            item = (len(payload[0]), course, x*16, y*16, *payload)
            if smallest is None or item[0] < smallest[0]:
                smallest = item
            if item[0] <= COURSE_BYTE_TARGET:
                break
        if smallest is None:
            raise ValueError(f'No encodable multi-edge tile on course {course+1}')
        choices.append(smallest)
    storage = {bank: bytearray() for bank in SPARSE_BANKS}
    desc = [bytes(11)] * len(levels)
    cells = []
    for size, course, x, y, data, index_size in sorted(choices, reverse=True):
        def room(bank):
            start, end = corner_bank.RANGES[bank]
            return end - start - len(storage[bank])
        available = [bank for bank in storage if size <= room(bank)]
        if not available:
            raise ValueError(f'Cannot place {size} bytes for course {course+1}')
        bank = min(available, key=room)
        address = 0x4000 + corner_bank.RANGES[bank][0] + len(storage[bank])
        storage[bank].extend(data)
        desc[course] = (x.to_bytes(3,'little') + y.to_bytes(3,'little') +
                        struct.pack('<BHH', bank-256, address, address+index_size))
        cells.append([course, x, y])
    directory = '_riding_sparse_courses::\n' + ''.join(
        ' .db ' + ','.join(map(str, row)) + '\n' for row in desc)
    sources = {bank: corner_bank.generate(gen, bank, data) for bank, data in storage.items() if data}
    return sources, cells, directory, counts


def generate(gen, template):
    levels, banks, _ = packed_inputs(gen)
    sources, cells, directory, counts = pack_courses(levels, banks, gen)
    for bank, (origin, priority) in REGIONS.items():
        # $4100: tile directory. $4500: 128 little-endian tile pointers.
        data = bytearray(1024 + 256 + 3*256)
        upper_bytes = {}
        count = 0
        for x, y in priority:
            col, row = x-origin, y-Y_ORIGIN
            if not (0 <= col < 32 and 0 <= row < 32):
                raise ValueError('Corner tile outside its bank directory')
            packed = pack_cell(cell_samples(levels[COURSE], banks, x*16, y*16), upper_bytes)
            if packed is None or len(data) + len(packed[0]) > 0x3b00:
                continue
            tile, upper_bytes = packed
            count += 1
            data[row*32 + col] = count
            struct.pack_into('<H', data, 1024 + 2*count, 0x4100 + len(data))
            data.extend(tile)
            cells.append([COURSE, x*16, y*16])
        for high, index in upper_bytes.items():
            for component, value in enumerate(high):
                data[1280 + component*256 + index] = value
        prefix = (f'CORNER_X_BLOCK = {origin // 16}\nCORNER_X_INSET = {origin % 16}\n'
                  f'CORNER_Y_BLOCK = {Y_ORIGIN // 16}\n'
                  f'corner_size_{bank} == {len(data)}\n')
        sources[bank] = corner_bank.generate(gen, bank, data, prefix_asm=prefix + template.read_text())
    write_if_changed(gen/'corner_cells.json', json.dumps({'cells': cells, 'candidate_counts': counts}) + '\n')
    return sources, directory
