"""Exact wheel geometry for complete 16-by-16 contact tiles."""
from collections import Counter, defaultdict
import struct

from corner_samples import cell_samples
from projection_tables import byte_lines

BANK = 503
# Keep the generated decoder and its palettes within the radial slab.
RESERVED_BYTES = 10240
# Only coordinates come from profiling. Compute both ordered normals and
# lengths for every integer center using the packed course's original edges.
TILES = {
    'steep': (31, ((23504, 39008), (27264, 39808), (25552, 39360), (27328, 39712))),
    'course48': (47, ((87408, 57312), (89168, 56992), (89232, 57056), (89168, 57008))),
}


def dispatch(name, tiles, side=16):
    offsets = (3, 7, 2, 6, 1, 5)

    def walk(items, depth):
        if depth == len(offsets):
            assert len(items) == 1
            return [f' ld bc,#{items[0][1]}', ' jp direct_known']
        step = offsets[depth] - (offsets[depth-1] if depth else 0)
        result = [' inc hl' if step > 0 else ' dec hl'] * abs(step)
        result.append(' ld a,(hl)')
        if depth >= 4:
            result.append(f' and #{256-side}')
        groups = defaultdict(list)
        for key, destination in items:
            groups[key[depth]].append((key, destination))
        for value, entries in groups.items():
            result.extend([f' cp #{value}', f' jp z,{entries[0][1]}_d{depth}'])
        result.append(' jp direct_miss')
        for entries in groups.values():
            result.extend([f'{entries[0][1]}_d{depth}:', *walk(entries, depth+1)])
        return result

    items = []
    for i, (x, y) in enumerate(tiles):
        assert not (x & (side-1) or y & (side-1)) and 0 <= x < 1 << 23 and 0 <= y < 1 << 23
        key = (x >> 16, y >> 16, x >> 8 & 255, y >> 8 & 255, x & (256-side), y & (256-side))
        items.append((key, f'direct_{name}_{i}'))
    return [f'direct_{name}_tiles::', ' ld h,d', ' ld l,e', *walk(items, 0)]


def packed_indices(blob, indices, bits):
    """Return A = indices[C]. An aligned pair, quartet or octet shares a byte."""
    step = 8 // bits
    data = [sum(indices[j+k] << (k*bits) for k in range(step)) for j in range(0, len(indices), step)]
    return [f' ld hl,#{blob(data)}', f' call direct_unpack{bits}']


def raw_lookup(blob, values):
    return [f' ld hl,#{blob(values)}', ' add hl,bc', ' ld a,(hl)']


def unrow(side):
    return [' swap a'] if side == 16 else [' rrca'] * 3


