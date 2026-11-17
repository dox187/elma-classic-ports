"""Compare the ZX0 cycle model with native SM83 execution of every packed block.

Uses check_graphics' independent tiles.npz expectations, host decoder, directory
checks and generated-bank comparisons. The small fixture calls zx0_decompress
directly with interrupts/LCD disabled and double speed enabled. Generated ROM
payloads are copied byte-for-byte into the fixture after linking; no production
files or generated banks are modified. Also exercises synthetic boundary cases.
"""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import random
import re
import subprocess
import sys

from pyboy import PyBoy

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'tools'))
from zx0 import decompress
from zx0_cost import DECODER_SHA256, analyze, copy_cycles, validate_decoder
import check_graphics as graphics


def synthetic_vectors(sdk, out, bank):
    vectors = []
    random_source = random.Random(1979)
    for size in (1, 2, 3, 16, 255, 256, 257, 511, 512, 513, 1024, 1536):
        vectors.append((f'repeat-{size}', bytes([0xA9]) * size))
        vectors.append((f'literal-{size}', random_source.randbytes(size)))
    vectors += [('overlap', b'abacaba' * 73 + b'a'),
                ('alternating', bytes(range(128)) * 4)]
    payload = bytearray()
    blocks = []
    for index, (name, raw) in enumerate(vectors):
        source, packed = out / (name + '.raw'), out / (name + '.zx0')
        source.write_bytes(raw)
        subprocess.run([str(sdk / 'bin/gbcompress'), '--alg=zx0', str(source), str(packed)],
                       check=True, capture_output=True)
        data = packed.read_bytes()
        assert decompress(data, len(raw)) == raw
        assert analyze(data, len(raw)).compressed_bytes == len(data)
        blocks.append(graphics.Block(bank, 0x4000 + len(payload), raw, 'synthetic', 0, index))
        payload.extend(data)
    assert len(payload) < 0x4000
    return blocks, bytes(payload)


def build_fixture(out, sdk, decoder, blocks, payloads):
    groups = [blocks[i:i + 1600] for i in range(0, len(blocks), 1600)]
    assert len(groups) < min(payloads)
    header = '#include <stdint.h>\ntypedef struct {uint16_t bank,address,length;} block_t;\n'
    sources = []
    for bank, group in enumerate(groups, 1):
        header += f'extern const block_t blocks{bank}[];\n'
        source = out / f'blocks{bank}.c'
        rows = ',\n'.join('{%d,%d,%d}' % (b.bank, b.address, len(b.expected)) for b in group)
        source.write_text(f'#pragma bank {bank}\n#include "blocks.h"\n'
                          f'const block_t blocks{bank}[]={{\n{rows}\n}};\n')
        sources.append(source)
    (out / 'blocks.h').write_text(header)
    driver = '''#include <gb/gb.h>
#include <gb/cgb.h>
#include <gbdk/zx0decompress.h>
#include <string.h>
#include "blocks.h"
block_t current_block;
volatile uint16_t case_id,cases_done;
volatile uint8_t done;
static void run_blocks(const block_t *blocks,uint16_t count) {
    uint16_t i;
    uint8_t previous=CURRENT_BANK;
    for(i=0;i<count;++i) {
        memcpy(&current_block,blocks+i,sizeof(current_block));
        memset((void *)0xA000,0xA5,1552);
        SWITCH_ROM_MBC5_8M(current_block.bank);
        zx0_decompress((void *)current_block.address,(void *)0xA000);
        SWITCH_ROM_MBC5_8M(previous);
        ++cases_done;
        ++case_id;
    }
}
void main(void) {
    disable_interrupts();
    DISPLAY_OFF;
    cpu_fast();
    ENABLE_RAM;
    rRAMB=1;
'''
    for bank, group in enumerate(groups, 1):
        driver += f'    SWITCH_ROM({bank});run_blocks(blocks{bank},{len(group)});\n'
    driver += '    done=1;\n    while(1) {}\n}\n'
    source = out / 'driver.c'
    source.write_text(driver)
    # Snapshot the hash-checked decoder so compilation cannot touch src/.
    assembly = out / 'world_zx0.s'
    assembly.write_bytes(decoder.read_bytes())
    validate_decoder(assembly)
    fixture = out / 'check.gbc'
    command = [sdk / 'bin/lcc', '-msm83:gb', '-Wf--opt-code-size',
               '-Wm-yC', '-Wm-yt0x1A', '-Wm-ya4', '-Wm-yo256', '-Wl-m', '-Wl-j',
               '-I' + str(out), '-o', fixture, source, assembly, *sources]
    result = subprocess.run(list(map(str, command)), capture_output=True, text=True, cwd=out)
    (out / 'compile.log').write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError('Native fixture build failed: ' + result.stdout + result.stderr)
    linked = bytearray(fixture.read_bytes())
    for bank, data in payloads.items():
        assert bank > len(groups) and len(data) <= 0x4000
        linked[bank * 0x4000:bank * 0x4000 + len(data)] = data
    # Keep the global cartridge checksum valid after inserting the test data.
    linked[0x14E:0x150] = bytes(2)
    linked[0x14E:0x150] = (sum(linked) & 65535).to_bytes(2, 'big')
    fixture.write_bytes(linked)
    for bank, data in payloads.items():
        assert graphics.rom_data(linked, (bank, 0x4000), len(data)) == data
    return fixture, bytes(linked)


