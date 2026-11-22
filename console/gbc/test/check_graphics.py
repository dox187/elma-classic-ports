"""Verify and time every packed scenery block with the native ZX0 decoder.

Run after ``make build/elma-gbc.gbc``. The helper ROM links the production world_decompress
and the generated graphics banks, checks those banks against --rom, and decodes
each unique manifest pointer into SRAM bank 1. Expected bytes come independently
from every level's tiles.npz, including partial final pattern blocks.
"""

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

import numpy as np
from pyboy import PyBoy

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'tools'))
from zx0 import decompress

DESTINATION = 0xA000
SCRATCH_BANK = 1
MAX_DECODED = 1536
GUARD_SIZE = 16
CANARY = 0xA5
ROWS_PER_BANK = 1600


@dataclass
class Block:
    bank: int
    address: int
    expected: bytes
    kind: str
    level: int
    index: int
    plane: int = None
    references: int = 1

    def location(self):
        location = {'bank': self.bank, 'address': self.address, 'level': self.level,
                    'index': self.index, 'decoded_bytes': len(self.expected)}
        if self.plane is not None:
            location['plane'] = self.plane
        return location


def graphics_profile(manifest):
    profile = manifest.get('pattern_codec'), manifest.get('map_codec'), manifest.get('pattern_block_bytes')
    if profile == ('zx0-512', 'zx0-planes32x16', 512) and manifest.get('map_plane_bytes') == 512:
        return 512, True
    if profile == ('zx0-1024', 'zx0-raw3-plane32x16', 1024) and 'map_plane_bytes' not in manifest:
        return 1024, False
    raise ValueError('Generate matching ZX0 pattern and map graphics before running this check')


def collect_blocks(gen, manifest):
    pattern_size, split_planes = graphics_profile(manifest)
    prefix = manifest.get('decode_cost_prefix_bytes', 0)
    assert prefix in (0, 1)
    unique = {}

    def add(pointer, data, kind, level, index, plane=None):
        bank, address = pointer
        address += prefix
        assert manifest['first_bank'] <= bank <= manifest['last_bank']
        assert 0x4000 <= address < 0x8000 and 0 < len(data) <= MAX_DECODED
        key = bank, address
        if key in unique:
            assert unique[key].expected == data, 'One packed pointer has conflicting expected bytes'
            assert unique[key].kind == kind, 'One packed pointer has conflicting block kinds'
            unique[key].references += 1
        else:
            unique[key] = Block(bank, address, data, kind, level, index, plane)

    for record in manifest['levels']:
        level = record['index'] + 1
        with np.load(gen / 'levels' / f'{level:02d}' / 'tiles.npz') as source:
            patterns = source['patterns'].tobytes()
            assert len(patterns) == record['pattern_count'] * 16
            assert len(record['pattern_blocks']) == (len(patterns) + pattern_size - 1) // pattern_size
            for i, pointer in enumerate(record['pattern_blocks']):
                add(pointer, patterns[i * pattern_size:(i + 1) * pattern_size], 'pattern', level, i)
            ids, attrs = source['ids'], source['attrs']
            assert ids.shape == attrs.shape and ids.shape[0] % 16 == ids.shape[1] % 32 == 0
            chunks = []
            for y in range(0, ids.shape[0], 16):
                for x in range(0, ids.shape[1], 32):
                    cells = ids[y:y + 16, x:x + 32].ravel()
                    chunks.append([(cells & 255).astype(np.uint8).tobytes(),
                                   (cells >> 8).astype(np.uint8).tobytes(),
                                   attrs[y:y + 16, x:x + 32].tobytes()])
            assert len(chunks) == len(record['chunks'])
            for i, (entry, planes) in enumerate(zip(record['chunks'], chunks)):
                assert all(len(data) == 512 for data in planes)
                if split_planes:
                    assert len(entry) == 3, 'Each map chunk must contain three plane pointers'
                    for plane, (pointer, data) in enumerate(zip(entry, planes)):
                        add(pointer, data, 'map', level, i, plane)
                else:
                    add(entry, b''.join(planes), 'map', level, i)
    assert len(manifest['levels']) == manifest['count'] and unique
    return list(unique.values())


