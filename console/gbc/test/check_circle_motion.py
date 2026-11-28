"""Check the linked body and wheel translation entries against exact integer arithmetic."""
import argparse
from pathlib import Path
import random
import struct
from check_normal_atlas import Cartridge

UNIT = 1 << 24
HALF = UNIT // 2
MASK = (1 << 32) - 1


def signed_fraction(value):
    return (value + HALF) % UNIT - HALF


def velocities(rng):
    edges = {-(1 << 31), (1 << 31) - 1, -1, 0, 1}
    for bit in range(32):
        for sign in (-1, 1):
            for offset in (-1, 0, 1):
                value = sign * (1 << bit) + offset
                if -(1 << 31) <= value < 1 << 31:
                    edges.add(value)
    samples = sorted(edges) * 18
    samples.extend(rng.randrange(-(1 << 31), 1 << 31) for _ in range(1800))
    samples.extend(rng.randrange(-(1 << 19), 1 << 19) for _ in range(2400))
    rng.shuffle(samples)
    return samples


def check(cart):
    rng = random.Random(32867)
    values = velocities(rng)
    memory = cart.m
    axes = 0
    for phase, scale in enumerate((1 << 20, 691380)):
        for i, vx in enumerate(values):
            slot = i % 3
            symbol = ('_motion_body', '_motion_wheel1', '_motion_wheel2')[slot]
            entry = cart.sym[symbol]
            memory[cart.code:cart.code + 5] = struct.pack('<BHBb', 0xcd, entry, 0x18, -2)
            body = cart.sym['_Bike'] + 24 * slot
            residual = cart.sym['_move_residual'] + 8 * slot
            velocity = (vx, values[-i - 1])
            position = [rng.getrandbits(32) for _ in velocity]
            products = [v * scale for v in velocity]
            if i % 3 == 0:
                fractions = [signed_fraction(-v - HALF + rng.randrange(-2, 3)) for v in products]
            else:
                fractions = [rng.randrange(-HALF, HALF) for _ in products]
            if i % 7 == 0:
                position = [0, 0xffff]
            if i % 11 == 0:
                position = [0xfffffffe, 0xfeed0000]
            memory[body:body + 16] = struct.pack('<IIii', *position, *velocity)
            memory[residual:residual + 8] = struct.pack('<ii', *fractions)
            memory[cart.sym['_riding_subphase']] = phase
            scratch = cart.sym['_q24_fraction']
            seed = bytes(rng.getrandbits(8) for _ in range(5))
            memory[scratch:scratch + 5] = seed
            cart.reg.PC, cart.reg.SP = cart.code, cart.stack
            cart.p.tick(1, False)

            expected_pos, expected_res = [], []
            for pos, product, fraction in zip(position, products, fractions):
                displacement = (product + fraction + HALF) // UNIT
                expected_pos.append((pos + displacement) & MASK)
                expected_res.append(product + fraction - UNIT * displacement)
            state = bytes(memory[body:body + 16])
            assert state == struct.pack('<IIii', *expected_pos, *velocity), (phase, slot, velocity)
            assert bytes(memory[residual:residual + 8]) == struct.pack('<ii', *expected_res)
            expected_scratch = struct.pack('<iB', signed_fraction(products[1]), 0) if phase else seed
            assert bytes(memory[scratch:scratch + 5]) == expected_scratch
            assert (cart.reg.PC, cart.reg.SP) == (cart.code + 3, cart.stack)
            assert memory[cart.sym['__current_bank']] == 9
            assert bytes(memory[0x4000:0x4020]) == cart.signature
            axes += 2
    return axes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', required=True, type=Path)
    args = parser.parse_args()
    cart = Cartridge(args.rom)
    try:
        print(f'{check(cart)} signed32 axes matched, including residual ties, word crossings, Q24 scratch and bank restoration.')
    finally:
        cart.p.stop(save=False)


if __name__ == '__main__':
    main()
