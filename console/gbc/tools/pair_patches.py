"""Exact ordered contact pairs over small blocks reached in the Curvaceous pinch."""
from head_clearance import write_if_changed
from corner_samples import cell_samples
from corner_pairs import pair_bytes
from projection_tables import byte_lines

COURSE = 37
# Each patch covers sixteen complete integer wheel positions. Data stays in
# the spare ends of existing low ROM banks, which the reader can map directly.
BLOCKS = (
    (63584, 19536, 14), (63628, 19524, 35), (63632, 19540, 15),
    (64972, 19440, 6), (64968, 19440, 7), (64992, 19684, 14),
    (63544, 19556, 28), (65288, 19432, 13),
    (63524, 19544, 23), (63532, 19544, 23), (63560, 19544, 23),
    (64964, 19680, 25), (64964, 19444, 25), (65008, 19684, 25),
    (63536, 19556, 1), (63528, 19552, 30), (64968, 19444, 33),
)


def generate(gen, template, levels, banks):
    lines = ['.area _CODE_15', 'patch_blocks::']
    for axis, coordinates in zip(('X', 'Y'), zip(*BLOCKS)):
        strips = [value >> 8 for value in coordinates]
        lines.extend([f'PATCH_{axis}_MIN = {min(strips)}',
                      f'PATCH_{axis}_SPAN = {max(strips)-min(strips)+1}'])
    x_min = min(x >> 8 for x, _, _ in BLOCKS)
    y_min = min(y >> 8 for _, y, _ in BLOCKS)
    sections = {}
    for i, (x, y, bank) in enumerate(BLOCKS):
        assert not ((x | y) & 3)
        tile = cell_samples(levels[COURSE], banks, x & ~15, y & ~15)
        pairs = []
        for dy in range(4):
            for dx in range(4):
                hit = tile[((y+dy) & 15)*16 + ((x+dx) & 15)]
                if len(hit) == 2:
                    pairs.append(pair_bytes(hit, x+dx, y+dy))
        if len(pairs) != 16:
            continue
        # The runtime checks the full signed 24-bit center against this key.
        assert 0 <= x < 65536 and 0 <= y < 65536
        strip_x, strip_y = (x >> 8)-x_min, (y >> 8)-y_min
        assert 0 <= strip_x < 16 and 0 <= strip_y < 15
        key = bytes((strip_x | strip_y << 4, x & 255, y & 255))
        lines += [*byte_lines(key), f' .db {bank}', f' .dw patch_data_{i}']
        packed = bytearray(pairs[0])
        for col in range(20):
            values = bytes(row[col] for row in pairs)
            if len(set(values)) > 1:
                packed.append(col)
                packed.extend(values)
        packed.append(255)
        sections.setdefault(bank, []).extend([f'patch_data_{i}:', *byte_lines(packed)])
    lines.extend(['patch_blocks_end::', ' .db 255',
                  '.globl patch_min_x, patch_min_y', 'patch_min_x = PATCH_X_MIN', 'patch_min_y = PATCH_Y_MIN'])
    for bank, payload in sections.items():
        lines.extend([f'.area _CODE_{bank}', f'patch_data_start_{bank}::', *payload, f'patch_data_end_{bank}::'])
    out = gen/'ordered_pair_blocks.s'
    write_if_changed(out, template.read_text() + '\n' + '\n'.join(lines) + '\n')
    return out
