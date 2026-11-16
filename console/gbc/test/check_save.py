"""Exercise production SM83 saves, real battery files, and interrupted commits.

The isolated ROM calls save.c directly; these are module fixtures, not completed
rides or controller-driven UI tests. Only bank15's first 2048 SRAM bytes belong
to saves; every other byte is checked against an independent canary image.
"""
import argparse
import binascii
import hashlib
import json
from pathlib import Path
import re
import subprocess

from pyboy import PyBoy

BASE = Path(__file__).resolve().parents[1]
RAM_SIZE = 16 * 8192
SAVE_BASE = 15 * 8192
SLOT_SIZE = 1024
DEFAULT_NAMES = [f'PLAYER {i}' for i in range(1, 5)]


def crc(slot):
    """Independent standard-library CCITT reference, excluding commit and CRC."""
    return binascii.crc_hqx(slot[:5] + slot[6:12] + slot[14:], 0xffff)


def make_slot(generation, player=0, names=None, records=None):
    slot = bytearray(SLOT_SIZE)
    slot[:4] = b'ELMS'
    slot[4:6] = bytes((1, 0xa5))
    slot[6:8] = (909).to_bytes(2, 'little')
    slot[8:12] = generation.to_bytes(4, 'little')
    slot[16] = player
    for i, name in enumerate(names or DEFAULT_NAMES):
        encoded = name.encode('ascii')
        assert 0 < len(encoded) <= 10
        slot[17 + i * 11:17 + i * 11 + len(encoded)] = encoded
    for (player, level), frames in (records or {}).items():
        offset = 61 + (player * 54 + level) * 4
        slot[offset:offset + 4] = frames.to_bytes(4, 'little')
    slot[12:14] = crc(slot).to_bytes(2, 'little')
    return bytes(slot)


def valid_slot(slot):
    return (slot[:6] == b'ELMS\x01\xa5'
            and int.from_bytes(slot[6:8], 'little') == 909
            and int.from_bytes(slot[12:14], 'little') == crc(slot))


def slot_from(image, index):
    start = SAVE_BASE + index * SLOT_SIZE
    return image[start:start + SLOT_SIZE]


def put_slot(image, index, slot):
    result = bytearray(image)
    start = SAVE_BASE + index * SLOT_SIZE
    result[start:start + SLOT_SIZE] = slot
    return bytes(result)


def guarded_image(fill=0xff):
    image = bytearray(((i * 29) ^ (i >> 7) ^ 0xa7) & 255
                      for i in range(RAM_SIZE))
    image[SAVE_BASE:SAVE_BASE + 2 * SLOT_SIZE] = bytes([fill]) * (2 * SLOT_SIZE)
    return bytes(image)


def check_guards(image, original):
    assert len(image) == RAM_SIZE, ('battery file size', len(image))
    assert image[:SAVE_BASE] == original[:SAVE_BASE], 'scratch SRAM banks0..14 changed'
    assert image[SAVE_BASE + 2048:] == original[SAVE_BASE + 2048:], 'bank15 tail changed'


