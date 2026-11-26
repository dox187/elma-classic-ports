"""Fuse the two rounded rolling impulses for constant throttle and changing brake torques."""
import re

from head_clearance import write_if_changed
from math_q24_coefficients import signed16_quotient_pages

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
            output.append(f' .ds {(12 - len(coefficients)) * 5 * 256}')
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
