"""Fuse the two rounded rolling impulses for constant throttle and changing brake torques."""
import re

from head_clearance import write_if_changed
from math_q24_coefficients import signed16_quotient_pages
import projection_tables

LIMIT = 1536
BANKS = (14, 6)


def rounded(value, multiplier):
    return (value * multiplier + (1 << 23)) >> 24


# Nonzero unit-X tangents sampled on the complete scheduled controller corpus.
# The directory verifies the full signed coefficient before selecting a row.
SHALLOW_COEFFICIENTS = (-86, 8, -15, -108, -104, -59, -27, -33, 104, -18, -32, -61,
                        -78, -5, -9, 50, 10, -56, -75, 24, -105)


def shallow_tangent_rows(coefficient):
    # Throwing away bits 0..7 before adding 256*h*k does not affect Q14.
    # Bias the low digit by a multiple of 64 so all its possible quotients
    # occupy two bits. The high digit's quotient cancels the same bias.
    low = [(v * coefficient + 8192) >> 8 for v in range(256)]
    bias = -(min(low) // 64)
    high_products = [((v ^ 128) - 128) * coefficient for v in range(256)]
    whole = [value // 64 - bias for value in high_products]
    fraction = [(value % 64) * 4 for value in high_products]
    if any(not 0 <= v // 64 + bias < 4 for v in low):
        raise ValueError('Shallow product exceeds two-bit low quotient')
    packed = [(v % 64) * 4 + v // 64 + bias for v in low]
    corrections = [4 * m * coefficient for m in range(-16, 16)]
    correction_page = ([v & 255 for v in corrections] +
                       [(v >> 8) & 255 for v in corrections] + [0] * 192)
    return [packed, fraction, [v & 255 for v in whole],
            [(v >> 8) & 255 for v in whole], correction_page]



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
)
SLOPE_EXTRA = (-12731, -10313, -12538, 10529, 769)
VERTICAL_TANGENT = (20, 16384)


def slope_rows(assembly):
    locations = {
        coefficient: (projection_tables.BANKS[i // projection_tables.ROWS_PER_BANK],
                      projection_tables.row_page(i))
        for i, coefficient in enumerate(projection_tables.COEFFICIENTS)
    }
    locations.update({c: (30, 0x6d + 3*i) for i, c in enumerate(SLOPE_EXTRA)})
    directory = bytearray(256)
    tangents = (*SLOPE_TANGENTS, VERTICAL_TANGENT)
    output = [assembly.with_name('roll_slopes.inc').read_text(), '.area _CODE_35',
              ' .bndry 256', 'slope_hash::']
    for i, (x, y) in enumerate(tangents, 1):
        mixed = (x ^ y) & 255
        low = (((mixed << 3) | (mixed >> 5)) ^ (x >> 8)) & 255
        if directory[low] or i >= 128:
            raise ValueError('Rolling tangent hash needs a distinct two-byte slot')
        directory[low] = 2*i
    output.extend(projection_tables.byte_lines(directory))
    output += ['slope_addresses::', ' .dw 0']
    output.extend(f' .dw slope_key_{i}' for i in range(len(tangents)))
    for i, (x, y) in enumerate(tangents):
        output += [f'slope_key_{i}:', f' .dw {x},{y}']
        if (x, y) == VERTICAL_TANGENT:
            output.append(' .db 0')
            continue
        row = []
        for coefficient in (x, y):
            bank, page = locations[coefficient]
            row.extend((page, bank & 255))
        # The top unsigned digit denotes the signed high byte plus 128.
        # The three U planes additionally bias each byte product by 2^23.
        # Both constants occupy whole upper words and survive low-byte carries.
        biases = [-0x800000 * 0x010101 // 65536 - coefficient*128 for coefficient in (x, y)]
        for correction in (sum(biases), *biases):
            row.extend((correction >> shift) & 255 for shift in (0, 8, 16))
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
    return output


def shallow_tangent_banks(assembly):
    output = [assembly.with_name('physics_roll_shallow.s').read_text()]
    directory = bytearray(256)
    for group, bank in enumerate((29, 30)):
        output.extend((f'.area _CODE_{bank}', f'ground_rows_{bank}::'))
        coefficients = SHALLOW_COEFFICIENTS[group * 12:(group + 1) * 12]
        for index, coefficient in enumerate(coefficients):
            directory[coefficient & 255] = 0x40 + index * 5 + group * 128
            for page in shallow_tangent_rows(coefficient):
                for i in range(0, 256, 32):
                    output.append(' .db ' + ','.join(map(str, page[i:i + 32])))
        if len(coefficients) < 12:
            if (12 - len(coefficients)) * 5 != 3 * len(SLOPE_EXTRA):
                raise ValueError('Supplemental three-plane rows must fill the unused shallow slots')
            output.append('slope_extra_rows::')
            for c in SLOPE_EXTRA:
                for page in projection_tables.planes(c)[:3]:
                    output.extend(projection_tables.byte_lines(page))
        labels = [f'ground_{name}_{bank}' for name in ('inputs', 'project', 'component', 'store')]
        output.append('ground_reader ' + ','.join(labels))
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
    gas = int(re.search(r'^#define GAS_TQ (\d+)$', constants, re.M)[1])
    if not 0 < gas <= 32767:
        raise ValueError('The torque lookup requires a positive signed16 throttle impulse')

    def coefficients(name):
        match = re.search(r'q24_C_' + name + r'\[2\]=\{(-?\d+),(-?\d+)\}', constants)
        return tuple(map(int, match.groups()))

    output = ['RIDING_ROLL_TABLES = 1', 'RIDING_GROUND_ROWS = 1', f'roll_gas = {gas}', f'roll_bias_pages = {LIMIT//256}',
              f'roll_pages = {2*LIMIT//256}', f'roll_data_size = {2*LIMIT}',
              f'roll_group_bytes = {2*LIMIT//32*2}', f'roll_full_bank = {BANKS[0]}',
              f'roll_partial_bank = {BANKS[1]}', assembly.read_text()]
    for phase, (torque, speed, bank) in enumerate(zip(coefficients('ROLL_T'), coefficients('ROLL_DV'), BANKS)):
        groups = [[] for _ in range(3)]
        packed = []
        steps = (0, gas, -gas)
        offsets = [t * speed // (1 << 24) for t in steps]
        for start in range(-LIMIT, LIMIT, 32):
            anchor = rounded(rounded(start, torque), speed)
            for group, offset in zip(groups, offsets):
                group.append(anchor + offset)
            for value in range(start, start + 32):
                tangential = rounded(value, torque)
                answers = [rounded(tangential + t, speed) for t in steps]
                delta = answers[0] - anchor
                carries = [answer - answers[0] - offset for answer, offset in zip(answers, offsets)]
                if (not 0 <= delta < 64 or any(bit not in (0, 1) for bit in carries)
                        or any(not -32768 <= answer <= 32767 for answer in answers)):
                    raise ValueError('Rolling impulse exceeds its exact table representation')
                packed.append(delta | (carries[1] << 6) | (carries[2] << 7))
        output += [f'.area _CODE_{bank}', f'roll_data_{phase}::']
        for i in range(0, len(packed), 32):
            output.append(' .db ' + ','.join(map(str, packed[i:i+32])))
        for mode, group in enumerate(groups):
            output.append(f'roll_bases_{phase}_{mode}::')
            for i in range(0, len(group), 16):
                output.append(' .dw ' + ','.join(map(str, group[i:i+16])))
        output.append(f'roll_transform_{phase}::')
        for scale in (torque, speed):
            for page in signed16_quotient_pages(scale):
                for i in range(0, 256, 32):
                    output.append(' .db ' + ','.join(map(str, page[i:i+32])))
    output.extend(shallow_tangent_banks(assembly))
    output.extend(slope_rows(assembly))
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
