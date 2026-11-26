"""Check linked stationary-pair certificates and complete cached wheel responses."""
import argparse
from collections import Counter
from pathlib import Path
import random
import re
import struct
import sys

from check_ordered_pair import Cartridge
from check_grounded_wheel import FIELDS
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from stopped_pair import NORMALS, COLUMNS, SIDE, Y_MIN, Y_CELLS, cell, normal_corners, normal_region


def checks(rom, reference, constants):
    scales = tuple(map(int, re.search(r'q24_C_OLD\[2\]=\{(-?\d+),(-?\d+)\}',
                                       constants.read_text()).groups()))
    target, old = Cartridge(rom), Cartridge(reference)
    mem, regs = target.mem, target.emu.register_file
    addr = target.symbols['_riding_stopped_pair_proof']
    bank, routine = addr >> 16, addr & 65535
    code, stack, inputs = 0xdfd0, 0xdf80, 0xdf60
    ct = target.symbols['_Ct']
    counts = Counter()

    def direct_setup():
        mem[0x2000] = mem[target.symbols['__current_bank']] = bank
        pointer = target.symbols['_riding_pair_impulse']
        mem[pointer:pointer+2] = struct.pack('<H', inputs)
        mem[code:code+5] = [0xcd, routine & 255, routine >> 8, 0x18, 0xfe]

    def probe(x, y, torque, answer):
        mem[inputs:inputs+12] = struct.pack('<iii', x, y, torque)
        regs.SP, regs.PC = stack, code
        target.emu.tick(1, False)
        assert (regs.SP, regs.PC, regs.A) == (stack, code+3, answer), (
            x, y, torque, answer, regs.A, bytes(mem[ct:ct+20]).hex())
        counts['native boxes'] += 1

    try:
        direct_setup()
        for nx, ny, px, py in NORMALS:
            normal = nx, ny, px, py
            for row in range(Y_CELLS):
                y = Y_MIN + row*SIDE
                for column, (x, width) in enumerate(COLUMNS):
                    if column in (15, 16):
                        continue    # narrower columns cover this interval
                    margin = cell(normal, x, width, y, scales)
                    sign = 2 if margin > 0 else 128
                    limit = (abs(margin) - 1)*32
                    opposed = -1 if margin > 0 else 1
                    for i, (dx, dy) in enumerate(((x,y), (x+width-1,y), (x,y+SIDE-1),
                                                   (x+width-1,y+SIDE-1))):
                        length = (384,447)[i & 1]
                        record = struct.pack('<10h', nx,ny,405,0,0,px,py,length,0,0)
                        mem[ct:ct+20] = record
                        torque = opposed * (limit + (i == 3)) if margin else 0
                        expected = sign if margin and i < 3 else 0
                        probe(dx, dy, torque, expected)
                        if expected:
                            # Independent unreduced products and signed Q24 reference.
                            for cnx, cny, cpx, cpy in normal_corners(normal):
                                assert (dx*cnx+dy*cny+8192)//16384 <= 0
                                assert (dx*cpx+dy*cpy+8192)//16384 <= 0
                                tangent = (-dx*cpy+dy*cpx+8192)//16384
                                for coefficient in scales:
                                    moment = ((tangent*length//64)*coefficient + 8388608)//16777216
                                    assert (moment+torque < 0) == (expected == 128)
                                    assert moment + torque != 0
                                    counts['integer witnesses'] += 1
            matching = bytearray(struct.pack('<10h', nx,ny,405,1,2,px,py,405,-1,-2))
            for byte in (0,1,2,3,10,11,12,13):
                for bit in range(8):
                    mutated = matching.copy()
                    mutated[byte] ^= 1 << bit
                    mem[ct:ct+20] = mutated
                    values = struct.unpack('<10h', mutated)
                    region = normal_region(values[:2] + values[5:7])
                    margin = cell(region,-16384,4096,-24576,scales) if region else 0
                    probe(-14336,-24576,0,2 if margin > 0 else 128 if margin < 0 else 0)
            for length in (-32768,383,448,32767):
                mem[ct:ct+20] = matching
                mem[ct+14:ct+16] = struct.pack('<h', length)
                probe(-14336,-24576,0,0)
            mem[ct:ct+20] = matching
            for coord, bounds in enumerate(((-65537,32768),(-81921,0),(-32769,32768))):
                for bad in (*bounds, -2**31, 2**31-1):
                    impulse = [-14336,-24576,0]
                    impulse[coord] = bad
                    probe(*impulse,0)

        mem[0x2000] = mem[target.symbols['__current_bank']] = target.bank
        center = struct.pack('<II', 0x12340000, 0xfedc0000)
        rng = random.Random(8424)
        # Hook logical dispatch counts on full cache hits. The reference and
        # candidate see the same pairs, including zero and nonzero separations.
        for tag, cart in [('reference',old),('candidate',target)]:
            for method in ('sure','supports'):
                value = cart.symbols['_riding_pair_'+method]
                cart.emu.hook_register(value >> 16, value & 65535,
                                       lambda k: counts.update([k]), f'{tag} {method}')
        normals = [*NORMALS, (-27,16384,16376,497), (402,16379,16207,2401),
                   (134,16383,16384,16), (-9606,13272,394,16379)]
        for i,(nx,ny,px,py) in enumerate(normals):
            for slot,direction in enumerate((1,-1)):
                for x1,y1 in ((0,0),(direction*510,direction*65),(direction*140,direction*300)):
                    records = struct.pack('<10h',nx,ny,406,0,0,px,py,405,x1,y1)
                    for cart in (old,target):
                        cart.fill(slot,center,records)
                    for turn in range(120):
                        fields = {key: rng.randbytes(size) for key,size in FIELDS.items()}
                        b = bytearray(fields['_Bike'])
                        k = 24*(slot+1)
                        b[k:k+8] = center
                        vx,vy = (0,0) if turn % 9 else (
                            rng.randint(-2**31,2**31-1), rng.randint(-2**31,2**31-1))
                        b[k+8:k+16] = struct.pack('<ii',vx,vy)
                        fields['_Bike'] = b
                        contact = bytearray(fields['_riding_audio_contact'])
                        contact[slot] = turn % 3
                        fields['_riding_audio_contact'] = contact
                        phase = turn & 1
                        dx = rng.randrange(-42000,24000)
                        dy = rng.randrange(-75000,-4000)
                        tq = (0,rng.randrange(-5000,5001),-32768,32767,0,0)[turn%6]
                        if turn%29==0:
                            dx,dy,tq = (-2**31,2**31-1,-2**31)
                        inputs32 = dx,dy,tq
                        expected = old.run(fields,phase,slot,inputs32,True)
                        actual = target.run(fields,phase,slot,inputs32,True)
                        assert expected == actual, (i,slot,direction,turn,inputs32)
                        counts['ordered wheel states'] += 1
        assert counts['reference sure'] > counts['candidate sure']
        assert counts['reference supports'] > counts['candidate supports']
    finally:
        target.emu.stop(save=False)
        old.emu.stop(save=False)
    print(dict(counts))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--gen', type=Path, required=True)
    args = parser.parse_args()
    checks(args.rom, args.reference, args.gen/'riding_constants.h')
