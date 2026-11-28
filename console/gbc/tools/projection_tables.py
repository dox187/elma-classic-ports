"""Generate the optional signed-coefficient projection reader for the full cartridge."""
from pathlib import Path
from tempfile import NamedTemporaryFile

DIRECTORY_BANK = 20
BANKS = (*range(21, 28), 477, 478, 479, 480, 502, 503, 504, 505, DIRECTORY_BANK)
ROWS_PER_BANK = 12
# The 216 standard and 24 extended test27 routes select the more frequent sign
# for each magnitude. The opposite sign uses the same five product planes.
COEFFICIENTS = (
    10973, -16383, -16379, -16382, -12167, 1097, 12417, -16368, -10689, -16362,
    134, -725, 3152, -16078, -15279, 5914, -4523, 402, -16378, -677,
    -16370, 1208, -246, 856, -16381, -3066, -412, -27, -240, -256,
    -169, -301, 1004, 1125, 457, 1116, -5069, -16095, -396, 6358,
    -170, -15747, -15580, -2927, -8449, -806, -15654, -163, -16120, -15100,
    -12484, -14037, -10611, -15702, 9809, -13123, -9638, 12195, 4677, 13249,
    -14955, -6692, -61, -8277, -10948, -14140, -16356, -15821, 4256, -3788,
    -15940, -5967, -15788, 4377, -15504, -15259, 5297, 4835, -5937, 394,
    -9636, 13251, -6840, -15270, -3013, 14888, -24, 16105, -807, 16207,
    -8275, -14141, -2401, -15854, 30, 1028, 7970, -15589, -15843, 5042,
    -536, 737, -538, -535, 16376, -15758, -101, -14315, 12416, 4174,
    -16351, 16367, -10682, 7872, 4487, -11764, 7856, 6893, -533, 3455,
    -539, 16377, -542, 1088, -16366, -819, -4419, -14863, -537, 1670,
    -497, -16364, 13593, 1155, 12397, -14282, 432, 8029, 404, 956,
    -9147, 1186, 1608, -10706, 410, -532, 1036, -805, -11292, -15586,
    1145, 5052, 13284, 12198, -11872, -13546, 15777, -13549, -159, -541,
    -10914, -512, 9212, -7931, -9217, -14337, -15455, 5440, -4135, -13007,
    -543, -11181, 9963, 920, 1344, 1020, 12236, 11975, -475, -14454,
    7840, -15965, 3680, -544, 1304, -16371, 7715, -16015, 960,
)
MIRRORED = tuple(-y for y in COEFFICIENTS)

# Code stays in fixed ROM while it reads the numeric tables in any high bank.
READER = """\
_riding_projection_fetch::
 jr c,_riding_projection_fetch_wide
 bit 7,h
 jr z,projection_narrow_direct
 res 7,h
 ; Multiply -x by the stored coefficient. +32768 requires the unsigned
 ; reader. Negating any other signed16 x leaves a signed16 operand.
 xor a
 sub e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
 cp #128
 jr nz,projection_narrow_direct
 ld a,e
 or a
 jr nz,projection_narrow_direct
 call projection_read_unsigned
 jr projection_extend_product
projection_narrow_direct:
 call _riding_projection_read_signed
projection_extend_product:
 ld a,h
 add a,a
 sbc a,a
 ld b,a
 ld c,a
 jp _riding_projection_hit
_riding_projection_fetch_wide::
 ; For x wider than signed16, combine unsigned low16*y with signed high16*y
 ; shifted left by 16. The low product's upper word must be sign extended.
 bit 7,h
 jr z,projection_read_wide
 ; Insert the product negation beneath the high-word source pointer.
 ; The ordinary reader restores the caller's MBC5 state before returning.
 res 7,h
 ld a,h
 pop bc
 ld hl,#_riding_projection_negate48
 push hl
 push bc
 ld h,a
projection_read_wide:
 ; Upper word pointer is above the return address. For a signed24 input,
 ; share the rolling reader's three-digit multiply in the already mapped bank.
 pop bc
 ld a,(bc)
 ld l,a
 inc bc
 ld a,(bc)
 ld b,a
 ld a,l
 add a
 sbc a
 cp b
 jr nz,projection_upper_word
 ld bc,#projection_extend_wide
 push bc
 ld a,l
 push af
 jp _riding_projection_saved24
projection_extend_wide:
 ld c,b
 ld a,b
 add a
 sbc a
 ld b,a
 jp _riding_projection_hit

projection_upper_word:
 ; X = unsigned(low word) + (signed(high word) << 16).
 ; Add the two overlapping words, extending the low product's sign.
 push de
 push hl
 ld e,l
 ld d,b
 call _riding_projection_read_signed
 ld b,h
 ld c,l
 pop hl
 ld a,h
 pop hl
 push bc
 push de
 ld d,h
 ld e,l
 ld h,a
 call projection_read_unsigned
 ld a,h
 add a
 sbc a
 pop bc
 add hl,bc
 pop bc
 bit 7,a
 jr z,projection_upper_carry
 dec bc
projection_upper_carry:
 jr nc,projection_upper_done
 inc bc
projection_upper_done:
 jp _riding_projection_hit

_riding_projection_read_signed::
 ; The shared low-byte page sits between the two upper-byte pairs.
 ld l,e
 ld c,(hl)
 inc h
 ld b,(hl)
 inc h
 ld e,(hl)
 ld l,d
 ld a,c
 add a,(hl)
 ld d,a
 inc h
 ld a,b
 adc a,(hl)
 ld c,a
 inc h
 ld a,#0
 adc a,(hl)
 ld h,a
 ld l,c
 ret

projection_read_unsigned:
 ; U[n] = n*y + 0x800000. Two unsigned rows have a combined bias
 ; of 0x80800000. Modulo-32 subtraction gives the exact signed32 result.
 ld l,e
 ld c,(hl)
 inc h
 ld b,(hl)
 inc h
 ld e,(hl)
 ld l,d
 ld a,c
 add a,(hl)
 ld d,a
 dec h
 dec h
 ld a,b
 adc a,(hl)
 ld c,a
 inc h
 ld a,#0
 adc a,(hl)
 ld h,a
 ld a,c
 sub a,#0x80
 ld l,a
 ld a,h
 sbc a,#0x80
 ld h,a
 ret
"""