def compile_fixture(out):
    sources = {name: (BASE / 'src' / name).read_bytes() for name in ('save.c', 'save.h')}
    for name, contents in sources.items():
        (out / name).write_bytes(contents)
    (out / 'driver.c').write_text(r'''#include <gb/gb.h>
#include <gb/cgb.h>
#include "save.h"
volatile uint8_t ready,command,argument_player,argument_level,result,bank_failures;
volatile uint8_t ram_failures;
volatile uint16_t commands,irq_count;
volatile uint32_t argument_frames,best_result;
char argument_name[32];
extern const uint8_t bank9_marker[];
void service(void) BANKED;
static void vblank(void) NONBANKED { ++irq_count; }
void main(void) NONBANKED {
 cpu_fast();add_VBL(vblank);set_interrupts(VBL_IFLAG);enable_interrupts();
 SWITCH_ROM(9);command=1;
 while(1) {
  if(command) {
   DISABLE_RAM;SWITCH_RAM(12);
   service();
   if(CURRENT_BANK!=9 || ((const volatile uint8_t *)bank9_marker)[0]!=0x99)++bank_failures;
   ++commands;command=0;ready=1;
  }
  vsync();
 }
}
''')
    (out / 'caller.c').write_text(r'''#pragma bank 5
#include <gb/gb.h>
#include "save.h"
extern volatile uint8_t command,argument_player,argument_level,result,bank_failures,ram_failures;
extern volatile uint32_t argument_frames,best_result;
extern char argument_name[32];
const uint8_t bank5_marker[]={0x55};
void service(void) BANKED {
 switch(command) {
 case 1:save_init();break;
 case 2:save_select(argument_player);break;
 case 3:save_name(argument_player,argument_name);break;
 case 4:best_result=save_best(argument_player,argument_level);break;
 case 5:result=save_record(argument_player,argument_level,argument_frames);break;
 case 6:save_name(argument_player,0);break;
 }
 if(CURRENT_BANK!=5 || ((const volatile uint8_t *)bank5_marker)[0]!=0x55)++bank_failures;
 if(*(volatile uint8_t *)0xa000!=0xa7 || *(volatile uint8_t *)0xa001!=0xba)++ram_failures;
}
''')
    (out / 'bank9.c').write_text('#pragma bank 9\n#include <gb/gb.h>\nconst uint8_t bank9_marker[]={0x99};\n')
    rom = out / 'check.gbc'
    module_command = [str(BASE / '.toolchain/gbdk/bin/lcc'), '-msm83:gb',
                      '-Wf--opt-code-size', '-I' + str(out), '-c',
                      '-o', str(out / 'save.o'), str(out / 'save.c')]
    result = subprocess.run(module_command, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    areas = {name: int(size, 16) for name, size in re.findall(
        r'^A (\S+) size ([0-9A-Fa-f]+) ', (out / 'save.o').read_text(), re.MULTILINE)}
    static_wram = sum(areas.get(name, 0) for name in ('_DATA', '_INITIALIZED', '_DABS', '_HRAM'))
    assert static_wram <= 50, ('save module exceeds static WRAM budget', static_wram)
    command = [str(BASE / '.toolchain/gbdk/bin/lcc'), '-msm83:gb',
               '-Wf--opt-code-size', '-Wm-yC', '-Wm-yt0x1b', '-Wm-ya16',
               '-Wm-yo16', '-Wl-m', '-Wl-j', '-I' + str(out), '-o', str(rom),
               *(str(out / name) for name in ('driver.c', 'caller.c', 'bank9.c', 'save.o'))]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    symbols = {name: int(value, 16) for name, value in re.findall(
        r'DEF (_\w+) 0x([0-9A-Fa-f]+)', rom.with_suffix('.noi').read_text())}
    for name in ('save_init', 'save_select', 'save_name', 'save_best', 'save_record'):
        assert symbols['_' + name] >> 16 == 7, (name, 'wrong ROM bank')
    binary = rom.read_bytes()
    assert binary[0x147] == 0x1b and binary[0x149] == 4, 'expected MBC5 battery + 128KiB SRAM'
    return rom, symbols, sources, [module_command, command], static_wram


class Driver:
    def __init__(self, rom, symbols, initial):
        self.rom, self.symbols, self.initial = rom, symbols, initial
        self.ram = Path(str(rom) + '.ram')
        self.ram.write_bytes(initial)
        self.p = PyBoy(str(rom), window='null', sound_emulated=False, cgb=True)
        self.p.set_emulation_speed(0)
        self.wait('ready')
        self.check_banks()

    def get(self, name, width=1):
        address = self.symbols['_' + name]
        return int.from_bytes(bytes(self.p.memory[address:address + width]), 'little')

    def put(self, name, value, width=1):
        address = self.symbols['_' + name]
        self.p.memory[address:address + width] = list(value.to_bytes(width, 'little'))

    def wait(self, name, value=1):
        for _ in range(600):
            if self.get(name) == value:
                return
            self.p.tick(1, False)
        raise AssertionError(('native command timed out', name, value, self.get('command')))

    def check_banks(self):
        assert self.get('bank_failures') == 0, 'ROM caller bank not restored'
        assert self.get('ram_failures') == 0, 'SRAM bank0 not restored or disabled'
        assert self.p.memory[0xffff] & 1, 'VBlank interrupt disabled'

    def call(self, command, player=0, level=0, frames=0, name=None):
        self.put('argument_player', player)
        self.put('argument_level', level)
        self.put('argument_frames', frames, 4)
        if name is not None:
            value = name.encode('ascii') + b'\0'
            assert len(value) <= 32
            address = self.symbols['_argument_name']
            self.p.memory[address:address + len(value)] = list(value)
        self.put('command', command)
        self.wait('command', 0)
        self.check_banks()
        return self.get('best_result', 4) if command == 4 else self.get('result')

    def names(self):
        address = self.symbols['_save_names']
        data = bytes(self.p.memory[address:address + 44])
        names = []
        for offset in range(0, 44, 11):
            chunk = data[offset:offset + 11]
            end = chunk.index(0)
            assert chunk[end:] == bytes(11 - end), ('name not zero-padded', chunk)
            names.append(chunk[:end].decode('ascii'))
        return names

    def state(self, player=0, names=None, records=None):
        assert self.get('save_player') == player, ('selected player', self.get('save_player'), player)
        assert self.names() == (names or DEFAULT_NAMES), ('player names', self.names())
        for owner in range(4):
            for level in range(54):
                actual = self.call(4, owner, level)
                expected = (records or {}).get((owner, level), 0)
                assert actual == expected, ('best isolation', owner, level, actual, expected)

    def close(self):
        self.check_banks()
        assert self.get('irq_count', 2), 'no VBlank interrupts serviced'
        self.p.stop(save=True)
        image = self.ram.read_bytes()
        check_guards(image, self.initial)
        return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=BASE / 'build/save-check')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / 'report.json').unlink(missing_ok=True)
    rom, symbols, sources, commands, static_wram = compile_fixture(out)
    boots = 0
    checks = []
    active = None

    def boot(image):
        nonlocal boots, active
        active = Driver(rom, symbols, image)
        boots += 1
        return active

    def close(driver):
        nonlocal active
        image = driver.close()
        active = None
        return image

    def expect_boot(image, player=0, names=None, records=None, unchanged=True):
        driver = boot(image)
        driver.state(player, names, records)
        result = close(driver)
        if unchanged:
            assert result == image, 'read-only boot/query modified SRAM'
        return result

    try:
        # Both common uninitialized battery patterns must remain unwritten.
        for fill in (0xff, 0):
            expect_boot(guarded_image(fill))
        checks.append('blank 00/FF SRAM defaults; all 216 records empty without writes')

        image = guarded_image()
        driver = boot(image)
        for player, name in enumerate(('ALPHA', 'BETA 2', 'GAMMA', 'DELTA')):
            driver.call(3, player, name=name)
        names = ['ALPHA', 'BETA 2', 'GAMMA', 'DELTA']
        driver.call(2, 3)
        records = {(player, level): 100000 + player * 1000 + level
                   for player in range(4) for level in (0, 53)}
        for (player, level), frames in records.items():
            assert driver.call(5, player, level, frames) == 1
        # Exercise the full uint32 range, rather than accidentally comparing low words.
        records[(1, 26)] = 0xffffffff
        assert driver.call(5, 1, 26, records[(1, 26)]) == 1
        driver.state(3, names, records)
        image = close(driver)
        (out / 'populated.ram').write_bytes(image)
        assert all(valid_slot(slot_from(image, index)) for index in (0, 1)), 'production CRC/slot format'
        expect_boot(image, 3, names, records)
        checks.append('names, active player, all players/edge levels and uint32 bests persist through battery-file reboot')

        driver = boot(image)
        for player, level in records:
            frames = records[(player, level)]
            assert driver.call(5, player, level, frames) == 0, 'equal result replaced best'
            if frames < 0xffffffff:
                assert driver.call(5, player, level, frames + 1) == 0, 'slower result replaced best'
            assert driver.call(5, player, level, 0) == 0, 'zero result accepted'
        for player, level in ((4, 0), (255, 0), (0, 54), (0, 255), (255, 255)):
            assert driver.call(4, player, level) == 0, 'out-of-range lookup'
            assert driver.call(5, player, level, 100) == 0, 'out-of-range record'
        for player in (4, 255):
            driver.call(2, player)
            driver.call(3, player, name='INVALID')
        for name in ('', '          ', 'lowercase', 'BAD!', 'BAD\nNAME'):
            driver.call(3, 3, name=name)
        driver.call(6, 3)
        driver.call(2, 3)
        driver.call(3, 3, name='DELTA')
        driver.state(3, names, records)
        assert close(driver) == image, 'rejected/no-op requests rewrote SRAM'
        checks.append('equal/slower/zero/invalid requests and unchanged names/selections cause no writes')

        driver = boot(image)
        assert driver.call(5, 1, 26, 0x10001) == 1
        records[(1, 26)] = 0x10001
        assert driver.call(5, 1, 26, 0x10000) == 1
        records[(1, 26)] = 0x10000
        driver.call(3, 0, name='  A B 7   ')
        names[0] = 'A B 7'
        driver.call(3, 2, name='1234567890EXTRA')
        names[2] = '1234567890'
        driver.call(2, 1)
        driver.state(1, names, records)
        image = close(driver)
        expect_boot(image, 1, names, records)
        checks.append('faster uint32 results replace best; names trim, retain spaces and cap at ten characters')

        # Build explicit independent reference slots to separate decoding and
        # selection checks from whatever production save_record just wrote.
        older_names = ['OLD ONE', 'OLD TWO', 'OLD THREE', 'OLD FOUR']
        newer_names = ['NEW ONE', 'NEW TWO', 'NEW THREE', 'NEW FOUR']
        older_records, newer_records = {(0, 0): 500, (3, 53): 900}, {(0, 0): 400, (3, 53): 800}
        older = make_slot(10, 1, older_names, older_records)
        newer = make_slot(11, 2, newer_names, newer_records)
        reference = put_slot(put_slot(guarded_image(), 0, older), 1, newer)
        expect_boot(reference, 2, newer_names, newer_records)
        expect_boot(put_slot(put_slot(guarded_image(), 0, newer), 1, older), 2, newer_names, newer_records)
        for offset in (0, 4, 6, 8, 12, 16, 17, 61, 924, 1023):
            damaged = bytearray(newer)
            damaged[offset] ^= 0x40
            expect_boot(put_slot(reference, 1, damaged), 1, older_names, older_records)
        checks.append('newest slot selected in either position; header/payload/reserved/CRC corruption falls back')

        # Valid checksums must not make an unsupported schema or malformed name
        # acceptable. These distinguish semantic validation from CRC rejection.
        for offset, replacement in ((4, b'\x02'), (6, b'\x00\x00'), (16, b'\x04'),
                                    (17, b' '), (17, b'lower'), (17, b'!'),
                                    (17, b'\0'), (17, b'AB \0'),
                                    (17, b'AB\0C'), (17, b'ABCDEFGHIJK')):
            malformed = bytearray(newer)
            malformed[offset:offset + len(replacement)] = replacement
            malformed[12:14] = crc(malformed).to_bytes(2, 'little')
            expect_boot(put_slot(reference, 1, malformed), 1, older_names, older_records)
        checks.append('valid-CRC unsupported versions, lengths, player indices and noncanonical names are rejected')

        # A power cut can leave any prefix of the destination copied, but the
        # destination commit marker remains invalid until the whole CRC is saved.
        torn_cases = 0
        stale = make_slot(9, 0)
        for prefix in (0, 1, 5, 6, 12, 16, 17, 61, 512, 925, 1023, 1024):
            torn = bytearray(newer[:prefix] + stale[prefix:])
            torn[5] = 0
            expect_boot(put_slot(reference, 1, torn), 1, older_names, older_records)
            torn_cases += 1
        expect_boot(put_slot(put_slot(reference, 0, bytes(SLOT_SIZE)), 1, bytes(SLOT_SIZE)))
        checks.append(f'{torn_cases} interrupted destination prefixes recover the previous commit; both invalid slots use defaults')
        driver = boot(put_slot(reference, 1, torn))
        driver.call(2, 3)
        repaired = close(driver)
        assert valid_slot(slot_from(repaired, 1)), 'next write did not repair interrupted destination'
        expect_boot(repaired, 3, older_names, older_records)
        checks.append('write after interrupted commit repairs destination and preserves previous records')

        # Unsigned half-range ordering must regard zero as newer than FFFFFFFF,
        # and a subsequent production commit must advance zero to one.
        rollover = put_slot(put_slot(guarded_image(), 0, make_slot(0xffffffff, 1, older_names, older_records)),
                            1, make_slot(0, 2, newer_names, newer_records))
        expect_boot(rollover, 2, newer_names, newer_records)
        driver = boot(rollover)
        assert driver.call(5, 0, 0, 399) == 1
        wrapped_records = newer_records.copy()
        wrapped_records[(0, 0)] = 399
        rollover = close(driver)
        assert int.from_bytes(slot_from(rollover, 0)[8:12], 'little') == 1
        assert valid_slot(slot_from(rollover, 0))
        expect_boot(rollover, 2, newer_names, wrapped_records)
        checks.append('uint32 generation rollover selects zero after FFFFFFFF and writes generation one')

        for name, contents in sources.items():
            assert (BASE / 'src' / name).read_bytes() == contents, 'production save source changed; rerun'
        report = {'status': 'passed', 'fixture': 'isolated native SM83 module calls; battery-file reboots',
                  'checks': checks, 'fresh_boots': boots, 'hardware_tested': False,
                  'source_sha256': {name: hashlib.sha256(data).hexdigest() for name, data in sources.items()},
                  'rom_sha256': hashlib.sha256(rom.read_bytes()).hexdigest(),
                  'rom_bank': 7, 'restored_caller_banks': [5, 9], 'restored_ram_bank': 0,
                  'save_module_static_wram_bytes': static_wram,
                  'guarded_sram_bytes_per_boot': RAM_SIZE - 2048,
                  'compile_commands': commands}
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
    finally:
        if active is not None:
            active.p.stop(save=False)


if __name__ == '__main__':
    main()
