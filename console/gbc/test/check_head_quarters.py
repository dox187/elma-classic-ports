"""Verify every linked quarter-metre certificate against the original finite edges."""
import argparse
import json
from pathlib import Path
import re
import struct
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))

from check_head_clearance import native_masks
from check_head_map_rom import HeadProbe
from check_physics_sweep import oracle
from physics_level import Resource, geometry, internal_levels


def wanted_quarters(segments,w,h):
    result = [0]*(w*h*16)
    for ax,ay,dx,dy,*_ in segments:
        bx,by=ax+dx,ay+dy
        for sy in range(max(0,(min(ay,by)-244)//256), min(16*h,(max(ay,by)+244)//256+1)):
            for sx in range(max(0,(min(ax,bx)-244)//256), min(16*w,(max(ax,bx)+244)//256+1)):
                idx=(sy//4)*4*w+sx//4
                bit=1<<(4*(sy%4)+sx%4)
                if result[idx]&bit:continue
                x,y=sx*256,sy*256
                corners=((x,y),(x+256,y),(x+256,y+256),(x,y+256))
                if (x<=ax<=x+256 and y<=ay<=y+256 or any(
                    oracle((*corners[i],*corners[(i+1)%4],ax,ay,dx,dy,244)) for i in range(4))):
                    result[idx]|=bit
    return result



def native_sweeps(rom,levels):
    count=hits=0
    probe=HeadProbe(rom)
    try:
        for idx,level in enumerate(levels):
            probe.select_level(idx)
            *_,segments,_,_=geometry(level)
            for ax,ay,dx,dy,*_ in segments[::max(1,len(segments)//4)][:4]:
                x=((ax+dx//2)//256)*256
                y=((ay+dy//2)//256)*256
                # Adjacent closed quarters, half-metre and metre boundaries,
                # both directions, shallow diagonals and exact DDA threshold.
                for d in (0,1,255,256,257,511,1023,1793,8192,8193):
                    for a,b in (((x-1,y),(x+d,y+1)),((x+d,y+1),(x-1,y)),
                                ((x,y-1),(x+1,y+d)),((x-1,y+1),(x+d,y-d))):
                        vx,vy=b[0]-a[0],b[1]-a[1]
                        n=max(1,(max(abs(vx),abs(vy))+8191)//8192)
                        radius=246 if n>1 else 244
                        # Integer DDA vertices use truncation toward zero.
                        def step(v,k):
                            return (1 if v>=0 else -1)*(abs(v)*k//n)
                        points=[(a[0]+step(vx,k),a[1]+step(vy,k)) for k in range(n+1)]
                        candidates=[edge[:4] for edge in segments
                            if max(a[0],b[0])+radius>=min(edge[0],edge[0]+edge[2])
                            and min(a[0],b[0])-radius<=max(edge[0],edge[0]+edge[2])
                            and max(a[1],b[1])+radius>=min(edge[1],edge[1]+edge[3])
                            and min(a[1],b[1])-radius<=max(edge[1],edge[1]+edge[3])]
                        want=any(oracle((*p,*q,*edge,radius))
                                 for p,q in zip(points,points[1:]) for edge in candidates)
                        got=probe.check((*a,*b))
                        assert got==want,(idx+1,a,b,n,want,got)
                        count+=1;hits+=got
    finally:
        probe.close()
    assert 0<hits<count
    return count,hits


def check(rom,res):
    sym={k:int(v,16) for k,v in re.findall(r'^DEF (\S+) 0x([0-9a-fA-F]+)$',rom.with_suffix('.noi').read_text(),re.M)}
    image=rom.read_bytes()
    def addr(bank,ptr):return bank*16384+ptr-16384
    def symbol(k):return addr(sym[k]>>16,sym[k]&65535)
    def word(pos):return struct.unpack_from('<H',image,pos)[0]
    pal=symbol('_head_quarter_palette')
    native=[]
    levels=internal_levels(Resource(res))
    count=refined=possible=occupied=0
    for idx,level in enumerate(levels):
        _,_,w,h,segs,_,_=geometry(level)
        truth=wanted_quarters(segs,w,h)
        data=symbol('_riding_head_maps')+8*idx
        assert tuple(image[data:data+2])==(w,h)
        rows=addr(4,word(data+2))
        bank=256+image[data+6]
        patterns=addr(bank,word(data+4))
        desc=symbol('_head_quarter_levels')+3*idx
        base=word(desc)
        assert base, ('Unrepresented original level',idx)
        fb=image[desc+2]+(256 if base&32768 else 0)
        base=addr(fb,base&32767)
        records=[]
        for y in range(4*h):
            row=addr(bank,word(rows+2*(y//4)))
            for x in range(4*w):
                group=image[row+x//16];cell=(x//4)%4;tile=4*(y%4)+x%4
                words=[word(patterns+8*group+2*c) for c in range(4)]
                required=truth[y*(4*w)+x]
                mask=0
                if words[cell] & (1<<tile):
                    index=sum(m.bit_count() for m in words[:cell])+(words[cell]&((1<<tile)-1)).bit_count()
                    payload=base+word(base+group*2)+3+3*(index//4)
                    lo=(image[payload+index%4//2]>>(4*(index%2)))&15
                    hi=(image[payload+2]>>(2*(index%4)))&3
                    mask=word(pal+2*(lo+16*hi))
                    refined+=16-mask.bit_count()
                    possible+=16-required.bit_count()
                    occupied+=1
                assert mask&required==required,(idx+1,x,y,hex(mask),hex(required))
                records.append((x,y,mask))
        count+=len(records)
        # Repeat cache hits, grid exits, and switch back from an invalid level.
        records.extend([records[-1],records[0],records[0],(4*w,0,65535),(0,4*h,65535),(255,255,65535)])
        native.extend((idx, records[i:i+1000]) for i in range(0,len(records),1000))
    native.extend((idx,[(0,0,65535)]) for idx in (len(levels),255))
    trials=native_masks(rom,native,'_riding_head_quarters')
    assert refined>possible//2
    sweeps,hits=native_sweeps(rom,levels)
    return dict(levels=len(levels),metres=count,quarters=16*count,
                coarse_occupied_metres=occupied,certified_new_quarters=refined,
                geometrically_empty_inside_coarse_occupied=possible,native_masks_and_bank_restores=trials,
                native_geometric_sweeps=sweeps,native_sweep_hits=hits)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom',type=Path,required=True)
    p.add_argument('--res',type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(check(a.rom,a.res)))
