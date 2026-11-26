"""Fuse the two rounded rolling impulses for constant throttle and changing brake torques."""
import re

from head_clearance import write_if_changed
from math_q24_coefficients import signed16_quotient_pages

LIMIT = 1536
BANKS = (14, 6)


def rounded(value, multiplier):
    return (value * multiplier + (1 << 23)) >> 24


def generate(gen, assembly):
    constants = (gen / 'riding_constants.h').read_text()
    gas = int(re.search(r'^#define GAS_TQ (\d+)$', constants, re.M)[1])
    if not 0 < gas <= 32767:
        raise ValueError('The torque lookup requires a positive signed16 throttle impulse')

    def coefficients(name):
        match = re.search(r'q24_C_' + name + r'\[2\]=\{(-?\d+),(-?\d+)\}', constants)
        return tuple(map(int, match.groups()))

    output = ['RIDING_ROLL_TABLES = 1', f'roll_gas = {gas}', f'roll_bias_pages = {LIMIT//256}',
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
