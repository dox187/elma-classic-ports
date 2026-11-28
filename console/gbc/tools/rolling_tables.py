"""Generate exact rounded wheel impulses and tangent projections."""
import json
import re

from head_clearance import write_if_changed
from math_q24_coefficients import signed16_quotient_pages
import head_lane_tables
import projection_tables

BANKS = (14, 6)
REACTION_WORD_BANK = 472


def rounded(value, multiplier):
    return (value * multiplier + (1 << 23)) >> 24


# Nonzero unit-X tangents sampled on the complete scheduled controller corpus.
# The directory verifies the full signed coefficient before selecting a row.
SHALLOW_COEFFICIENTS = (-86, 8, -15, -108, -104, -59, -27, -33, 104, -18, -32, -61,
                        -78, -5, -9, 50, 10, -56, -75, 24, -105)


def shallow_tangent_rows(coefficient):
    # Reverse the low digit for negative slopes so every threshold adds one.
    # The largest slope is 108/16384, hence at most two thresholds per byte.
    magnitude = abs(coefficient)
    lower, first, second = [], [], []
    for digit in range(256):
        high = (digit ^ 128) - 128
        base, remainder = divmod(8192 + high*256*coefficient
                                 + min(coefficient, 0)*255, 16384)
        lower.append(base & 255)
        if abs(coefficient) < 64:
            if not -128 <= base <= 127:
                raise ValueError('Small shallow quotient exceeds signed byte')
        elif (base < 0) != ((high < 0) != (coefficient < 0)) or not -256 <= base < 256:
            raise ValueError('Shallow quotient cannot use the high digit sign')
        first.append(min(255, (16383 - remainder)//magnitude))
        second.append(min(255, (32767 - remainder)//magnitude))
    corrections = [4*m*coefficient for m in range(-16, 16)]
    return [lower, first, second, bytes(256), [v & 255 for v in corrections] +
            [(v >> 8) & 255 for v in corrections]]


# Frequent noncardinal rolling tangents. Each key is verified at full width.
SLOPE_TANGENTS = (
    (-12731, -10313), (-12538, 10529), (-16362, 769), (-16382, -246),
    (-16383, 134), (-16379, -412), (-16379, 402), (-16368, -725),
    (-15279, 5914), (-16370, -677), (-16379, -396), (-16362, 856),
    (-16383, -170), (-16381, -301), (-16382, -240), (-15747, -4523),
    (-16383, -163), (-16078, 3152), (-16382, -256), (-16378, 457),
    (-16120, -2927), (-14037, -8449), (-10611, -12484), (-15702, 4677),
    (-13123, 9809), (-14955, -6692), (-9638, 13249), (-14140, -8277),
    (-15821, 4256), (-16379, 394), (-15788, 4377), (-6840, 14888),
    (-15504, 5297), (-9636, 13251), (-14141, -8275), (-15940, -3788),
    (-3013, 16105), (-15270, -5937), (-15589, 5042), (-15758, 4487),
    (-15843, 4174), (-4419, 15777), (-14282, 8029), (737, 16367),
    (-15586, 5052), (-16378, 432), (-14337, -7931), (-15455, 5440),
    (-13007, 9963), (-16356, 956), (-11872, -11292), (-15965, 3680),
    (-9217, -13546), (-11181, 11975), (-16381, 402), (-497, 16376),
    (-16095, -3066), (-15580, -5069), (-13549, 9212),
    (-10948, 12195), (-10689, 12417), (-15259, -5967), (-10914, 12198),
    (-10682, 12416), (-2401, 16207), (-16364, -819), (-12167, 10973),
    (-15654, 4835), (-15100, 6358), (-14454, 7715), (-16015, 3455),
    (-14863, 6893), (-10706, 12397), (-14315, 7970), (-16383, -159),
    (-15854, -4135), (-9147, 13593), (-16366, -807),
)
SLOPE_EXTRA = (-12731, -10313, -12538, 10529, 769)
# Each group occupies unused product planes in its existing shallow bank.
LOCAL_TANGENTS = {
    29: ((-16379, -396), (-16379, 402), (-16078, 3152), (-16379, -412)),
    30: ((-15580, -5069), (-14282, 8029)),
}

VERTICAL_TANGENT = (20, 16384)


def slope_rows(assembly, gen):
    _, locations = projection_tables.generated_rows(gen)
    locations.update({c: (30, 0x6d + 3*i) for i, c in enumerate(SLOPE_EXTRA)})
    directory = bytearray(256)
    tangents = (*SLOPE_TANGENTS, VERTICAL_TANGENT)
    output = [assembly.with_name('roll_slopes.inc').read_text(), '.area _CODE_35',
              ' .bndry 256', 'slope_hash::']
    if len(set(tangents)) != len(tangents) or len(tangents) > 127:
        raise ValueError('Rolling tangent directory needs distinct two-byte slots')
    for i, (x, y) in enumerate(tangents, 1):
        if abs(x) + abs(y) > 32767:
            raise ValueError('Rolling tangent exceeds the signed24 input dot bound')
        mixed = (x ^ y) & 255
        low = (((mixed << 3) | (mixed >> 5)) ^ (x >> 8)) & 255
        while directory[low]:
            low = (low + 1) & 255
        directory[low] = 2*i
    output.extend(projection_tables.byte_lines(directory))
    output += ['slope_addresses::', ' .dw 0']
    output.extend(f' .dw slope_key_{i}' for i in range(len(tangents)))
    for i, (x, y) in enumerate(tangents):
        output += [f'slope_key_{i}:', f' .dw {x},{y}']
        if (x, y) == VERTICAL_TANGENT:
            output.append(' .db 0')
            continue
        local = next(((bank, i) for bank, group in LOCAL_TANGENTS.items()
                      for i, tangent in enumerate(group) if tangent == (x, y)), None)
        if local is not None:
            bank, slot = local
            output += [f' .db 1,{bank}', f' .dw local_inputs_{bank}_{slot},local_project_{bank}_{slot}']
            continue
        row = []
        for coefficient in (x, y):
            bank, page = locations[coefficient]
            if (bank >> 8) != ((bank >> 7) & 1):
                raise ValueError('Rolling projection bank must encode its ninth bit in bit seven')
            row.extend((page, bank & 255))
        output.append(' .db ' + ','.join(map(str, row)))

    # A signed16 input times 20 can cross one Q14 rounding threshold
    # over its low byte. A wider input adds 80 for each signed upper word.
    c = VERTICAL_TANGENT[0]
    bases, thresholds = [], []
    for digit in range(256):
        whole, rem = divmod(((digit ^ 128) - 128)*256*c + 8192, 16384)
        bases.append(whole & 255)
        thresholds.append(min(255, (16383 - rem)//c))
    correction = [4*c*m for m in range(-16, 16)]
    output += [' .bndry 256', 'slope_vertical_rows::']
    for row in (bases, thresholds, [n & 255 for n in correction], [(n >> 8) & 255 for n in correction]):
        output.extend(projection_tables.byte_lines(row))
    output += ['.area _CODE_30', ' .bndry 16', 'slope_extra_bias:']
    for coefficient in SLOPE_EXTRA:
        correction = -(0x800000 * 0x010101 // 65536) - coefficient * 128
        output.extend(projection_tables.byte_lines([(correction >> n) & 255 for n in (0, 8, 16)]))
    return output


def shallow_tangent_banks(assembly, gen):
    from haircut_terrain import bank_sections
    terrain = bank_sections(gen)
    output = [assembly.with_name('physics_roll_shallow.s').read_text(),
              assembly.with_name('roll_local.inc').read_text(),
              assembly.with_name('haircut_terrain.inc').read_text()]
    directory = bytearray(256)
    for group, bank in enumerate((29, 30)):
        output.extend((f'.area _CODE_{bank}', f'ground_rows_{bank}::'))
        coefficients = SHALLOW_COEFFICIENTS[group * 12:(group + 1) * 12]
        holes = [0x40 + i*5 + offset for i, k in enumerate(coefficients)
                 for offset in ((2, 3) if abs(k) < 64 else (3,))]
        factors = list(dict.fromkeys(k for pair in LOCAL_TANGENTS[bank] for k in pair))
        if len(factors)*3 > len(holes):
            raise ValueError('Rolling product planes exceed the shallow bank')
        tangent_code = [
            f'local_tangent local_inputs_{bank}_{i},local_project_{bank}_{i},'
            f'local_product_{bank}_{factors.index(x)},local_product_{bank}_{factors.index(y)},'
            f'local_sum_{bank},local_round_{bank},local_store_{bank}'
            for i, (x, y) in enumerate(LOCAL_TANGENTS[bank])]
        pages = {}
        for i, k in enumerate(factors):
            unsigned = [0x800000 + low*k for low in range(256)]
            for digit, page in enumerate(holes[3*i:3*i+3]):
                pages[page] = [(v >> (8*digit)) & 255 for v in unsigned]
        for index, coefficient in enumerate(coefficients):
            directory[coefficient & 255] = 0x40 + index * 5 + group * 128
            start = 0x40 + index*5
            for offset, original in enumerate(shallow_tangent_rows(coefficient)):
                page = pages.get(start+offset, original)
                for i in range(0, len(page), 32):
                    output.append(' .db ' + ','.join(map(str, page[i:i + 32])))
            output.append(f'ground_threshold_reader {start},{int(coefficient < 0)},{int(abs(coefficient) < 64)}')
            if index < len(factors):
                k = factors[index]
                output += [' .bndry 128']
                upper = [top*k - 0x8080 for top in range(-8, 8)]
                for shift in (0, 8, 16):
                    output.extend(projection_tables.byte_lines([(v >> shift) & 255 for v in upper]))
                args = [f'local_product_{bank}_{index}', *holes[3*index:3*index+3], start+4]
                output.append('local_product ' + ','.join(map(str, args)))
            if bank == 29 and index == 11:
                output.append('ground_select_kernel')
            extra = index - len(factors)
            if 0 <= extra < len(tangent_code)-3:
                output.append(tangent_code[extra+3])
            output.extend(terrain.get((bank, index), ()))
            output += [' .bndry 256']
        if len(coefficients) < 12:
            if (12 - len(coefficients)) * 5 != 3 * len(SLOPE_EXTRA):
                raise ValueError('Supplemental three-plane rows must fill the unused shallow slots')
            output.append('slope_extra_rows::')
            for c in SLOPE_EXTRA:
                for page in projection_tables.planes(c)[:3]:
                    output.extend(projection_tables.byte_lines(page))
        labels = [f'ground_{name}_{bank}' for name in ('inputs', 'project', 'component', 'store')]
        output.append('ground_reader ' + ','.join(labels))
        output.extend(tangent_code[:3])
        output.append(f'local_finish local_sum_{bank},local_round_{bank},local_store_{bank}')
    output += ['.area _CODE_30', 'roll_bank30_wheels']
    output += ['.area _CODE_29', 'ground_flat_kernel', ' .bndry 256', 'ground_directory::']
    for i in range(0, 256, 32):
        output.append(' .db ' + ','.join(map(str, directory[i:i + 32])))
    return output


def validate_shallow_layout(symbols):
    for bank in (29, 30):
        if symbols.get(f'ground_rows_{bank}') != (bank << 16) + 0x4000:
            raise ValueError(f'Shallow tangent rows must start at bank {bank} address 0x4000')
        for label in ('ground_inputs', 'ground_project'):
            if symbols.get(f'{label}_{bank}', 0) != symbols[f'{label}_29'] + ((bank-29) << 16):
                raise ValueError('Shallow tangent readers must share switchable-window entry addresses')
    if symbols.get('slope_extra_rows') != 0x1e6d00:
        raise ValueError('Supplemental rolling projection rows must start at bank 30 address 0x6d00')
    for label in ('slope_hash', 'slope_addresses', 'slope_vertical_rows'):
        value = symbols[label]
        if value >> 16 != 35 or value & 255:
            raise ValueError(f'{label} must be page-aligned in bank 35')
    directory = symbols['ground_directory']
    if directory >> 16 != 29 or directory & 255:
        raise ValueError('Shallow tangent directory must begin on a page in bank 29')


def generate(gen, assembly):
    constants = (gen / 'riding_constants.h').read_text()

    def coefficients(name):
        match = re.search(r'q24_C_' + name + r'\[2\]=\{(-?\d+),(-?\d+)\}', constants)
        return tuple(map(int, match.groups()))

    output = ['RIDING_ROLL_TABLES = 1', 'RIDING_GROUND_ROWS = 1',
              f'roll_full_bank = {BANKS[0]}', f'roll_partial_bank = {BANKS[1]}',
              assembly.read_text()]
    # The common wheel-speed coefficient has a nonnegative low-byte
    # quotient below 256 and a signed16 quotient for any signed17 input.
    # Wider products retain the scheduled Q24 entry and its saturation rules.
    omega = coefficients('ROLL_W')
    manifest_path = gen / 'physics_q24_manifest.json'
    if omega[0] == omega[1] and 0 < omega[0] < (1 << 22) and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        index = manifest['coefficient_values'].index(omega[0])
        bank = manifest['first_bank'] + index//2
        output[:0] = ['RIDING_ROLL_OMEGA = 1', f'roll_omega_bank = {bank & 255}',
                      f'roll_omega_high = {bank >> 8}', f'roll_omega_page = {0x40 + (index%2)*0x20}']
    scalar = ['.module physics_roll_scalar', '.area _CODE']
    for phase, (torque, speed, bank) in enumerate(zip(coefficients('ROLL_T'), coefficients('ROLL_DV'), BANKS)):
        first = signed16_quotient_pages(torque)
        if any(first[2]) or any(not -32768 <= rounded(i, torque) < 32768
                                for i in (-32768, 32767)):
            raise ValueError('Rolling torque quotient must fit signed16 with an unsigned-byte low term')
        first = [first[i] for i in (0, 1, 3, 4, 5)]
        direct = [rounded(i, speed) for i in range(-1024, 1024)]
        if any(not -32768 <= q < 32768 for q in direct):
            raise ValueError('Direct rolling speed quotient must fit signed16')
        short = [[(q >> shift) & 255 for q in direct] for shift in (0, 8)]
        scalar.append(f'.area _CODE_{bank}')
        for name, planes in [('first', first), ('short', short),
                             ('second', signed16_quotient_pages(speed))]:
            scalar.append(f'roll_{name}_{phase}::')
            for plane in planes:
                scalar.extend(projection_tables.byte_lines(plane))
    write_if_changed(gen / 'physics_roll_scalar.s', '\n'.join(scalar) + '\n')
    output.extend(shallow_tangent_banks(assembly, gen))
    output.extend(slope_rows(assembly, gen))
    graphics_file = gen / 'level_manifest.json'
    if graphics_file.exists():
        graphics = json.loads(graphics_file.read_text())
        if graphics.get('rolling_map_banks'):
            output.insert(0, f"ROLL_DIRECTORY_BANK = {graphics['rolling_map_banks'][0]}")
    dest = gen / 'physics_roll_game.s'
    write_if_changed(dest, '\n'.join(output) + '\n')
    return dest


def generate_free(gen, source):
    """Precompute the exact Q24 quotient and fraction at full throttle."""
    constants = (gen / 'riding_constants.h').read_text()
    gas = int(re.search(r'^#define GAS_TQ (\d+)$', constants, re.M)[1])
    scales = tuple(map(int, re.search(r'q24_C_FREE\[2\]=\{(-?\d+),(-?\d+)\}', constants).groups()))
    output = ['RIDING_FREE_THROTTLE = 1', f'free_gas = {gas}', source.read_text(),
              '.area _CODE_9', 'free_throttle_values:']
    for torque in (gas, -gas):
        for scale in scales:
            result = rounded(torque, scale)
            if not -(1 << 31) <= result < (1 << 31):
                raise ValueError('Free-wheel throttle impulse saturates')
            fraction = torque * scale - (result << 24)
            row = [(n >> shift) & 255 for n in (fraction, result) for shift in (0, 8, 16, 24)]
            output.append(' .db ' + ','.join(map(str, row)))
    dest = gen / 'physics_free_game.s'
    write_if_changed(dest, '\n'.join(output) + '\n')
    return dest


def generate_reaction(gen, assembly, reciprocal_source):
    """Compose the reciprocal-index and Q24 torque factors at fixed throttle."""
    constants = (gen / 'riding_constants.h').read_text()
    gas = int(re.search(r'^#define GAS_TQ (\d+)$', constants, re.M)[1])
    scales = re.search(r'q24_C_REACT\[2\]=\{(-?\d+),(-?\d+)\}', constants)
    raw = re.sub(r'//[^\n]*', '', reciprocal_source.read_text()).strip().rstrip(',')
    reciprocals = [int(value) for value in raw.split(',')]
    if len(reciprocals) != 256 or not 0 < gas <= 32767:
        raise ValueError('Unexpected scheduled wheel reaction table')
    output = ['RIDING_GAS_REACTION = 1', f'reaction_gas = {gas}', assembly.read_text(),
              '.area _CODE_7', '_riding_gas_rows::']
    for scale in map(int, scales.groups()):
        for torque in (gas, -gas):
            row = [rounded((torque*r) >> 8, scale) for r in reciprocals]
            if any(not -(1<<23) <= value < 1<<23 for value in row):
                raise ValueError('Gas reaction exceeds signed24')
            for shift in (0, 8, 16):
                for i in range(0, len(row), 32):
                    output.append(' .db ' + ','.join(str((v >> shift) & 255) for v in row[i:i+32]))
    dest = gen / 'physics_suspension_game.s'
    write_if_changed(dest, '\n'.join(output) + '\n')
    return dest


def reaction_word_table(gen, original, dest=None):
    """Store two exhaustive signed16 C_REACT products before the first live scenery."""
    constants = (gen / 'riding_constants.h').read_text()
    scales = re.search(r'q24_C_REACT\[2\]=\{(-?\d+),(-?\d+)\}', constants)
    pages = [page for scale in map(int, scales.groups()) for page in signed16_quotient_pages(scale)]
    rows = bytes(value for page in pages for value in page)
    head_lane_tables.verify_graphics_range(gen, len(rows), REACTION_WORD_BANK, 0)
    data = original.read_text().split('{', 1)[1].split('}', 1)[0]
    payload = bytes(map(int, data.strip().rstrip(',').split(',')))
    if len(rows) != 14 * 256 or len(rows) > len(payload):
        raise ValueError('Reaction coefficient pages exceed the graphics bank')
    lines = [f'.module reaction_words_{REACTION_WORD_BANK}', f'.area _CODE_{REACTION_WORD_BANK}',
             f'_level_bank_{REACTION_WORD_BANK}::', '_riding_reaction_words::']
    for label, block in ((None, rows), ('_riding_reaction_words_end', payload[len(rows):])):
        if label:
            lines.append(label + '::')
        lines.extend(' .db ' + ','.join(map(str, block[i:i+32])) for i in range(0, len(block), 32))
    result = (dest or gen) / f'reaction_words_{REACTION_WORD_BANK}.s'
    write_if_changed(result, '\n'.join(lines) + '\n')
    return result
