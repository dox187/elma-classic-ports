"""Generate the optional signed-coefficient projection reader for the full cartridge."""
from pathlib import Path
from tempfile import NamedTemporaryFile

BANKS = (477, 478, 479, 480, 502, 503, 504, 505)
# Frozen from the 54 test8 neutral controller routes (signed16 or wider x).
# Popularity changes only hit rate. The full signed coefficient is checked.
COEFFICIENTS = (
    16384, -16384, -16379, -16383, -86, 16383, 16379, -16382, 16382, 457,
    -725, 402, -677, 134, -3066, -5069, -412, 8, -301, -240,
    -256, -246, -163, -104, -169, -170, 104, -108, 3152, -4523,
    -78, 5914, -396, -61, -59, -33, -6692, -32, -27, 856,
    -16378, -16370, -16095, -8277, -15580, 4256, 9809, -8449, -2927, -12484,
    394, -18, 50, -16078, -15279, -15, -15747, -5, -16381, -14955,
    16381, 16378, 16370, 16368, 16095, -14140, 13249, 16078, -15821, -13123,
    -14037, 4677, 10, -10611, 16362, 14955, -75, 14140, 15821, 13123,
)

# Code stays in fixed ROM while it reads the numeric tables in any high bank.
READER = """\
_riding_projection_fetch::
 jr c,30$
 call 50$
 ld a,h
 add a,a
 sbc a,a
 ld b,a
 ld c,a
 jp _riding_projection_hit
30$:
 ; For x wider than signed16, combine unsigned low16*y with signed high16*y
 ; shifted left by 16. The low product's upper word must be sign extended.
 push hl
 call 60$
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
 call 50$
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

50$:
 ld l,e
 ld e,(hl)
 inc h
 ld c,(hl)
 inc h
 ld b,(hl)
 ld l,d
 inc h
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

60$:
 ; U[n] = n*y + 0x800000. Two unsigned rows have a combined bias
 ; of 0x80800000. Modulo-32 subtraction gives the exact signed32 result.
 ld l,e
 ld e,(hl)
 inc h
 ld c,(hl)
 inc h
 ld b,(hl)
 dec h
 dec h
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
 ld a,c
 sub a,#0x80
 ld l,a
 ld a,h
 sbc a,#0x80
 ld h,a
 ret
"""


def row_page(index):
    return 0x40 + 6 * (index % 10)


def directory():
    tags, banks, pages = (bytearray(256) for _ in range(3))
    for index, y in enumerate(COEFFICIENTS):
        high = (y >> 8) & 255
        slot = (((high >> 2) | (high << 6)) - y) & 255
        if banks[slot]:
            raise ValueError(f'Projection directory collision for coefficient {y}')
        tags[slot] = high
        banks[slot] = BANKS[index // 10] & 255
        pages[slot] = row_page(index)
    return tags, banks, pages


def planes(y):
    unsigned = [x * y + 0x800000 for x in range(256)]
    signed = [((x ^ 128) - 128) * y - 0x8000 for x in range(256)]
    if not (0 <= min(unsigned) and max(unsigned) < 1 << 24 and
            -(1 << 23) <= min(signed) and max(signed) < 1 << 23):
        raise ValueError(f'Projection planes exceed 24 bits for coefficient {y}')
    return [bytes((value >> shift) & 255 for value in row)
            for row in (unsigned, signed) for shift in (0, 8, 16)]


def byte_lines(data):
    return [' .db ' + ','.join(map(str, data[i:i + 32])) for i in range(0, len(data), 32)]


def generate(source, destination):
    """Enable the cart reader. Standalone native fixtures assemble source directly."""
    output = ['RIDING_PROJECTION_TABLES = 1', source.read_text()]
    output.extend(('.area _CODE', '_riding_projection_directory::'))
    for page in directory():
        output.extend(byte_lines(page))
    output.append(READER)
    for group, bank in enumerate(BANKS):
        output.extend((f'.area _CODE_{bank}', f'_riding_projection_bank_{bank}::'))
        for y in COEFFICIENTS[group * 10:(group + 1) * 10]:
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
    if not 0 <= symbols['_riding_projection_directory'] <= 0x4000 - 768:
        raise ValueError('Projection directory must be in fixed ROM')
    for bank in BANKS:
        start = (bank << 16) | 0x4000
        expected_size = 0x3c00
        if (symbols.get(f'_riding_projection_bank_{bank}') != start or
                symbols.get(f's__CODE_{bank}') != start or
                symbols.get(f'l__CODE_{bank}') != expected_size):
            raise ValueError(f'Overlapping or misaligned signed projection table in bank {bank}')
