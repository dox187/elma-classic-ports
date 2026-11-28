"""Verify cold signed scenery directory allocation and the larger-pack fallback."""
import argparse
import struct
from pathlib import Path

from check_normal_atlas import Cartridge


def check(rom):
    cart = Cartridge(rom)
    m, sym = cart.m, cart.sym

    def rom_bytes(bank, address, size):
        offset = bank * 16384 + (address & 16383)
        return cart.image[offset:offset+size]

    def call():
        routine = sym['_world_prepare_directory']
        bank = routine >> 16
        m[0x2000] = m[sym['__current_bank']] = bank
        m[cart.code:cart.code+5] = struct.pack('<BHB', 0xcd, routine & 65535, 0x18) + b'\xfe'
        cart.reg.PC, cart.reg.SP = cart.code, cart.stack
        for _ in range(16):
            cart.p.tick(1, False)
            if cart.reg.PC == cart.code + 3:
                break
        assert (cart.reg.PC, cart.reg.SP) == (cart.code+3, cart.stack)
        assert m[sym['__current_bank']] == bank and bytes(m[0x4000:0x4020]) == rom_bytes(bank, 0x4000, 32)

    levels = sym['_world_levels']
    directory = sym['_wheel_terrain_maps']
    poison = bytes((i*47+13) & 255 for i in range(8192))
    try:
        for bank in range(4):
            m[0x4000] = bank
            m[0xa000:0xc000] = poison
        m[0x4000] = 0
        checked = 0
        for index in range(57):
            level = index if index < 54 else 0
            header = bytearray(rom_bytes(levels>>16,(levels & 65535) + 33*level,33))
            wheel_height = rom_bytes(directory>>16,(directory & 65535) + 4*level,4)[1]
            if index == 54:
                header[30] = 10
            elif index == 55:
                header[31] = 16
            elif index == 56:
                wheel_height = 65
            w, h = header[30:32]
            bank, address = struct.unpack_from('<HH', header, 18)
            m[sym['_game_world']:sym['_game_world']+33] = header
            m[sym['_wheel_course_size']+1] = wheel_height
            m[0xa000:0xc000] = poison
            pointers = sym['_raw_chunk_rows']
            m[pointers:pointers+32] = b'\x93' * 32
            expected = bytearray(poison)
            rows = [0x9393] * 16
            if index < 54:
                assert w <= 9 and h <= 15 and wheel_height <= 64
                for y in range(h):
                    row = 0xad40 + (y//5)*256 + (y%5)*36
                    rows[y] = row
                    expected[row-0xa000:row-0xa000+4*w] = rom_bytes(bank,address+4*w*y,4*w)
                    checked += w
            else:
                rows = [address + 4*w*y for y in range(16)]
            call()
            assert bytes(m[0xa000:0xc000]) == expected, index
            assert struct.unpack('<16H',bytes(m[pointers:pointers+32])) == tuple(rows), index
        for bank in (1,2,3):
            m[0x4000] = bank
            assert bytes(m[0xa000:0xc000]) == poison, bank
        print(f'54 cold starts, {checked} exact scenery descriptors and three guarded ROM fallbacks.')
    finally:
        cart.p.stop(save=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    check(parser.parse_args().rom)
