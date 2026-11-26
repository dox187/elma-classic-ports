"""Pack signed quarter waves and derive exact periodic Q24 geometry rows."""
import json
from pathlib import Path
import re
import struct

import physics_sine


def write_generated(path, text):
    if not path.exists() or path.read_text() != text:
        path.write_text(text)
    return path


def emit_bytes(values):
    return ''.join(' .db ' + ','.join(map(str, values[i:i+32])) + '\n'
                   for i in range(0, len(values), 32))


def generate(gen, src, out=None):
    coefficients = json.loads((gen / 'q24-coefficients.json').read_text())
    factors = []
    for name in ('C_H_X', 'C_H_Y', 'C_RREST'):
        first, second = coefficients[name]
        if first != second:
            raise ValueError(f'Pose factor {name} varies between substeps')
        factors.append(first)
    fixed = (src / 'physics_q24.h').read_text()
    for name in ('Q24_ANCHOR_X', 'Q24_ANCHOR_Y'):
        factors.append(int(re.search(rf'^#define {name} (\d+)L$', fixed, re.M)[1]))

    def products(v):
        return tuple((v*k + (1 << 23)) >> 24 for k in factors)

    # Keep the established upright records and drop the former general
    # residual arrays from bank 1 once the packed scaler owns that path.
    hot = []
    for value in range(0x3f00, 0x4001):
        hx, hy, rest, ax, ay = products(value)
        if (hx >> 8, hy >> 8, ax >> 16, -ay >> 16) != (0, 2, 3, -3):
            raise ValueError(f'Unexpected upright geometry digits at {value}')
        hot.append(struct.pack('<BBHHH', hx, hy & 255, rest, ax & 65535, -ay & 65535))
    geometry = ('#pragma bank 1\n#include <stdint.h>\n'
                'const uint8_t riding_pose_hot_rows[][8]={\n'
                + ',\n'.join('{'+','.join(map(str,row))+'}' for row in hot)
                + '\n};\nint32_t riding_pose_anchor[4];\n'
                'int16_t riding_pose_rest[2], riding_pose_trig[2];\n')
    write_generated((out or gen) / 'pose_geometry_packed.c', geometry)

    # The upper bit records an exact interpolation endpoint. All other
    # negative samples are the one's complement of their positive partner.
    sine = physics_sine.read_sintab(src / 'physics_math.c')
    text = '.module pose_products\n' + (src / 'pose_scalar_decode.inc').read_text() + '\n'
    for bank in (16, 17):
        data = bytearray()
        for phase in range((bank-16)*8192, (bank-15)*8192):
            positive = physics_sine.interpolate(sine, phase)
            negative = physics_sine.interpolate(sine, phase+32768)
            if not 0 <= positive < 0x4000 or negative not in (-positive, ~positive):
                raise ValueError(f'Unrepresentable quarter-wave sample at {phase}')
            data.extend(struct.pack('<H', positive | (0x8000 if negative == -positive else 0)))
        text += f'.area _CODE_{bank}\n_physics_sine_{bank}::\n' + emit_bytes(data)

    # Each signed high byte chooses a multiple of 1600 and a bounded
    # remainder. At a half-tie, keep the remainder on the input's side of zero.
    for bank, negative in ((18, False), (19, True)):
        suffix = '_n' if negative else ''
        first = -1536 if negative else 0
        h_bias, r_bias, a_bias = (64, 1024, 96) if negative else (0, 0, 0)
        pages = []
        for high in (range(-64, 0) if negative else range(65)):
            value = high * 256
            remainder = -((-value) % 1600) if negative else value % 1600
            offset = value - remainder
            base = products(offset)
            if (base[3] | base[4]) & 255:
                raise ValueError('Pose anchor block advances a partial byte')
            for low in range(1 if high == 64 else 256):
                part = products(remainder + low)
                if tuple(x+y for x, y in zip(base, part)) != products(value+low):
                    raise ValueError(f'Pose period loses precision at {value+low}')
            pages.append((0x48 + (remainder-first)//32, offset))

        start = f'pose_bank_{bank}'
        text += f'.area _CODE_{bank}\n{start}::\n'
        for tag in ('cos', 'sin'):
            text += (f'pose_scalar_{tag}{suffix}::\n'
                     f' pose_dispatch rows{suffix},{tag}_lo{suffix},{int(negative)}\n')

        def block(tag, offset):
            hx, hy, rest, ax, ay = products(offset)
            sin = tag == 'sin'
            head = '_riding_pose_sine' if sin else '_riding_pose_cosine'
            seat = '_riding_pose_rest' if sin else '_riding_pose_rest+2'
            rest -= r_bias
            args = (head, seat, f'pose_{tag}_ax', int(sin), hx+128, hy-h_bias+128,
                    1-rest if sin else rest, (ax >> 8)-a_bias, (ay >> 8)-a_bias)
            return (f'bl_{tag}{suffix}_{abs(offset)}:\n'
                    + ' pose_block ' + ','.join(map(str, args)) + '\n')

        # Occupy the gap preceding the first high-byte directory.
        text += block('cos', 0)
        def column(address, label, values):
            return (f' .ds {address}-(.-{start})\n{label}{suffix}::\n .db '
                    + ','.join(map(str, values))+'\n')

        index = 64 if negative else 0
        text += column(128+index, 'rows', [v for v, _ in pages])
        for page, tag in ((1, 'cos'), (2, 'sin')):
            labels = [f'bl_{tag}{suffix}_{abs(base)}' for _, base in pages]
            text += column(256*page+index, tag+'_hi', ['>'+name for name in labels])
            text += column(256*page+128+index, tag+'_lo', ['<'+name for name in labels])
        for offset in sorted({base for _, base in pages}):
            for tag in ('cos', 'sin'):
                if offset or tag != 'cos':
                    text += block(tag, offset)

        data = bytearray()
        for v in range(first, first+1792):
            hx, hy, rest, ax, ay = products(v)
            row = (hx & 255, hy+h_bias, rest+r_bias, ax+a_bias*256, ay+a_bias*256)
            if not -128 <= hx < 128:
                raise ValueError(f'Pose head remainder exceeds a byte at {v}')
            data.extend(struct.pack('<BBHHH', *row))
        text += f' .ds 2048-(.-{start})\npose_rows_{bank}::\n' + emit_bytes(data)
    return write_generated((out or gen) / 'pose_products.s', text)


def validate_layout(symbols):
    for bank in (16, 17, 18, 19):
        if symbols.get(f'l__CODE_{bank}') != 16384:
            raise ValueError(f'Pose data must occupy exactly bank {bank}')
    for bank in (16, 17):
        if symbols.get(f'_physics_sine_{bank}') != (bank << 16) | 0x4000:
            raise ValueError(f'Packed wave must start at the base of bank {bank}')
    for bank in (18, 19):
        if symbols.get(f'pose_rows_{bank}') != (bank << 16) | 0x4800:
            raise ValueError(f'Misaligned scalar rows in bank {bank}')
    for name in ('pose_scalar_cos', 'pose_scalar_sin'):
        if symbols[name] & 65535 != symbols[name+'_n'] & 65535:
            raise ValueError('Signed scalar decoders must share an entry address')