def rom_data(rom, pointer, length):
    bank, address = pointer
    assert 0x4000 <= address and address + length <= 0x8000
    offset = bank * 0x4000 + address - 0x4000
    data = rom[offset:offset + length]
    assert len(data) == length, f'ROM is missing bank {bank}'
    return data


def verify_inputs(gen, manifest, blocks, rom):
    _, split_planes = graphics_profile(manifest)
    # Check the directories too: these are the pointers the game actually uses.
    for record in manifest['levels']:
        map_entries = ([pointer for chunk in record['chunks'] for pointer in chunk]
                       if split_planes else record['chunks'])
        for directory, entries in (('patterns', record['pattern_blocks']), ('chunk_directory', map_entries)):
            expected = b''.join(struct.pack('<HH', *pointer) for pointer in entries)
            assert rom_data(rom, record[directory], len(expected)) == expected, (
                f'ROM directory differs from manifest: level {record["index"] + 1}, {directory}')
    for block in blocks:
        packed = rom_data(rom, (block.bank, block.address), 0x8000 - block.address)
        if manifest.get('decode_cost_prefix_bytes'):
            from zx0_cost import decode_cycles, validate_decoder
            assert manifest['decoder_sha256'] == validate_decoder()
            stored = rom_data(rom, (block.bank, block.address - 1), 1)[0]
            assert stored == (decode_cycles(packed, len(block.expected)) + 911) // 912, (
                f'ROM decode cost differs from native model: {block.location()}')
        assert decompress(packed, len(block.expected)) == block.expected, (
            f'Host decode differs from tiles.npz: {block.location()}')
    payloads = {}
    for bank in range(manifest['first_bank'], manifest['last_bank'] + 1):
        source = gen / f'level_bank_{bank}.c'
        initializer = re.search(r'\[\]\s*=\s*\{([^}]*)\}', source.read_text(), re.S)
        assert initializer, f'Cannot read generated array: {source}'
        data = bytes(int(value, 0) for value in re.findall(r'0x[\da-fA-F]+|\d+', initializer[1]))
        assert rom_data(rom, (bank, 0x4000), len(data)) == data, (
            f'Generated bank {bank} differs from --rom; rebuild the game')
        payloads[bank] = data
    return payloads


