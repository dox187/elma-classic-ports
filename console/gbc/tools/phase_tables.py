"""Exact partial-step movement products in the two dedicated movement banks."""
import json
import re


def generate(gen, source):
    manifest = json.loads((gen / 'physics_q24_manifest.json').read_text())
    header = (gen / 'physics_q24_coefficients.h').read_text()
    index = int(re.search(r'^#define Q24_MOVE (\d+)$', header, re.M)[1])
    scale = manifest['coefficient_values'][index]
    # The direct row's floor occupies signed8. The wider two-row sum uses
    # signed16. Its high digit already includes eight low zero bits.
    if not 0 < scale <= (1 << 20):
        return source

    lines = ['RIDING_PHASE_TABLES = 1', source.read_text()]

    def pages(values, shifts):
        for shift in shifts:
            data = [(v >> shift) & 255 for v in values]
            for offset in range(0, 256, 32):
                lines.append(' .db ' + ','.join(map(str, data[offset:offset+32])))

    lines.extend(('.area _CODE_32', '_riding_phase_words::'))
    for nibble in range(16):
        if nibble == 7:
            # This hole in the high-word range holds the unsigned low byte.
            pages([low * scale for low in range(256)], (0, 8, 16, 24))
        else:
            upper = nibble if nibble < 8 else nibble - 16
            pages([((upper * 256 + low) << 8) * scale for low in range(256)],
                  (8, 16, 24, 32))

    lines.extend(('.area _CODE_33', '_riding_phase_direct::'))
    for nibble in range(16):
        upper = nibble if nibble < 8 else nibble - 16
        pages([(upper * 256 + low) * scale for low in range(256)], (0, 8, 16, 24))

    output = gen / 'physics_phase_game.s'
    text = '\n'.join(lines) + '\n'
    if not output.exists() or output.read_text() != text:
        output.write_text(text)
    return output
