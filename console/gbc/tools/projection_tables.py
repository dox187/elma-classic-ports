"""Generate the optional signed-coefficient projection reader for the full cartridge."""
from pathlib import Path
from tempfile import NamedTemporaryFile

DIRECTORY_BANK = 20
BANKS = (*range(21, 28), 477, 478, 479, 480, 502, 503, 504, 505, DIRECTORY_BANK)
ROWS_PER_BANK = 12
# Frozen from all 216 test23 controller routes. Store the more frequent sign
# for each magnitude. The opposite sign uses the same five product planes.
COEFFICIENTS = (
    -16384, -16383, -16379, -16382, -104, -86, -108, -16368, 8, -16362,
    134, -725, 3152, -16078, -15279, 5914, -4523, 402, -16378, -677,
    -16370, -15, -246, 856, -16381, -3066, -412, -27, -240, -256,
    -169, -301, -59, -33, 457, -32, -5069, -16095, -396, 50,
    -170, -15747, -15580, -2927, -8449, -18, -78, -163, -16120, -5,
    -12484, -14037, -10611, -15702, 9809, -13123, -9638, -9, 4677, 13249,
    -14955, -6692, 61, -8277, 10, -14140, -16356, -15821, 4256, -3788,
    -15940, -5967, -15788, 4377, -15504, -15259, 5297, 408, -5937, 394,
    -9636, 13251, -6840, -15270, -3013, 14888, 407, 16105, 409, 16207,
    -8275, -14141, -2401, -957, -91, -2942, 16118, -15589, -15843, 5042,
    -536, 737, -538, -535, 16376, -15758, -13874, -8715, 406, 4174,
    16351, 16367, -3643, -15974, 4487, -11764, -11404, -534, -533, -56,
    -539, 16377, 13941, -15559, -5132, -819, -4419, 405, -537, 1046,
    -497, -16364, 614, 8607, -75, -14282, 432, 8029, 404, 956,
    9789, 9606, -13138, 615, -540, -532, 16277, 1868, -11292, -15586,
    617, 5052, 13284, 613, -11872, -13546, 15777, -13549, 1613, -541,
    616, -512, 9212, -7931, -9217, -14337, -15455, 5440, 9590, -13007,
    -26, -11181, 9963, -9687, 13214, 618, -531, 11975, -475, -14454,
    -530, -15965, 3680, -544, -124, -16371, 7715, -16015, -529,
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
 push hl
 call projection_read_unsigned
 pop bc
 push de
 push hl
 ldhl sp,#4
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld h,b
 call _riding_projection_read_signed
 pop bc
 ld a,b
 add a,a
 sbc a,a
 push hl
 ld h,a
 ld l,a
 ld a,e
 add a,c
 ld e,a
 ld a,d
 adc a,b
 ld d,a
 pop bc
 ld a,l
 adc a,c
 ld c,a
 ld a,h
 adc a,b
 ld b,a
 ld h,d
 ld l,e
 pop de
 add sp,#2
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


def directory():
    # Each high-byte group uses three pages addressed directly by the low
    # byte. Two high bytes can share a group if their occupied lows differ.
    # The high tag and nonzero bank must still match on every lookup.
    lows = {}
    for y in (*COEFFICIENTS, *MIRRORED):
        lows.setdefault(y >> 8 & 255, set()).add(y & 255)
    occupied, groups = [], []
    table_page = row_page(len(COEFFICIENTS) - 1) + 5
    routing = bytearray([table_page + 1] * 256)
    for high in sorted(lows, key=lambda h: -len(lows[h])):
        group = next((i for i, used in enumerate(occupied) if used.isdisjoint(lows[high])), len(groups))
        if group == len(groups):
            occupied.append(set())
            groups.append([bytearray(256) for _ in range(3)])
        routing[high] = table_page + 1 + 3*group
        occupied[group].update(lows[high])
    if table_page + 1 + 3*len(groups) > 0x80:
        raise ValueError('Projection directory exceeds bank 20')
    for index, stored in enumerate(COEFFICIENTS):
        for y in (stored, -stored):
            high, low = (y >> 8) & 255, y & 255
            tags, banks, pages = groups[(routing[high] - table_page - 1)//3]
            tags[low] = high
            banks[low] = BANKS[index // ROWS_PER_BANK] & 255
            pages[low] = row_page(index) | (128 if y != stored else 0)
    return [routing, *(page for group in groups for page in group)]


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
    output.append('_riding_projection_directory::')
    for page in directory():
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
        if bank == DIRECTORY_BANK:
            if symbols['_riding_projection_directory'] != start + expected_size:
                raise ValueError('Projection directory must follow the last numeric row in bank 20')
            expected_size += len(directory()) * 256
        end = start + symbols.get(f'l__CODE_{bank}',0)
        tail = symbols.get(f'_head_quarter_tail_{bank}',end)
        if (symbols.get(f'_riding_projection_bank_{bank}') != start or
                symbols.get(f's__CODE_{bank}') != start or
                tail != start+expected_size or symbols.get(f'_head_quarter_end_{bank}',tail) != end):
            raise ValueError(f'Overlapping or misaligned signed projection table in bank {bank}')
