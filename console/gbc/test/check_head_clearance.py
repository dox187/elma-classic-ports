"""Check all emitted 1 m head masks against all finite edges in each shipped map."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import re
import struct

from pyboy import PyBoy
from check_physics_sweep import oracle

def contents(path):
    return bytes(map(int, path.read_bytes().split(b'={', 1)[1].split(b'}', 1)[0].split(b',')))


def native_masks(rom, levels):
    symbols = {name: int(value, 16) for name, value in
               re.findall(r'^DEF (\S+) 0x([0-9a-fA-F]+)$', rom.with_suffix('.noi').read_text(), re.M)}
    image = bytearray(rom.read_bytes())
    main = symbols['_main']
    image[main:main+3] = bytes((0xf3, 0x18, 0xfe))  # Boot through CRT, disable interrupts and wait.
    emu = PyBoy(BytesIO(image), window='null', cgb=True, sound_emulated=False)
    emu.set_emulation_speed(0)
    try:
        emu.tick(200, False)
        assert emu.register_file.PC == main + 1
        memory = emu.memory
        memory[0] = 0x0a
        memory[0x4000] = 0
        memory[0x2000] = 4
        memory[symbols['__current_bank']] = 4
        # Inspect a ROM-window byte that distinguishes the caller from both
        # dictionary banks and every intermediate high/low MBC5 selection.
        offset = next(i for i in range(16384)
                      if all(image[4*16384+i] != image[b*16384+i] for b in (250, 251, 260, 506, 507)))
        # Run a batch below the test stack in WRAM. SRAM contains x,y,mask_lo,mask_hi records,
        # followed by FE. HL advances through the batch across each C ABI call.
        start = 0xdf00
        code = bytearray((0x21, 0, 0xa0))  # ld hl,$a000
        loop = len(code)
        code.extend((0x2a, 0xfe, 0xfe, 0x28, 0))  # ld a,(hl+); cp $fe; jr z,done
        success_branch = len(code)-1
        code.extend((0x5e, 0x23, 0xe5, 0xcd))     # ld e,(hl); inc hl; push hl; call
        code.extend(struct.pack('<H', symbols['_riding_head_cell_mask'] & 65535))
        code.extend((0xe1, 0x2a, 0xb9, 0x20, 0))  # pop hl; ld a,(hl+); cp c; jr nz,fail
        fail_branches = [len(code)-1]
        code.extend((0x2a, 0xb8, 0x20, 0))        # ld a,(hl+); cp b; jr nz,fail
        fail_branches.append(len(code)-1)
        for addr, expected in ((symbols['__current_bank'], 4), (16384+offset, image[4*16384+offset])):
            code.extend((0xfa, *struct.pack('<H', addr), 0xfe, expected, 0x20, 0))
            fail_branches.append(len(code)-1)
        code.extend((0x18, (loop-len(code)-2) & 255))
        fail = len(code)
        code.extend((0x18, 0xfe))
        done = len(code)
        code.extend((0x18, 0xfe))
        code[success_branch] = done-success_branch-1
        for i in fail_branches:
            code[i] = fail-i-1
        memory[start:start+len(code)] = list(code)
        total = 0
        for index, records in levels:
            memory[symbols['_physics_level_index']] = index
            batch = b''.join(struct.pack('<BBH', *row) for row in records) + bytes((0xfe,))
            assert len(batch) <= 8192
            memory[0xa000:0xa000+len(batch)] = list(batch)
            regs = emu.register_file
            regs.PC, regs.SP = start, 0xdff0
            for _ in range(80):
                emu.tick(1, False)
                if regs.PC in (start+done, start+fail):
                    break
            assert regs.PC == start+done and regs.SP == 0xdff0, (index, hex(regs.PC), hex(regs.HL), regs.A, regs.B, regs.C)
            total += len(records)
        return total
    finally:
        emu.stop(save=False)


def check(gen, rom=None):
    manifest = json.loads((gen / 'physics_bank_manifest.json').read_text())
    banks = {b: contents(gen / f'physics_bank_{b}.c') for b in manifest['banks']}
    masks = {int(p.stem.rsplit('_', 1)[1]): contents(p) for p in gen.glob('physics_head_bank_*.c')}
    metadata = (gen / 'physics_head_map.c').read_text()
    row_tables = {int(i): list(map(int, rows.split(','))) for i, rows in
                  re.findall(r'head_row_(\d+)\[\]=\{([\d,]+)\};', metadata)}
    descriptors = re.findall(r'^ \{(\d+),(\d+),head_row_(\d+),(\d+),(\d+),0\},$', metadata, re.M)
    assert len(descriptors) == len(manifest['levels'])
    total = occupied = segments = 0
    native_levels = []
    for level, desc in zip(manifest['levels'], descriptors):
        w, h, table, patterns, bank = map(int, desc)
        stride = (w + 3) // 4
        rows = row_tables[table]
        assert len(rows) == h and all(b - a == stride for a, b in zip(rows, rows[1:]))
        assert (w, h) == tuple(level['grid']) and stride == (w + 3) // 4
        edges = set()
        def visit(ptr_bank, ptr, cx, cy):
            addr, delta, count = struct.unpack_from('<HBB', banks[ptr_bank], ptr - 16384)
            bank_data = level['base_bank'] + delta
            if count == 255:
                for i in range(16):
                    visit(bank_data, addr + 4*i, cx, cy)
            else:
                for i in range(count):
                    x, y, dx, dy = struct.unpack_from('<4h', banks[bank_data], addr - 16384 + 18*i)
                    edges.add((cx*4096 + x, cy*4096 + y, dx, dy))
        for cy in range(h):
            for cx in range(w):
                visit(level['directory_bank'], level['directory_address'] + 4*(cy*w+cx), cx, cy)
        segments += len(edges)
        # Compare with the union of every segment in the level, independently
        # of the 4 m directory and its dense 1 m child selection. Intersect
        # the segment capsule with each of the four edges of the closed tile;
        # also cover a segment lying wholly inside the tile.
        wanted = set()
        for ax, ay, dx, dy in edges:
            bx, by = ax+dx, ay+dy
            for ty in range(max(0, (min(ay, by)-244)//1024), min(4*h, (max(ay, by)+244)//1024+1)):
                for tx in range(max(0, (min(ax, bx)-244)//1024), min(4*w, (max(ax, bx)+244)//1024+1)):
                    if (tx, ty) in wanted:
                        continue
                    x, y = tx*1024, ty*1024
                    corners = ((x, y), (x+1024, y), (x+1024, y+1024), (x, y+1024))
                    if (x <= ax <= x+1024 and y <= ay <= y+1024 or
                            any(oracle((*corners[i], *corners[(i+1) % 4], ax, ay, dx, dy, 244))
                                for i in range(4))):
                        wanted.add((tx, ty))
        data = masks[256 + bank]
        actual = set()
        records = []
        for cy in range(h):
            for cx in range(w):
                group = data[rows[cy] - 16384 + cx//4]
                mask = struct.unpack_from('<H', data, patterns - 16384 + group*8 + (cx%4)*2)[0]
                records.append((cx, cy, mask))
                actual.update((cx*4+t%4, cy*4+t//4) for t in range(16) if mask & (1 << t))
        assert actual == wanted, (level['index'], list(actual ^ wanted)[:8])
        records += [records[-1], records[0], records[0], (w, 0, 65535), (0, h, 65535), (255, 255, 65535)]
        native_levels.append((level['index'], records))
        total += w*h*16
        occupied += len(actual)
    report = {'levels': len(descriptors), 'distinct_edges_by_level': segments, 'tiles': total,
            'occupied': occupied, 'certified_clear': total - occupied}
    if rom:
        native_levels.extend((index, [(0, 0, 65535)]) for index in (len(descriptors), 255))
        report['native_masks_and_bank_restores'] = native_masks(rom, native_levels)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gen', type=Path, required=True)
    parser.add_argument('--rom', type=Path, help='also verify the linked SM83 reader and MBC5 bank restoration')
    args = parser.parse_args()
    print(json.dumps(check(args.gen, args.rom)))
