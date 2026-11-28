"""Exact partial-step movement products in the two dedicated movement banks."""
import json
import re

from bike_frames16 import read_array
from head_clearance import write_if_changed
from projection_tables import byte_lines


def generate(gen, source):
    manifest = json.loads((gen / 'physics_q24_manifest.json').read_text())
    header = (gen / 'physics_q24_coefficients.h').read_text()
    index = int(re.search(r'^#define Q24_MOVE (\d+)$', header, re.M)[1])
    scale = manifest['coefficient_values'][index]
    # The direct row's floor occupies signed8. The wider two-row sum uses
    # signed16. Its high digit already includes eight low zero bits.
    if not 0 < scale <= (1 << 20):
        return source

    angle_index = int(re.search(r'^#define Q24_ANGLE (\d+)$', header, re.M)[1])
    angle = manifest['coefficient_values'][angle_index]
    if not 0 < angle < 1 << 30:
        raise ValueError('Wheel angular coefficient exceeds the signed16 product table')

    lines = ['RIDING_PHASE_TABLES = 1', source.read_text()]

    def pages(values, shifts):
        for shift in shifts:
            data = [(v >> shift) & 255 for v in values]
            for offset in range(0, 256, 32):
                lines.append(' .db ' + ','.join(map(str, data[offset:offset+32])))

    lines.extend(('.area _CODE_32', '_riding_phase_words::'))
    pages([n * scale for n in range(256)], (0,))
    pages([n * scale for n in range(256)], (0, 8, 16, 24))
    for upper in (*range(7), *range(-8, 0)):
        pages([((upper * 256 + low) << 8) * scale for low in range(256)],
              (16, 24, 32))
    lines.append('motion_s32_high::')
    pages([(n if n < 128 else n-256) >> 4 for n in range(256)], (0,))
    lines.append('motion_low_nibble:')
    pages([n << 4 for n in range(256)], (0,))
    lines.append('motion_high_nibble:')
    pages([n >> 4 for n in range(256)], (0,))
    lines.append('motion_upper_page::')
    directory = [0] * 256
    for i, upper in enumerate((*range(7), *range(-8, 0))):
        directory[upper & 255] = 0x45 + 3*i
    pages(directory, (0,))
    lines.extend(('.area _CODE_33', '_riding_phase_direct::'))
    pages([low * scale for low in range(256)], (0,))
    for nibble in range(16):
        upper = nibble if nibble < 8 else nibble - 16
        pages([(upper * 256 + low) * scale for low in range(256)], (8, 16, 24))

    # Wheel motion consumes only the rounded quotient. Bits 0..7 of the
    # low product cannot carry into the high byte term, which starts at bit 8.
    lines.append('angle_low_rows:')
    bias = 1 << 23
    pages([n * angle + bias for n in range(256)], (8, 16, 24, 32))
    lines.append('angle_high_rows:')
    pages([((n if n < 128 else n-256) << 8) * angle for n in range(256)],
          (8, 16, 24, 32, 40))
    lines.append('angle_minus_one:')
    pages([(n-256) * angle + bias for n in range(256)], (24, 32))

    lines.append(' wheel_angle_reader')
    output = gen / 'physics_phase_game.s'
    text = '\n'.join(lines) + '\n'
    if not output.exists() or output.read_text() != text:
        output.write_text(text)
    return output


def circle_source(gen, source, phase):
    """Link the positioned circle kernel only when its product pages are present."""
    if phase.name != 'physics_phase_game.s':
        return source
    output = gen / 'physics_circle_game.s'
    text = 'RIDING_PAIRED_CIRCLES = 1\n' + source.read_text()
    if not output.exists() or output.read_text() != text:
        output.write_text(text)
    return output


def body_angle_pages(gen, out=None):
    """Place every 256-entry angular lookup on a page without padding bank 3."""
    header = gen / 'physics_angle_rows.h'
    names = [f'riding_angle_digit{i}' for i in range(4)]
    names.extend(f'riding_angle_frac{i}' for i in range(3))
    names.extend(('riding_oms_product', 'riding_angle_carry', 'riding_angle_negative'))
    lines = ['.module body_angle_pages', '.area _CODE_3', 'body_angle_pages::']
    for name in names:
        data = read_array(header, name)
        lines.extend(('_' + name + '::', *byte_lines(data)))
    output = (out or gen) / 'body_angle_pages.s'
    write_if_changed(output, '\n'.join(lines) + '\n')
    return output


def body_angle(gen, source, out=None):
    """Fold the signed fractional high byte's bias into the top velocity row."""
    constants = (gen / 'riding_constants.h').read_text()
    match = re.search(r'q24_C_OMS\[2\]=\{(\d+),(\d+)\}', constants)
    if not match:
        raise ValueError('Missing scheduled body angular coefficient')
    scale = int(match[1])
    if scale != int(match[2]) or not 0x40000100 <= scale < 0x80000000:
        raise ValueError('Unsupported body angular coefficient')
    lines = ['RIDING_OMS_NEAR = 1', 'RIDING_ANGLE_PAGES = 1', source.read_text(),
             '.area _CODE_3', 'oms_near_rows:']
    for digit in range(32):
        signed = digit if digit < 16 else digit - 32
        value = ((signed * 65536 - 128) * scale) >> 24
        lines.append(' .db ' + ','.join(str(value >> shift & 255) for shift in (0, 8, 16, 24)))
    output = (out or gen) / 'physics_body_angle_game.s'
    text = '\n'.join(lines) + '\n'
    if not output.exists() or output.read_text() != text:
        output.write_text(text)
    return output


def torque_words(gen):
    """Exact low and signed high byte products for both angular moments."""
    constants = (gen / 'riding_constants.h').read_text()
    lines = ['.module torque_words', '.area _CODE_1']
    for name, width in (('C_SPRING_T', 4), ('C_FRIC_T', 3)):
        pair = re.search(r'q24_'+name+r'\[2\]=\{(\d+),(\d+)\}', constants)
        for phase, scale in enumerate(map(int, pair.groups())):
            lines.append(f'_torque_{name}_{phase}::')
            if scale*255 >= 1 << (width*8):
                raise ValueError(f'Angular coefficient exceeds its digit width: {name}')
            for signed in (False, True):
                values = [(n-256 if signed and n >= 128 else n)*scale for n in range(256)]
                for b in range(width):
                    for i in range(0,256,32):
                        lines.append(' .db '+','.join(str((v>>(8*b))&255) for v in values[i:i+32]))
    out = gen/'torque_words.s'
    text = '\n'.join(lines)+'\n'
    if not out.exists() or out.read_text()!=text:
        out.write_text(text)
    return out
