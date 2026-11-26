"""Select immediate brake Q24 indices when every relevant table entry agrees."""
import json
import re

from head_clearance import write_if_changed
from math_q24_coefficients import signed16_quotient_pages


def terrain_prefix(gen):
    """The packer allocates its final level directory after all segment payloads."""
    manifest = gen / 'physics_bank_manifest.json'
    if not manifest.exists():
        return None
    layout = json.loads(manifest.read_text())
    last = layout['levels'][-1]
    if (layout['banks'][-1] != 93 or last['directory_bank'] != 93 or
            not 0x4000 <= last['directory_address'] < 0x8000):
        return None
    width, height = last['grid']
    size = last['directory_address'] - 0x4000 + width * height * 4
    if not 0 < size <= 0x2800:
        return None
    return size


def terrain_object(gen, size):
    path = gen / 'physics_bank_93.c'
    header, values = path.read_text().split('={', 1)
    payload = bytes(map(int, values.split('}', 1)[0].strip().split(',')))
    if len(payload) != 16384 or any(b != 255 for b in payload[size:]):
        raise ValueError('Unexpected data beyond the final terrain directory')
    # The following assembly begins with 256-byte coefficient pages.
    size = (size + 255) & ~255
    rows = [','.join(map(str, payload[k:min(size, k+32)])) for k in range(0, size, 32)]
    dest = gen / 'brake_terrain.c'
    write_if_changed(dest, header.replace('[16384]', f'[{size}]') + '={\n' + ',\n'.join(rows) + '\n};\n')
    return dest


def generate(gen, assembly, destination=None):
    dispatch = (gen / 'physics_q24_dispatch.c').read_text()
    indices = {name: (int(first), int(second)) for name, first, second in re.findall(
        r'q24_index_C_BRAKE_(A|W|GW)\[2\]=\{(\d+),(\d+)\}', dispatch)}
    definitions = []
    for symbol, names in (('brake_angle_index', ('A',)), ('brake_damping_index', ('W', 'GW'))):
        values = {index for name in names for index in indices[name]}
        if len(values) == 1:
            definitions.append(f'{symbol} = {values.pop()}\n')
    rows = []
    scales = {key: tuple(map(int, values)) for key, *values in re.findall(
        r'q24_C_BRAKE_(A|GW|W)\[2\]=\{(-?\d+),(-?\d+)\}', (gen / 'riding_constants.h').read_text())}
    if (len(definitions) == 2 and terrain_prefix(gen) is not None and
            len(set(scales['A'])) == 1 and len(set(scales['W'] + scales['GW'])) == 1 and
            0 < scales['A'][0] < 1 << 24 and 0 < scales['W'][0] < 1 << 30):
        definitions.append('brake_tables = 1\n')
        pages = signed16_quotient_pages(scales['A'][0])
        # The angle product is signed16 and its low-byte quotient is unsigned8.
        tables = [('brake_angle_rows', [pages[i] for i in (0, 1, 3, 4, 5)])]
        m = scales['W'][0]
        # A signed-byte damping result fits signed16 for the admitted scales.
        signed_bytes = list(range(128)) + list(range(-128, 0))
        rows8 = [[(v * m >> shift) & 255 for v in signed_bytes] for shift in (0, 8, 16)]
        rows8.extend([[(v * m + (1 << 23)) >> shift & 255 for v in signed_bytes]
                      for shift in (24, 32)])
        tables.append(('brake_damp_byte', rows8))
        for name, inputs, bias in [('brake_damp_low', range(256), 1 << 23),
                                   ('brake_damp_high', [((v + 128) % 256) - 128 for v in range(256)], 0)]:
            tables.append((name, [[((v*m+bias) >> shift) & 255 for v in inputs]
                                  for shift in range(0, 40, 8)]))
        for name, table in tables:
            rows.append(name + '::\n')
            for page in table:
                rows.extend(' .db ' + ','.join(map(str, page[i:i+32])) + '\n' for i in range(0, 256, 32))
    output = destination or gen / 'physics_brake_game.s'
    source = assembly.read_text().replace('; GENERATED BRAKE PAGES', ''.join(rows))
    write_if_changed(output, ''.join(definitions) + source)
    return output
