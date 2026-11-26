"""Check both signed16 multiply entry points in the linked scheduled game ROM."""
import argparse
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
    for x in range(4096):
        assert int.from_bytes(image[offset+4*x:offset+4*x+4], 'little') == x*x

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
    try:
        p.tick(240, False)
        r = p.register_file
        for i, (x, y) in enumerate(cases):
            addr = symbols['_riding_mul16_regs' if i & 1 else '_riding_mul16']
            p.memory[code:code+6] = (0xf3, 0xcd, addr & 255, addr >> 8, 0x18, 0xfe)
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
    finally:
        p.stop(save=False)
    print(f'{len(cases)} signed16 products and 4096 table records passed')


if __name__ == '__main__':
    main()
