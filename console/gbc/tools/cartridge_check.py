"""Build a non-writing MBC5 diagnostic around an existing 8 MiB game ROM.

Only ROM0 changes. Every byte in banks 1..511 comes from the source ROM.
Full-bank CRC-16/CCITT-FALSE checks detect read errors, but are not collision
proof. The quick check covers four physics banks selected by --first-bank;
A scans all switchable banks and B repeats it. Use --verify for PyBoy checks.
"""

import argparse
import binascii
import hashlib
import json
from pathlib import Path
import re
import subprocess


BASE = Path(__file__).resolve().parents[1]
BANK_SIZE = 16384
BANK_COUNT = 512


def crc16(data):
    return binascii.crc_hqx(data, 0xFFFF)


def fix_checksums(rom):
    rom[0x14D] = (-sum(rom[0x134:0x14D]) - 25) & 255
    rom[0x14E:0x150] = b'\0\0'
    rom[0x14E:0x150] = (sum(rom) & 65535).to_bytes(2, 'big')


def c_driver(checksums, source_sha, version, first_bank):
    table = [binascii.crc_hqx(bytes([i]), 0) for i in range(256)]
    arrays = '\n'.join(
        'const uint16_t %s[] = {\n%s\n};' % (
            name, ',\n'.join(','.join('0x%04x' % n for n in data[i:i + 12])
                             for i in range(0, len(data), 12)))
        for name, data in [('crc_table', table), ('expected_crc', checksums)])
    return '''#include <gb/gb.h>
#include <gb/cgb.h>
#include <gbdk/console.h>
#include <stdio.h>
#include <stdint.h>
#pragma bank 0
''' + arrays + '''
/* Emulator-visible results; all code and expected data reside in ROM0. */
volatile uint8_t diag_state; /* 0 running, 1 physics pass, 2 all pass, 3 fail */
volatile uint8_t diag_phase;
volatile uint16_t diag_bank, diag_expected, diag_actual, diag_checked;
volatile uint16_t selected_bank;
const palette_color_t screen_palette[] = {RGB_WHITE, RGB_BLACK, RGB_BLACK, RGB_BLACK};

void select_bank(uint16_t bank) {
    /* Track both MBC5 bits explicitly; CURRENT_BANK tracks only eight bits. */
    rROMB0 = (uint8_t)bank;
    rROMB1 = (uint8_t)(bank >> 8);
    selected_bank = bank;
}

uint16_t bank_crc(uint16_t bank) {
    uint16_t saved = selected_bank;
    uint16_t count = 16384u;
    uint16_t crc = 0xffffu;
    const volatile uint8_t *ptr = (const volatile uint8_t *)0x4000;
    select_bank(bank);
    do {
        uint8_t index = (uint8_t)(crc >> 8) ^ *ptr++;
        crc = (crc << 8) ^ crc_table[index];
    } while (--count);
    select_bank(saved);
    return crc;
}

void hex4(uint16_t value) {
    const char *digits = "0123456789ABCDEF";
    putchar(digits[(value >> 12) & 15]);
    putchar(digits[(value >> 8) & 15]);
    putchar(digits[(value >> 4) & 15]);
    putchar(digits[value & 15]);
}

void heading(void) {
    cls();
    set_bkg_palette(0, 1, screen_palette);
    printf("ELMA CART CHECK\\n");
    printf("VERSION_TEXT 8MiB MBC5\\n");
    printf("SHA SHA_TEXT\\n\\n");
    printf("CRC16 whole banks\\n");
}

void scan(uint8_t all) {
    uint16_t bank;
    diag_state = 0;
    diag_phase = all;
    diag_checked = 0;
    heading();
    gotoxy(0, 6);
    printf(all ? "ALL BANKS 1-511" : "PHYSICS FIRST_BANK-LAST_BANK");
    for (bank = all ? 1u : FIRST_BANKu; bank < (all ? 512u : END_BANKu); ++bank) {
        diag_bank = bank;
        gotoxy(0, 8);
        printf("Bank %u/511   ", bank);
        diag_expected = expected_crc[bank];
        diag_actual = bank_crc(bank);
        ++diag_checked;
        if (diag_actual != diag_expected) {
            gotoxy(0, 7);
            printf("FAIL");
            gotoxy(0, 10);
            printf("Expected "); hex4(diag_expected);
            gotoxy(0, 11);
            printf("Read     "); hex4(diag_actual);
            if (bank > 256u && diag_actual == expected_crc[bank & 255u]) {
                gotoxy(0, 13);
                printf("Matches bank %u", bank & 255u);
                gotoxy(0, 14);
                printf("Possible ROM alias");
            }
            gotoxy(0, 16);
            printf("A: all B: physics");
            diag_state = 3;
            return;
        }
    }
    gotoxy(0, 7);
    printf(all ? "ALL BANKS PASS" : "PHYSICS PASS");
    gotoxy(0, 10);
    printf("%u banks checked", diag_checked);
    gotoxy(0, 12);
    printf("A: scan all banks");
    gotoxy(0, 13);
    printf("B: repeat physics");
    diag_state = all ? 2 : 1;
}

void main(void) {
    uint8_t previous = 0;
    uint8_t buttons;
    cpu_fast();
    select_bank(1);
    /* Never enable or write cartridge SRAM. */
    scan(0);
    while (1) {
        vsync();
        buttons = joypad();
        if ((buttons & J_A) && !(previous & J_A)) scan(1);
        else if ((buttons & J_B) && !(previous & J_B)) scan(0);
        previous = buttons;
    }
}
'''.replace('VERSION_TEXT', version).replace('SHA_TEXT', source_sha[:12]).replace(
    'FIRST_BANK', str(first_bank)).replace('LAST_BANK', str(first_bank+3)).replace('END_BANK', str(first_bank+4))


