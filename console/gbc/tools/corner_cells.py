"""Pack exact terrain contacts for geometry-selected and frequently visited corners."""
import json
import struct

import corner_bank
import corner_pairs
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


def shared_rows(indices):
    row_slots = {}
    row_ids = bytearray()
    for offset in range(0, 256, 16):
        row = bytes(indices[offset:offset+16])
        row_ids.append(16 * row_slots.setdefault(row, len(row_slots)))
    return row_ids + b''.join(row_slots)


def pack_cell(samples, upper_bytes, address):
    indices = bytearray()
    dictionary = {}
    pair_header = any(len(hit) == 2 for hit in samples)
    for contacts in samples:
        if len(contacts) == 1:
            index = dictionary.setdefault(contacts[0], len(dictionary) + 1 + pair_header)
            if index >= 255:
                return None
        else:
            index = 255 if contacts else 0
        indices.append(index)
    # Three low bytes and an index reconstruct the six original bytes.
    # Neighbouring positions share the upper bytes of their normals and distance.
    palette = dict(upper_bytes)
    if pair_header:
        indices.extend(bytes(4))  # First dictionary record points to the ordered-pair directory.
    for contact in dictionary:
        high = tuple((v >> 8) & 255 for v in contact)
        key = palette.setdefault(high, len(palette))
        if key >= 256:
            return None
        indices.extend((key, *(v & 255 for v in contact)))
    rows = shared_rows(indices[:256])
    # The high bit of a directory entry selects shared rows. A raw tile's
    # dictionary always starts 256 bytes after its origin.
    index_size = 2 + len(rows)
    shared = index_size < 256
    if shared:
        indices = struct.pack('<H', address+index_size) + rows + indices[256:]
    return indices, palette, shared


SPARSE_BANKS = (283, 447, 472, 475)
# Reserve a table on every course before spending more on the two dense regions.
COURSE_BYTE_TARGET = 392


def sparse_payload(samples):
    colors, indices = {}, bytearray()
    for hit in samples:
        index = 255 if hit else 0
        if len(hit) == 1:
            index = colors.setdefault(hit[0], len(colors) + 1)
            if index >= 255:
                return None
        indices.append(index)
    indices = shared_rows(indices)
    # Preserve the geometry tile selection metric used before high-byte packing.
    selection_size = len(indices) + 6*len(colors)
    palette, records = {}, bytearray()
    for contact in colors:
        upper = bytes((v >> 8) & 255 for v in contact)
        records.extend((*(v & 255 for v in contact), palette.setdefault(upper, len(palette))))
    # The linker places this tile before its final address is known. The first
    # word of the dictionary is a relative palette pointer until allocation.
    data = indices + struct.pack('<HH', 4 + len(records), 0) + records + b''.join(palette)
    return data, len(indices), selection_size


def sparse_start(bank):
    start = corner_bank.RANGES[bank][0]
    return start + (corner_bank.CODE_BYTES if bank == corner_pairs.PAIR_BANK else 0)


def pack_courses(levels, banks):
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
            data, index_size, selection_size = payload
            item = (selection_size, course, x*16, y*16, data, index_size)
            if smallest is None or selection_size < smallest[0]:
                smallest = item
            if selection_size <= COURSE_BYTE_TARGET:
                break
        if smallest is None:
            raise ValueError(f'No encodable multi-edge tile on course {course+1}')
        choices.append(smallest[1:])
    # The two-strip reader selects the second tile by the middle X byte.
    primary_strip = {course: (x >> 8) & 255 for course, x, _, _, _ in choices}
    for course, x, y in corner_pairs.EXTRA_TILES:
        first = primary_strip.pop(course, None)
        if first is None or first == (x >> 8) & 255:
            raise ValueError(f'Course {course+1} needs two distinct X strips for a second corner tile')
        data, index_size, _ = sparse_payload(cell_samples(levels[course], banks, x, y))
        choices.append((course, x, y, data, index_size))
    storage = {bank: bytearray() for bank in SPARSE_BANKS}
    desc, secondary = [bytes(11)] * len(levels), []
    cells, pair_slots = [], {}
    for course, x, y, data, index_size in sorted(choices, key=lambda item: len(item[3]), reverse=True):
        def room(bank):
            return corner_bank.RANGES[bank][1] - sparse_start(bank) - len(storage[bank])
        available = [bank for bank in storage if len(data) <= room(bank)]
        if not available:
            raise ValueError(f'Cannot place {len(data)} bytes for course {course+1}')
        bank = min(available, key=room)
        address = 0x4000 + sparse_start(bank) + len(storage[bank])
        dictionary = address + index_size
        palette, = struct.unpack_from('<H', data, index_size)
        struct.pack_into('<H', data, index_size, dictionary + palette)
        pair_slots[course, x, y] = (bank, len(storage[bank]) + index_size + 2)
        storage[bank].extend(data)
        descriptor = (x.to_bytes(3,'little') + y.to_bytes(3,'little') +
                      struct.pack('<BHH', bank-256, address, dictionary))
        if (course, x, y) in corner_pairs.EXTRA_TILES:
            secondary.append(bytes([course]) + descriptor)
        else:
            desc[course] = descriptor
        cells.append([course, x, y])
    def records(rows):
        return ''.join(' .db ' + ','.join(map(str, row)) + '\n' for row in rows)
    directory = '_riding_sparse_courses::\n' + records(desc)
    directory += 'corner_secondary_keys::\n' + records(secondary) + ' .db 255\n'
    return storage, pair_slots, cells, directory, counts


