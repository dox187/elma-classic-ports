"""Verify the cartridge's boot-loaded spring and damper kernels against integer Q24."""
import argparse
from io import BytesIO
from pathlib import Path
import random
import re
import struct

from pyboy import PyBoy


def vectors():
    rng = random.Random(0x4343)
    edges = [-(1<<31), (1<<31)-1, -16777217, -16777216, -8388609, -8388608,
             -65537, -65536, -32769, -257, -256, -255, -1, 0, 1, 254, 255,
             256, 257, 32767, 65535, 65536, 65537, 8388607, 8388608, 16777215, 16777216]
    for i in range(len(edges)):
        yield [edges[(i+n) % len(edges)] for n in (0,3,5,7)]
    for x in range(-260,261):
        yield [x]*4
    for bits in (8,16,18,20,23,31):
        for _ in range(160):
            yield [rng.randrange(-(1<<bits),1<<bits) for _ in range(4)]


def check(rom, gen, alternate):
    symbols = {k:int(v,16) for k,v in re.findall(r'^DEF (\S+) 0x(\w+)',
                                                 rom.with_suffix('.noi').read_text(), re.M)}
    image = bytearray(rom.read_bytes())
    main = symbols['_main']
    image[main:main+2] = bytes([0x18,0xfe])  # stop after the real CRT initialization
    ram = symbols['ss_wram_code']
    source = symbols['ss_force_image']
    size = symbols['ss_force_image_end'] - source
    offset = (source >> 16)*16384 + (source & 16383)
    maps = symbols['ss_wram_banks']
    row = symbols['_riding_spring_product_rows']
    constants = (gen/'riding_constants.h').read_text()
    families = [('spring','C_SPRING_FW',row,row+28), ('damper','C_FRIC_W',row+28,symbols['ss_damping'])]
    scales = [tuple(map(int,re.search(r'q24_'+name+r'\[2\]=\{(\d+),(\d+)\}',constants).groups()))
              for _,name,_,_ in families]
    selectors = [symbols['_q24_index_'+name] for _,name,_,_ in families]
    base = image[symbols['_q24_first_bank_low']]
    expected_banks = bytes((base + (image[sel+phase] >> 1)) & 255 for sel in selectors for phase in (0,1))
    if alternate:
        first, second = selectors
        image[first:first+2],image[second:second+2] = image[second:second+2],image[first:first+2]
        scales.reverse()
        expected_banks = bytes(4)
    emu = PyBoy(BytesIO(image),window='null',sound_emulated=False,cgb=True)
    emu.set_emulation_speed(0)
    mem,reg = emu.memory,emu.register_file
    try:
        for warm in (False, True):
            if warm:
                mem[ram:ram+size] = [0x76]*size
                mem[maps:maps+4] = [0xff]*4
                reg.PC,reg.A,reg.B = 0x100,0x11,0
            emu.tick(200,False)
            assert reg.PC == main
            assert bytes(mem[ram:ram+size]) == image[offset:offset+size]
            assert bytes(mem[maps:maps+4]) == expected_banks
            assert mem[symbols['__current_bank']] == 1
            assert bytes(mem[0x4000:0x4040]) == image[16384:16384+64]
        mem[0xffff] = mem[0xff0f] = 0
        mem[0x2000] = mem[symbols['__current_bank']] = 8
        code, stack = 0xdfc0, 0xdfa0
        count = 0
        for (group,_,dest,inputs),coefficients in zip(families,scales):
            for phase,scale in enumerate(coefficients):
                entry = 'ss_apply_'+group if phase else '_riding_prepare_'+group+'_products'
                addr = symbols[entry] & 65535
                mem[symbols['_riding_subphase']] = phase
                mem[code:code+6] = [0xf3,0xcd,addr&255,addr>>8,0x18,0xfe]
                for paired in (0,1):
                    for xs in vectors():
                        mem[symbols['ss_paired']] = paired
                        mem[dest:dest+28] = [0xa5]*28
                        mem[inputs:inputs+16] = struct.pack('<4i',*xs)
                        reg.PC,reg.SP = code,stack
                        emu.tick(1,False)
                        assert (reg.PC,reg.SP) == (code+4,stack)
                        expected = [((x*scale+(1<<23)) % (1<<56)).to_bytes(7,'little') for x in xs]
                        if paired:
                            expected = [value if i==2 else bytes([0xa5])*7 for i,value in enumerate(expected)]
                        assert bytes(mem[dest:dest+28]) == b''.join(expected), (group,phase,paired,xs)
                        assert mem[symbols['__current_bank']] == 8
                        assert bytes(mem[0x4000:0x4008]) == image[8*16384:8*16384+8]
                        count += 1
    finally:
        emu.stop(save=False)
    print(f'{count} force groups, {count*4} lane slots, two CRT boots, alternate pages = {alternate}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', required=True, type=Path)
    parser.add_argument('--gen', required=True, type=Path)
    args = parser.parse_args()
    for alternate in (False,True):
        check(args.rom,args.gen,alternate)
