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
from projection_tables import BANKS, COEFFICIENTS, MIRRORED, ROWS_PER_BANK, row_page, validate_layout


def verify_table_bytes(image, symbols):
    table = symbols['_riding_projection_hash']
    assert table == 0x200
    accepted = {}
    for y in range(-32768, 32768):
        high, low = divmod(abs(y), 256)
        if y < 0 and low:
            slot = ~(y + image[table + ((y >> 8) & 255)]) & 255
        else:
            slot = (low + image[table + high]) & 255
        if image[table + 256 + slot] == high:
            bank = image[table + 512 + slot]
            page = image[table + 768 + slot] ^ (128 if y < 0 else 0)
            accepted[y] = (bank + (256 if bank & 128 else 0), page)
    expected = {y: (BANKS[i // ROWS_PER_BANK], row_page(i)) for i, y in enumerate(COEFFICIENTS)}
    for y in MIRRORED:
        bank, page = expected[-y]
        expected[y] = (bank, page | 128)
    assert expected == accepted
    for y, (bank, page) in accepted.items():
        mirror = bool(page & 128)
        start = (bank << 14) + ((page & 127) - 0x40) * 256
        planes = image[start:start + 1280]
        unsigned, signed = [], []
        for n in range(256):
            value = sum(planes[p*256+n] << (8*j) for j,p in enumerate((2,0,1)))
            unsigned.append(value)
            value = sum(planes[p*256+n] << (8*j) for j,p in enumerate((2,3,4)))
            signed.append((value ^ (1 << 23)) - (1 << 23))
            assert unsigned[-1] - 0x800000 == n * (-y if mirror else y)
            assert signed[-1] + 0x8000 == ((n ^ 128) - 128) * (-y if mirror else y)
        for x in range(-32768, 32768):
            operand = -x if mirror else x
            if operand == 32768:
                product = unsigned[0] + (unsigned[128] << 8) - 0x80800000
            else:
                product = unsigned[operand & 255] + (signed[(operand >> 8) & 255] << 8)
            assert product == x * y
    return 65536 * len(accepted)


def check_shallow_tables(image, symbols):
    checked = 0
    for magnitude in (9, 61):
        symbol = symbols[f'_riding_shallow_dot_{magnitude}']
        assert symbol >> 16 == 4
        base = 4 * 16384 + (symbol & 16383)
        for y in range(-32768, 32768):
            addr = base + ((y >> 8) & 255)
            q = (image[addr] ^ 128) - 128
            q -= (y & 255) > image[addr + 256]
            assert q == (8192 - y * magnitude) // 16384
            checked += 1
    return checked


def check_shallow_native(p, symbols, code, stack, source, current_bank, bank_windows):
    entry = symbols['_riding_dotq14_regs']
    p.memory[code:code+6] = [0xf3,0xcd,entry & 255,entry >> 8,0x18,0xfe]
    limit = 1 << 31
    rng = random.Random(0xD0720)
    xs = (-limit, -limit + 1, -limit + 121, -1, 0, 1, limit - 121, limit - 2, limit - 1)
    ys = (-limit, -65537, -32769, -32768, -32767, -8192, -1, 0,
          1, 8192, 32766, 32767, 32768, 65536, limit - 1)
    checked = 0
    for weight in (-32768, -16384, -16129, -16128, -62, -61, -60, -10, -9, -8,
                   1, 127, 256, 8192, 16383, 16384, 32767):
        for i in range(512):
            x, y = (xs[i % len(xs)], ys[i // len(xs)]) if i < len(xs)*len(ys) else (
                rng.choice(xs), rng.randint(-32768, 32767))
            unit = 16384 if i & 2 else -16384
            xy, normal = ((x, y), (unit, weight)) if i & 1 else ((y, x), (weight, unit))
            raw = b''.join(n.to_bytes(4, 'little', signed=True) for n in xy)
            raw += b''.join(n.to_bytes(2, 'little', signed=True) for n in normal)
            p.memory[source:source+12] = raw
            reg = p.register_file
            reg.SP, reg.PC, reg.HL = stack, code, source + 8
            reg.D, reg.E = source >> 8, source & 255
            bank = (5,9,14)[i % 3]
            p.memory[0x2000] = p.memory[current_bank] = bank
            p.tick(1, False)
            expected = max(-limit, min(limit-1, (8192 + y*weight + x*unit) // 16384))
            assert (reg.HL << 16 | reg.D << 8 | reg.E) == (expected & 0xffffffff), (x, y, weight)
            assert (reg.PC, reg.SP) == (code+4, stack)
            assert bytes(p.memory[source:source+12]) == raw
            assert p.memory[current_bank] == bank
            assert bytes(p.memory[0x4000:0x4020]) == bank_windows[bank]
            checked += 1
    return checked


def check_rolling_projections(p, symbols, code, stack, source, current_bank, bank_windows):
    entry = symbols['_riding_roll_project_pair']
    p.memory[code:code+6] = [0xf3, 0xcd, entry & 255, entry >> 8, 0x18, 0xfe]
    guards = bytes((0x31, 0x8c))
    checked = 0
    for y in (*COEFFICIENTS, *MIRRORED, -32768, 32767):
        for speed in (-32769, -32768, -32767, -8192, -1, 0, 1, 8192, 32766, 32767, 32768):
            pair = (y, -y if y != -32768 else 32767)
            args = speed.to_bytes(4, 'little', signed=True) + b''.join(
                value.to_bytes(2, 'little', signed=True) for value in pair)
            p.memory[stack:stack+10] = args + guards
            p.memory[source-2:source+10] = guards + bytes(8) + guards
            reg = p.register_file
            reg.SP, reg.PC, reg.HL = stack, code, source
            bank = (5, 9, 14)[checked % 3]
            p.memory[current_bank] = p.memory[0x2000] = bank
            p.tick(1, False)
            want = b''.join(((speed*v + 8192) >> 14).to_bytes(4, 'little', signed=True) for v in pair)
            assert bytes(p.memory[source-2:source+10]) == guards + want + guards, (speed, pair)
            assert (reg.SP, reg.PC) == (stack, code+4)
            assert bytes(p.memory[stack:stack+10]) == args + guards
            assert p.memory[current_bank] == bank
            assert bytes(p.memory[0x4000:0x4020]) == bank_windows[bank]
            checked += 1
    return checked


def vectors():
    endpoints = (-(1 << 31), -(1 << 31) + 1, -8388609, -8388608, -65537,
                 -65536, -32769, -32768, -257, -256, -255, -1, 0, 1, 127,
                 255, 256, 257, 32767, 32768, 65535, 65536, 8388607,
                 8388608, (1 << 31) - 1)
    rng = random.Random(960010)
    for x in range(-257, 2):
        for y in (-32768, -32767, -16384, -256, -1, 0, 1, 255, 16384, 32767):
            yield x, y
    for y in (*COEFFICIENTS, *MIRRORED):
        for x in endpoints:
            yield x, y
        for _ in range(16):
            yield rng.randint(-32768, 32767), y
            yield rng.randint(-(1 << 31), (1 << 31) - 1), y
    # Exercise every low-byte slot with several tags, including signed extremes.
    for slot in range(256):
        for high in (0, 0x7f, 0x80, 0xff):
            y = (((high * 256 + slot) ^ 32768) - 32768)
            yield -32768, y
            yield 0x456789ab, y
    for high in (-257, -256, -129, -128, -2, -1, 0, 1, 2, 127, 128, 255, 256):
        for low in (0, 1, 0x7fff, 0x8000, 0xffff):
            for y in (COEFFICIENTS[0], -COEFFICIENTS[0], COEFFICIENTS[-1], -COEFFICIENTS[-1]):
                yield (high << 16) + low, y
    for boundary in (32768, 65536, 131072):
        for delta in (-2, -1, 0, 1, 2):
            for sign in (-1, 1):
                for y in (-32768, -24585, -4098, -773, 773, 4098, 24585, 32767):
                    yield sign*(boundary+delta), y
    for _ in range(4096):
        yield rng.choice(endpoints) if rng.randrange(2) else rng.randint(-(1 << 31), (1 << 31)-1), rng.randint(-32768, 32767)


def check_single_shifts(p, symbols, code, stack, current_bank, bank_windows):
    """Probe both saturation boundaries, half ties and every supported shift."""
    rng = random.Random(0x260628)
    checks = 0
    for rounded, name in ((False, '_riding_mulshift32'), (True, '_riding_mulq32')):
        addr = symbols[name]
        p.memory[code:code+6] = (0xf3, 0xcd, addr & 255, addr >> 8, 0x18, 0xfe)
        for shift in range(int(rounded), 17):
            bias = 1 << (shift-1) if rounded else 0
            for coef in (-32768, -16384, -410, -257, -1, 0, 1, 255, 409, 16384, 32767):
                xs = {-2**31, 2**31-1, -65537, 32768, 0, rng.randrange(-2**31, 2**31)}
                if coef:
                    for output in (-2**31-1, -2**31, -1, 0, 1, 2**31-1, 2**31):
                        center = ((output << shift) - bias) // coef
                        xs.update(x for x in range(center-1, center+3) if -2**31 <= x < 2**31)
                for x in sorted(xs):
                    args = x.to_bytes(4, 'little', signed=True) + coef.to_bytes(2, 'little', signed=True) + bytes((shift, 0x71, 0xda))
                    p.memory[stack:stack+len(args)] = args
                    bank = (5, 9, 14)[checks % 3]
                    p.memory[current_bank] = p.memory[0x2000] = bank
                    reg = p.register_file
                    reg.SP, reg.PC = stack, code
                    p.tick(1, False)
                    got = reg.HL << 16 | reg.D << 8 | reg.E
                    expected = max(-2**31, min(2**31-1, (x*coef+bias) >> shift))
                    assert got == (expected & 0xffffffff), (name, shift, x, coef, got, expected)
                    assert (reg.SP, reg.PC) == (stack, code+4)
                    assert bytes(p.memory[stack:stack+len(args)]) == args
                    assert p.memory[current_bank] == bank
                    assert bytes(p.memory[0x4000:0x4020]) == bank_windows[bank]
                    checks += 1
    return checks


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
            hits += y in (*COEFFICIENTS, *MIRRORED) and not -255 <= x <= 255
            started += 1
        dots = 0
        rng = random.Random(0x96d07)
        raw = [-32768,-32767,-16384,-8192,-256,-1,0,1,255,8192,16384,32767]
        geom = symbols['_dotq14']
        p.memory[code:code+len(routine)] = [0xf3,0xcd,geom & 255,geom >> 8,0x18,0xfe]
        for i in range(9600):
            a,b,c,d = [rng.randint(-32768,32767) for _ in range(4)]
            if i < len(raw)**2*7:
                a,b = raw[(i//7) % len(raw)],raw[i//7//len(raw)]
                c,d = ((0,-16384),(16384,0),(0,0),(-16384,0),(0,16384),
                       (-32768,-32768),(32767,32767))[i%7]
            elif i % 3:
                c,d = rng.choice(COEFFICIENTS),rng.choice(COEFFICIENTS)
            p.memory[stack:stack+6] = (int(c).to_bytes(2,'little',signed=True)
                                      + int(d).to_bytes(2,'little',signed=True) + guards)
            reg.SP,reg.PC = stack,code
            reg.D,reg.E,reg.B,reg.C = (a>>8)&255,a&255,(b>>8)&255,b&255
            p.tick(1, False)
            # This older ABI specifies a wrapped 32-bit sum before saturation.
            fixed = ((a*c+b*d+8192+2**31) % 2**32)-2**31
            want = max(-32768,min(32767,fixed >> 14))
            assert (reg.B<<8 | reg.C) == want & 65535, (a,b,c,d,want)
            assert (reg.SP,reg.PC) == (stack+4,code+4)
            assert bytes(p.memory[stack+4:stack+6]) == guards
            assert bytes(p.memory[0x4000:0x4020]) == bank_windows[bank]
            dots += 1
        shifted = check_single_shifts(p, symbols, code, stack, current_bank, bank_windows)
        rolling = check_rolling_projections(p, symbols, code, stack, source, current_bank, bank_windows)
        shallow = check_shallow_native(p, symbols, code, stack, source, current_bank, bank_windows)
    finally:
        p.stop(save=False)
    return {'native_products': started, 'native_shifts': shifted, 'table_path_vectors': hits, 'fallback_vectors': started - hits, 'native_geometry_dots': dots, 'native_shallow_dots': shallow, 'native_rolling_pairs': rolling}


def check_interrupts(image, symbols):
    # Start the real cartridge once, then use its installed GBDK VBlank handler.
    # Interrupt once at dispatch and once inside the selected product reader.
    code, source, stack = 0xc900, 0xc930, 0xcff0
    entry = symbols['_riding_projection_product_regs']
    lookup = symbols['_riding_projection_read_directory']
    current = symbols['__current_bank']
    # EI; NOP; CALL product; DI; JR -2
    driver = [0xfb, 0, 0xcd, entry & 255, entry >> 8, 0xf3, 0x18, 0xfe]
    fetch = symbols['_riding_projection_fetch']
    wide = symbols['_riding_projection_fetch_wide']
    narrow = symbols['_riding_projection_read_signed']
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
        # Both widths must actually execute this bank's reader. Short
        # coefficients and exact unit normals can finish wholly in fixed ROM.
        rows = COEFFICIENTS[i*ROWS_PER_BANK:(i+1)*ROWS_PER_BANK]
        canonical = next(y for y in rows if abs(y) > 255 and abs(y) != 16384)
        for x, y in ((-32768, canonical), (0x73ef01fd, canonical), (-0x72340123, -canonical),
                     (32767, -canonical)):
            for target in (lookup, fetch, narrow if -32768 <= x <= 32767 else wide):
                p = PyBoy(BytesIO(image), window='null', sound_emulated=False, cgb=True)
                p.set_emulation_speed(0)
                try:
                    snapshot.seek(0)
                    p.load_state(snapshot)
                    irq = {}
                    reg = p.register_file

                    def inject(_):
                        if 'requested' not in irq:
                            irq['requested'] = reg.PC
                            p.memory[0xff0f] = 1

                    def vblank(_):
                        s = reg.SP
                        pc = p.memory[s] + (p.memory[s+1] << 8)
                        if lookup <= pc < lookup+4 or fetch <= pc < fetch+256:
                            irq['interrupted'] = pc

                    p.hook_register(0, target, inject, None)
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
                    assert got == (x*y) & ((1 << 48)-1), (x, y, bank, caller, hex(target), hex(got), hex((x*y) & ((1<<48)-1)), irq, reg.PC)
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
    checks = {'exact_narrow_table_products': verify_table_bytes(image, symbols), 'checked_directory_inputs': 65536}
    if '_riding_shallow_dot_61' in symbols or '_riding_shallow_dot_9' in symbols:
        checks['shallow_table_inputs'] = check_shallow_tables(image, symbols)
    checks.update(check_native(image, symbols))
    checks['VBlank_interrupts_in_reader'] = check_interrupts(image, symbols)
    print(json.dumps(checks))


if __name__ == '__main__':
    main()