def row_page(index):
    return 0x40 + 5 * (index % ROWS_PER_BANK)


def fixed_hash():
    # For a given high byte, addition of a displacement permutes all 256
    # low bytes. Matching the stored high byte therefore proves the whole key.
    groups = {}
    for index, coefficient in enumerate(COEFFICIENTS):
        value = abs(coefficient)
        groups.setdefault(value >> 8, []).append((value & 255, index, coefficient))
    displacements = bytearray(256)
    tags = bytearray([255]) * 256
    banks, pages = bytearray(256), bytearray(256)
    for high, rows in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
        for delta in range(256):
            if all(tags[(low + delta) & 255] == 255 for low, _, _ in rows):
                break
        else:
            raise ValueError(f'Cannot place projection magnitudes with high byte {high}')
        displacements[high] = delta
        displacements[255 - high] = 255 - delta
        for low, index, coefficient in rows:
            slot = (low + delta) & 255
            tags[slot] = high
            banks[slot] = BANKS[index // ROWS_PER_BANK] & 255
            pages[slot] = row_page(index) | (128 if coefficient < 0 else 0)
    return displacements, tags, banks, pages


def hash_source(gen):
    from head_clearance import write_if_changed
    lines = ['.module projection_hash', '.area _CODE', '_riding_projection_hash::']
    for page in fixed_hash():
        lines.extend(byte_lines(page))
    path = gen/'physics_projection_hash.s'
    write_if_changed(path, '\n'.join(lines)+'\n')
    return path


def planes(y):
    unsigned = [x * y + 0x800000 for x in range(256)]
    signed = [((x ^ 128) - 128) * y - 0x8000 for x in range(256)]
    if not (0 <= min(unsigned) and max(unsigned) < 1 << 24 and
            -(1 << 23) <= min(signed) and max(signed) < 1 << 23):
        raise ValueError(f'Projection planes exceed 24 bits for coefficient {y}')
    return [bytes((value >> shift) & 255 for value in row)
            for row, shifts in ((unsigned, (8, 16, 0)), (signed, (8, 16))) for shift in shifts]


def shallow_rows(magnitude):
    """For y = high * 256 + low, increasing low can cross one Q14 boundary."""
    quotient, threshold = bytearray(), bytearray()
    for digit in range(256):
        high = (digit ^ 128) - 128
        whole, remainder = divmod(8192 - high * 256 * magnitude, 16384)
        quotient.append(whole & 255)
        threshold.append(min(255, remainder // magnitude))
    return quotient, threshold


def byte_lines(data):
    return [' .db ' + ','.join(map(str, data[i:i + 32])) for i in range(0, len(data), 32)]


def generate(source, destination):
    """Enable the cart reader. Standalone native fixtures assemble source directly."""
    output = ['RIDING_PROJECTION_TABLES = 1', source.read_text()]
    output.append('.area _CODE')
    output.append(READER)
    output.append('.area _CODE_4')
    for magnitude in (61, 9):
        output.append(f'_riding_shallow_dot_{magnitude}::')
        for row in shallow_rows(magnitude):
            output.extend(byte_lines(row))
    for group, bank in enumerate(BANKS):
        output.extend((f'.area _CODE_{bank}', f'_riding_projection_bank_{bank}::'))
        for y in COEFFICIENTS[group * ROWS_PER_BANK:(group + 1) * ROWS_PER_BANK]:
            for page in planes(y):
                output.extend(byte_lines(page))
    result = '\n'.join(output) + '\n'
    if not destination.is_file() or destination.read_text() != result:
        temporary = NamedTemporaryFile(mode='w', dir=destination.parent, delete=False)
        pending = Path(temporary.name)
        try:
            with temporary:
                temporary.write(result)
            pending.replace(destination)
        finally:
            pending.unlink(missing_ok=True)
    return destination


def validate_layout(symbols):
    """Every indexed product plane starts at its expected physical bank address."""
    for index, bank in enumerate(BANKS):
        start = (bank << 16) | 0x4000
        count = len(COEFFICIENTS[index*ROWS_PER_BANK:(index+1)*ROWS_PER_BANK])
        expected_size = count * 1280
        end = start + symbols.get(f'l__CODE_{bank}',0)
        tail = symbols.get(f'_head_quarter_tail_{bank}',end)
        tail_end = symbols.get(f'_head_quarter_end_{bank}',tail)
        if bank == 20 and '_riding_wheel_refinement' in symbols:
            tail = symbols['_riding_wheel_refinement']
            tail_end = symbols.get('_wheel_refinement_end')
        if f'patch_data_start_{bank}' in symbols:
            patch_start = symbols[f'patch_data_start_{bank}']
            patch_end = symbols[f'patch_data_end_{bank}']
            if patch_start != start+expected_size or not patch_start < patch_end == tail:
                raise ValueError(f'Ordered pair blocks overlap projection or head tables in bank {bank}')
            tail = patch_start
        if (symbols.get(f'_riding_projection_bank_{bank}') != start or
                symbols.get(f's__CODE_{bank}') != start or
                tail != start+expected_size or tail_end != end):
            raise ValueError(f'Overlapping or misaligned signed projection table in bank {bank}')
