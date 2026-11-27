"""Compare each linked radial atlas entry with the original cartridge integer kernel."""
import argparse
import math
from collections import Counter
from io import BytesIO
from pathlib import Path
import re
import struct

from pyboy import PyBoy


class Cartridge:
    def __init__(self, rom):
        self.sym = {k:int(v,16) for k,v in re.findall(r'^DEF (\S+) 0x(\w+)$',rom.with_suffix('.noi').read_text(),re.M)}
        image = bytearray(rom.read_bytes())
        main = self.sym['_main']
        image[main:main+3] = bytes((0xf3,0x18,0xfe))
        self.p = PyBoy(BytesIO(image),window='null',sound_emulated=False,cgb=True)
        self.p.set_emulation_speed(0)
        self.p.tick(220,False)
        self.m,self.reg = self.p.memory,self.p.register_file
        self.m[0xffff] = self.m[0xff0f] = 0
        # The solver uses work RAM for its own key and normalized contact.
        # Keep the guarded output independent of each cartridge's linker layout.
        self.m[0x0000], self.m[0x4000] = 0x0a, 0
        self.m[0x2000],self.m[0x3000],self.m[self.sym['__current_bank']] = 9,0,9
        self.signature = image[9*16384:9*16384+32]
        self.image = image
        self.stack,self.code = 0xdf00,0xdfe0

    def call(self, name, x, y, dest, d2=0, irq=False):
        addr = self.sym[name]
        if name in ('_riding_normal_fast', '_riding_normal_physical'):
            args = struct.pack('<hhiH',x,y,d2,dest)
        else:
            args = bytes(range(10))
        self.m[self.stack:self.stack+10] = args
        pattern = bytes((19*j+x-y)&255 for j in range(22))
        self.m[dest-8:dest+14] = pattern
        code = bytes((0xfb if irq else 0xf3,0,0xcd,addr&255,(addr>>8)&255,0xf3,0x18,0xfe))
        self.m[self.code:self.code+len(code)] = code
        self.reg.PC,self.reg.SP = self.code,self.stack
        self.reg.D,self.reg.E,self.reg.B,self.reg.C = (x>>8)&255,x&255,(y>>8)&255,y&255
        self.reg.HL = dest
        for _ in range(8):
            self.p.tick(1,False)
            if self.reg.PC==self.code+6:
                break
        assert (self.reg.PC,self.reg.SP)==(self.code+6,self.stack)
        assert bytes(self.m[self.stack:self.stack+10])==args
        out = bytes(self.m[dest-8:dest+14])
        assert out[:8]+out[14:]==pattern[:8]+pattern[14:]
        assert self.m[self.sym['__current_bank']]==9 and bytes(self.m[0x4000:0x4020])==self.signature
        return self.reg.A,out[8:14],pattern[8:14]


    def merge(self, first, second, qx, qy):
        address = self.sym['_Ct']
        self.m[address:address+20] = first + b'\x55'*4 + second + b'\xaa'*4
        for name, value in (('_riding_contact_qx', qx), ('_riding_contact_qy', qy)):
            dest = self.sym[name]
            self.m[dest:dest+2] = struct.pack('<H', value & 65535)
        routine = self.sym['_riding_contact_merge']
        self.m[self.code:self.code+5] = bytes((0xcd, routine & 255, (routine >> 8) & 255, 0x18, 0xfe))
        self.reg.PC, self.reg.SP = self.code, self.stack
        self.p.tick(1, False)
        assert (self.reg.PC, self.reg.SP) == (self.code + 3, self.stack)
        assert self.m[self.sym['__current_bank']] == 9
        assert bytes(self.m[0x4000:0x4020]) == self.signature
        return self.reg.A, bytes(self.m[address:address+20])