def build_fixture(gen, out, game_rom, blocks, payloads):
    groups = [blocks[i:i + ROWS_PER_BANK] for i in range(0, len(blocks), ROWS_PER_BANK)]
    assert len(groups) < min(payloads), 'Fixture metadata would overlap graphics banks'
    header = '#include <stdint.h>\ntypedef struct {uint16_t bank,address,length;} block_t;\n'
    sources = []
    for bank, group in enumerate(groups, 1):
        header += f'extern const block_t blocks{bank}[];\n'
        path = out / f'blocks{bank}.c'
        rows = ',\n'.join('{%d,%d,%d}' % (b.bank, b.address, len(b.expected)) for b in group)
        path.write_text(f'#pragma bank {bank}\n#include "blocks.h"\n'
                        f'const block_t blocks{bank}[]={{\n{rows}\n}};\n')
        sources.append(path)
    (out / 'blocks.h').write_text(header)
    driver = '''#include <gb/gb.h>
#include <gb/cgb.h>
#include <string.h>
#include "blocks.h"
void world_decompress(uint16_t,uint16_t,uint8_t,uint16_t) NONBANKED;
block_t current_block;
volatile uint16_t case_id,cases_done;
volatile uint8_t done;
static void run_blocks(const block_t *blocks,uint16_t count) {
    uint16_t i;
    for(i=0;i<count;++i) {
        memcpy(&current_block,blocks+i,sizeof(current_block));
        rRAMB=1;
        memset((void *)0xA000,0xA5,1552);
        rRAMB=0;
        world_decompress(current_block.bank,current_block.address,1,0xA000);
        ++cases_done;
        ++case_id;
    }
}
void main(void) {
    disable_interrupts();
    DISPLAY_OFF;
    cpu_fast();
    ENABLE_RAM;
    rRAMB=0;
    memset((void *)0xA000,0x3C,1552);
'''
    for bank, group in enumerate(groups, 1):
        driver += f'    SWITCH_ROM({bank});run_blocks(blocks{bank},{len(group)});\n'
    driver += '    done=1;\n    while(1) {}\n}\n'
    driver_path = out / 'driver.c'
    driver_path.write_text(driver)
    # The build manifest supplies cached objects only. Byte comparisons below
    # independently reject stale objects, including a cache from another export.
    cached = {}
    build_manifest = game_rom.with_suffix('.build.json')
    if build_manifest.is_file():
        build = json.loads(build_manifest.read_text())
        cached = {Path(source).resolve(): Path(obj)
                  for source, obj in zip(build['sources'], build['objects'])}
    data_sources = []
    reused = 0
    for bank in payloads:
        source = gen / f'level_bank_{bank}.c'
        obj = cached.get(source)
        if obj is not None and obj.is_file():
            data_sources.append(obj)
            reused += 1
        else:
            data_sources.append(source)
    fixture = out / 'check.gbc'
    command = [BASE / '.toolchain/gbdk/bin/lcc', '-msm83:gb', '-Wf--opt-code-size',
               '-Wf--max-allocs-per-node', '-Wf100000', '-Wm-yC', '-Wm-yt0x1A',
               '-Wm-ya4', '-Wm-yo256', '-Wl-m', '-Wl-j', '-I' + str(out),
               '-o', fixture, driver_path, BASE / 'src/world_decompress.c', BASE / 'src/world_zx0.s',
               *sources, *data_sources]
    result = subprocess.run(list(map(str, command)), capture_output=True, text=True)
    (out / 'compile.log').write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError('Fixture build failed:\n' + result.stdout + result.stderr)
    linked = fixture.read_bytes()
    for bank, data in payloads.items():
        assert rom_data(linked, (bank, 0x4000), len(data)) == data, (
            f'Helper bank {bank} differs from the game; rebuild stale graphics objects')
    return fixture, linked, reused


