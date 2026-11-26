"""Check the linked single-contact impulse predicate against an integer dot product."""
import argparse
from io import BytesIO
from pathlib import Path
import random
import re
import struct

from pyboy import PyBoy


def vectors():
    rng = random.Random(0x9615)
    extrema = (-2**31, -2**31+1, -65537, -65536, -1, 0, 1, 65535, 65536, 2**31-1)
    for x in extrema:
        for y in extrema:
            for nx, ny in ((-32768, -32768), (32767, 32767), (0, -16384),
                           (8191, 8448), (-1024, 32767), (0, 0)):
                yield x, y, nx, ny
    # Isolate the exact half-unit tie, both alone and after cancellation.
    for ny in (-32768, -8192, 0, 8192, 8448, 16384, 32767):
        for y in (-65000, -256, -1, 0, 1, 256, 65000):
            for raw in (8191, 8192, 8193):
                for nx in (-1, 1):
                    yield (raw - y*ny)*nx, y, nx, ny
    # Probe the band edges and both sides of the folded high-byte comparison.
    for x in (-65537, -65536, -2049, -2048, -257, -256, -1,
              0, 255, 256, 2047, 2048, 65535, 65536):
        folded = (x if x >= 0 else ~x) >> 8
        for nx in (-8193, -8192, -1025, -1024, 1023, 1024, 8191, 8192):
            edge = (folded >> (3 if -1024 <= nx < 1024 else 0)) * 256
            for y in (edge-1, edge, edge+255, edge+256):
                for ny in (8447, 8448, 16384):
                    yield x, y, nx, ny
                    yield x, ~y, nx, ny
    # Diagonal dominance compares folded magnitude bytes, including carry
    # from doubling, sign extension outside 16 bits, and positive Q14 ties.
    for folded in (0, 1, 31, 126, 127, 128, 255):
        threshold = 2 * (folded + 1) * 256
        for x in (folded*256, (folded+1)*256-1, -(folded+1)*256):
            for y in (threshold-1, threshold, -threshold, -threshold-1, 65536, -65537):
                for nx in (-16385, -16384, -8193, -8192, 8191, 8192, 16383, 16384):
                    for ny in (8447, 8448, 32767):
                        yield x, y, nx, ny
    for nx in (-4097, -4096, -1025, 1024, 4095, 4096):
        for x in (-65536, -14336, -257, 255, 14335, 65535):
            ybin = ((x if x >= 0 else ~x) >> 9) + 1
            for offset in (-1, 0, 1):
                y = 256*ybin + offset
                for ny in (8447, 8448, 32767):
                    yield x, y, nx, ny
                    yield x, ~y, nx, ny
    for _ in range(3000):
        yield (rng.randint(-2**31, 2**31-1), rng.randint(-2**31, 2**31-1),
               rng.randint(-32768, 32767), rng.randint(-32768, 32767))
        yield (rng.randint(-65536, 65535), rng.randint(-100000, 100000),
               rng.randint(-8192, 8191), rng.randint(8448, 32767))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    args = parser.parse_args()
    symbols = {k: int(v, 16) for k, v in re.findall(
        r'^DEF (\S+) 0x([0-9a-fA-F]+)', args.rom.with_suffix('.noi').read_text(), re.M)}
    fn = symbols['_riding_single_impulse_outward']
    bank = fn >> 16
    code, stack, vector = 0xdfd0, 0xdf80, 0xdfb0
    contact = symbols['_Ct']
    assert symbols['s__HEAP'] < stack - 128
    image = bytearray(args.rom.read_bytes())
    image[0x100:0x102] = b'\x18\xfe'
    emu = PyBoy(BytesIO(image), window='null', cgb=True, sound_emulated=False)
    emu.set_emulation_speed(0)
    emu.tick(200, False)
    mem, regs = emu.memory, emu.register_file
    mem[0xffff] = mem[0xff0f] = 0
    mem[0x3000] = 0
    mem[0x2000] = mem[symbols['__current_bank']] = bank
    mem[code:code+5] = [0xcd, fn & 255, (fn >> 8) & 255, 0x18, 0xfe]
    guard = bytes(range(8))
    mem[stack:stack+8] = guard
    actual_fallbacks = 0

    def fallback(_):
        nonlocal actual_fallbacks
        actual_fallbacks += 1

    dot = symbols['_riding_dotq14_regs']
    emu.hook_register(dot >> 16, dot & 65535, fallback, None)
    count = 0
    try:
        for x, y, nx, ny in vectors():
            impulse = struct.pack('<ii', x, y)
            normal = struct.pack('<hh', nx, ny)
            mem[vector:vector+8], mem[contact:contact+4] = impulse, normal
            regs.D, regs.E = vector >> 8, vector & 255
            regs.PC, regs.SP = code, stack
            emu.tick(1, False)
            positive = x*nx + y*ny >= 8192
            assert bool(regs.F & 0x80) == (not positive), (x, y, nx, ny, positive)
            assert (regs.PC, regs.SP) == (code+3, stack)
            assert bytes(mem[stack:stack+8]) == guard
            assert bytes(mem[vector:vector+8]) == impulse and bytes(mem[contact:contact+4]) == normal
            assert mem[symbols['__current_bank']] == bank
            assert mem[fn & 65535] == mem[bank, fn & 65535]
            count += 1
        assert 0 < actual_fallbacks < count
        print(f'{count} exact impulse sign decisions, including {count-actual_fallbacks} '
              f'dominant products and {actual_fallbacks} complete projections.')
    finally:
        emu.stop(save=False)


if __name__ == '__main__':
    main()
