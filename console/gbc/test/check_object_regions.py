"""Check the linked object broad phase on all cartridge courses and the signed seam."""
import argparse
from pathlib import Path
import random
import struct

from check_normal_atlas import Cartridge


def rom_offset(bank, address):
    return bank * 16384 + (address & 16383)


def level_objects(cart):
    directory = cart.sym['_world_levels']
    offset = rom_offset(directory >> 16, directory)
    for entry in range(offset, offset+54*33, 33):
        bank, address = struct.unpack_from('<HH', cart.image, entry+26)
        start = rom_offset(bank, address)
        count = cart.image[entry+32]
        yield bytes(cart.image[start:start+count*14])
    # Include an empty course between two selections to catch stale membership.
    yield b''
    # Positive and negative signed coordinates, inclusive threshold edges,
    # and stripe reuse when a ninth object joins the course.
    yield b''.join(struct.pack('<HHBiiB', 0, 0, 2, x, y, 0)
                   for x, y in zip((13106, 13107, 13108, 52428, 52429, 52430, -13107,
                                     -52429, -2147483648, 2147483647),
                                    (52430, 52429, 52428, 13108, 13107, 13106, -52429,
                                     -13107, 2147483647, -2147483648)))
    yield b''.join(struct.pack('<HHBiiB', 0, 0, 2, x*65536, y*65536, 0)
                   for x, y in ((32767, -32768), (-32768, 32767), (63, 64)))


def invoke(cart, symbol):
    bank, address = divmod(cart.sym[symbol], 65536)
    cart.m[0x2000] = cart.m[cart.sym['__current_bank']] = bank
    cart.m[cart.code:cart.code+5] = struct.pack('<BHBb', 0xcd, address, 0x18, -2)
    cart.reg.PC, cart.reg.SP = cart.code, cart.stack
    for _ in range(12):
        cart.p.tick(1, False)
        if cart.reg.PC == cart.code+3:
            break
    assert (cart.reg.PC, cart.reg.SP) == (cart.code+3, cart.stack)
    assert cart.m[cart.sym['__current_bank']] == bank
    return cart.reg.A


def check(rom):
    rng = random.Random(0x5e59)
    cart = Cartridge(rom)
    tested = 0
    try:
        pose = cart.sym['_gbc_bike']
        for level, data in enumerate(level_objects(cart)):
            count = len(data)//14
            start = cart.sym['_game_objects']
            if count:
                cart.m[start:start+len(data)] = data
            cart.m[cart.sym['_game_world']+32] = count
            # Course selection may follow a save/menu access. Check that
            # SRAM0 gets selected and that both adjacent scratch bytes survive.
            cart.m[0x4000] = 0
            cart.m[0xa5ff], cart.m[0xa800] = 0x5a, 0xa5
            cart.m[0x4000] = 3
            cart.m[0] = 0
            invoke(cart, '_gbc_build_object_regions')
            assert (cart.m[0xa5ff], cart.m[0xa800]) == (0x5a, 0xa5)
            xs, ys = [0]*256, [0]*256
            objects = [(x, y) for _, _, _, x, y, _ in struct.iter_unpack('<HHBiiB', data)]
            for index, (x, y) in enumerate(objects):
                lane = 1 << (((x >> 16) if count > 8 else index) & 7)
                for coordinate, table in ((x, xs), (y, ys)):
                    for cell in range((coordinate-52429) >> 16, ((coordinate+52429) >> 16)+1):
                        table[cell & 255] |= lane
            assert bytes(cart.m[0xa600:0xa700]) == bytes(xs)
            assert bytes(cart.m[0xa700:0xa800]) == bytes(ys)
            points = [((rng.randrange(65536), rng.randrange(65536)), i%3)
                      for i in range(256)]
            points.extend(((((x>>16)+dx)&65535, ((y>>16)+dy)&65535), slot) for x, y in objects
                          for slot in range(3) for dx in (-1, 0, 1) for dy in (-1, 0, 1))
            for (x, y), slot in points:
                parts = [(rng.randrange(65536), rng.randrange(65536)) for _ in range(3)]
                parts[slot] = x, y
                for pos, (px, py) in zip((12, 22, 42), parts):
                    cart.m[pose+pos:pose+pos+2] = struct.pack('<H', px)
                    cart.m[pose+pos+4:pose+pos+6] = struct.pack('<H', py)
                expected = any(xs[px & 255] & ys[py & 255] for px, py in parts)
                assert bool(invoke(cart, '_gbc_objects_maybe_reachable')) == expected, (level, parts)
                tested += 1
    finally:
        cart.p.stop(save=False)
    print(f'{tested} linked object masks matched over 54 courses, empty reset and signed coordinate wrap.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    check(parser.parse_args().rom)