def check_endpoint_roundtrips(target, reference, totals):
    routine = target.sym['contact_root_certificate']
    table = reference.sym['_riding_normal_rsqrt']
    offset = (table >> 16) * 16384 + (table & 16383)
    reciprocals = struct.unpack_from('<297H', reference.image, offset)
    stored_length = target.sym['normal_cache_value'] + 4
    current_bank = target.sym['__current_bank']
    target.m[0x2000] = target.m[current_bank] = routine >> 16
    target.m[target.code:target.code+5] = bytes((0xcd, routine & 255, (routine >> 8) & 255, 0x18, 0xfe))
    verdicts = {}
    try:
        for x in range(-409, 410):
            last_y = math.isqrt(410**2 - 1 - x*x)
            for y in range(-last_y, last_y+1):
                d2 = x*x + y*y
                if d2 < 16384:
                    length = math.isqrt(d2)
                    if length:
                        nx = (abs(x) << 14) // length * (-1 if x < 0 else 1)
                        ny = (abs(y) << 14) // length * (-1 if y < 0 else 1)
                    else:
                        nx, ny = 0, 16384
                else:
                    reciprocal = reciprocals[(d2 - 16384) >> 9]
                    nx, ny = x*reciprocal >> 4, y*reciprocal >> 4
                    length = (x*nx + y*ny + 8192) >> 14
                    key = reciprocal, length
                    if key not in verdicts:
                        target.m[stored_length:stored_length+2] = struct.pack('<h', length)
                        target.reg.B, target.reg.C = reciprocal >> 8, reciprocal & 255
                        target.reg.PC, target.reg.SP = target.code, target.stack
                        target.p.tick(1, False)
                        assert (target.reg.PC, target.reg.SP) == (target.code+3, target.stack)
                        assert target.reg.A in (2, 64)
                        verdicts[key] = target.reg.A
                    if verdicts[key] == 2:
                        totals['arithmetic endpoint fallbacks'] += 1
                        continue
                assert ((length*nx + 8192) >> 14, (length*ny + 8192) >> 14) == (x, y), (x, y)
                totals['exact endpoint roundtrips'] += 1
        assert totals['arithmetic endpoint fallbacks'] and 64 in verdicts.values()
    finally:
        target.m[0x2000] = target.m[current_bank] = 9


