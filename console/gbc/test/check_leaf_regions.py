"""Compare repeated 64-unit wheel queries with the linked original ordered iterator."""
import argparse
from collections import Counter
from io import BytesIO
import json
from pathlib import Path
import random
import re
import struct

from pyboy import PyBoy
from check_wheel_terrain import leaves


class Iterator:
    def __init__(self, rom):
        self.symbols = {name: int(value, 16) for name, value in re.findall(
            r'^DEF (\S+) 0x([0-9A-Fa-f]+)$', rom.with_suffix('.noi').read_text(), re.M)}
        self.image = bytearray(rom.read_bytes())
        self.image[0x100:0x102] = bytes([0x18, 0xfe])
        self.p = PyBoy(BytesIO(self.image), window='null', sound_emulated=False, cgb=True)
        self.p.set_emulation_speed(0)
        self.p.tick(240, False)
        self.p.memory[0xff0f] = self.p.memory[0xffff] = 0

    def call(self, symbol, x=0, y=0, a=0, stack_byte=None):
        memory, regs = self.p.memory, self.p.register_file
        pc, sp = 0xc900, 0xcf80
        address = self.symbols[symbol] & 65535
        code = [0xf3]
        if stack_byte is not None:
            code += [0x06, stack_byte, 0xc5, 0x33]  # push BC and discard C.
        code += [0xcd, address & 255, address >> 8, 0x18, 0xfe]
        memory[pc:pc+len(code)] = code
        done = pc+len(code)-2
        memory[0x2000] = memory[self.symbols['__current_bank']] = 9
        regs.PC, regs.SP, regs.A = pc, sp, a
        regs.D, regs.E, regs.B, regs.C = x >> 8, x & 255, y >> 8, y & 255
        for _ in range(12):
            self.p.tick(1, False)
            if regs.PC == done: break
        assert regs.PC == done and regs.SP == sp
        assert memory[self.symbols['__current_bank']] == 9
        assert bytes(memory[0x4000:0x4010]) == self.image[9*16384:9*16384+16]
        return regs.A

    def install(self, records):
        # The two ROMs use identical WRAM fixture addresses. Reuse the same
        # address across different leaves and explicitly exercise reset.
        self.call('_physics_collision_reset')
        self.p.memory[0xc400:0xc400+len(records)*18] = b''.join(
            struct.pack('<6hH4B', *r) for r in records)

    def leaf_entry(self, x, y, start, count):
        key = struct.pack('<BBH', (x//64+128)&255, (y//64+128)&255, 0xc400+18*start)
        base, memory = self.symbols['_riding_leaf_regions'], self.p.memory
        entries = [slot for slot in range(base,base+128,32)
                   if memory[slot+4] and memory[slot+13] == count and bytes(memory[slot:slot+4]) == key]
        assert len(entries) == 1, (x,y,start,count,entries)
        return entries[0]

    def query(self, x, y, start, count, seed):
        s, memory = self.symbols, self.p.memory
        cursor, left, ct = s['_Seg_cur'], s['_Seg_left'], s['_Ct']
        memory[cursor:cursor+2] = struct.pack('<H', 0xc400+start*18)
        memory[left] = count
        memory[ct:ct+20] = seed
        n = self.call('_riding_contacts_loop', x, y)
        return n, bytes(memory[ct:ct+20]), bytes(memory[cursor:cursor+2]), memory[left]


def check_invalidation(current, old, levels):
    # Leave a warm plane at this WRAM pointer, replace its bytes with an
    # opposite normal, and exercise both reset and a full FIFO rotation.
    record = (0,32,1024,0,16384,0,1024,128,160,128,145)
    replacement = (1024,32,-1024,0,-16384,0,1024,128,160,128,145)
    for machine in (current, old):
        machine.call('_physics_collision_select', a=0)
        machine.install([record])
    seed = bytes(range(20))
    def agree():
        got = current.query(128,32,0,1,seed)
        assert got == old.query(128,32,0,1,seed) and got[0] == 1
        return got[1]
    before = agree()
    assert agree() == before
    cells = []
    desc = levels[0]
    for cy in range(desc['grid'][1]):
        for cx in range(desc['grid'][0]):
            subs = leaves(old.image,desc,cx,cy)
            sub = next((i for i, records in enumerate(subs) if records), None)
            if sub is not None: cells.append((cx,cy,sub))
            if len(cells) == 4: break
        if len(cells) == 4: break
    assert len(cells) == 4
    for machine in (current,old):
        for cx,cy,sub in cells:
            machine.call('_seg_query', x=cy, a=cx, stack_byte=sub)
        machine.p.memory[0xc400:0xc412] = struct.pack('<6hH4B',*replacement)
    assert current.p.memory[current.symbols['_riding_leaf_regions_dirty']]
    after = agree()
    assert after != before and agree() == after
    for machine in (current,old):
        machine.call('_physics_collision_select', a=1)
        machine.p.memory[0xc400:0xc412] = struct.pack('<6hH4B',*record)
    assert current.p.memory[current.symbols['_riding_leaf_regions_dirty']]
    assert agree() == before



def check_ambiguous_windows(current, old):
    # Box-rejected guards before and after contributors exercise both cursor
    # outcomes. Distinct initial Ct bytes expose any enlarged copy on a hit.
    empty = (0,0,1024,0,16384,0,1024,0,0,0,0)
    def plane(py):
        return (0,py,1024,0,16384,0,1024,128,145,128,145)
    def cross(px):
        return (px,0,0,1024,0,16384,1024,128,145,128,145)
    rng = random.Random(0x9628)
    checks = 0
    for geometries in ((plane(500),plane(500)), (plane(960),plane(500)), (plane(128),plane(640)),
                       (plane(128),cross(640)), (plane(960),cross(960))):
        records = [empty, *geometries, empty, empty, empty]
        for machine in (current,old):
            machine.install(records)
        for start,count in ((0,6),(0,5),(1,4),(0,6)):
            for x,y in ((480,480),(480,480),(480,480),(480,480),(481,481),
                        (481,481),(496,494),(496,494),(480,480),(480,480)):
                seed = rng.randbytes(20)
                actual = current.query(x,y,start,count,seed)
                assert actual == old.query(x,y,start,count,seed), (geometries,x,y,start,count,actual)
                checks += 1
            slot = current.leaf_entry(x,y,start,count)
            assert current.p.memory[slot+16] == 2, (geometries,start,count)
    return checks

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--gen', type=Path, required=True)
    args = parser.parse_args()
    current, old = Iterator(args.rom), Iterator(args.reference)
    rng = random.Random(0x9626)
    levels = json.loads((args.gen/'physics_bank_manifest.json').read_text())['levels']
    counts, kinds = Counter(), Counter()
    try:
        check_invalidation(current, old, levels)
        ambiguous_checks = check_ambiguous_windows(current, old)
        for level in levels:
            w, h = level['grid']
            selected = 0
            cells = list(range(w*h))
            rng.shuffle(cells)
            for n in cells:
                groups = leaves(old.image, level, n%w, n//w)
                sub = rng.randrange(16)
                records = groups[sub]
                if not records: continue
                for machine in (current, old): machine.install(records)
                for _ in range(3):
                    # Choose a box intersecting one real record when possible.
                    r = rng.choice(records)
                    lo_x = max(16*(sub%4), r[7]-128)
                    hi_x = min(16*(sub%4)+15, r[8]-128)
                    lo_y = max(16*(sub//4), r[9]-128)
                    hi_y = min(16*(sub//4)+15, r[10]-128)
                    if hi_x<lo_x or hi_y<lo_y: continue
                    bx, by = rng.randint(lo_x,hi_x), rng.randint(lo_y,hi_y)
                    # Switch the count on an otherwise identical pointer/key.
                    for count in dict.fromkeys((len(records), min(2,len(records)))):
                        start = rng.randrange(len(records)-count+1)
                        for xo,yo in ((31,32),(0,0),(63,63),(0,63),(63,0),(31,32)):
                            x,y = bx*64+xo,by*64+yo
                            seed = rng.randbytes(20)
                            expected = old.query(x,y,start,count,seed)
                            actual = current.query(x,y,start,count,seed)
                            assert actual == expected, (level['name'], x,y, start,count, actual,expected)
                            counts[actual[0]] += 1
                            entry = current.leaf_entry(x,y,start,count)
                            kinds[current.p.memory[entry+4]] += 1
                selected += 1
                if selected == 18: break
    finally:
        current.p.stop(save=False)
        old.p.stop(save=False)
    assert all(counts[n] for n in (0, 1, 2)) and all(kinds[n] for n in (1, 2, 3, 12))
    # Unit-Y retains the low three kind bits when its plane distance is cached.
    assert kinds[5] + kinds[13] > 0
    print(f'{ambiguous_checks} ambiguous queries, {sum(counts.values())} catalog queries, counts {dict(counts)}, cache kinds {dict(kinds)}')


if __name__ == '__main__':
    main()