def check_native(fixture, blocks, estimates):
    symbols = {name: int(address, 16) for name, address in re.findall(
        r'DEF (_\w+) 0x([0-9a-fA-F]+)', fixture.with_suffix('.noi').read_text())}
    p = PyBoy(str(fixture), window='null', sound_emulated=False, cgb=True)
    p.set_emulation_speed(0)
    pending = None
    hooked = set()
    timings = []

    def number(name, size=2):
        address = symbols['_' + name]
        return int.from_bytes(bytes(p.memory[address:address + size]), 'little')

    def returned(_):
        nonlocal pending
        assert pending is not None
        index, start = pending
        measured = p._cycles() - start
        block = blocks[index]
        actual = bytes(p.memory[1, 0xA000:0xA000 + 1552])
        size = len(block.expected)
        assert actual[:size] == block.expected, ('Native output differs', block.location())
        assert actual[size:] == bytes([0xA5]) * (1552 - size), ('Guard overwrite', block.location())
        assert measured == estimates[index].cycles, (
            'Cycle estimate differs', index, block.location(), estimates[index].cycles, measured)
        timings.append(measured)
        pending = None

    def entered(_):
        nonlocal pending
        assert pending is None
        index = number('case_id')
        assert index == len(timings) < len(blocks)
        assert not p.memory[0xFF40] & 0x80 and p.memory[0xFF4D] & 0x80
        sp = p.register_file.SP
        address = p.memory[sp] | (p.memory[sp + 1] << 8)
        assert address < 0x4000
        if address not in hooked:
            p.hook_register(0, address, returned, None)
            hooked.add(address)
        pending = index, p._cycles()

    p.hook_register(0, symbols['_zx0_decompress'], entered, None)
    try:
        for _ in range(2000):
            p.tick(100, False)
            if number('done', 1):
                break
        else:
            raise AssertionError(f'Native decoder timed out after {len(timings)} blocks')
        assert pending is None and number('cases_done') == len(blocks) == len(timings)
    finally:
        p.stop(save=False)
    return timings


