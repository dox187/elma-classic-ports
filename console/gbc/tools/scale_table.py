"""Generate exact unsigned 8x8 products for the coefficient multiplier.

Eight complete ROM banks hold rows selected by the 8-bit multiplier. Both
bytes of a signed 16-bit input use the same bank, so one bank switch serves
the whole multiplication. Each row holds the 256 low bytes followed by all 256 high bytes.
The multiplicand directly addresses a page without a 16-bit index shift.
"""
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for bank in range(36, 44):
        rows = []
        for m in range((bank - 36) * 32, (bank - 35) * 32):
            for shift in (0, 8):
                rows.append(','.join(str(((m * x) >> shift) & 255) for x in range(256)))
        text = '#include <stdint.h>\n#pragma bank %d\n' % bank
        text += 'const uint8_t physics_scale_planes_%d[16384] = {\n' % bank
        text += ',\n'.join(rows) + '\n};\n'
        (args.out / ('physics_scale_%d.c' % bank)).write_text(text)


if __name__ == '__main__':
    main()
