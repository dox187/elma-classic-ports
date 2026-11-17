"""Exact interrupt-free SM83 T-cycle cost of src/world_zx0.s.

The model follows the assembly labels and its sentinel bit buffer, including
conditional calls/returns and the single-byte literal shortcut. Costs cover
_zx0_decompress entry through its final RET, excluding the caller's CALL,
bank/SRAM switching, interrupt handlers and any other caller work. CGB double
speed changes the elapsed time per T-cycle, not the counts returned here.

The source hash is deliberately mandatory: changing the decoder requires
reviewing this model and rerunning the native cycle comparison before updating
the hash. Inputs are bounded and malformed streams fail instead of returning a
potentially unsafe estimate. Trailing bytes are allowed, as in zx0.decompress.
"""

from dataclasses import dataclass
import hashlib
from pathlib import Path


DECODER_SHA256 = '5dfd043ef1f7b4f3154802ec22d1c4182e16e72afc4505bf2be924a16b55877a'
DECODER_SOURCE = Path(__file__).resolve().parents[1] / 'src/world_zx0.s'


def validate_decoder(source=None):
    """Fail closed if the assembly differs from the model's reviewed source."""
    path = DECODER_SOURCE if source is None else Path(source)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != DECODER_SHA256:
        raise ValueError(f'ZX0 cycle model does not match decoder {path}: {digest}')
    return digest


@dataclass(frozen=True)
class CycleEstimate:
    cycles: int
    compressed_bytes: int
    decoded_bytes: int
    bit_refills: int
    literal_runs: int
    short_literal_runs: int
    match_runs: int
    new_offsets: int
    elias_data_bits: int


