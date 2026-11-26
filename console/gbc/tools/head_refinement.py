"""Pack conservative quarter-metre swept-head masks inside occupied metre tiles."""
from collections import Counter
from functools import lru_cache
import struct

from head_clearance import packed_inputs, touches_tile, write_if_changed

# Independent tails. The linker places these objects after their owning data,
# and its per-bank size checks reject any overlap with another bank window.
ROOM = {501:8192, **dict.fromkeys((*range(21,28), *range(477,481), *range(502,506)), 1024),
        13:7400, 4:505, 5:850, 14:5600, 3:4450, 1:5100, 2:4400, 15:3400, 7:2300, 6:2100, 507:2700}


def group_masks(level, banks):
    base = level['base_bank']
    def pointer(bank, address):
        return struct.unpack_from('<HBB', banks[bank], address - 0x4000)
    @lru_cache(None)
    def records(ptr):
        addr, delta, count = ptr
        return tuple(struct.unpack_from('<4h', banks[base+delta], addr-16384+18*i)
                     for i in range(count))
    w, h = level['grid']
    groups = {}
    for y in range(h):
        for x0 in range(0,w,4):
            fine = [0]*64
            for j in range(min(4,w-x0)):
                ptr = pointer(level['directory_bank'], level['directory_address']+4*(w*y+x0+j))
                for t in range(16):
                    leaf = records(pointer(base+ptr[1],ptr[0]+4*t) if ptr[2]==255 else ptr)
                    if not leaf:
                        continue
                    x, ty = (t%4)*1024, (t//4)*1024
                    fine[j*16+t] = sum(1<<q for q in range(16)
                        if any(touches_tile(edge,x+256*(q%4),ty+256*(q//4),256) for edge in leaf))
            # This key and insertion order exactly reproduce encode_level's
            # four coarse words. A shared group's union can only add set bits.
            key = sum(1<<i for i,p in enumerate(fine) if p)
            if key in groups:
                old = groups[key]
                for i,p in enumerate(fine):
                    old[i] |= p
            else:
                groups[key] = fine
    return list(groups.values())


def make_palette(groups):
    frequencies = Counter(p for level in groups for group in level for p in group if p)
    frequencies.pop(65535,None)
    palette = [65535] + [p for p,_ in frequencies.most_common(63)]
    # Keep the smallest conservative superset. Full occupancy always exists.
    order = sorted(range(len(palette)),key=lambda i:palette[i].bit_count())
    codes = {p:next(i for i in order if p & palette[i] == p) for p in frequencies}
    codes[65535] = 0
    return palette,codes


def pack_level(groups,codes):
    data = bytearray(2*len(groups))
    seen = {}
    for i,group in enumerate(groups):
        starts = [sum(bool(v) for v in group[:stop]) for stop in (16,32,48)]
        ids = [codes[v] for v in group if v]
        # Four six-bit values use three bytes. Pad the final quartet so the
        # reader can always load the shared high-two-bit plane at offset 2.
        payload = bytearray(starts)
        for j in range(0,len(ids),4):
            a,b,c,d = (ids[j:j+4]+[0]*3)[:4]
            payload.extend(((a&15)|((b&15)<<4), (c&15)|((d&15)<<4),
                            (a>>4)|((b>>4)<<2)|((c>>4)<<4)|((d>>4)<<6)))
        key = bytes(payload)
        if key not in seen:
            seen[key] = len(data)
            data.extend(payload)
        struct.pack_into('<H',data,2*i,seen[key])
    return data


def byte_lines(data):
    return [' .db '+','.join(map(str,data[j:j+32])) for j in range(0,len(data),32)]


def generate(gen,dest=None):
    levels,banks,_ = packed_inputs(gen)
    groups = [group_masks(l,banks) for l in levels]
    palette,codes = make_palette(groups)
    payloads = [pack_level(level,codes) for level in groups]
    room = ROOM.copy()
    placement = {}
    for i in sorted(range(len(levels)),key=lambda i:-len(payloads[i])):
        # Best fit keeps complete levels in one bank, including the smaller
        # projection tails. Future level sets can fall back to the metre map.
        fits = [b for b in room if room[b]>=len(payloads[i])]
        if fits:
            bank = min(fits,key=lambda b:(b<477,room[b],b))
            room[bank] -= len(payloads[i])
            placement[i] = bank
    out = ['.module head_refinement','.area _CODE_4','_head_quarter_levels::']
    for i in range(len(levels)):
        if i in placement:
            b=placement[i]
            out += [f' .dw head_quarter_{i}'+('+0x8000' if b>=256 else ''),f' .db {b&255}']
        else:
            out += [' .dw 0',' .db 0']
    out += ['_head_quarter_palette::', *[' .dw '+str(p) for p in palette]]
    out += ['_head_count_bits::', *byte_lines(bytes(x.bit_count() for x in range(256)))]
    for bank in sorted(set(placement.values())):
        out += [f'.area _CODE_{bank}', f'_head_quarter_tail_{bank}::']
        for i,b in placement.items():
            if b==bank:
                out += [f'head_quarter_{i}::',*byte_lines(payloads[i])]
        out += [f'_head_quarter_end_{bank}::']
    path = (dest or gen)/'head_quarters.s'
    write_if_changed(path,'\n'.join(out)+'\n')
    return path


def validate_layout(symbols):
    if (symbols.get('_riding_head_quarters',0) >> 16 != 4 or
            symbols.get('_head_quarter_levels',0) >> 16 != 4 or
            symbols.get('_head_quarter_palette',0) >> 16 != 4 or
            symbols.get('_riding_head_quarter_code',65535) >= 0x4000):
        raise ValueError('Quarter-metre head maps need their sweep caller in bank 4 and a fixed reader')
    for bank,capacity in ROOM.items():
        start = symbols.get(f'_head_quarter_tail_{bank}')
        if start is None:
            continue
        end = symbols[f'_head_quarter_end_{bank}']
        if (start >> 16 != bank or not 0 < end-start <= capacity or
                end != symbols[f's__CODE_{bank}'] + symbols[f'l__CODE_{bank}'] or
                end > (bank<<16)+0x8000):
            raise ValueError(f'Quarter-metre head map exceeds the tail of bank {bank}')
