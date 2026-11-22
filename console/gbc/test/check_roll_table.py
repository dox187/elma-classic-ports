"""Check both separately rounded rolling impulses on the linked cartridge."""
import argparse
from io import BytesIO
from pathlib import Path
import re
import struct

from pyboy import PyBoy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    args = parser.parse_args()
    names = {s:int(n,16) for s,n in re.findall(
        r'^DEF (\S+) 0x([0-9a-fA-F]+)', args.rom.with_suffix('.noi').read_text(), re.M)}
    fn = names['_riding_roll_table_delta']
    assert fn < 0x4000
    address = names['s__HEAP'] + 48
    torque_address = address + 16
    stack = 0xdfa0
    assert torque_address + 4 < stack-32
    image = bytearray(args.rom.read_bytes())
    image[0x100:0x102] = bytes([0x18, 0xfe])
    emu = PyBoy(BytesIO(image), window='null', cgb=True, sound_emulated=False)
    emu.set_emulation_speed(0)
    emu.tick(190, False)
    mem, regs = emu.memory, emu.register_file
    mem[0xffff] = mem[0xff0f] = 0
    mem[address:address+5] = [0xcd, fn & 255, fn >> 8, 0x18, 0xfe]
    sentinel = bytes(image[9*0x4000+120:9*0x4000+136])
    count = 0
    try:
        for phase,(t,s) in enumerate(((2115702,112030763),(3208767,73867549))):
            mem[names['_riding_subphase']] = phase
            for tq in (0, 2400, -2400, 1, -1, 2399, 2401, -2399, -2401,
                       2400+65536, -2400-65536, 2**31-1, -2**31):
                valid = tq in (0,2400,-2400)
                values = list(range(-3072,3072)) if valid else [-3072,-1,0,1,3071]
                values.extend((-2**31, -65536, -3073, 3072, 65536, 2**31-1))
                mem[torque_address:torque_address+4] = struct.pack('<i', tq)
                mem[0x3000] = 0
                mem[0x2000] = mem[names['__current_bank']] = 9
                for v in values:
                    regs.HL = torque_address
                    regs.D, regs.E = (v >> 24) & 255, (v >> 16) & 255
                    regs.B, regs.C = (v >> 8) & 255, v & 255
                    regs.SP, regs.PC = stack, address
                    emu.tick(1, False)
                    hit = valid and -3072 <= v < 3072
                    assert regs.PC == address+3 and regs.SP == stack
                    assert bool(regs.F & 0x10) == hit, (v,tq,phase)
                    first = (v * t + 2**23) >> 24
                    expected = ((first + tq)*s + 2**23) >> 24 if hit else v
                    actual = (regs.D << 24) | (regs.E << 16) | (regs.B << 8) | regs.C
                    assert actual == expected & 0xffffffff, (v,tq,phase,actual,expected)
                    assert bytes(mem[0x4078:0x4088]) == sentinel and mem[names['__current_bank']] == 9
                    count += 1
        free = names['_riding_free_throttle']
        assert free >> 16 == 9
        mem[address:address+5] = [0xcd, free & 255, free >> 8 & 255, 0x18, 0xfe]
        free_count = 0
        for phase, scale in enumerate((16542280, 10907162)):
            mem[names['_riding_subphase']] = phase
            for torque in (0, 2400, -2400, 2399, 2401, -2399, -2401, 0x10960,
                           -0x10960, 0xff0960, -0xff0960, 2**31-1, -2**31):
                fraction = names['_q24_fraction']
                saturated = names['_q24_saturated']
                mem[fraction:fraction+4] = bytes.fromhex('81428418')
                mem[saturated] = 1
                regs.D, regs.E = (torque >> 24) & 255, (torque >> 16) & 255
                regs.B, regs.C = (torque >> 8) & 255, torque & 255
                regs.SP, regs.PC = stack, address
                emu.tick(1, False)
                hit = abs(torque) == 2400
                assert bool(regs.F & 0x10) == hit and regs.SP == stack and regs.PC == address+3
                impulse = (torque * scale + (1 << 23)) >> 24
                want_fraction = struct.pack('<i', torque*scale-(impulse<<24)) if hit else bytes.fromhex('81428418')
                assert bytes(mem[fraction:fraction+4]) == want_fraction and mem[saturated] == int(not hit)
                got = (regs.D << 24) | (regs.E << 16) | (regs.B << 8) | regs.C
                assert got == (impulse if hit else torque) & 0xffffffff
                free_count += 1
        gas = names['_riding_gas_reaction']
        mem[0x2000] = mem[names['__current_bank']] = gas >> 16
        mem[address:address+5] = [0xcd, gas & 255, gas >> 8 & 255, 0x18, 0xfe]
        # Each row is independently selected from the squared, clamped arm.
        coords = {}
        for x in range(128):
            for y in range(128):
                coords.setdefault(min(255, (x*x+y*y) >> 5), (16*x,16*y))
        assert len(coords) == 256
        base = Path(__file__).resolve().parents[3]
        data = re.sub(r'//[^\n]*', '', (base/'console/nes/src/recip.inc').read_text())
        reciprocals = [int(v) for v in data.strip().rstrip(',').split(',')]
        gas_count = 0
        sentinel = bytes(image[8*0x4000+120:8*0x4000+136])
        for phase, scale in enumerate((212865451, 140352960)):
            mem[names['_riding_subphase']] = phase
            for index,(kx,ky) in coords.items():
                for tq in (2400,-2400,0,2401,-2401,2400+65536,-2400-65536):
                    args = struct.pack('<ihh',tq,kx,ky)
                    mem[stack:stack+8] = args
                    regs.SP, regs.PC = stack, address
                    emu.tick(1, False)
                    hit = index >= 16 and abs(tq) == 2400
                    assert bool(regs.F & 0x10) == hit, (phase,index,tq)
                    assert regs.SP == stack and regs.PC == address+3
                    assert bytes(mem[stack:stack+8]) == args
                    assert bytes(mem[0x4078:0x4088]) == sentinel and mem[names['__current_bank']] == 8
                    if hit:
                        want = (((tq*reciprocals[index]) >> 8)*scale + 2**23) >> 24
                        got = (regs.B<<24) | (regs.C<<16) | (regs.D<<8) | regs.E
                        assert got == want & 0xffffffff, (phase,index,tq,got,want)
                    gas_count += 1
    finally:
        emu.stop(save=False)
    print(f'{count} native rolling cases, {gas_count} throttle reaction and {free_count} free-wheel throttle cases passed')


if __name__ == '__main__':
    main()