def direct_field(blob, field, side):
    # Separate integer X/Y terms of a nearly planar field, storing every
    # residual explicitly. If more than four are needed use all 256 bytes.
    def mode(values):
        return Counter(values).most_common(1)[0][0]
    rows = list(field[::side])
    for _ in range(3):
        cols = [mode((field[y*side+x] - rows[y]) & 255 for y in range(side)) for x in range(side)]
        rows = [mode((field[y*side+x] - cols[x]) & 255 for x in range(side)) for y in range(side)]
    delta = [(value - rows[i // side] - cols[i % side]) & 255 for i, value in enumerate(field)]
    palette = list(dict.fromkeys(delta))
    if len(palette) > 4:
        return raw_lookup(blob, field)
    code = [' ld a,c', *unrow(side), f' and #{side-1}', ' ld e,a', f' ld hl,#{blob(rows)}',
            ' add hl,de', ' ld a,(hl)', ' push af', ' ld a,c', f' and #{side-1}', ' ld e,a',
            f' ld hl,#{blob(cols)}', ' add hl,de', ' pop af', ' add (hl)']
    if len(palette) == 1:
        return code + ([f' add #{palette[0]}'] if palette[0] else [])
    bits = 1 if len(palette) == 2 else 2
    indices = [palette.index(value) for value in delta]
    return code + [' push af', *packed_indices(blob, indices, bits), ' ld e,a',
                   f' ld hl,#{blob(palette)}', ' add hl,de', ' pop af', ' add (hl)']


def palette_index(blob, indices, colors, side):
    rows = [indices[j:j+side] for j in range(0, len(indices), side)]
    if len(set(rows)) == 1:
        return [' ld a,c', f' and #{side-1}', ' ld e,a', f' ld hl,#{blob(rows[0])}', ' add hl,de', ' ld a,(hl)']
    if all(len(set(row)) == 1 for row in rows):
        return [' ld a,c', *unrow(side), f' and #{side-1}', ' ld e,a', f' ld hl,#{blob(indices[::side])}', ' add hl,de', ' ld a,(hl)']
    if colors > 16:
        return raw_lookup(blob, indices)
    bits = 1 if colors <= 2 else 2 if colors <= 4 else 4
    return packed_indices(blob, indices, bits)


def tile_reader(blob, samples, side=16):
    # Nx, Ny, length are live for each returned contact. The ordinary
    # length projection rebuilds both points only when a pair is returned.
    records = [b''.join(struct.pack('<hhh', *contact) for contact in hit) for hit in samples]
    fields = {}
    for index in range(max(map(len, records))):
        padding = next(row[index] for row in records if len(row) > index)
        offset = index if index < 6 else index+4
        fields[offset] = tuple(row[index] if len(row) > index else padding for row in records)
    fields[None] = tuple(map(len, samples))

    families = defaultdict(list)
    for dest, field in fields.items():
        colors = {}
        indices = tuple(colors.setdefault(v, len(colors)) for v in field)
        families[indices].append((dest, tuple(colors)))
    lines = []
    for indices, group in families.items():
        colors = len(group[0][1])
        shared = []
        if colors > 1 and (colors <= 16 or len(group) > 1):
            shared = palette_index(blob, indices, colors, side) + [' ld e,a']
        lines += shared
        for dest, palette in group:
            if colors == 1:
                lines.append(f' ld a,#{palette[0]}')
            elif shared:
                lines.extend([f' ld hl,#{blob(palette)}', ' add hl,de', ' ld a,(hl)'])
            else:
                lines.extend(direct_field(blob, fields[dest], side))
            lines.append(' push af' if dest is None else f' ld (#_Ct+{dest}),a')
    return [*lines, ' pop af', ' jp direct_decoded']


def generate(template, levels, banks):
    blobs = {}
    def blob(data):
        return f'direct_bytes_{blobs.setdefault(bytes(data), len(blobs))}'

    lines = [f'DIRECT_BANK = {BANK}']
    for name, (_, tiles) in TILES.items():
        quarters = [y >> 8 for _, y in tiles]
        assert 0 <= min(quarters) <= max(quarters) < 256
        lines.append(f'DIRECT_{name.upper()}_BOUNDS = {min(quarters)*256+max(quarters)-min(quarters)+1}')
    low, high = template.read_text().split(f'.area _CODE_{BANK}\n')
    runtime = '\n'.join([*lines, low])
    lines = [high]
    for name, (course, tiles) in TILES.items():
        lines.extend(dispatch(name, tiles))
        for i, (x, y) in enumerate(tiles):
            samples = cell_samples(levels[course], banks, x, y)
            lines.extend([f'direct_{name}_{i}:', *tile_reader(blob, samples)])
    for bits, shift in ((1, 3), (2, 2), (4, 1)):
        name = f'direct_unpack{bits}'
        lines.extend([name+':', ' ld a,c', *[' srl a']*shift, ' ld e,a', ' add hl,de', ' ld a,(hl)'])
        for j in range(shift):
            rotates = [' swap a'] if bits << j == 4 else [' rrca'] * (bits << j)
            lines.extend([f' bit {j},c', f' jr z,{name}_{j}', *rotates, f'{name}_{j}:'])
        lines.extend([f' and #{(1<<bits)-1}', ' ret'])
    for data, index in blobs.items():
        lines.extend([f'direct_bytes_{index}:', *byte_lines(data)])
    return runtime, '\n'.join([*lines, 'direct_data_end::', ''])