def check_physical_lengths(target, oracle, totals):
    def rom_offset(symbol):
        address = target.sym[symbol]
        return (address >> 16)*16384 + (address & 16383)

    roots = struct.unpack_from('<297H', target.image, rom_offset('_riding_normal_rsqrt'))
    rows = rom_offset('normal_length_rows')
    patterns = rom_offset('normal_length_patterns')
    representatives = {}
    for x in range(-410, 411):
        for y in range(-410, 411):
            squared = x*x + y*y
            if not 65536 <= squared < 168448:
                continue
            offset = rows + 2*((squared-65536) >> 9)
            base, pattern = target.image[offset:offset+2]
            slot = (squared >> 5) & 15
            code = (target.image[patterns+4*pattern+slot//4] >> (2*(slot%4))) & 3
            representatives.setdefault(squared >> 5, (x, y, squared))
            if not code:
                totals['full dot fallbacks'] += 1
                continue
            reciprocal = roots[(squared-16384) >> 9]
            nx, ny = x*reciprocal >> 4, y*reciprocal >> 4
            expected = (x*nx + y*ny + 8192) >> 14
            assert base+249+code == expected, (x, y, squared)
            totals['certified physical lengths'] += 1

    # Invoke every populated slot and compare all six output bytes with
    # the preceding cartridge, including opposite signs in every fifth slot.
    for slot, (x, y, squared) in representatives.items():
        for sign in ((1, -1) if slot%5 == 0 else (1,)):
            _, got, _ = target.call('_riding_normal_physical', sign*x, sign*y, 0xa201, squared)
            _, want, _ = oracle.call('_riding_normal_fast', sign*x, sign*y, 0xa201, squared)
            assert got == want, (x, y, squared, sign)
            totals['linked physical lengths'] += 1
    # Public callers can supply an unrelated squared length to the same kernel.
    for squared in (16384, 65536, 65537, 71680, 98304, 131071, 131072, 168099,
                    168447, 168448, 33570817, 2147483647):
        for x in (-32768, -513, -512, -511, -410, -257, -256, -255, -1, 0,
                  1, 255, 256, 257, 410, 511, 512, 32767):
            for y in (x, min(-x, 32767)):
                _, got, _ = target.call('_riding_normal_fast', x, y, 0xa201, squared)
                _, want, _ = oracle.call('_riding_normal_fast', x, y, 0xa201, squared)
                assert got == want, (x, y, squared)
                totals['arbitrary squared lengths'] += 1


def check(rom, reference):
    target, old = Cartridge(rom),Cartridge(reference)
    totals = Counter()
    sym,image = target.sym,target.image
    start = sym['_riding_normal_groups'] & 65535
    dir_offset = 9*16384+(start&16383)
    reader = sym['_riding_normal_ring_mapped']
    representatives = {}
    contacts = (0xa101,0xa2ff)
    try:
        for small in range(290):
            limit,group,lo = struct.unpack_from('<BHB',image,dir_offset+4*(small//2))
            assert limit+256 == math.isqrt(410**2-1-(small&~1)**2)
            if not group:
                continue
            bank = lo+256
            header = bank*16384+(group&16383)+4*(small&1)
            first,count,ptr = struct.unpack_from('<BBH',image,header)
            bigs = [b for b in range(small,410) if 396**2<=small**2+b*b<410**2]
            assert bigs==list(range(256+first,256+first+count))
            assert 0x4000<=ptr<=0x8000-8*count
            representatives[bank] = small,bigs[-1]
            totals['rows'] += 1
            for large in bigs:
                d2 = small*small+large*large
                totals['entries'] += 1
                for order in ((small,large),(large,small)):
                    for sx,sy in ((1,1),(-1,1),(1,-1),(-1,-1)):
                        x,y = order[0]*sx,order[1]*sy
                        dest = contacts[totals['signed permutations']&1]
                        hit,got,_ = target.call('_riding_normal_ring',x,y,dest)
                        _,want,_ = old.call('_riding_normal_fast',x,y,dest,d2)
                        assert hit==1 and got==want,(x,y,d2,hit,got.hex(),want.hex())
                        totals['signed permutations'] += 1
                        if '_riding_ring_equal_points' in sym:
                            # Exercise the actual merge with identical vectors, then
                            # with a different contact while the physical cache is warm.
                            qx, qy = (x*257) ^ 0x7ff0, (y*503) ^ 0x800f
                            assert target.merge(got, got, qx, qy) == old.merge(want, want, qx, qy)
                            totals['equal contact pairs'] += 1
                            if (small + large) % 11 == 0:
                                other = struct.pack('<hhh', 0, 16384, 395 + large % 15)
                                assert target.merge(other, got, qx, qy) == old.merge(other, want, qx, qy)
                                totals['mixed contact pairs'] += 1
        assert totals['entries']==4440 and totals['rows']==290
        # Every bank must survive an IRQ taken immediately after the mapper
        # changes both registers, including the exact public/physical cache key.
        for bank,(x,y) in representatives.items():
            requested,seen = [],[]
            def inject(_):
                if not requested:
                    requested.append(bank)
                    assert bytes(target.m[0x4000:0x4020])==image[bank*16384:bank*16384+32]
                    target.m[0xff0f] = 1
            def vblank(_):
                sp=target.reg.SP
                if reader <= int.from_bytes(bytes(target.m[sp:sp+2]),'little') < reader+65:
                    seen.append(bank)
            target.p.hook_register(0,reader,inject,None)
            target.p.hook_register(0,0x40,vblank,None)
            target.m[0xffff],target.m[0xff0f] = 1,0
            hit,got,_=target.call('_riding_normal_ring',-x,y,contacts[0],irq=True)
            target.m[0xffff],target.m[0xff0f] = 0,0
            target.p.hook_deregister(0,reader)
            target.p.hook_deregister(0,0x40)
            _,want,_=old.call('_riding_normal_fast',-x,y,contacts[0],x*x+y*y)
            assert hit==1 and got==want and seen,(bank,x,y,seen)
            totals['interrupted banks'] += 1
        # Observe work only to distinguish a cache hit from re-evaluation.
        # A public caller may present the same coordinates with another d2.
        counts = Counter()
        mul = sym.get('_riding_projection_signed16', sym['_riding_mul16_regs'])
        target.p.hook_register(mul>>16,mul&65535,lambda _:counts.update(['multiply']),None)
        target.p.hook_register(0,reader,lambda _:counts.update(['mapped']),None)
        x,y = -93,393
        d2 = x*x+y*y
        for name,key,should_map,should_multiply in (
                ('ring',d2,True,False),('ring',d2,False,False),('fast',d2,False,False),
                ('fast',d2^4096,False,True),('fast',d2^4096,False,False),
                ('ring',d2,True,False),('fast',d2,False,False)):
            counts.clear()
            _,got,_=target.call('_riding_normal_'+name,x,y,contacts[0],key)
            _,want,_=old.call('_riding_normal_fast',x,y,contacts[1],key)
            assert got==want and bool(counts['mapped'])==should_map and bool(counts['multiply'])==should_multiply
            totals['observed cache hits and replacements'] += 1
        target.p.hook_deregister(mul>>16,mul&65535)
        target.p.hook_deregister(0,reader)
        if 'normal_fraction' in sym:
            for x in range(-127,128):
                for y in range(-127,128):
                    d2 = x*x + y*y
                    if d2 >= 16384:
                        continue
                    length = math.isqrt(d2)
                    if length:
                        nx = (abs(x) << 14) // length
                        ny = (abs(y) << 14) // length
                        vector = (-nx if x < 0 else nx, -ny if y < 0 else ny, length)
                    else:
                        vector = (0, 16384, 0)
                    _,got,_ = target.call('_riding_normal_fast',x,y,contacts[0],d2)
                    assert got == struct.pack('<hhh', *vector), (x,y,got,vector)
                    totals['deep physical vectors'] += 1
        for x,y in ((289,289),(398,0),(0,-405),(-128,382),(250,-314)):
            physical=x*x+y*y
            for d2 in (physical,physical,physical+1,physical^256,physical^65536,
                       physical^16777216,0,1,16383,16384,-1,-2147483648,2147483647,physical):
                _,want,_=old.call('_riding_normal_fast',x,y,contacts[0],d2)
                _,got,_=target.call('_riding_normal_fast',x,y,contacts[1],d2)
                assert got==want,(x,y,d2,got,want)
                hit,got,_=target.call('_riding_normal_ring',x,y,contacts[0])
                _,want,_=old.call('_riding_normal_fast',x,y,contacts[1],physical)
                assert hit and got==want,(x,y,d2,got,want)
                totals['public and physical transitions'] += 1
        # Carry lets the endpoint caller reject a proven exterior immediately.
        # At each edge check the neighbor on both sides for both axis orders.
        for small in range(290):
            radius = (410**2 - 1 - small**2)
            big = math.isqrt(radius)
            for large in (big-1, big, big+1, big+2):
                for x, y in ((small, large), (-large, small)):
                    hit, _, _ = target.call('_riding_normal_ring', x, y, contacts[0])
                    outside = bool(target.reg.F & 0x10)
                    assert outside == (x*x+y*y >= 410**2), (x, y, hit, outside)
                    assert not (hit and outside)
                    totals['endpoint boundary flags'] += 1
        for x,y in ((0,0),(127,1),(0,395),(0,410),(280,277),(290,290),
                    (511,128),(512,0),(-32768,0),(32767,32767),(-32768,-32768)):
            hit,got,pattern=target.call('_riding_normal_ring',x,y,contacts[0])
            assert not hit and got==pattern
            for d2 in (0,16383,16384,168098,33570817,-1,2147483647):
                _,want,_=old.call('_riding_normal_fast',x,y,contacts[0],d2)
                _,got,_=target.call('_riding_normal_fast',x,y,contacts[1],d2)
                assert want==got
                totals['public edge cases'] += 1
        if 'contact_root_certificate' in sym:
            check_endpoint_roundtrips(target, old, totals)
        if '_riding_normal_physical' in sym:
            check_physical_lengths(target, old, totals)
        print(dict(totals))
    finally:
        target.p.stop(save=False)
        old.p.stop(save=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom',type=Path,required=True)
    parser.add_argument('--reference',type=Path,help='optional arithmetic-oracle ROM; defaults to a second emulator running the current public kernel')
    args=parser.parse_args()
    check(args.rom,args.reference or args.rom)
