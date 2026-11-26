"""Compare the linked wheel contact filter with the exact subpixel projection."""
import argparse
from io import BytesIO
from pathlib import Path
import re
import struct

from pyboy import PyBoy


def cases():
    for nx in range(-65, 2):
        boundary = 8192 // max(1, abs(nx))
        for fx in sorted({0, 128, 255, *(x for x in range(boundary-1, boundary+3) if 0 <= x <= 255)}):
            for fy in (0, 1, 121, 122, 123, 124, 125, 254, 255):
                for length in (-32768, 403, 404, 405, 408, 409, 410, 32767):
                    yield nx, 16384, fx, fy, length
    # Both signs and both sides of the high-byte sum certificate. Extreme
    # fractions attain the minimum and maximum of each affine projection.
    for xh in (-17, -16, -15, 31, 32, 49, 50, 51, 63, 64, 65):
        for yh in {-17, -16, 64, 65, 99-xh, 100-xh, 101-xh}:
            for low in (0, 255):
                nx, ny = 256*xh+low, 256*yh+low
                if not -32768 <= ny <= 32767:
                    continue
                for fx, fy in ((0, 255), (255, 0), (255, 255)):
                    for length in (404, 405, 407, 408, 409):
                        yield nx, ny, fx, fy, length
    for ny in (0, -16384, 16128, 16383, 16385, 32767):
        for nx in (-32768, -257, -256, -128, -61, -1, 0, 63, 32767):
            for length in (402, 404, 405, 409, 412):
                yield nx, ny, 251, 211, length


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    rom = parser.parse_args().rom
    sy = {k:int(v,16) for k,v in re.findall(r'^DEF (\S+) 0x(\w+)',rom.with_suffix('.noi').read_text(),re.M)}
    image = bytearray(rom.read_bytes())
    image[0x100:0x102] = bytes((0x18,0xfe))
    emu = PyBoy(BytesIO(image),window='null',sound_emulated=False,cgb=True)
    emu.set_emulation_speed(0)
    try:
        emu.tick(200,False)
        mem, reg = emu.memory, emu.register_file
        ptr, wheel, stack, code = 0xde00,0xde20,0xdf00,0xdfe0
        target = sy['_riding_contact_push']
        bank = target >> 16
        mem[0xffff] = mem[0xff0f] = mem[0x3000] = 0
        mem[sy['__current_bank']] = mem[0x2000] = bank
        mem[code:code+5] = bytes((0xcd,target&255,target>>8&255,0x18,0xfe))
        for count, case in enumerate(cases(),1):
            nx,ny,fx,fy,length = case
            mem[ptr:ptr+6] = struct.pack('<hhh',nx,ny,length)
            mem[wheel],mem[wheel+4] = fx,fy
            reg.B,reg.C,reg.D,reg.E = ptr>>8,ptr&255,wheel>>8,wheel&255
            reg.SP,reg.PC = stack,code
            emu.tick(1,False)
            push = 103547 - 256*length - ((nx*fx+ny*fy+8192)//16384)
            expected = 2 if push>0 else int(push>-1311)
            assert reg.A==expected and (reg.PC,reg.SP)==(code+3,stack),case
            if push>0:
                assert (reg.D<<24 | reg.E<<16 | reg.B<<8 | reg.C)==push,case
            assert mem[0x4000]==mem[bank,0x4000] and mem[sy['__current_bank']]==bank
        print(f'{count} native contact classifications and positive impulses matched.')
    finally:
        emu.stop(save=False)


if __name__=='__main__':
    main()
