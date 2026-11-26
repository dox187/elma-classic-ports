"""Exercise the linked 16-unit tangent bounds at both ends of a terrain segment."""
import argparse
import math
from pathlib import Path
import random
import struct

from check_normal_atlas import Cartridge


def margin(x, y):
    squared = (x*x + y*y) * 16385**2
    radius = math.isqrt(squared)
    if radius*radius < squared:
        radius += 1
    return (radius + 16383) // 16384


def expected(tangent, length, down, up):
    if tangent < 0:
        return 2 if tangent + up < 0 else 0
    if tangent - down < 0:
        return 0
    if tangent - down > length:
        return 3
    return 4 if tangent + up < length else 0


def check(rom):
    cart = Cartridge(rom)
    mem, reg, sym = cart.m, cart.reg, cart.sym
    rng = random.Random(4303)
    seen = [0]*5
    try:
        routine = sym['corner_tight']
        table = sym['corner_max_projection']
        assert routine >> 16 == table >> 16
        bank = routine >> 16
        mem[0x2000] = mem[sym['__current_bank']] = bank
        table_addr = table & 65535
        assert bytes(mem[table_addr:table_addr+256]) == bytes(
            margin(x,y) for x in range(16) for y in range(16))
        mem[cart.code:cart.code+5] = [0xcd, routine & 255, (routine>>8)&255, 0x18, 0xfe]
        record = 0xa600
        mem[sym['contact_loop_seg']:sym['contact_loop_seg']+2] = struct.pack('<H', record)
        for i in range(32768):
            x, y = i & 15, (i >> 4) & 15
            angle = rng.randrange(4096)*math.tau/4096
            nx, ny = round(16384*math.cos(angle)), round(16384*math.sin(angle))
            length = rng.choice([0,1,15,42,80,600,16383])
            p = rng.randrange(-32,33) + (length if i&256 else 0)
            residual = rng.choice([-8192,-8191,-1,0,1,8190,8191])
            mem[record+8:record+14] = struct.pack('<hhH', nx, ny, length | ((i & 3)<<14))
            mem[sym['_riding_contact_qx']] = x
            mem[sym['_riding_contact_qy']] = y
            reg.B, reg.C = (p>>8)&255, p&255
            reg.PC, reg.SP = cart.code, cart.stack
            cart.p.tick(1, False)
            assert (reg.PC,reg.SP,reg.B,reg.C) == (cart.code+3,cart.stack,(p>>8)&255,p&255)
            assert mem[sym['__current_bank']] == bank
            dx, dy = (15-x if nx<0 else x), (15-y if ny<0 else y)
            result = reg.A
            assert result == expected(p,length,margin(dx,dy),margin(15-dx,15-dy))
            if result:
                raw = 16384*p + residual
                for cx in (0,15):
                    for cy in (0,15):
                        shifted = (raw + (cx-x)*nx + (cy-y)*ny + 8192) >> 14
                        if result == 2:
                            assert shifted < 0
                        elif result == 3:
                            assert shifted > length
                        else:
                            assert 0 <= shifted < length
            seen[result] += 1
    finally:
        cart.p.stop(save=False)
    assert all(seen[i] for i in (0,2,3,4))
    print(f'{sum(seen)} linked tile classifications, including {seen[2]} starts, '
          f'{seen[3]} ends and {seen[4]} strict interiors.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    check(parser.parse_args().rom)
