"""Bounded host decoder for the forward ZX0 stream emitted by GBDK 4.5.0.

Format reference: https://github.com/einar-saukas/ZX0
Used to verify generated blocks and bytes read back from the linked ROM.
"""


def decompress(data, expected_size):
    position = 0
    bits = mask = 0
    backtrack = False
    output = bytearray()

    def byte():
        nonlocal position
        if position >= len(data):
            raise ValueError('Truncated ZX0 block')
        value = data[position]
        position += 1
        return value

    def bit():
        nonlocal bits, mask, backtrack
        if backtrack:
            backtrack = False
            return data[position - 1] & 1
        mask >>= 1
        if not mask:
            bits, mask = byte(), 128
        return int(bool(bits & mask))

    def gamma(inverted=False):
        value = 1
        while not bit():
            value = (value << 1) | (bit() ^ inverted)
            if value > max(expected_size, 256):
                raise ValueError('Oversized ZX0 length or offset')
        return value

    offset = 1
    state = 'literal'
    while True:
        if state == 'literal':
            count = gamma()
            if len(output) + count > expected_size:
                raise ValueError('ZX0 literals exceed output size')
            output.extend(byte() for _ in range(count))
            state = 'offset' if bit() else 'repeat'
            continue
        if state == 'offset':
            high = gamma(True)
            if high == 256:
                if len(output) != expected_size:
                    raise ValueError('ZX0 output has the wrong size')
                return bytes(output)
            offset = high * 128 - (byte() >> 1)
            backtrack = True
            count = gamma() + 1
        else:
            count = gamma()
        if offset > len(output) or len(output) + count > expected_size:
            raise ValueError('Invalid ZX0 back reference')
        for _ in range(count):
            output.append(output[-offset])
        state = 'offset' if bit() else 'literal'