def generate(gen, template):
    levels, banks, _ = packed_inputs(gen)
    storage, pair_slots, cells, directory, counts = pack_courses(levels, banks)
    prefixes = {}
    for bank, (origin, priority) in REGIONS.items():
        # $4100: tile directory. $4500: 128 little-endian tile pointers.
        data = bytearray(1024 + 256 + 3*256)
        upper_bytes = {}
        count = 0
        for x, y in priority:
            col, row = x-origin, y-Y_ORIGIN
            if not (0 <= col < 32 and 0 <= row < 32):
                raise ValueError('Corner tile outside its bank directory')
            address = 0x4100 + len(data)
            packed = pack_cell(cell_samples(levels[COURSE], banks, x*16, y*16), upper_bytes, address)
            if packed is None or len(data) + len(packed[0]) > 0x3b00:
                continue
            tile, upper_bytes, shared = packed
            count += 1
            if count >= 128:
                raise ValueError('Corner tile pointer directory is full')
            data[row*32 + col] = count | (0x80 if shared else 0)
            struct.pack_into('<H', data, 1024 + 2*count, address)
            dictionary = (int.from_bytes(tile[:2], 'little') - address) if shared else 256
            pair_slots[COURSE, x*16, y*16] = (bank, len(data) + dictionary)
            data.extend(tile)
            cells.append([COURSE, x*16, y*16])
        for high, index in upper_bytes.items():
            for component, value in enumerate(high):
                data[1280 + component*256 + index] = value
        prefix = (f'CORNER_X_BLOCK = {origin // 16}\nCORNER_X_INSET = {origin % 16}\n'
                  f'CORNER_Y_BLOCK = {Y_ORIGIN // 16}\n'
                  f'corner_size_{bank} == {len(data)}\n')
        storage[bank] = data
        prefixes[bank] = prefix + template.read_text()
    pair_tiles = {}
    for key in pair_slots:
        course, x, y = key
        samples = cell_samples(levels[course], banks, x, y)
        if any(len(hit) == 2 for hit in samples):
            pair_tiles[key] = samples
    bank = corner_pairs.PAIR_BANK
    start, end = corner_bank.RANGES[bank]
    address = 0x4000 + start + corner_bank.CODE_BYTES + len(storage[bank])
    prefixes[bank] = template.with_name('corner_pair_reader.inc').read_text()
    data, pointers, blocks = corner_pairs.pack_tiles(pair_tiles, end + 0x4000 - address, address)
    for key, pointer in pointers.items():
        tile_bank, offset = pair_slots[key]
        struct.pack_into('<H', storage[tile_bank], offset, pointer)
    storage[bank].extend(data)
    sources = {bank: corner_bank.generate(gen, bank, data, prefix_asm=prefixes.get(bank))
               for bank, data in storage.items() if data}
    write_if_changed(gen/'corner_cells.json', json.dumps({'cells': cells, 'candidate_counts': counts, 'pair_blocks': blocks}) + '\n')
    return sources, directory