def check_native(fixture, linked, blocks):
    symbols = {name: int(address, 16) for name, address in re.findall(
        r'DEF (_\w+) 0x([0-9a-fA-F]+)', fixture.with_suffix('.noi').read_text())}
    assert symbols['_world_decompress'] < 0x4000, 'Decoder wrapper must execute from ROM0'
    p = PyBoy(str(fixture), window='null', sound_emulated=False, cgb=True)
    p.set_emulation_speed(0)
    pending = None
    return_hooks = set()
    timings = []

    def number(name, size=2):
        address = symbols['_' + name]
        return int.from_bytes(bytes(p.memory[address:address + size]), 'little')

    def observe_cycles():
        # CPU T-cycles are monotonic even with the LCD off and cpu_fast enabled.
        return p._cycles()

    def returned(_):
        nonlocal pending
        assert pending is not None, 'Return without a decoder entry'
        case, start, bank = pending
        cycles = observe_cycles() - start
        block = blocks[case]
        size = len(block.expected)
        actual = bytes(p.memory[SCRATCH_BANK, DESTINATION:DESTINATION + MAX_DECODED + GUARD_SIZE])
        assert actual[:size] == block.expected, f'Native bytes differ: {block.location()}'
        assert actual[size:] == bytes([CANARY]) * (len(actual) - size), (
            f'Decoder overwrote trailing guards: {block.location()}')
        assert p.memory[symbols['__current_bank']] == bank, 'CURRENT_BANK was not restored'
        assert bytes(p.memory[0x4000:0x4020]) == rom_data(linked, (bank, 0x4000), 32), (
            'Hardware ROM bank was not restored')
        assert bytes(p.memory[DESTINATION:DESTINATION + MAX_DECODED + GUARD_SIZE]) == (
            bytes([0x3C]) * (MAX_DECODED + GUARD_SIZE)), 'SRAM bank 0 was modified or not restored'
        assert cycles > 0
        timings.append(cycles)
        pending = None

    def entered(_):
        nonlocal pending
        assert pending is None, 'Nested decoder entry'
        case = number('case_id')
        assert case == len(timings) < len(blocks), 'Unexpected decoder call order'
        block = blocks[case]
        row = symbols['_current_block']
        assert bytes(p.memory[row:row + 6]) == struct.pack('<HHH', block.bank, block.address,
                                                        len(block.expected))
        assert not p.memory[0xFF40] & 0x80 and p.memory[0xFF4D] & 0x80, (
            'Timing fixture must have LCD off and CGB double speed enabled')
        bank = p.memory[symbols['__current_bank']]
        assert bank == 1 + case // ROWS_PER_BANK
        sp = p.register_file.SP
        address = p.memory[sp] | (p.memory[sp + 1] << 8)
        assert address < 0x4000, 'Decoder caller must execute from ROM0'
        if address not in return_hooks:
            p.hook_register(0, address, returned, None)
            return_hooks.add(address)
        pending = case, observe_cycles(), bank

    p.hook_register(0, symbols['_world_decompress'], entered, None)
    try:
        # The cap catches a missing terminator or broken native return without
        # allowing a corrupt stream to keep the check running indefinitely.
        for _ in range(2000):
            p.tick(100, False)
            if number('done', 1):
                break
        else:
            raise AssertionError(f'Native decoder timed out after {len(timings)} blocks')
        assert pending is None and number('cases_done') == len(blocks) == len(timings)
    finally:
        p.stop(save=False)
    report = {}
    for kind in ('pattern', 'map'):
        cases = [(b, cycles) for b, cycles in zip(blocks, timings) if b.kind == kind]
        worst, maximum = max(cases, key=lambda item: item[1])
        report[kind] = {'calls': len(cases), 'min': min(c for _, c in cases), 'max': maximum,
                        'mean': sum(c for _, c in cases) / len(cases),
                        'worst_block': worst.location(),
                        'decoded_sizes': dict(sorted(Counter(len(b.expected) for b, _ in cases).items()))}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, default=BASE / 'build/elma-gbc.gbc')
    parser.add_argument('--gen', type=Path, default=BASE / 'build/gen')
    parser.add_argument('--out', type=Path, default=BASE / 'build/graphics-block-check')
    args = parser.parse_args()
    gen, game_rom, out = args.gen.resolve(), args.rom.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((gen / 'level_manifest.json').read_text())
    blocks = collect_blocks(gen, manifest)
    rom = game_rom.read_bytes()
    payloads = verify_inputs(gen, manifest, blocks, rom)
    print(f'Checking {len(blocks)} unique ZX0 blocks from {manifest["count"]} levels', flush=True)
    fixture, linked, reused = build_fixture(gen, out, game_rom, blocks, payloads)
    timing = check_native(fixture, linked, blocks)
    # Leave the rest of world.c's cold-work allowance for directory reads,
    # cache bookkeeping, strip gathering, interrupts and the caller margin.
    _, split_planes = graphics_profile(manifest)
    limits = {'pattern': 100000, 'map': 100000} if split_planes else {'pattern': 190000, 'map': 220000}
    for kind, limit in limits.items():
        assert timing[kind]['max'] <= limit, f'{kind.title()} decoder exceeds its preparation budget'
    report = {'rom': str(game_rom), 'rom_sha256': hashlib.sha256(rom).hexdigest(),
              'levels': manifest['count'], 'references': sum(b.references for b in blocks),
              'unique_blocks': len(blocks), 'verified_blocks': len(blocks),
              'graphics_banks': [min(payloads), max(payloads)], 'cached_objects': reused,
              'decoded_bytes': sum(len(b.expected) for b in blocks),
              'guard_failures': 0, 'bank_failures': 0,
              'pattern_codec': manifest['pattern_codec'], 'map_codec': manifest['map_codec'],
              'pattern_block_bytes': manifest['pattern_block_bytes'],
              'map_plane_bytes': manifest.get('map_plane_bytes'), 'decode_cycle_limits': limits,
              'timing_unit': 'CPU T-cycles at CGB double speed, function entry through return',
              'timing': timing}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