def verify(out, report):
    from pyboy import PyBoy
    first_bank = report['physics_banks'][0]

    symbols = {name: int(value, 16) for name, value in re.findall(
        r'DEF (_\w+) 0x([0-9a-fA-F]+)', out.with_suffix('.noi').read_text())}

    def run(path, alias=False):
        emulator = PyBoy(str(path), window='null', sound_emulated=False, cgb=True)
        emulator.set_emulation_speed(0)
        frames = 0

        def read(name, size=2):
            addr = symbols['_' + name]
            return int.from_bytes(bytes(emulator.memory[addr:addr + size]), 'little')

        def wait_done():
            nonlocal frames
            for _ in range(600):
                emulator.tick(100)
                frames += 100
                if read('diag_state', 1):
                    return {name: read(name, 1 if name in ('diag_state', 'diag_phase') else 2)
                            for name in ('diag_state', 'diag_phase', 'diag_bank',
                                         'diag_expected', 'diag_actual', 'diag_checked',
                                         'selected_bank')}
            raise AssertionError('Diagnostic timed out')

        try:
            quick = wait_done()
            assert quick['selected_bank'] == 1, quick
            assert bytes(emulator.memory[0x4000:0x8000]) == path.read_bytes()[BANK_SIZE:2 * BANK_SIZE], 'ROM bank 1 was not restored'
            emulator.screen.image.save(path.with_suffix('.physics.png'))
            if alias:
                assert quick['diag_state'] == 3 and quick['diag_bank'] == first_bank, quick
                assert quick['diag_expected'] == report['bank_crc16'][first_bank], quick
                assert quick['diag_actual'] == report['bank_crc16'][first_bank & 255], quick
                assert quick['diag_expected'] != quick['diag_actual'], quick
                return {'physics': quick, 'frames': frames}
            assert quick['diag_state'] == 1 and quick['diag_checked'] == 4, quick
            emulator.button_press('a')
            emulator.tick(2)
            emulator.button_release('a')
            complete = wait_done()
            assert complete['diag_state'] == 2 and complete['diag_checked'] == 511, complete
            assert complete['selected_bank'] == 1, complete
            assert bytes(emulator.memory[0x4000:0x8000]) == path.read_bytes()[BANK_SIZE:2 * BANK_SIZE], 'ROM bank 1 was not restored'
            emulator.screen.image.save(path.with_suffix('.all.png'))
            return {'physics': quick, 'all': complete, 'frames': frames}
        finally:
            emulator.stop(save=False)

    normal = run(out)
    damaged = bytearray(out.read_bytes())
    # Mimic a missing MBC5 high ROM address bit while retaining diagnostic ROM0.
    damaged[256 * BANK_SIZE:] = damaged[:256 * BANK_SIZE]
    fix_checksums(damaged)
    alias_path = out.with_name(out.stem + '-alias.gbc')
    alias_path.write_bytes(damaged)
    return {'normal': normal, 'upper_half_alias': run(alias_path, alias=True)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=BASE / 'build/elma-gbc-v0.7-8m.gbc')
    parser.add_argument('--out', type=Path, default=BASE / 'build/elma-gbc-v0.7-8m-check.gbc')
    parser.add_argument('--sdk', type=Path, default=BASE / '.toolchain/gbdk')
    parser.add_argument('--first-bank', type=int, default=508,
                        help='first physics bank: 477 for the relocated build, 508 for original 0.7')
    parser.add_argument('--verify', action='store_true', help='test clean and aliased ROMs in PyBoy')
    args = parser.parse_args()
    source, out = args.source.resolve(), args.out.resolve()
    if source == out:
        raise ValueError('Diagnostic must not overwrite the source ROM')
    if not 256 <= args.first_bank <= BANK_COUNT-4:
        raise ValueError('The four physics banks must fit in the upper ROM half')
    original = source.read_bytes()
    if len(original) != BANK_SIZE * BANK_COUNT or original[0x147:0x14A] != bytes((0x1B, 8, 3)):
        raise ValueError('Source must be 8 MiB MBC5+RAM+battery with 32 KiB RAM')
    sha = hashlib.sha256(original).hexdigest()
    version_match = re.search(r'v\d+(?:\.\d+)+', source.stem)
    version = version_match[0] if version_match else 'custom'
    checksums = [crc16(original[i * BANK_SIZE:(i + 1) * BANK_SIZE]) for i in range(BANK_COUNT)]
    # A known CRC vector guards the host-side parameter choice.
    assert crc16(b'123456789') == 0x29B1
    out.parent.mkdir(parents=True, exist_ok=True)
    driver = out.with_suffix('.c')
    driver.write_text(c_driver(checksums, sha, version, args.first_bank))
    subprocess.run([str(args.sdk.resolve() / 'bin/lcc'), '-msm83:gb', '-Wf--opt-code-size',
                    '-Wm-yC', '-Wm-yt0x1B', '-Wm-ya4', '-Wm-yo512', '-Wm-ynELMA-CHECK',
                    '-Wl-m', '-Wl-j', '-o', str(out), str(driver)], check=True)
    rom = bytearray(out.read_bytes())
    assert len(rom) == len(original), 'Linker must create all 512 ROM banks'
    assert rom[0x143] == 0xC0 and rom[0x147:0x14A] == bytes((0x1B, 8, 3))
    rom[BANK_SIZE:] = original[BANK_SIZE:]
    fix_checksums(rom)
    assert rom[BANK_SIZE:] == original[BANK_SIZE:], 'All switchable banks must remain identical'
    assert source.read_bytes() == original, 'Source changed during diagnostic build'
    out.write_bytes(rom)
    report = {
        'source': str(source), 'source_version': version, 'source_sha256': sha,
        'output': str(out), 'output_sha256': hashlib.sha256(rom).hexdigest(),
        'bytes': len(rom), 'cartridge_type': 'MBC5+RAM+BATTERY', 'ram_kib': 32,
        'preserved_banks': [1, 511], 'preserved_bytes': len(rom) - BANK_SIZE,
        'physics_banks': [args.first_bank, args.first_bank+3],
        'switchable_banks_identical': True, 'cartridge_sram_writes': False,
        'checksum': 'CRC-16/CCITT-FALSE, poly 0x1021, init 0xFFFF, no reflection/xorout',
        'checksum_limitation': 'Matching CRC16 values are not proof against collisions.',
        'bank_crc16': checksums,
    }
    if args.verify:
        report['pyboy'] = verify(out, report)
    out.with_suffix('.report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'bank_crc16'}, indent=2))


if __name__ == '__main__':
    main()