def copy_cycles(count):
    """world_zx0_copy, including its RET but excluding the caller's CALL.

    Setup costs 36 T for odd counts or 44 T for even counts. Every byte costs
    24 T (LD A,(HL+); LD (DE),A; INC DE). There are count//2+1 DEC C/JR tests,
    normally 16 T each. Every 512 bytes adds one DEC B/JR NZ trip (12 T above
    that baseline); the final trip adds 8 T, followed by RET (16 T).
    """
    if not 1 <= count <= 65535:
        raise ValueError('ZX0 copy count must fit a positive 16-bit register')
    return (36 if count & 1 else 44) + 24 * count + 16 * (count // 2 + 1) + 12 * (count // 512) + 24


def analyze(data, expected_size, decoder_source=None):
    """Decode one stream symbolically and return its exact native cycle cost."""
    validate_decoder(decoder_source)
    if not 1 <= expected_size <= 65535:
        raise ValueError('ZX0 output size must be between 1 and 65535')
    data = memoryview(data).cast('B')
    position = 0
    output = bytearray()
    a = 128
    bc = 0
    last_offset = 65535
    # Four LD r,r; LD BC,nn; PUSH BC; INC BC; LD A,n.
    cycles = 4 * 4 + 12 + 16 + 8 + 8
    refills = literal_runs = short_literals = matches = new_offsets = data_bits = 0

    def byte():
        nonlocal position
        if position >= len(data):
            raise ValueError('Truncated ZX0 block')
        value = data[position]
        position += 1
        return value

    def shift():
        nonlocal a, cycles
        carry = a >> 7
        a = (a << 1) & 255
        cycles += 4  # ADD A,A
        return carry

    def stop_bit():
        nonlocal a, cycles, refills
        carry = shift()
        if a:
            cycles += 12  # JR NZ,ready, taken
        else:
            cycles += 8 + 8 + 4  # JR NZ untaken; LD A,(HL+); RLA
            value = byte()
            a, carry = ((value << 1) | carry) & 255, value >> 7
            refills += 1
        return carry

    def elias(backtrack=False):
        nonlocal bc, cycles, data_bits
        # Matches either world_zx0_elias_loop or _elias_backtrack. The callers
        # account for CALL and, for _elias, INC C separately.
        pairs = 0
        while True:
            if not backtrack:
                if stop_bit():
                    cycles += 20  # RET C, taken
                    return
                cycles += 8  # RET C, untaken
            # ADD A,A; RL C; RL B; JR elias_loop. The data bit cannot refill.
            bc = ((bc << 1) | shift()) & 65535
            cycles += 8 + 8 + 12
            data_bits += 1
            pairs += 1
            if pairs > 16:
                raise ValueError('Oversized ZX0 Elias code')
            backtrack = False

    def literal(count):
        nonlocal position
        if len(output) + count > expected_size:
            raise ValueError('ZX0 literals exceed output size')
        if position + count > len(data):
            raise ValueError('Truncated ZX0 literals')
        output.extend(data[position:position + count])
        position += count

    state = 'literal'
    while True:
        if state == 'literal':
            literal_runs += 1
            if stop_bit():
                # JR NC untaken; LD C,A; LD A,(HL+); LD (DE),A; INC DE;
                # LD A,C; LD C,0. A is unchanged after the temporary use of C.
                cycles += 8 + 4 + 8 + 8 + 8 + 4 + 8
                literal(1)
                short_literals += 1
            else:
                cycles += 12 + 12 + 24  # JR NC taken; LD BC,1; CALL backtrack
                bc = 1
                elias(True)
                literal(bc)
                # LDH (bits),A; CALL copy; LDH A,(bits); JR literal_done.
                cycles += 12 + 24 + copy_cycles(bc) + 12 + 12
            bc = 0
            if shift():
                cycles += 12  # JR C,new_offset, taken
                state = 'offset'
                continue
            cycles += 8 + 24 + 4  # JR C untaken; CALL elias; INC C
            bc = 1
            elias()
        elif state == 'offset':
            # POP BC; LD C,254; CALL elias_loop.
            cycles += 12 + 8 + 24
            bc = (last_offset & 0xFF00) | 254
            elias()
            low = ((bc & 255) + 1) & 255
            cycles += 4  # INC C
            if not low:
                cycles += 20  # RET Z, taken: decoder exit
                if len(output) != expected_size:
                    raise ValueError('ZX0 output has the wrong size')
                return CycleEstimate(cycles, position, len(output), refills,
                                     literal_runs, short_literals, matches,
                                     new_offsets, data_bits)
            cycles += 8  # RET Z, untaken
            # LD B,C; LD C,(HL); INC HL; RR B; RR C. Elias returns carry set,
            # and INC C preserves it, so the signed offset's top bit is one.
            value = byte()
            last_offset = ((((low >> 1) | 128) << 8) | ((value >> 1) | ((low & 1) << 7)))
            cycles += 4 + 8 + 8 + 8 + 8 + 16 + 12  # ...; PUSH BC; LD BC,1
            bc = 1
            if value & 1:
                cycles += 12  # CALL NC,backtrack, untaken
            else:
                cycles += 24  # CALL NC,backtrack, taken
                elias(True)
            bc += 1
            cycles += 8 + 12  # INC BC; JR match
            new_offsets += 1

        # world_zx0_match: preserve A/HL, retrieve the stack offset and call copy.
        offset = 65536 - last_offset
        if not bc or offset > len(output) or len(output) + bc > expected_size:
            raise ValueError('Invalid ZX0 back reference')
        cycles += 12 + 16 + 12 + 8 + 8 + 4 + 8 + 24 + copy_cycles(bc)
        for _ in range(bc):
            output.append(output[-offset])
        matches += 1
        bc = 0
        cycles += 12 + 12  # POP HL; LDH A,(bits)
        if shift():
            cycles += 8  # JR NC,literals, untaken
            state = 'offset'
        else:
            cycles += 12  # JR NC,literals, taken
            state = 'literal'


def decode_cycles(packed, expected_size, decoder_source=None):
    """Return entry-through-return CPU T-cycles for one validated stream."""
    return analyze(packed, expected_size, decoder_source).cycles
