"""Compare the cartridge's fused spring/damper impulse and both Q24 remainders."""
import argparse
from io import BytesIO
from pathlib import Path
import random
import re
import struct

from pyboy import PyBoy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--gen', type=Path, required=True)
    args = parser.parse_args()
    symbols = {name: int(value, 16) for name, value in re.findall(
        r'^DEF (\S+) 0x([0-9A-Fa-f]+)', args.rom.with_suffix('.noi').read_text(), re.M)}
    constants = (args.gen/'riding_constants.h').read_text()
    scales = [tuple(map(int, re.search(r'q24_'+name+r'\[2\]=\{(\d+),(\d+)\}', constants).groups()))
              for name in ('C_SPRING_T', 'C_FRIC_T')]
    image = bytearray(args.rom.read_bytes())
    image[0x100:0x102] = bytes((0x18, 0xfe))
    gb = PyBoy(BytesIO(image), window='null', cgb=True, sound_emulated=False)
    gb.set_emulation_speed(0)
    gb.tick(200, False)
    mem, regs = gb.memory, gb.register_file
    code, stack = 0xdfd0, 0xdf80
    assert symbols['s__HEAP']+128 < stack
    mem[0xffff] = mem[0xff0f] = mem[0x3000] = 0
    mem[0x2000] = mem[symbols['__current_bank']] = 8
    entry = symbols['ss_word_torque']
    mem[code:code+5] = [0xcd, entry & 255, entry >> 8, 0x18, 0xfe]
    q = 1 << 24
    edges = (-32768, -32767, -2048, -257, -256, -255, -1, 0, 1, 127, 128,
             255, 256, 257, 2048, 32766, 32767)
    rng = random.Random(0x9638)
    pairs = [(s, d) for s in edges for d in edges]
    pairs.extend((rng.randrange(-32768, 32768), rng.randrange(-32768, 32768)) for _ in range(1200))
    state, fraction = symbols['_riding_suspension_state']+44, symbols['_q24_fraction']
    count = 0
    try:
        for phase in (0, 1):
            mem[symbols['_riding_subphase']] = phase
            for spring, damping in pairs:
                raw = spring*scales[0][phase] + damping*scales[1][phase]
                tie = (raw % q)-q//2
                for previous in (-q//2, q//2-1, tie, max(tie-1,-q//2), min(tie+1,q//2-1)):
                    for name, value in (('ss_coarse', spring), ('ss_tr', damping),
                                        ('_angular_residual', previous)):
                        addr = symbols[name]
                        mem[addr:addr+4] = struct.pack('<i', value)
                    regs.SP, regs.PC = stack, code
                    gb.tick(1, False)
                    impulse = (previous-raw+q//2)//q
                    residual = previous-raw-impulse*q
                    damp_residual = (damping*scales[1][phase]+q//2)%q-q//2
                    assert struct.unpack('<ii', bytes(mem[state:state+8])) == (impulse, residual), (
                        phase, spring, damping, previous)
                    assert bytes(mem[fraction:fraction+5]) == struct.pack('<iB', damp_residual, 0)
                    assert (regs.SP, regs.PC) == (stack, code+3)
                    assert mem[0x4000:0x4008] == mem[8, 0x4000:0x4008]
                    count += 1
    finally:
        gb.stop(save=False)
    print(f'{count} exact signed angular torque pairs, including half-unit ties and their neighbors.')


if __name__ == '__main__':
    main()
