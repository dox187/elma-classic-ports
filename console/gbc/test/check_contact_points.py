"""Check the cartridge's rounded wheel contact coordinates against integer geometry."""
import argparse
from io import BytesIO
from pathlib import Path
import random
import re
import struct

from pyboy import PyBoy


def check(rom):
    symbols = {k: int(v, 16) for k, v in re.findall(
        r'^DEF (\S+) 0x([a-fA-F0-9]+)', rom.with_suffix('.noi').read_text(), re.M)}
    image = bytearray(rom.read_bytes())
    address = symbols['_riding_contact_high']
    start = (address >> 16)*16384 + (address & 16383)
    for length in range(404, 410):
        base = start + (length-404)*1024
        for n in range(-32768, 32768):
            high = n >> 8 & 255
            whole = image[base+high] | image[base+256+high] << 8
            whole = (whole ^ 32768)-32768
            group = image[base+512+((n >> 5) & 511)]
            value = whole + (group & 7) + ((n & 31) > group >> 3)
            assert value == (n*length+8192) >> 14, (n, length)

    image[0x100:0x102] = b'\x18\xfe'
    p = PyBoy(BytesIO(image), window='null', sound_emulated=False, cgb=True)
    p.set_emulation_speed(0)
    rng = random.Random(0x27_0404)
    code, record, stack = 0xc900, 0xc980, 0xcff0
    addr = symbols['_riding_contact_point_lookup']
    reg, mem = p.register_file, p.memory
    try:
        p.tick(240, False)
        mem[code:code+6] = [0xf3, 0xcd, addr & 255, addr >> 8 & 255, 0x18, 0xfe]
        mem[0x2000] = mem[symbols['__current_bank']] = 9
        levels = (-32768, 403, 404, 405, 406, 407, 408, 409, 410, 660, 32767)
        for i in range(6144):
            nx, ny, qx, qy = (rng.randrange(-32768, 32768) for _ in range(4))
            length = levels[i % len(levels)]
            raw = struct.pack('<5h', nx, ny, length, 263, -131)
            mem[record-1:record+11] = b'\x39'+raw+b'\x93'
            mem[symbols['_riding_contact_qx']:symbols['_riding_contact_qx']+2] = struct.pack('<h', qx)
            mem[symbols['_riding_contact_qy']:symbols['_riding_contact_qy']+2] = struct.pack('<h', qy)
            reg.SP, reg.PC, reg.D, reg.E = stack, code, record >> 8, record & 255
            p.tick(1, False)
            hit = 404 <= length <= 409
            assert reg.A == hit and (reg.PC, reg.SP) == (code+4, stack)
            if hit:
                raw = raw[:6]+struct.pack('<2H', (qx-((nx*length+8192)>>14)) & 65535,
                                          (qy-((ny*length+8192)>>14)) & 65535)
            assert bytes(mem[record-1:record+11]) == b'\x39'+raw+b'\x93', (nx, ny, length, qx, qy)
            assert mem[symbols['__current_bank']] == 9
            assert bytes(mem[0x4000:0x4020]) == image[9*16384:9*16384+32]
        # The uncached merge reconstructs both points with the same length.
        # Check every narrow length, including rounding ties and the signed
        # high digit, as well as the saturated fallback for wide lengths.
        pair = symbols['_riding_contact_length_point']
        bank = pair >> 16
        mem[0x2000] = mem[symbols['__current_bank']] = bank
        mem[code:code+6] = [0xf3, 0xcd, pair & 255, pair >> 8 & 255, 0x18, 0xfe]
        cases = 0
        for length in (*range(512), -32768, -32767, -512, -1, 512, 16384, 32767):
            for nx in (-32768, -16384, -8192, -32, -1, 0, 1, 32, 8192, 16384, 32767,
                       rng.randrange(-32768, 32768)):
                ny, qx, qy = (rng.randrange(-32768, 32768) for _ in range(3))
                header = struct.pack('<3h', nx, ny, length)
                mem[record-1:record+11] = b'\x39'+header+b'\xaa'*4+b'\x93'
                for axis, q in (('x', qx), ('y', qy)):
                    pos = symbols['_riding_contact_q'+axis]
                    mem[pos:pos+2] = struct.pack('<h', q)
                reg.SP, reg.PC, reg.B, reg.C = stack, code, record >> 8, record & 255
                p.tick(1, False)
                projected = [max(-32768, min(32767, (n*length+8192) >> 14)) for n in (nx, ny)]
                point = struct.pack('<HH', (qx-projected[0]) & 65535, (qy-projected[1]) & 65535)
                assert bytes(mem[record-1:record+11]) == b'\x39'+header+point+b'\x93', (nx, ny, length)
                assert (reg.PC, reg.SP) == (code+4, stack) and mem[symbols['__current_bank']] == bank
                assert bytes(mem[0x4000:0x4020]) == image[bank*16384:bank*16384+32]
                cases += 1
        print(f'393216 table inputs, 6144 linked point lookups and {cases} uncached point pairs passed')
    finally:
        p.stop(save=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    check(parser.parse_args().rom)
