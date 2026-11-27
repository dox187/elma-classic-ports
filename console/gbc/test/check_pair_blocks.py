"""Compare every linked four-by-four pair block with the unpatched terrain solver."""
import argparse
from pathlib import Path
import struct

from check_corner_results import WheelQueries


def read_patch(cart, wheel):
    # Run the same bank trampoline as the wheel resolver from unbanked WRAM.
    routine = cart.sym['_riding_patch_lookup']
    call = cart.sym['___sdcc_bcall_ehl']
    code = bytes((0x1e, routine >> 16, 0x21, routine & 255, routine >> 8 & 255,
                  0xcd, call & 255, call >> 8, 0x18, 0xfe))
    cart.m[cart.code:cart.code+len(code)] = code
    cart.reg.PC, cart.reg.SP = cart.code, cart.stack
    cart.reg.B, cart.reg.C = wheel >> 8, wheel & 255
    cart.p.tick(1, False)
    assert (cart.reg.PC, cart.reg.SP) == (cart.code+8, cart.stack)
    assert cart.m[cart.sym['__current_bank']] == 9
    assert bytes(cart.m[0x4000:0x4020]) == cart.signature
    return cart.reg.A


def check(rom, reference):
    target, oracle = WheelQueries(rom), WheelQueries(reference)
    try:
        oracle.invoke('_physics_collision_select', a=37)
        target.invoke('_physics_collision_select', a=37)
        def offset(sym):
            addr = target.sym[sym]
            return (addr >> 16)*16384 + (addr & 16383)
        directory = target.image[offset('patch_blocks'):offset('patch_blocks_end')]
        covered = set()
        ring = set()
        for key in range(0, len(directory), 6):
            strip, low_x, low_y = directory[key:key+3]
            x = ((target.sym['patch_min_x']+(strip & 15)) << 8) | low_x
            y = ((target.sym['patch_min_y']+(strip >> 4)) << 8) | low_y
            covered.update((x+dx, y+dy) for dy in range(4) for dx in range(4))
            ring.update((x+dx, y+dy) for dy in range(-1,5) for dx in range(-1,5))
            ring.update(((x+0x10000, y), (x, y+0x10000), (x-0x10000, y)))
        assert covered and len(covered)*6 == len(directory)*16
        checks = warm = 0
        for x, y in sorted(covered | ring):
            pair = None
            if (x, y) in covered:
                assert oracle.full_query(x, y) == 2
                pair = oracle.read('_Ct', 20)
            for slot, fraction in ((0, 0), (1, 255)):
                position = struct.pack('<ii', x*256+fraction, y*256+255-fraction)
                poison = bytes(((i+13)*31) & 255 for i in range(20))
                wheel = target.prepare(slot, position, poison)
                cache = target.sym['_wheel_surface_cache'] + 29*slot
                saved = bytes([61])*29
                target.m[cache:cache+29] = saved
                before = target.fallback_state()
                result = read_patch(target, wheel)
                if pair is None:
                    assert result == 255 and target.fallback_state() == before
                    assert target.read('_Ct', 20) == poison
                else:
                    assert result == 2 and target.read('_Ct', 20) == pair, (x, y, slot)
                    upper = position[2:4] + position[6:]
                    assert bytes(target.m[cache:cache+5]) == upper + bytes([0])
                    # A warm exact key defers to the prepared pair. A one-bit
                    # fractional or upper-word difference must still read this block.
                    seed = upper + bytes([9]) + position[:2] + position[4:6] + pair
                    for byte in (None, 0, 2, 5, 7):
                        key = bytearray(seed)
                        if byte is not None:
                            key[byte] ^= 1
                        target.m[cache:cache+29] = key
                        target.m[target.sym['_Ct']:target.sym['_Ct']+20] = poison
                        before = target.fallback_state()
                        result = read_patch(target, wheel)
                        if byte is None:
                            assert result == 255 and target.fallback_state() == before
                            assert target.read('_Ct', 20) == poison
                        else:
                            assert result == 2 and target.read('_Ct', 20) == pair
                        warm += 1
                checks += 1
        print(f'{len(covered)} exact pair centers, {checks} wheel/edge/alias probes, '
              f'{warm} prepared-pair and near-key checks passed')
    finally:
        for cart in (target, oracle):
            cart.p.stop(save=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    args = parser.parse_args()
    check(args.rom, args.reference)