def focused_checks(out, decoder):
    changed = out / 'changed_decoder.s'
    changed.write_bytes(decoder.read_bytes() + b'\n; changed\n')
    try:
        validate_decoder(changed)
    except ValueError:
        pass
    else:
        raise AssertionError('Changed decoder was accepted')
    # Count register transitions throughout the current output-size range and at
    # every 512-byte boundary up to 65535, without using the closed form.
    lengths = sorted(set(range(1, 1537)) | {512 * k + d for k in range(1, 128) for d in (-1, 0, 1)} | {65535})
    for count in lengths:
        b, c = (count >> 9) + 1, ((count >> 1) + 1) & 255
        actual = 8 + 8 + 4 + 4
        remaining = count
        if count & 1:
            actual += 12 + 24
            remaining -= 1
        else:
            actual += 8 + 12
        while True:
            c = (c - 1) & 255
            actual += 4
            if c:
                actual += 12
            else:
                actual += 8 + 4
                b -= 1
                if not b:
                    actual += 8 + 16
                    break
                actual += 12
            actual += 48
            remaining -= 2
        assert remaining == 0 and actual == copy_cycles(count), count
    return {'source_hash_guard': True, 'copy_lengths_checked': len(lengths)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, default=BASE / 'build/elma-gbc-v0.91-4m.gbc')
    parser.add_argument('--gen', type=Path, default=BASE / 'build/gen')
    parser.add_argument('--sdk', type=Path, default=BASE / '.toolchain/gbdk')
    parser.add_argument('--decoder', type=Path, default=BASE / 'src/world_zx0.s')
    parser.add_argument('--out', type=Path, default=BASE / 'build/zx0-cycle-check')
    args = parser.parse_args()
    gen, out, sdk, decoder = (p.resolve() for p in (args.gen, args.out, args.sdk, args.decoder))
    out.mkdir(parents=True, exist_ok=True)
    validate_decoder(decoder)
    manifest = json.loads((gen / 'level_manifest.json').read_text())
    blocks = graphics.collect_blocks(gen, manifest)
    production_count = len(blocks)
    rom = args.rom.read_bytes()
    payloads = graphics.verify_inputs(gen, manifest, blocks, rom)
    synthetic, payload = synthetic_vectors(sdk, out, 1 + (len(blocks) + 26 + 1599) // 1600)
    blocks.extend(synthetic)
    payloads[synthetic[0].bank] = payload
    fixture, linked = build_fixture(out, sdk, decoder, blocks, payloads)
    estimates = []
    for block in blocks:
        stream = graphics.rom_data(linked, (block.bank, block.address), 0x8000 - block.address)
        assert decompress(stream, len(block.expected)) == block.expected
        estimate = analyze(stream, len(block.expected), decoder)
        # Exact consumed bytes remain a valid independent stream; a truncated
        # stream must not obtain a successful estimate.
        consumed = stream[:estimate.compressed_bytes]
        assert decompress(consumed, len(block.expected)) == block.expected
        try:
            analyze(consumed[:-1], len(block.expected), decoder)
        except ValueError:
            pass
        else:
            raise AssertionError('Truncated stream was accepted')
        estimates.append(estimate)
    print(f'Timing {production_count} production and {len(synthetic)} synthetic streams', flush=True)
    timings = check_native(fixture, blocks, estimates)
    report = {'decoder_sha256': DECODER_SHA256,
              'rom_sha256': hashlib.sha256(rom).hexdigest(),
              'production_streams': production_count, 'synthetic_streams': len(synthetic),
              'timing_unit': 'CPU T-cycles, _zx0_decompress entry through return, IRQ disabled',
              'max_absolute_deviation': max(abs(t - e.cycles) for t, e in zip(timings, estimates)),
              'undercounts': sum(e.cycles < t for t, e in zip(timings, estimates)),
              'checks': focused_checks(out, decoder), 'timing': {}}
    for kind in ('pattern', 'map', 'synthetic'):
        cases = [(b, t) for b, t in zip(blocks, timings) if b.kind == kind]
        ordered = sorted(t for _, t in cases)
        report['timing'][kind] = {'count': len(cases), 'min': ordered[0], 'max': ordered[-1],
                                  'median': ordered[len(ordered) // 2],
                                  'mean': sum(ordered) / len(ordered),
                                  'worst': max(cases, key=lambda x: x[1])[0].location()}
    rows = [dict(b.location(), kind=b.kind, references=b.references,
                 native_cycles=t, **asdict(e)) for b, t, e in zip(blocks, timings, estimates)]
    (out / 'cycles.json').write_text(json.dumps(rows, indent=2) + '\n')
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
