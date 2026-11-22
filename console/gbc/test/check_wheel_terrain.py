"""Check the shipped half-metre wheel map, both cache paths and MBC5 interrupts."""
import argparse
import json
from collections import Counter
from io import BytesIO
from pathlib import Path
import random
import re
import struct
import sys

from pyboy import PyBoy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from wheel_terrain import GENERAL, validate_layout

WINDOW = 64


def offset(bank, address):
    return bank*16384+address-0x4000


def leaves(image, level, cx, cy):
    def pointer(bank, addr):
        return struct.unpack_from('<HBB',image,offset(bank,addr))
    def records(ptr):
        addr,rel,n = ptr
        base = offset(level['base_bank']+rel,addr)
        return tuple(struct.unpack_from('<6hH4B',image,base+18*i) for i in range(n))
    w,_ = level['grid']
    root = pointer(level['directory_bank'],level['directory_address']+4*(cy*w+cx))
    if root[2] != 255:
        return (records(root),)*16
    return tuple(records(pointer(level['base_bank']+root[1],root[0]+4*i)) for i in range(16))


def verify_square(code, records, x, y):
    """Bound each possible contributor independently using the four clipped corners."""
    if code==GENERAL:
        return
    if code >= WINDOW:
        start, length = divmod(code-WINDOW,4)
        keep = range(start,start+length+1)
        assert keep.stop <= len(records) and len(keep) < len(records)
    else:
        assert code <= len(records)
        keep = ()

    for i,(px,py,dx,dy,ex,ey,flags,bx,bX,by,bY) in enumerate(records,1):
        if i-1 in keep:
            continue
        xmin,xmax = max(x,64*(bx-128)), min(x+511,64*(bX-127)-1)
        ymin,ymax = max(y,64*(by-128)), min(y+511,64*(bY-127)-1)
        if xmin>xmax or ymin>ymax:
            continue
        corners = [(xx-px,yy-py) for xx in (xmin,xmax) for yy in (ymin,ymax)]
        assert all(-32768<=vx<=32767 and -32768<=vy<=32767 for vx,vy in corners)
        def projections(ax,ay):
            return [max(-32768,min(32767,(vx*ax+vy*ay+8192)//16384)) for vx,vy in corners]
        distances = projections(-ey,ex)
        if min(distances)>=410 or max(distances)<=-410:
            continue
        tangent = projections(ex,ey)
        end = flags & 16383
        last = end-int(bool(flags & 32768))
        caps = []
        if min(tangent)<0 and not flags&16384:
            caps.append((px,py))
        if max(tangent)>end and not flags&32768:
            caps.append((px+dx,py+dy))
        for vx,vy in caps:
            assert all(-32768 <= xx-vx <= 32767 and -32768 <= yy-vy <= 32767
                       for xx in (xmin,xmax) for yy in (ymin,ymax))
            # Closest integer point in this rectangle to the real vertex.
            near_x = min(xmax,max(xmin,vx))-vx
            near_y = min(ymax,max(ymin,vy))-vy
            assert near_x**2+near_y**2>=410**2, (code,i,'radial cap')
        if i==code:
            assert min(tangent)>=0 and max(tangent)<=last, (code,i,'tangent bounds')
        else:
            assert max(tangent)<0 or min(tangent)>last, (code,i,'additional interior')


def read_row(image,maps,level,cy):
    w,h,table = struct.unpack_from('<BBH',image,maps+4*level)
    addr,lo = struct.unpack_from('<HB',image,offset(9,table+3*cy))
    bank = lo + (256 if addr & 0x8000 else 0)
    return w,h,addr,bank,offset(bank,addr & 0x7fff)


def read_pattern(image,row,cx,sub,extended):
    w,_,addr,bank,source = row
    if addr <= 1:
        return addr
    index = image[source+cx]
    if not index:
        return 0
    if extended and index >= 128:
        layout = source - 18*(256-index)
        assert layout >= bank*16384 and layout+18 <= source
        flags = int.from_bytes(image[layout+16:layout+18],'little')
        return image[layout+sub] + 256*((flags>>sub)&1)
    return image[source+w+16*(index-1)+sub]


def linked_rows(gen, image, symbols, baseline):
    levels = json.loads((gen/'physics_bank_manifest.json').read_text())['levels']
    maps = offset(9,symbols['_wheel_terrain_maps'] & 65535)
    patterns = offset(9,symbols['_wheel_terrain_patterns'] & 65535)
    if baseline:
        old_rom, old_symbols = baseline
        old_maps = offset(9,old_symbols['_wheel_terrain_maps'] & 65535)
        old_patterns = offset(9,old_symbols['_wheel_terrain_patterns'] & 65535)
    rng = random.Random(0x73511)
    samples, totals, interrupts = [], Counter(), {}
    for level,desc in enumerate(levels):
        w,h,directory = struct.unpack_from('<BBH',image,maps+4*level)
        assert (w,h) == tuple(desc['grid'])
        groups = {key:[] for key in ('empty','plane','general','window')}
        for cy in range(h):
            row = read_row(image,maps,level,cy)
            if baseline:
                old_row = read_row(old_rom,old_maps,level,cy)
            for cx in range(w):
                cell = leaves(image,desc,cx,cy)
                for sub,records in enumerate(cell):
                    pattern = read_pattern(image,row,cx,sub,True)
                    if baseline:
                        old_pattern = read_pattern(old_rom,old_row,cx,sub,False)
                    for half in range(4):
                        code = image[patterns+4*pattern+half]
                        if baseline:
                            old = old_rom[old_patterns+4*old_pattern+half]
                            assert old == GENERAL or code == old, (level,cx,cy,sub,half,old,code)
                        verify_square(code,records,sub%4*1024+half%2*512,sub//4*1024+half//2*512)
                        kind = ('empty' if code == 0 else 'general' if code == GENERAL else
                                'window' if code >= WINDOW else 'plane')
                        totals[kind] += 1
                        # Retain a deterministic sample of each type on every level.
                        if kind == 'window' or rng.randrange(15 if kind=='plane' else 60) == 0:
                            x = cx*16 + sub%4*4 + half%2*2
                            y = cy*16 + sub//4*4 + half//2*2
                            groups[kind].append((x,y,code))
                            if row[2] > 1 and code not in (0,GENERAL):
                                interrupts.setdefault(row[3]>=256,(level,x,y,code,row[3]))
        selected = []
        for kind, points in groups.items():
            limit = 100 if kind == 'window' else 24
            selected.extend(rng.sample(points, min(limit,len(points))))
        samples.append(selected)
        assert groups['window'], ('course without an ordered window', level)
    assert sum(totals.values()) == 64*sum(w*h for w,h in (l['grid'] for l in levels))
    assert totals['plane'] > 100000 and totals['empty'] > 1000000
    assert totals['window'] > 10000
    return samples,totals,interrupts


def native(image, sy, samples, interrupts):
    main = sy['_main']
    image = bytearray(image)
    image[main:main+3] = bytes([0xf3,0x18,0xfe])  # Boot normally through CRT.
    p = PyBoy(BytesIO(image),window='null',cgb=True,sound_emulated=False)
    p.set_emulation_speed(0)
    mr,reg = p.memory,p.register_file
    pc,sp = 0xdfe0,0xdf80
    caller = bytes(image[9*16384:9*16384+32])
    def call(name,de=0,bc=0,a=0,irq=False):
        addr = sy[name]
        code = [0xfb if irq else 0xf3,0,0xcd,addr&255,(addr>>8)&255,0xf3,0x18,0xfe]
        mr[pc:pc+len(code)] = code
        reg.PC,reg.SP,reg.D,reg.E,reg.B,reg.C,reg.A = pc,sp,de>>8,de&255,bc>>8,bc&255,a
        for _ in range(10):
            p.tick(1,False)
            if reg.PC == pc+6: break
        assert reg.PC == pc+6 and reg.SP == sp, (name,hex(reg.PC),hex(reg.SP))
        assert mr[sy['__current_bank']] == 9 and bytes(mr[0x4000:0x4020]) == caller
        return reg.A
    counts = Counter()
    try:
        p.tick(220,False)
        assert reg.PC == main+1
        mr[0x2000],mr[0x3000],mr[sy['__current_bank']] = 9,0,9
        mr[0xff0f],mr[0xffff] = 0,0
        wheels = [sy['_Bike']+24,sy['_Bike']+48]
        ct = sy['_Ct']
        offsets = (0,63,64,127,128,191,192,255)
        for lev,points in enumerate(samples):
            assert call('_physics_collision_select',a=lev)
            for i,(x,y,code) in enumerate(points):
                x += i&1
                y += (i>>1)&1
                assert call('_riding_wheel_lookup',x,y) == code, (lev,x,y,code)
                mr[sy['_wheel_surface_cache']+4] = 0
                for j in range(2):
                    if j and WINDOW <= code < GENERAL:
                        # Evict all three leaf slots before revisiting the warm square.
                        for idx in range(3):
                            mr[wheels[1]:wheels[1]+8] = struct.pack('<II',idx<<20,0)
                            call('_riding_wheel_surface',wheels[1])
                    rx = (x*256+offsets[(i+4*j)%8])*256+255
                    ry = (y*256+offsets[(3*i+5*j)%8])*256+127
                    for wheel in wheels:
                        mr[wheel:wheel+8] = struct.pack('<II',rx,ry)
                    seed = bytes([0x55])*20
                    mr[ct:ct+20] = seed
                    n = call('_riding_wheel_surface',wheels[1])  # Always runs the full iterator.
                    wanted = bytes(mr[ct:ct+20])
                    cursor = sy['_Seg_cur']
                    left = sy['_Seg_left']
                    iterator = mr[cursor:cursor+2],mr[left]
                    mr[ct:ct+20] = seed
                    got = call('_riding_cert_hit',wheels[0])
                    if code == GENERAL:
                        assert got == GENERAL
                    elif code >= WINDOW:
                        result = bytes(mr[ct:ct+20])
                        actual_iterator = mr[cursor:cursor+2],mr[left]
                        assert got == n and result == wanted, (lev,x,y,code,n,got,wanted,result)
                        assert actual_iterator == iterator, (lev,x,y,code,n,iterator,actual_iterator)
                        counts[('window warm' if j else 'window cold',got)] += 1
                    else:
                        assert got == n and n<=1 and (not n or bytes(mr[ct:ct+6])==wanted[:6]), (
                            lev+1,x,y,rx,ry,code,n,got,wanted,bytes(mr[ct:ct+6]))
                        counts[('warm' if j else 'cold',got)] += 1
            for x,y in ((65535,0),(0,65535),(4096,0),(0,4096)):
                assert call('_riding_wheel_lookup',x,y)==GENERAL
        # Inject a VBlank at the first instruction with the full data bank visible.
        reader = sy['_riding_wheel_read_map']
        target = image.index(bytes([0xea,0,0x30]),reader,reader+32)+3
        for lev,x,y,code,bank in interrupts.values():
            assert call('_physics_collision_select',a=lev)
            seen = []
            requested = []
            def inject(_):
                if requested:
                    return
                requested.append(reg.PC)
                assert bytes(mr[0x4000:0x4020]) == bytes(image[bank*16384:bank*16384+32])
                mr[0xff0f] = 1
            def vblank(_):
                saved = mr[reg.SP]+256*mr[reg.SP+1]
                if reader <= saved < reader+64: seen.append(saved)
            p.hook_register(0,target,inject,None)
            p.hook_register(0,0x40,vblank,None)
            mr[0xffff],mr[0xff0f] = 1,0
            assert call('_riding_wheel_lookup',x,y,irq=True) == code and seen, (bank,seen)
            mr[0xffff],mr[0xff0f] = 0,0
            p.hook_deregister(0,target)
            p.hook_deregister(0,0x40)
            counts['VBlank'] += 1
        assert counts['VBlank'] == 2
        for path in ('window warm','window cold'):
            assert all(counts[path,n] for n in (0,1,2))
    finally:
        p.stop(save=False)
    return counts


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom',type=Path,required=True)
    parser.add_argument('--gen',type=Path,required=True)
    parser.add_argument('--baseline-rom',type=Path,help='original 16-byte terrain layout for per-tile coverage regression')
    args = parser.parse_args()
    def symbols(rom):
        return {k:int(v,16) for k,v in re.findall(r'^DEF (\S+) 0x([\da-fA-F]+)$',
                                              rom.with_suffix('.noi').read_text(),re.M)}
    sy = symbols(args.rom)
    validate_layout(sy)
    image = args.rom.read_bytes()
    baseline = (args.baseline_rom.read_bytes(),symbols(args.baseline_rom)) if args.baseline_rom else None
    samples,totals,interrupts = linked_rows(args.gen,image,sy,baseline)
    print('Linked half-metre certificates:',dict(totals),flush=True)
    print('Native contacts:',dict(native(image,sy,samples,interrupts)))
