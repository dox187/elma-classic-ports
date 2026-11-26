"""Check the linked shallow projections and affine wheel cache against integer geometry."""
import argparse
from io import BytesIO
from pathlib import Path
import random
import re
import struct

from pyboy import PyBoy


def signed16(value):
    return ((value + 32768) & 65535) - 32768


def projected(x, y, nx, ny):
    raw = (x*nx + y*ny + 8192 + (1 << 31)) % (1 << 32) - (1 << 31)
    return min(32767, max(-32768, raw >> 14))


def check_thresholds(rom):
    for coefficient in range(2, 128):
        row = 34*16384 + 128*coefficient
        for x in range(8192):
            start = row + 2*(x >> 7)
            value, threshold = rom[start:start+2]
            offset = x & 127
            rounded = (value & 127) + (offset >= threshold)
            assert rounded == (x*coefficient + 8192) >> 14
            negative = -rounded + bool(value & 128 and offset == 0)
            assert negative == (8192 - x*coefficient) >> 14


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    rom = parser.parse_args().rom
    symbols = {name: int(value, 16) for name, value in re.findall(
        r'^DEF (\S+) 0x([0-9A-Fa-f]+)', rom.with_suffix('.noi').read_text(), re.M)}
    image = bytearray(rom.read_bytes())
    check_thresholds(image)
    image[0x100:0x102] = bytes((0x18, 0xfe))
    emulator = PyBoy(BytesIO(image), window='null', sound_emulated=False, cgb=True)
    emulator.set_emulation_speed(0)
    rng = random.Random(0x9626)
    code, stack = 0xc900, 0xcfd0
    memory, registers = emulator.memory, emulator.register_file

    def call(symbol, bank, x, y):
        address = symbols[symbol] & 65535
        memory[code:code+6] = (0xf3, 0xcd, address & 255, address >> 8, 0x18, 0xfe)
        memory[0x2000] = memory[symbols['__current_bank']] = bank
        registers.PC, registers.SP = code, stack
        registers.D, registers.E = x >> 8 & 255, x & 255
        registers.B, registers.C = y >> 8 & 255, y & 255
        emulator.tick(1, False)
        assert registers.PC == code+4
        assert memory[symbols['__current_bank']] == bank
        assert bytes(memory[0x4000:0x4008]) == image[bank*16384:bank*16384+8]

    try:
        emulator.tick(240, False)
        memory[0xffff] = memory[0xff0f] = 0
        coordinates = (-32768, -8192, -7937, -7936, -4096, -128, 0, 128, 4096,
                       7936, 8191, 8192, 32767)
        coefficients = (-32768, -256, -255, -129, -128, -127, -64, -2, -1, 0,
                        1, 2, 64, 127, 128, 255, 256, 32767)
        dots = 0
        for nx in coefficients:
            for ny in (-16384, 16384, -16383, 16000):
                for x in coordinates:
                    y = rng.choice(coordinates)
                    memory[stack:stack+6] = struct.pack('<hhH', nx, ny, 0xd935)
                    call('_riding_terrain_dotq14', 7 if dots & 1 else 9, x, y)
                    assert registers.SP == stack+4 and memory[stack+4] == 0x35
                    assert signed16(registers.B*256+registers.C) == projected(x, y, nx, ny)
                    dots += 1

        cache = symbols['_wheel_surface_cache']
        contact = symbols['_Ct']
        # Use scratch for the circle, away from both the call stack and game globals.
        wheel = 0xc948 if (symbols['_Bike']+48) & 255 == 0x40 else 0xc940
        offsets = (0, 1, 63, 64, 127, 128, 191, 192, 254, 255)
        normals = ((61, -16384), (-61, 16384), (0, -16384), (16384, 0),
                   (63, 16383), (-11585, 11585), (16382, 246), (32767, -32768))
        modes = set()
        plane_queries = 0
        for i in range(1024):
            nx, ny = normals[i % len(normals)] if i % 3 else (
                rng.randint(-32768, 32767), rng.randint(-32768, 32767))
            bx, by = rng.randint(-700, 700), rng.randint(-700, 700)
            if i % 5 == 0:
                bx = rng.choice((-32768, -32600, 32512, 32650, 32767))
            if i % 7 == 0:
                by = rng.choice((-32768, -32600, 32512, 32650, 32767))
            clipped = i & 1
            bounds = (64, 191, 0, 127) if clipped else (0, 255, 0, 255)
            memory[cache:cache+29] = struct.pack('<HHB4h4B', 0x32, 0x51,
                                                  2+clipped, bx, by, nx, ny, *bounds) + bytes(12)
            for step in range(8):
                x, y = (rng.choice(offsets), rng.choice(offsets)) if step else (80, 50)
                memory[wheel:wheel+8] = struct.pack('<BBHBBH', 39, x, 0x32, 176, y, 0x51)
                memory[contact:contact+20] = bytes([0x5a])*20
                call('_riding_cert_hit', 9, wheel, 0)
                distance = projected(signed16(bx+x), signed16(by+y), nx, ny)
                accepted = abs(distance) < 410 and bounds[0] <= x <= bounds[1] and bounds[2] <= y <= bounds[3]
                assert registers.SP == stack and registers.A == accepted, (i, x, y, distance)
                expected = bytearray([0x5a])*20
                if accepted:
                    sign = -1 if distance < 0 else 1
                    struct.pack_into('<3h', expected, 0, signed16(sign*nx), signed16(sign*ny), abs(distance))
                assert bytes(memory[contact:contact+20]) == expected
                modes.add(memory[cache+4])
                plane_queries += 1
        assert modes == {2, 3, 10, 11}
    finally:
        emulator.stop(save=False)
    print(f'{2*8192*126} signed threshold values, {dots} native dots and {plane_queries} plane queries passed')


if __name__ == '__main__':
    main()
