"""Validate the linked projection tables, native signed48 products and caller state."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import random
import re
import sys

from pyboy import PyBoy

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'tools'))
from projection_tables import BANKS, COEFFICIENTS, row_page, validate_layout


def verify_table_bytes(image):
    prefix = image[BANKS[0] << 14:(BANKS[0] << 14) + 256]
    table = BANKS[0] << 14
    tags = image[table + 256:table + 512]
    banks = image[table + 512:table + 768]
    pages = image[table + 768:table + 1024]
    accepted = {}
    for y in range(-32768, 32768):
        high = (y >> 8) & 255
        slot = (((high >> 2) | (high << 6)) - y) & 255
        if banks[slot] and tags[slot] == high:
            accepted[y] = (banks[slot] + 256, pages[slot])
    expected = {y: (BANKS[i // 10], row_page(i)) for i, y in enumerate(COEFFICIENTS)}
    assert expected == accepted
    for bank in BANKS:
        assert image[bank << 14:(bank << 14) + 256] == prefix, bank
    for y, (bank, page) in accepted.items():
        start = (bank << 14) + (page - 0x40) * 256
        planes = image[start:start + 1536]
        unsigned, signed = [], []
        for n in range(256):
            value = sum(planes[j*256+n] << (8*j) for j in range(3))
            unsigned.append(value)
            value = sum(planes[(3+j)*256+n] << (8*j) for j in range(3))
            signed.append((value ^ (1 << 23)) - (1 << 23))
            assert unsigned[-1] - 0x800000 == n * y
            assert signed[-1] + 0x8000 == ((n ^ 128) - 128) * y
        for x in range(-32768, 32768):
            assert unsigned[x & 255] + (signed[(x >> 8) & 255] << 8) == x * y
    return 65536 * len(accepted)


def vectors():
    endpoints = (-(1 << 31), -(1 << 31) + 1, -8388609, -8388608, -65537,
                 -65536, -32769, -32768, -257, -256, -255, -1, 0, 1, 127,
                 255, 256, 257, 32767, 32768, 65535, 65536, 8388607,
                 8388608, (1 << 31) - 1)
    rng = random.Random(960010)
    for y in COEFFICIENTS:
        for x in endpoints:
            yield x, y
        for _ in range(16):
            yield rng.randint(-32768, 32767), y
            yield rng.randint(-(1 << 31), (1 << 31) - 1), y
    # Exercise every slot with a different high-byte tag, including empty
    # slots whose zero tag matches. The zero bank marker must still miss.
    for slot in range(256):
        for high in (0, 0x7f, 0x80, 0xff):
            low = (((high >> 2) | (high << 6)) - slot) & 255
            y = (((high * 256 + low) ^ 32768) - 32768)
            yield -32768, y
            yield 0x456789ab, y
    for _ in range(4096):
        yield rng.choice(endpoints) if rng.randrange(2) else rng.randint(-(1 << 31), (1 << 31)-1), rng.randint(-32768, 32767)


def check_native(image, symbols):
    # The test driver runs below the normal WRAM stack without changing the
    # linked product or table bytes. Mask interrupts for deterministic vectors.
    image = bytearray(image)
    image[0x100:0x102] = bytes((0x18, 0xfe))
    p = PyBoy(BytesIO(image), window='null', sound_emulated=False, cgb=True)
    p.set_emulation_speed(0)
    started = 0
    hits = 0
    address = symbols['_riding_projection_product_regs']
    code, source, stack = 0xc900, 0xc930, 0xcff0
    current_bank = symbols['__current_bank']
    routine = [0xf3, 0xcd, address & 255, address >> 8, 0x18, 0xfe]
    caller_banks = (1, 5, 9, 14, 36, 175)
    bank_windows = {bank: image[(bank << 14):(bank << 14) + 32] for bank in caller_banks}
    guards = bytes((0x35, 0xda))
    try:
        p.tick(240, False)
        p.memory[0xffff] = 0
        p.memory[0xff0f] = 0
        p.memory[code:code+len(routine)] = routine
        for x, y in vectors():
            bank = caller_banks[started % len(caller_banks)]
            p.memory[0x3000] = 0
            p.memory[0x2000] = bank
            p.memory[current_bank] = bank
            raw = guards + x.to_bytes(4, 'little', signed=True) + guards
            p.memory[source-2:source+6] = raw
            p.memory[stack:stack+2] = guards
            p.memory[stack-64:stack-62] = guards
            reg = p.register_file
            reg.SP, reg.PC, reg.HL = stack, code, source
            reg.B, reg.C = (y >> 8) & 255, y & 255
            p.tick(1, False)
            got = reg.B << 40 | reg.C << 32 | reg.HL << 16 | reg.D << 8 | reg.E
            assert got == (x * y) & ((1 << 48) - 1), (x, y, hex(got), hex(x*y & ((1<<48)-1)))
            assert (reg.SP, reg.PC) == (stack, code + 4), (x, y, reg.SP, reg.PC)
            assert bytes(p.memory[source-2:source+6]) == raw
            assert bytes(p.memory[stack:stack+2]) == guards
            assert bytes(p.memory[stack-64:stack-62]) == guards
            assert p.memory[current_bank] == bank
            assert bytes(p.memory[0x4000:0x4020]) == bank_windows[bank], (x, y, bank)
            hits += y in COEFFICIENTS and not 0 <= x <= 255
            started += 1
    finally:
        p.stop(save=False)
    return {'native_products': started, 'table_path_vectors': hits, 'fallback_vectors': started - hits}


def check_interrupts(image, symbols):
    # Start the real cartridge once, then use its installed GBDK VBlank handler.
    # PyBoy's 9-bit bank hooks need a fresh registration for each invocation.
    code, source, stack = 0xc900, 0xc930, 0xcff0
    entry = symbols['_riding_projection_product_regs']
    current = symbols['__current_bank']
    # EI; NOP; CALL product; DI; JR -2
    driver = [0xfb, 0, 0xcd, entry & 255, entry >> 8, 0xf3, 0x18, 0xfe]
    prefix = image[BANKS[0] << 14:(BANKS[0] << 14) + 256]
    after_switch = prefix.index(bytes((0xea, 0, 0x20))) + 3
    bios = PyBoy(BytesIO(image), window='null', sound_emulated=False, cgb=True)
    bios.set_emulation_speed(0)
    snapshot = BytesIO()
    try:
        bios.tick(240, False)
        bios.save_state(snapshot)
    finally:
        bios.stop(save=False)
    checked = 0
    for i, bank in enumerate(BANKS):
        y = COEFFICIENTS[10*i]
        for x in (-32768, 0x73ef01fd, -0x72340123):
            for target_bank, target in ((BANKS[0], 0x4000), (bank, 0x4000 + after_switch)):
                p = PyBoy(BytesIO(image), window='null', sound_emulated=False, cgb=True)
                p.set_emulation_speed(0)
                try:
                    snapshot.seek(0)
                    p.load_state(snapshot)
                    irq = {}
                    reg = p.register_file

                    def inject(_):
                        irq['requested'] = reg.PC
                        p.memory[0xff0f] = 1

                    def vblank(_):
                        s = reg.SP
                        pc = p.memory[s] + (p.memory[s+1] << 8)
                        if 0x4000 <= pc < 0x4100:
                            irq['interrupted'] = pc

                    p.hook_register(target_bank, target, inject, None)
                    p.hook_register(0, 0x40, vblank, None)
                    caller = (5, 9, 14)[checked % 3]
                    p.memory[current] = caller
                    p.memory[0x3000] = 0
                    p.memory[0x2000] = caller
                    p.memory[code:code+len(driver)] = driver
                    p.memory[source:source+4] = x.to_bytes(4, 'little', signed=True)
                    reg.SP, reg.PC, reg.HL = stack, code, source
                    reg.B, reg.C = (y >> 8) & 255, y & 255
                    p.memory[0xff0f] = 0
                    p.memory[0xffff] = 1
                    p.tick(1, False)
                    got = reg.B << 40 | reg.C << 32 | reg.HL << 16 | reg.D << 8 | reg.E
                    assert irq.get('requested') == target and 'interrupted' in irq, (bank, x, irq)
                    assert got == (x*y) & ((1 << 48)-1)
                    assert (reg.SP, reg.PC) == (stack, code+6)
                    assert p.memory[current] == caller
                    assert bytes(p.memory[0x4000:0x4020]) == image[caller << 14:(caller << 14)+32]
                    checked += 1
                finally:
                    p.stop(save=False)
    return checked


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom', type=Path, required=True)
    args = p.parse_args()
    symbols = {k: int(v, 16) for k, v in re.findall(r'^DEF (\S+) 0x([a-fA-F0-9]+)$',
                                                    args.rom.with_suffix('.noi').read_text(), re.M)}
    validate_layout(symbols)
    image = args.rom.read_bytes()
    checks = {'exact_narrow_table_products': verify_table_bytes(image), 'checked_directory_inputs': 65536}
    checks.update(check_native(image, symbols))
    checks['VBlank_interrupts_in_reader'] = check_interrupts(image, symbols)
    print(json.dumps(checks))


if __name__ == '__main__':
    main()
