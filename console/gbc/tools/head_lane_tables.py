"""Exact swept-head clearance in quarter-metre strips near the original starts."""
from functools import lru_cache
import json
import struct

from head_clearance import packed_inputs, write_if_changed

BANK = 469
OFFSET = 0x2400
COLUMNS = 56
RADIUS = 244


def touches_rectangle(edge, x0, x1, y0, y1):
    """Return whether the segment comes strictly within the head radius of the rectangle."""
    ax, ay, dx, dy = edge
    bx, by = ax + dx, ay + dy
    if (max(ax, bx) + RADIUS <= x0 or min(ax, bx) - RADIUS >= x1 or
            max(ay, by) + RADIUS <= y0 or min(ay, by) - RADIUS >= y1):
        return False
    corners = ((x0, y0), (x1, y0), (x0, y1), (x1, y1))
    cross = [(x-ax)*dy - (y-ay)*dx for x,y in corners]
    if (x1 >= min(ax,bx) and x0 <= max(ax,bx) and y1 >= min(ay,by) and
            y0 <= max(ay,by) and min(cross) <= 0 <= max(cross)):
        return True
    for x,y in ((ax,ay),(bx,by)):
        gx,gy=max(x0-x,x-x1,0),max(y0-y,y-y1,0)
        if gx*gx + gy*gy < RADIUS*RADIUS:
            return True
    length2 = dx*dx + dy*dy
    return any(0 < (x-ax)*dx+(y-ay)*dy < length2 and c*c < RADIUS*RADIUS*length2
               for (x,y),c in zip(corners,cross))


def course_edges(level, banks):
    """The riding records store each original segment relative to its coarse cell."""
    def pointer(bank, addr):
        return struct.unpack_from('<HBB', banks[bank], addr-0x4000)

    @lru_cache(None)
    def read(ref):
        addr, delta, n = ref
        bank = level['base_bank'] + delta
        if n == 255:
            return set().union(*(read(pointer(bank,addr+4*i)) for i in range(16)))
        return {struct.unpack_from('<4h', banks[bank], addr-0x4000+18*i) for i in range(n)}

    edges = set()
    w,h = level['grid']
    for y in range(h):
        for x in range(w):
            ref = pointer(level['directory_bank'],level['directory_address']+4*(y*w+x))
            for ax,ay,dx,dy in read(ref):
                edges.add((ax+x*4096,ay+y*4096,dx,dy))
    return sorted(edges)


def course_lanes(level, edges):
    sx,sy = [(v-65536*o)//64 for v,o in zip(level['start_q16'],level['origin_m'])]
    qx = max(0,min(16*level['grid'][0]-COLUMNS,sx//256-COLUMNS//2))
    qy = max(0,(sy+700)//32-128) & ~7
    target = (sy+700)//32-qy
    previous = target
    data = bytearray()
    for i in range(COLUMNS):
        x0 = (qx+i)*256
        x1 = x0+256
        blocked = bytearray(256)
        for edge in edges:
            ax,ay,dx,dy = edge
            if min(ax,ax+dx)-RADIUS >= x1 or max(ax,ax+dx)+RADIUS <= x0:
                continue
            bottom = max(0,(min(ay,ay+dy)-RADIUS-1)//32-qy)
            top = min(255,(max(ay,ay+dy)+RADIUS+1)//32-qy)
            def touches(j):
                return touches_rectangle(edge,x0,x1,(j+qy)*32,(j+qy+1)*32)
            while bottom <= top and not touches(bottom):
                bottom += 1
            while top >= bottom and not touches(top):
                top -= 1
            # Intersecting a convex capsule with a strip gives one vertical interval.
            if bottom <= top:
                blocked[bottom:top+1] = bytes([1])*(top-bottom+1)
        # Choose one contiguous open run. The ranking controls coverage only.
        runs = []
        j = 0
        while j < 256:
            if blocked[j]:
                j += 1
                continue
            a = j
            while j < 256 and not blocked[j]:
                j += 1
            b = j-1
            distance = max(a-target,target-b,0)
            continuity = max(a-previous,previous-b,0)
            runs.append((b-a+1-5*distance-continuity,a,b))
        if runs:
            _,a,b = max(runs)
            previous = max(a,min(b,target))
        else:
            a,b = 255,0
        data.extend((a,b))
    return (qx,qy//8),data


def verify_graphics_range(gen, size, bank=BANK, offset=OFFSET):
    manifest = json.loads((gen/'level_manifest.json').read_text())
    first = bank*16384 + offset
    end = first + size
    def verify(location, length):
        bank,addr = location
        start = (bank & 511)*16384+addr-0x4000
        if length and start < end and first < start+length:
            raise ValueError(f'Numeric table overlaps scenery at {location}')
    for level in manifest['levels']:
        for pointer in level['chunks']:
            verify(pointer,1024 if pointer[0]&0xc000 else 1536)
        verify(level['patterns'],16*level['pattern_count'])
        verify(level['palette'],56)
        verify(level['chunk_directory'],4*len(level['chunks']))
        verify(level['objects_pointer'],14*len(level['objects']))
    if bank in manifest['rolling_map_banks'] or manifest['rider_product_first_bank']<=bank<manifest['rider_product_first_bank']+8:
        raise ValueError('Numeric table overlaps indexed physics tables')


def generate(gen, template, dest=None):
    dest = dest or gen
    levels,banks,_ = packed_inputs(gen)
    if len(levels)!=54:
        raise ValueError('The linked strip lookup expects 54 original courses')
    origins = []
    data = bytearray()
    for level in levels:
        origin, lanes = course_lanes(level,course_edges(level,banks))
        origins.append(origin)
        data.extend(lanes)
    verify_graphics_range(gen,len(data))
    source = (gen/f'level_bank_{BANK}.c').read_text()
    bank = bytearray(map(int,source.split('{',1)[1].split('}',1)[0].split(',')))
    if OFFSET + len(data) + 2 > len(bank):
        raise ValueError('Head lane data or the lookahead exceed the graphics bank')
    bank[OFFSET:OFFSET+len(data)] = data
    asm = template.read_text()+'\n_riding_head_lane_origins::\nstrip_origins:\n'+''.join(f' .dw {x},{y}\n' for x,y in origins)
    code = dest/'head_lanes_game.s'
    table = dest/f'head_lanes_bank_{BANK}.s'
    write_if_changed(code,asm)
    lines = [f'.module strip_data469', f'.area _CODE_{BANK}', f'_level_bank_{BANK}::']
    for start,end,name in ((0,OFFSET,None), (OFFSET,OFFSET+len(data),'_riding_head_lane_data'),
                           (OFFSET+len(data),len(bank),'_riding_head_lane_end')):
        if name:
            lines.append(name+'::')
        for i in range(start,end,40):
            lines.append(' .db '+','.join(map(str,bank[i:min(i+40,end)])))
    write_if_changed(table,'\n'.join(lines)+'\n')
    return code,table


def validate_layout(symbols):
    start = (BANK<<16)+0x4000+OFFSET
    if (symbols.get('_head_strip_filtered',0)>>16 != 4 or
            symbols.get('_riding_head_lane_bank13',0)>>16 != 13 or
            symbols.get('_riding_head_lane_origins',0)>>16 != 13 or
            symbols.get('_riding_head_lane_data') != start or
            symbols.get('_riding_head_lane_end') != start+54*COLUMNS*2 or
            symbols.get(f'_normal_atlas_tail_{BANK}',start+16384) < start+54*COLUMNS*2+2):
        raise ValueError('Swept-head strip code or data moved outside its validated bank range')
