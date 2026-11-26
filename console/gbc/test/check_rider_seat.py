"""Exercise the shipped banked seat/ellipse lookup against the original fixed-point constraints."""
import argparse
from collections import Counter
from io import BytesIO
import math
from pathlib import Path
import random
import re
import struct

from pyboy import PyBoy


def constants(gen):
    header = (gen / 'riding_constants.h').read_text()
    c = {name: int(value) for name, value in re.findall(r'^#define (\w+) (-?\d+)$', header, re.M)}
    c['bucket'] = [int(v) for v in re.search(
        r'^#define RIDING_ELLIPSE_INSIDE_Y_VALUES ([0-9,]+)$', header, re.M)[1].split(',')]
    for name in ('SEAT_NX', 'SEAT_NY', 'ELLIPSE'):
        c[name] = tuple(map(int, re.search(rf'q24_C_{name}\[2\]=\{{([0-9,]+)\}}', header)[1].split(',')))
    return c


def round_product(n, multiplier):
    return max(-32768, min(32767, (n * multiplier + (1 << 23)) >> 24))


def signed16(n):
    return ((n + 32768) & 65535) - 32768


def oracle(x, y, c, phase):
    tx, ty = x, y
    moved = False
    if (not c['RIDING_SEAT_FAST_ENABLED'] or x > c['RIDING_SEAT_FAST_X'] or
            y < c['RIDING_SEAT_FAST_Y'] or y > c['RIDER_TOP']):
        under = signed16(round_product(y - c['SEAT_Y'], c['SEAT_NY'][phase]) - round_product(
            x - c['SEAT_X'], c['SEAT_NX'][phase]))
        if under < 0:
            tx = signed16(tx + round_product(under, c['SEAT_NX'][phase]))
            ty = signed16(ty - round_product(under, c['SEAT_NY'][phase]))
            moved = True
    x = max(c['RIDER_LEFT'], min(c['RIDER_RIGHT'], tx))
    y = min(c['RIDER_TOP'], ty)
    moved |= (x, y) != (tx, ty)
    if x > 0 and y > 0 and y > c['bucket'][x >> c['RIDING_ELLIPSE_BUCKET_SHIFT']]:
        xs = round_product(x, c['ELLIPSE'][phase])
        square = xs * xs + y * y
        if square > c['RIDER_TOP'] ** 2:
            length = math.isqrt(square)
            return 2, x * c['RIDER_TOP'] // length, y * c['RIDER_TOP'] // length
    return (2 if moved else 1), x, y


def inputs(c):
    points = set()
    top = c['RIDER_TOP']
    for x in range(1, c['RIDER_RIGHT'] + 1):
        xs = round_product(x, c['ELLIPSE'][0])
        true_edge = math.isqrt(max(0, top * top - xs * xs))
        bucket = c['bucket'][x >> c['RIDING_ELLIPSE_BUCKET_SHIFT']]
        for edge in (true_edge, bucket, max(true_edge, bucket) + 16, top):
            points.update((x, y) for y in range(edge-1, edge+2))
    for x in range(-512, 512):
        projected = round_product(x - c['SEAT_X'], c['SEAT_NX'][0])
        # Probe on both sides of the separately rounded seat line.
        y = c['SEAT_Y'] + (projected << 24) // c['SEAT_NY'][0]
        points.update((x, yy) for yy in range(y-2, y+3))
    for x in (-32768, -513, -512, -511, -1, 0, 265, 266, 267, 510, 511, 512, 32767):
        points.update((x, y) for y in (-32768, -1, 0, 1, 491, 492, 493, 766, 767, 768, 32767))
    rng = random.Random(0x96ea7)
    points.update((rng.randrange(-512, 512), rng.randrange(768)) for _ in range(2000))
    # Cover narrow/wrapped coordinates, including underflow of the original
    # signed16 seat distance and the signed16 y position after correction.
    edges = (-32768, -32767, -32256, -16384, -513, -512, -257, -256,
             -1, 0, 1, 255, 256, 511, 512, 16384, 32255, 32766, 32767)
    points.update((x, y) for x in edges for y in edges)
    points.update((rng.randrange(-32768, 32768), rng.randrange(-32768, 32768))
                  for _ in range(2000))
    return sorted(points)


def check(rom, gen):
    c = constants(gen)
    symbols = {name: int(v, 16) for name, v in re.findall(
        r'^DEF (\S+) 0x([0-9A-Fa-f]+)$', rom.with_suffix('.noi').read_text(), re.M)}
    seat = symbols['_riding_seat_lookup']
    # Use the game's banked ABI and its stack argument. Return to the caller in bank 8.
    start = symbols['_main']
    image = bytearray(rom.read_bytes())
    call = (bytes([0x1e, seat >> 16, 0x21]) + struct.pack('<H', seat & 65535) +
            bytes([0xcd]) + struct.pack('<H', symbols['___sdcc_bcall_ehl']) + bytes([0x18, 0xfe]))
    image[start:start+3+len(call)] = bytes([0xf3, 0x18, 0xfe]) + call
    p = PyBoy(BytesIO(image), window='null', cgb=True, sound_emulated=False)
    p.set_emulation_speed(0)
    p.tick(200, False)
    regs, mem = p.register_file, p.memory
    assert regs.PC == start + 1
    out, sp = symbols['s__HEAP'] + 16, 0xdfa0
    assert out + 16 < sp - 64
    mem[0x2000] = mem[symbols['__current_bank']] = 8
    mem[sp:sp+2] = struct.pack('<H', out)
    counts = Counter()
    try:
        for i, (x, y) in enumerate(inputs(c)):
            for turned in (0, 1):
                phase = (i + turned) & 1
                raw_x = ((-x + 32768) & 65535) - 32768 if turned else x
                before = struct.pack('<hh', raw_x, y)
                mem[out-1:out+5] = b'\xa5' + before + b'\x5a'
                mem[symbols['_Bike']+96] = turned
                mem[symbols['_riding_subphase']] = phase
                regs.SP, regs.PC = sp, start + 3
                p.tick(1, False)
                assert regs.PC == start + 11 and regs.SP == sp and mem[symbols['__current_bank']] == 8
                assert bytes(mem[sp:sp+2]) == struct.pack('<H', out)
                result = regs.A
                after = bytes(mem[out-1:out+5])
                status, xx, yy = oracle(x, y, c, phase)
                assert result == status, (x, y, turned, phase, result, status)
                expected = struct.pack('<hh', xx, yy) if result == 2 else before
                assert after == b'\xa5' + expected + b'\x5a', (x, y, turned, phase, result, after, expected)
                counts[result] += 1
    finally:
        p.stop(save=False)
    assert min(counts[n] for n in (1, 2)) > 100
    print(f'{sum(counts.values())} native seat cases passed ({counts[0]} fallbacks, '
          f'{counts[1]} unchanged, {counts[2]} corrected)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--gen', type=Path, required=True)
    args = parser.parse_args()
    check(args.rom, args.gen)
