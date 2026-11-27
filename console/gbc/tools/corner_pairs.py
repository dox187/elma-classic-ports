"""Compact ordered wheel pairs in 4-by-4 blocks of an existing corner tile."""
import struct

from corner_samples import q14

PAIR_BANK = 472
# Only addresses are profiled. All sixteen positions of each chosen block
# are evaluated against the packed segment list in its original order.
PROFILE_BLOCKS = {
    (31, 23440, 38688): ((8, 8),),
    (31, 25216, 39408): ((4, 12),),
    (37, 65104, 38288): ((0, 4), (4, 4)),
    (40, 31808, 31104): ((8, 8), (4, 8), (4, 12), (8, 12)),
    (46, 3952, 8672): ((0, 4), (4, 4)),
    (47, 72192, 3808): ((8, 8),),
    (50, 5904, 13904): ((4, 8), (0, 4), (4, 0), (8, 8)),
}
EXTRA_TILES = tuple(key for key in PROFILE_BLOCKS if key != (31, 23440, 38688))


def pair_bytes(pair, x, y):
    # The iterator returns its terrain points relative to the 4096-unit leaf.
    return b''.join(struct.pack('<5h', nx, ny, length,
                                (x & 4095) - q14(nx*length),
                                (y & 4095) - q14(ny*length))
                    for nx, ny, length in pair)


def encode_block(samples, x, y, bx, by):
    records = []
    for dy in range(by, by+4):
        for dx in range(bx, bx+4):
            hit = samples[dy*16+dx]
            records.append(pair_bytes(hit, x+dx, y+dy) if len(hit) == 2 else None)
    pairs = [row for row in records if row is not None]
    if not pairs:
        return None
    first = pairs[0]
    varying = [j for j in range(20) if any(row[j] != first[j] for row in pairs)]
    # Copy the full template before applying this pixel's varying bytes.
    # The stride byte gives the size of each of the sixteen pixel records.
    stride = len(varying)
    payload = bytes([stride]) + bytes((row or first)[j] for row in records for j in varying)
    return payload + first + bytes(varying), len(pairs)


def pack_tiles(tiles, available, address):
    """Prefer measured tiles, keeping the center blocks of other tiles when space permits."""
    blocks = []
    for (course, x, y), samples in tiles.items():
        for by in range(0, 16, 4):
            for bx in range(0, 16, 4):
                block = encode_block(samples, x, y, bx, by)
                if block is None:
                    continue
                data, count = block
                key = course, x, y
                # Highest-cost observed placements, then blocks nearest each tile's center.
                if (bx, by) in PROFILE_BLOCKS.get(key, ()):
                    priority = 3
                elif key in PROFILE_BLOCKS or course == 10:
                    priority = 2
                else:
                    priority = 1
                distance = abs(bx+2-8) + abs(by+2-8)
                blocks.append((priority, -distance, count/len(data), key, bx, by, data))
    payload = bytearray()
    directories, selected = {}, []
    for _, _, _, key, bx, by, data in sorted(blocks, reverse=True):
        new_size = len(data) + (0 if key in directories else 32)
        if len(payload) + new_size > available:
            continue
        if key not in directories:
            directories[key] = len(payload)
            payload.extend(bytes(32))
        struct.pack_into('<H', payload, directories[key] + 2*(by + bx//4),
                         address + len(payload))
        payload.extend(data)
        selected.append([*key, bx, by])
    return payload, {key: address+offset for key, offset in directories.items()}, selected
