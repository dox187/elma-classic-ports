"""Sets the region of the header of a LoROM image and its checksum.

  romfix.py IN OUT --tv ntsc|pal
"""

import argparse

HEADER = 0x7FC0
COUNTRY = {'ntsc': 0x01, 'pal': 0x02}  # USA, Europe


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('out')
    ap.add_argument('--tv', choices=sorted(COUNTRY), default='ntsc')
    a = ap.parse_args()
    rom = bytearray(open(a.rom, 'rb').read())
    rom[HEADER + 0x19] = COUNTRY[a.tv]
    rom[HEADER + 0x1C:HEADER + 0x20] = b'\xff\xff\x00\x00'
    total = sum(rom) & 0xFFFF
    rom[HEADER + 0x1C:HEADER + 0x1E] = (total ^ 0xFFFF).to_bytes(2, 'little')
    rom[HEADER + 0x1E:HEADER + 0x20] = total.to_bytes(2, 'little')
    with open(a.out, 'wb') as f:
        f.write(rom)


if __name__ == '__main__':
    main()
