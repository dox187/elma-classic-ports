"""Generate exact unsigned 8x8 products for the coefficient multiplier.

Eight complete ROM banks hold rows selected by the 8-bit multiplier. Both
bytes of a signed 16-bit input use the same bank, so one bank switch serves
the whole multiplication. Each row contains 256 little-endian uint16 values.
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
            rows.append(','.join(str(m * x) for x in range(256)))
        text = '#include <stdint.h>\n#pragma bank %d\n' % bank
        text += 'const uint16_t physics_scale_%d[16384/2] = {\n' % bank
        text += ',\n'.join(rows) + '\n};\n'
        (args.out / ('physics_scale_%d.c' % bank)).write_text(text)


if __name__ == '__main__':
    main()
