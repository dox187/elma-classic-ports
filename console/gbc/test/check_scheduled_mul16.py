"""Check both signed16 multiply entry points in the linked scheduled game ROM."""
import argparse
from math import isqrt
from io import BytesIO
from pathlib import Path
import random
import re

from pyboy import PyBoy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', required=True, type=Path)
    rom = parser.parse_args().rom
    symbols = {name: int(addr, 16) for name, addr in re.findall(
        r'^DEF (\S+) 0x([0-9a-fA-F]+)', rom.with_suffix('.noi').read_text(), re.M)}
    image = bytearray(rom.read_bytes())
    squares = symbols['_riding_small_squares']
    assert squares == 0x1c4000
    offset = (squares >> 16) * 16384
    assert symbols['_riding_endpoint_square_rows'] == squares + 256
    assert symbols['_riding_square_rows'] == squares + 1280
    for x in range(-512, 4096):
        digit = x & 255
        row = offset + 256 + 512 * ((x + 512) // 256)
        value = image[offset+digit] | image[row+digit] << 8 | image[row+256+digit] << 16
        assert value == x*x

    image[0x100:0x102] = bytes((0x18, 0xfe))
    p = PyBoy(BytesIO(image), window='null', sound_emulated=False, cgb=True)
    p.set_emulation_speed(0)
    cases = [(v, v) for v in range(-4097, 4098)]
    edges = (-32768, -32767, -16384, -4096, -512, -256, -255, -1, 0,
             1, 255, 256, 511, 4095, 4096, 16384, 32767)
    cases.extend((x, y) for x in edges for y in edges)
    rng = random.Random(0x9624)
    cases.extend((rng.randint(-32768, 32767), rng.randint(-32768, 32767)) for _ in range(4096))
    code, stack = 0xc900, 0xcff0
    geometry_cases = 0
    try:
        p.tick(240, False)
        r = p.register_file
        for i, (x, y) in enumerate(cases):
            addr = symbols['_riding_mul16_regs' if i & 1 else '_riding_mul16']
            p.memory[code:code+6] = (0xf3, 0xcd, addr & 255, addr >> 8 & 255, 0x18, 0xfe)
            args = x.to_bytes(2, 'little', signed=True) + y.to_bytes(2, 'little', signed=True) + b'\x35\xda'
            p.memory[stack:stack+len(args)] = args
            bank = (1, 8, 9, 28, 175)[i % 5]
            p.memory[symbols['__current_bank']] = bank
            p.memory[0x2000] = bank
            p.memory[0x3000] = 0
            r.SP, r.PC = stack, code
            r.D, r.E, r.B, r.C = x >> 8 & 255, x & 255, y >> 8 & 255, y & 255
            p.tick(1, False)
            assert r.HL << 16 | r.D << 8 | r.E == (x*y) & 0xffffffff, (x, y)
            assert (r.SP, r.PC) == (stack, code + 4)
            assert bytes(p.memory[stack:stack+len(args)]) == args
            assert p.memory[symbols['__current_bank']] == bank
            assert bytes(p.memory[0x4000:0x4020]) == image[bank*16384:bank*16384+32]
        coords = (-32768, -4097, -512, -410, -409, -256, -128, -103, -102,
                  -101, -1, 0, 1, 101, 102, 103, 127, 255, 256, 409, 410, 32767)
        for name in ('_riding_merge_close', '_riding_endpoint_squared'):
            addr = symbols[name]
            p.memory[code:code+6] = (0xf3, 0xcd, addr & 255, addr >> 8 & 255, 0x18, 0xfe)
            pairs = [(x, y) for x in coords for y in coords]
            if name == '_riding_endpoint_squared':
                pairs = [(x, y) for x, y in pairs if abs(x) < 410 and abs(y) < 410]
                pairs.extend((rng.randint(-409, 409), rng.randint(-409, 409)) for _ in range(512))
            else:
                for x in range(-101, 102):
                    limit = isqrt(102**2 - 1 - x*x)
                    pairs.extend((x, sign*(limit+d)) for sign in (-1, 1) for d in (-1, 0, 1))
            for x, y in pairs:
                p.memory[symbols['__current_bank']] = p.memory[0x2000] = 9
                r.SP, r.PC = stack, code
                r.D, r.E, r.B, r.C = x >> 8 & 255, x & 255, y >> 8 & 255, y & 255
                p.tick(1, False)
                d2 = x*x + y*y
                if name == '_riding_merge_close':
                    assert r.A == int(d2 < 102**2), (x, y, r.A)
                else:
                    assert (r.D << 24 | r.E << 16 | r.B << 8 | r.C) == d2, (x, y, d2)
                assert (r.SP, r.PC) == (stack, code+4)
                assert p.memory[symbols['__current_bank']] == 9
                assert bytes(p.memory[0x4000:0x4020]) == image[9*16384:9*16384+32]
                geometry_cases += 1
    finally:
        p.stop(save=False)
    print(f'{len(cases)} signed16 products and 4608 table records passed; {geometry_cases} wheel geometry checks passed')


if __name__ == '__main__':
    main()
