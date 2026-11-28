"""Share raw pattern array ends between courses without changing the DMA reader."""
from itertools import combinations
import json
import struct

import numpy as np

from assets import array, rgb555
import corner_bank
import head_lane_tables
import rider_map_tables
import rolling_map_banks
from rolling_tables import REACTION_WORD_BANK

BANK_BYTES = 0x4000
# Four consecutive banks between the last pinned graphics overlays.
RELEASED = (465, 466, 467, 468)


def packed_maps(ids, attrs):
    height, width = ids.shape
    for y in range(0, height, 16):
        for x in range(0, width, 32):
            values = ids[y:y+16, x:x+32].ravel()
            low = bytes(values.astype(np.uint8))
            high = bytes((values >> 8).astype(np.uint8))
            attr = bytes(attrs[y:y+16, x:x+32].ravel())
            if high.count(high[0]) == 512 and high[0] < 64:
                yield 0x8000 | (high[0] << 9), low + attr
            elif max(high) < 8 and not any(value & 0x98 for value in attr):
                yield 0x4000, low + bytes(a | ((v & 3) << 3) | ((v & 4) << 5)
                                         for a, v in zip(attr, high))
            else:
                yield 0, low + high + attr


def lengths(ids, attrs):
    # The original artwork uses only CGB palette and flip bits.
    if np.any(attrs & 0x98):
        raise ValueError('Unexpected CGB attribute bits in rendered art')
    h, w = ids.shape
    high = (ids >> 8).reshape(h//16, 16, w//32, 32).transpose(0, 2, 1, 3).reshape(-1, 512)
    upper, lower = high.max(axis=1), high.min(axis=1)
    return 512 * np.count_nonzero((upper >= 8) & ((upper != lower) | (upper >= 64)))


def order_pair(a, b, overlap):
    # ID 0 is the out-of-map tile in both courses. B's first tile must
    # start the shared suffix. If A needs that tile first as well, retain
    # the duplicate at A's start. B's only extra tile can be its ID 0.
    lead = [a[0], *(t for t in a[1:] if t not in overlap and t != b[0])]
    shared = [b[0], *(t for t in b[1:] if t in overlap)]
    tail = [t for t in b[1:] if t not in overlap]
    return lead, shared, tail


def remap(ids, original, reordered):
    # Assign a repeated border pattern to its original zero ID.
    slots = {tile: i for i, tile in reversed(list(enumerate(reordered)))}
    return np.asarray([slots[tile] for tile in original], dtype=np.uint16)[ids]


def best_pairs(courses):
    sets = [set(patterns) for patterns, _, _ in courses]
    base = [lengths(ids, attrs) for _, ids, attrs in courses]
    candidates = []
    for i, j in combinations(range(len(courses)), 2):
        # Resident and spatially colored courses retain their exact ID order.
        if min(len(sets[i]), len(sets[j])) <= 1024:
            continue
        overlap = sets[i] & sets[j]
        if len(overlap) < 32:
            continue
        for first, second in ((i, j), (j, i)):
            a, ids_a, attr_a = courses[first]
            b, ids_b, attr_b = courses[second]
            lead, shared, tail = order_pair(a, b, overlap)
            if len(lead) + len(shared) >= 32768:
                continue
            estimate = 16 * (len(a) + len(b) - len(lead) - len(shared) - len(tail))
            estimate -= lengths(remap(ids_a, a, lead + shared), attr_a) - base[first]
            estimate -= lengths(remap(ids_b, b, shared + tail), attr_b) - base[second]
            if estimate > 0:
                candidates.append((estimate, first, second))
    used = set()
    for _, first, second in sorted(candidates, reverse=True):
        if first not in used and second not in used:
            yield first, second, order_pair(courses[first][0], courses[second][0],
                                           sets[first] & sets[second])
            used.update((first, second))


class Layout:
    def __init__(self, first, last, released):
        self.banks = {b: bytearray(BANK_BYTES) for b in range(first, last+1) if b not in released}
        self.ends = dict.fromkeys(self.banks, 0)
        self.holes = [[b*BANK_BYTES, (b+1)*BANK_BYTES] for b in self.banks]

    def write(self, start, data):
        bank, offset = divmod(start, BANK_BYTES)
        while data:
            n = min(len(data), BANK_BYTES-offset)
            self.banks[bank][offset:offset+n] = data[:n]
            self.ends[bank] = max(self.ends[bank], offset+n)
            data = data[n:]
            bank, offset = bank+1, 0

    def reserve(self, bank, offset, data):
        start = bank*BANK_BYTES+offset
        end = start+len(data)
        i = next(i for i, (lo, hi) in enumerate(self.holes) if lo <= start <= end <= hi)
        lo, hi = self.holes.pop(i)
        self.holes[i:i] = [[a,b] for a,b in ((lo,start),(end,hi)) if a < b]
        self.write(start, data)

    def place(self, data, align=1, span=False):
        n = len(data)
        holes = self.holes if not span else self.join_holes()
        valid = []
        for lo, hi in holes:
            start = (lo+align-1) & -align
            if start+n <= hi:
                valid.append((hi-start-n, start))
        if not valid:
            raise ValueError(f'No scenery extent fits {n} bytes')
        _, start = min(valid)
        bank, offset = divmod(start, BANK_BYTES)
        end = start+n
        for b in range(bank, (end-1)//BANK_BYTES+1):
            lo = max(start,b*BANK_BYTES)
            hi = min(end,(b+1)*BANK_BYTES)
            self.reserve(b, lo % BANK_BYTES, data[lo-start:hi-start])
        return bank, 0x4000+offset

    def join_holes(self):
        merged = []
        for lo, hi in self.holes:
            if merged and merged[-1][1] == lo:
                merged[-1][1] = hi
            else:
                merged.append([lo,hi])
        return merged


def load_tiles(gen, record):
    path = gen / 'levels' / f'{record["index"]+1:02}'
    with np.load(path/'tiles.npz') as source:
        patterns = [bytes(row) for row in source['patterns'].reshape(-1, 16)]
        return patterns, source['ids'], source['attrs']


def packed_tiles(record, original):
    """Return packed IDs and patterns while keeping the render cache independent."""
    order = record.get('pattern_order')
    if order is None:
        return original['ids'], original['patterns'].tobytes()
    source = original['patterns'].reshape(-1, 16)
    inverse = np.zeros(len(source), dtype=np.uint16)
    restored = np.asarray(order)
    slots = np.arange(len(order), dtype=np.uint16)
    # -1 can occupy an unused interior position for B's border pattern.
    for slot, index in zip(reversed(slots), reversed(restored)):
        if index >= 0:
            inverse[index] = slot
    data = bytearray(source[restored].tobytes())
    if -1 in order:
        i = order.index(-1)
        data[16*i:16*i+16] = bytes.fromhex(record['unused_border_pattern'])
    return inverse[original['ids']], bytes(data)


def compact(gen):
    """Repack the existing exact scheduled graphics before linking terrain tails."""
    path = gen/'level_manifest.json'
    manifest = json.loads(path.read_text())
    if (manifest['map_codec'] != rolling_map_banks.CODEC or manifest.get('released_banks')
            or manifest['first_bank'] != 94 or manifest['last_bank'] != 476):
        raise ValueError('Expected an original scheduled scenery pack')
    records = manifest['levels']
    courses = [load_tiles(gen, record) for record in records]
    first, last = manifest['first_bank'], manifest['last_bank']
    layout = Layout(first, last, RELEASED)
    for bank, data in rolling_map_banks.product_payloads(manifest['rolling_map_banks']).items():
        layout.reserve(bank, 0, data)
    rider = manifest['rider_product_first_bank']
    for i, data in enumerate(rider_map_tables.product_tables((gen/'riding_constants.h').read_text())):
        layout.reserve(rider+i, 0, data)
    reservations = {bank:start for bank,(start,_) in corner_bank.RANGES.items()}
    reservations[head_lane_tables.BANK] = head_lane_tables.OFFSET
    from scenery_pins import BANK as PINS_BANK, OFFSET as PINS_OFFSET
    reservations[PINS_BANK] = PINS_OFFSET
    reservations[REACTION_WORD_BANK] = 0
    reservations[476] = 0x2000
    for bank, start in reservations.items():
        limit = 0x3c00 if bank != 476 else BANK_BYTES
        layout.reserve(bank, start, bytes(limit-start))
        if bank == 476:
            layout.ends[bank] = start

    dictionaries = []
    paired = set()
    updated = courses[:]
    for a, b, (lead, shared, tail) in best_pairs(courses):
        paired.update((a, b))
        dictionaries.append((lead+shared+tail, [(a, 0), (b, len(lead)*16)]))
        for i, order in ((a, lead+shared), (b, shared+tail)):
            patterns, ids, attrs = courses[i]
            numbers = {tile:k for k,tile in enumerate(patterns)}
            indices = [numbers.get(tile,-1) for tile in order]
            records[i]['source_pattern_count'] = len(patterns)
            records[i]['pattern_order'] = indices
            if -1 in indices:
                records[i]['unused_border_pattern'] = order[indices.index(-1)].hex()
            updated[i] = order, remap(ids,patterns,order), attrs
    dictionaries.extend((patterns, [(i,0)]) for i,(patterns,_,_) in enumerate(courses) if i not in paired)
    for patterns, references in sorted(dictionaries, key=lambda item:-len(item[0])):
        bank, address = layout.place(b''.join(patterns), 16, span=True)
        base = bank*BANK_BYTES + address-0x4000
        for i, offset in references:
            bank, address = divmod(base+offset, BANK_BYTES)
            records[i]['patterns'] = [bank, 0x4000+address]
            records[i]['pattern_count'] = len(updated[i][0])

    encoded = [list(packed_maps(ids, attrs)) for _,ids,attrs in updated]
    payloads = dict.fromkeys(data for entries in encoded for _,data in entries)
    locations = {data:layout.place(data) for data in sorted(payloads,key=lambda data:-len(data))}
    for record, entries in zip(records, encoded):
        record['chunks'] = [[locations[data][0] | tag, locations[data][1]] for tag,data in entries]
        directory = b''.join(struct.pack('<HH', *entry) for entry in record['chunks'])
        record['chunk_directory'] = list(layout.place(directory, 2))
        record['objects_pointer'] = list(layout.place(
            b''.join(struct.pack('<HHBiiB', *obj) for obj in record['objects']), 2))
        with np.load(gen/'levels'/f'{record["index"]+1:02}'/'tiles.npz') as tiles:
            palette = struct.pack('<28H', *rgb555(tiles['palettes']))
        record['palette'] = list(layout.place(palette, 2))

    catalogue = gen/'level_catalogue.c'
    text = catalogue.read_text()
    start = text.index('const world_level_t world_levels[]={\n')+len('const world_level_t world_levels[]={\n')
    end = text.index('\n};',start)
    rows = []
    for record in records:
        width,height = record['size_px']
        x,y = record['origin_m']
        pointers = ','.join('{%d,%d}' % tuple(record[name]) for name in
                            ('patterns','chunk_directory','palette','objects_pointer'))
        rows.append('{%d,%d,%dL,%dL,%d,%s,%d,%d,%d}' %
                    (width,height,x*65536,y*65536,record['pattern_count'],pointers,
                     width//256,height//128,len(record['objects'])))
    catalogue.write_text(text[:start]+',\n'.join(rows)+text[end:])
    for bank in RELEASED:
        (gen/f'level_bank_{bank}.c').unlink()
    for bank, data in layout.banks.items():
        size = layout.ends[bank] = max(1, layout.ends[bank])
        (gen/f'level_bank_{bank}.c').write_text(
            f'#include <stdint.h>\n#pragma bank {bank}\n' + array(f'level_bank_{bank}',data[:size]))
    manifest['released_banks'] = list(RELEASED)
    manifest['payload_bytes'] = sum(layout.ends.values())
    manifest['physical_bank_bytes'] = len(layout.banks)*BANK_BYTES
    path.write_text(json.dumps(manifest,indent=2)+'\n')
    print(f'{len(paired)} shared courses, {manifest["payload_bytes"]} graphics bytes, free banks {RELEASED}')
