"""Check torque selection, coefficients and arm projections on the linked cart."""
import argparse
from io import BytesIO
from pathlib import Path
import random
import re
import struct

from pyboy import PyBoy


def wheel_reaction_cases():
    # Cover every reciprocal index, including both sides of the close-distance cutoff.
    arms = {}
    for x in range(128):
        for y in range(128):
            index = min(255, (x*x + y*y) >> 5)
            arms.setdefault(index, (x*16, y*16))
    assert len(arms) == 256
    rng = random.Random(456)
    for phase in range(2):
        for x, y in arms.values():
            for tq in (2400, -2400, 2401, -2399, 32767, -32768, 32768, -32769,
                       0x1000000, -0x1000000, 2**31-1, -2**31):
                yield phase, tq, x, y
        for _ in range(400):
            yield phase, rng.randint(-2**31, 2**31-1), rng.randint(-32768, 32767), rng.randint(-32768, 32767)


def reaction_input(torque, x, y):
    index = min(255, (((x >> 4)**2 + (y >> 4)**2) >> 5))
    if index < 16 and (x or y):
        magnitude = (abs(torque) << 22) // (x*x + y*y)
        raw = -magnitude if torque < 0 else magnitude
    else:
        # The packed reciprocal rounds 2^17 / (max(index,16) + 1/2).
        denominator = 2*max(index, 16) + 1
        reciprocal = ((1 << 18) + denominator//2) // denominator
        raw = (torque*reciprocal) >> 8
    return max(-2**31, min(2**31-1, raw))


def check(rom, gen):
    symbols = {s: int(n, 16) for s, n in re.findall(
        r'^DEF (\S+) 0x([0-9a-fA-F]+)', rom.with_suffix('.noi').read_text(), re.M)}
    constants = (gen / 'riding_constants.h').read_text()
    scales = re.search(r'q24_C_REACT\[2\]=\{(-?\d+),(-?\d+)\}', constants)
    image = bytearray(rom.read_bytes())
    image[0x100:0x102] = bytes((0x18, 0xfe))
    emu = PyBoy(BytesIO(image), window='null', cgb=True, sound_emulated=False)
    emu.set_emulation_speed(0)
    emu.tick(190, False)
    mem, regs = emu.memory, emu.register_file
    mem[0xffff] = mem[0xff0f] = 0
    code, out, stack = 0xd900, 0xd000, 0xdfb0
    entry = symbols['_riding_reaction_coefficient']
    call = [0xcd, entry & 255, entry >> 8]
    mem[0x3000] = 0
    mem[0x2000] = mem[symbols['__current_bank']] = 8
    sentinel = bytes(image[8*16384+64:8*16384+96])

    def check_return(pc):
        assert regs.PC == pc and regs.SP == stack
        assert mem[symbols['__current_bank']] == 8 and bytes(mem[0x4040:0x4060]) == sentinel

    def result(value, scale):
        return max(-2**31, min(2**31-1, (value*scale + 2**23) >> 24))

    rng = random.Random(0x472)
    wide = [-2**31, -2**31+1, -0x1000001, -65536, -65535, -32769,
            32768, 65535, 65536, 0x1000000, 2**31-2, 2**31-1]
    for _ in range(512):
        magnitude = rng.randint(32769, 2**31-1)
        wide.append(magnitude if rng.randrange(2) else -magnitude)

    try:
        for phase, scale in enumerate(map(int, scales.groups())):
            mem[symbols['_riding_subphase']] = phase
            # BC walks one page of signed inputs. HL walks the WRAM result buffer.
            body = [0xc5, 0xe5,                      # push bc, hl
                    0x50, 0x59,                      # de = bc
                    0x78, 0x87, 0x9f, 0x67, 0x6f,    # hl = sign extension of b
                    *call, 0xe1,                     # coefficient -> bc:de, pop hl
                    0x7b, 0x22, 0x7a, 0x22,          # emit low word
                    0x79, 0x22, 0x78, 0x22,          # emit high word
                    0xc1, 0x03, 0x79, 0xb7]          # pop bc, inc bc, test c
            body += [0x20, (-len(body)-2) & 255]     # jr nz, loop
            end = code + len(body)
            mem[code:end+2] = body + [0x18, 0xfe]
            for high in range(-128, 128):
                regs.B, regs.C = high & 255, 0
                regs.HL, regs.PC, regs.SP = out, code, stack
                emu.tick(5, False)
                check_return(end)
                expected = [result(high*256+low, scale) for low in range(256)]
                assert bytes(mem[out:out+1024]) == struct.pack('<256i', *expected), (phase, high)

            mem[code:code+5] = call + [0x18, 0xfe]
            for v in wide:
                regs.HL, regs.D, regs.E = (v >> 16) & 65535, (v >> 8) & 255, v & 255
                regs.PC, regs.SP = code, stack
                emu.tick(1, False)
                check_return(code+3)
                got = (regs.B << 24) | (regs.C << 16) | (regs.D << 8) | regs.E
                assert got == result(v, scale) & 0xffffffff, (phase, v, got)

        if 'ss_prepare_reaction' in symbols:
            prepare = symbols['ss_prepare_reaction'] & 65535
            project = symbols['ss_reaction_q14'] & 65535
            # Exercise both signed high-word corrections, their limits and the wide fallback.
            torques = {h*65536 + low for h in range(-4, 5)
                       for low in (-32768, -32767, -8192, -1, 0, 1, 8192, 32767)}
            torques.update((-2**31, 2**31-1))
            for arm in (-32768, -2049, -2048, -2047, -1, 0, 1, 2047, 2048, 32767):
                body = [0xcd, prepare & 255, prepare >> 8, 0x01, arm & 255, (arm >> 8) & 255,
                        0xcd, project & 255, project >> 8]
                end = code + len(body)
                mem[code:end+2] = body + [0x18, 0xfe]
                for torque in torques:
                    regs.B, regs.C = (torque >> 24) & 255, (torque >> 16) & 255
                    regs.D, regs.E = (torque >> 8) & 255, torque & 255
                    regs.PC, regs.SP = code, stack
                    emu.tick(1, False)
                    check_return(end)
                    got = (regs.HL << 16) | (regs.D << 8) | regs.E
                    expected = max(-2**31, min(2**31-1, (torque*arm + 8192) >> 14))
                    assert got == expected & 0xffffffff, (torque, arm, got, expected)
            print(f'{len(torques)*10} signed reaction-arm projections matched')

        if 'ss_wheel_reaction_value' in symbols:
            entry = symbols['ss_wheel_reaction_value'] & 65535
            coarse = symbols['ss_coarse']
            phase_scales = list(map(int, scales.groups()))
            mem[code:code+5] = [0xcd, entry & 255, entry >> 8, 0x18, 0xfe]
            for count, (phase, torque, x, y) in enumerate(wheel_reaction_cases(), 1):
                arms = struct.pack('<hh', x, y)
                tq = struct.pack('<i', torque)
                mem[coarse:coarse+4], mem[out:out+4] = arms, tq
                mem[symbols['_riding_subphase']] = phase
                regs.B, regs.C = (y >> 8) & 255, y & 255
                regs.D, regs.E = (x >> 8) & 255, x & 255
                regs.HL, regs.PC, regs.SP = out, code, stack
                emu.tick(1, False)
                check_return(code+3)
                actual = (regs.B << 24) | (regs.C << 16) | (regs.D << 8) | regs.E
                expected = result(reaction_input(torque, x, y), phase_scales[phase])
                assert actual == expected & 0xffffffff, (phase, torque, x, y, actual, expected)
                assert bytes(mem[coarse:coarse+4]) == arms and bytes(mem[out:out+4]) == tq
            print(f'{count} wheel reactions matched across both phases')
    finally:
        emu.stop(save=False)
    print(f'131072 signed16 and {2*len(wide)} signed32 reaction products matched')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--gen', type=Path, required=True)
    args = parser.parse_args()
    check(args.rom, args.gen)
