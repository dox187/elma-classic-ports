"""Compile conservative wheel certificates from the cartridge's ordered collision records."""
from collections import Counter
from functools import lru_cache
import json
import re
import struct

from head_clearance import packed_inputs, write_if_changed
from wheel_refinement import refinement_tables

GENERAL = 255
WINDOW = 64
RADIUS = 410
SIZE = 512
RECORD = struct.Struct('<6hH4B')


def projected_range(x0, x1, y0, y1, dx, dy):
    """Extrema of the solver's signed rounded Q14 dot over an integer box."""
    a, b = x0 * dx, x1 * dx
    c, d = y0 * dy, y1 * dy
    return ((min(a, b) + min(c, d) + 8192) >> 14,
            (max(a, b) + max(c, d) + 8192) >> 14)


@lru_cache(maxsize=None)
def interior_bounds(ex, ey, last):
    """Integer X/Y bounds of the finite strip accepted by both rounded dots."""
    determinant = ex*ex + ey*ey
    if not determinant:
        return -32768, 32767, -32768, 32767
    # Round-to-nearest with positive ties gives these inclusive raw Q14
    # intervals for tangent 0..last and perpendicular distance -409..409.
    tangent = (-8192, (last+1)*16384 - 8193)
    normal = (-409*16384 - 8192, 410*16384 - 8193)

    def axis(a, b):
        t = tangent[0]*a, tangent[1]*a
        n = normal[0]*b, normal[1]*b
        lower = min(t) + min(n)
        upper = max(t) + max(n)
        return (lower+determinant-1)//determinant, upper//determinant

    # Invert the packed direction matrix, including its quantized length.
    return axis(ex, -ey) + axis(ey, ex)


def classify(records, x, y, size=SIZE):
    # Keep the legacy plane classification as well as every record whose
    # interior or real radial cap might contribute anywhere in this square.
    single = first = last_index = 0
    for i, (px, py, dx, dy, ex, ey, length, bx, bx1, by, by1) in enumerate(records, 1):
        x0, x1 = max(x, (bx-128)*64)-px, min(x+size-1, (bx1-127)*64-1)-px
        y0, y1 = max(y, (by-128)*64)-py, min(y+size-1, (by1-127)*64-1)-py
        if x0 > x1 or y0 > y1:
            continue
        # The native loop subtracts in signed16 before either rounded dot.
        # Packed 8 m pieces fit easily. Fall back for any future wider input.
        if (min(x0,y0) < -32768 or max(x1,y1) > 32767 or
                max(abs(ex), abs(ey)) > 16384):
            return GENERAL, GENERAL
        if max(abs(x0), abs(x1))+max(abs(y0),abs(y1)) > 32767:
            return GENERAL, GENERAL
        d0, d1 = projected_range(x0,x1,y0,y1,-ey,ex)
        if d1 <= -RADIUS or d0 >= RADIUS:
            continue
        p0, p1 = projected_range(x0,x1,y0,y1,ex,ey)
        end = length & 0x3fff
        last = end - bool(length & 0x8000)
        # The synthetic end at p==end is owned by the next piece. Only
        # original endpoints can contribute a radial contact outside [0,end].
        def near_vertex(vx, vy):
            tx = max(x0-vx, vx-x1, 0)
            ty = max(y0-vy, vy-y1, 0)
            return tx*tx + ty*ty < RADIUS*RADIUS
        cap = p0 < 0 and not length & 0x4000 and near_vertex(0, 0)
        if p1 > end and not length & 0x8000:
            if min(x0-dx,y0-dy) < -32768 or max(x1-dx,y1-dy) > 32767:
                return GENERAL, GENERAL
            cap = cap or near_vertex(dx, dy)
        interior = p1 >= 0 and p0 <= last
        if interior and not cap:
            ix0, ix1, iy0, iy1 = interior_bounds(ex, ey, last)
            interior = x1 >= ix0 and x0 <= ix1 and y1 >= iy0 and y0 <= iy1
        if not interior and not cap:
            continue
        first = first or i
        last_index = i
        single = GENERAL if single or cap or p0 < 0 or p1 > last else i
    if single != GENERAL:
        code = single if single < WINDOW else GENERAL
        return code, code
    count = last_index - first + 1
    code = WINDOW + 4*(first-1) + count-1
    if not 1 <= count <= 4 or code >= GENERAL or count == len(records):
        return GENERAL, GENERAL
    return GENERAL, code


def level_rows(level, banks):
    base = level['base_bank']
    def pointer(bank, address):
        return struct.unpack_from('<HBB', banks[bank], address-0x4000)
    @lru_cache(maxsize=None)
    def records(ptr):
        addr, rel, count = ptr
        if not count:
            return ()
        return tuple(RECORD.iter_unpack(banks[base+rel][addr-0x4000:addr-0x4000+RECORD.size*count]))
    w, h = level['grid']
    for y in range(h):
        row = []
        for x in range(w):
            ptr = pointer(level['directory_bank'],level['directory_address']+4*(w*y+x))
            blocks = []
            for i in range(16):
                child = pointer(base+ptr[1], ptr[0]+i*4) if ptr[2] == 255 else ptr
                leaf = records(child)
                if not leaf:
                    blocks.append((bytes(4), bytes(4), bytes(16)))
                else:
                    tx, ty = (i%4)*1024, (i//4)*1024
                    squares = [classify(leaf, tx+sx*SIZE, ty+sy*SIZE)
                               for sy in range(2) for sx in range(2)]
                    original, refined = zip(*squares)
                    quarters = bytes(classify(leaf, tx+qx*256, ty+qy*256, 256)[1]
                                     if refined[2*(qy//2)+qx//2] == GENERAL or
                                        original[2*(qy//2)+qx//2] == GENERAL
                                     else refined[2*(qy//2)+qx//2]
                                     for qy in range(4) for qx in range(4))
                    blocks.append((bytes(original), bytes(refined), quarters))
            row.append(tuple(blocks))
        yield row


def data_lines(data):
    return [' .db '+','.join(map(str,data[i:i+24])) for i in range(0,len(data),24)]


def generate(gen, dest=None):
    if dest is None:
        dest = gen
    levels, banks, _ = packed_inputs(gen)
    rows = [[*level_rows(level,banks)] for level in levels]
    # Retain the original 256 patterns. An additional page describes the
    # most useful exact refinements, selected independently for each metre.
    pairs = Counter(block[:2] for level in rows for row in level for cell in row for block in cell)
    frequencies = Counter()
    for (old, new), count in pairs.items():
        frequencies[old] += count
    zero, unknown = bytes(4), bytes([GENERAL])*4
    del frequencies[zero], frequencies[unknown]
    patterns = [zero, unknown] + [p for p,_ in frequencies.most_common(254)]
    codes = {p:i for i,p in enumerate(patterns)}
    gains = Counter()
    for (old, new), count in pairs.items():
        if new in codes:
            continue
        previous = old if old in codes else unknown
        gains[new] += count * sum(a == GENERAL and b != GENERAL for a,b in zip(previous,new))
    # The upper page always starts exactly 256 entries after the lower page.
    extra = [p for p,benefit in gains.most_common(256) if benefit]
    codes.update((p,256+i) for i,p in enumerate(extra))
    if extra:
        patterns += [unknown] * (256-len(patterns)) + extra
    def pack_cell(cell):
        ids = [codes.get(new, codes.get(old,1)) for old,new,_ in cell]
        flags = sum((index >> 8) << bit for bit,index in enumerate(ids))
        return bytes(i & 255 for i in ids) + flags.to_bytes(2,'little')
    # Plain rows have a second 128-entry dictionary. Keep the originally
    # selected non-general answer in every quarter. Intersect refinements
    # across cells sharing a row-local layout, so the row takes no more ROM.
    quarter_candidates = Counter()
    prepared = []
    for level in rows:
        level_rows_prepared = []
        for row in level:
            layouts = {}
            cells = [pack_cell(cell) for cell in row]
            for cell, data in zip(row, cells):
                if data[-2:] == bytes(2) and max(data[:16]) < 128 and any(data):
                    layouts.setdefault(data, []).append(cell)
            variants = {}
            for layout, members in layouts.items():
                alternatives = []
                for sub, index in enumerate(layout[:16]):
                    old = patterns[index]
                    if GENERAL not in old:
                        alternatives.append(None)
                        continue
                    # Each cell in a shared layout can have different records.
                    values = bytearray(16)
                    for q in range(16):
                        h = (q//8)*2 + (q%4)//2
                        if old[h] != GENERAL:
                            values[q] = old[h]
                        else:
                            code = members[0][sub][2][q]
                            values[q] = code if all(c[sub][2][q] == code for c in members) else GENERAL
                    key = bytes(values)
                    gain = sum(old[(q//8)*2+(q%4)//2] == GENERAL and v != GENERAL
                               for q,v in enumerate(key))
                    alternatives.append(key if gain else None)
                    if gain:
                        quarter_candidates[key] += gain * len(members)
                variants[layout] = alternatives
            level_rows_prepared.append((cells, variants))
        prepared.append(level_rows_prepared)
    quarter_patterns = [p for p,_ in quarter_candidates.most_common(128)]
    quarter_codes = {p:i for i,p in enumerate(quarter_patterns)}
    # Each level_bank array starts at 0x4000, as required by the graphics
    # engine. Append row records to the available tails *after* these objects.
    graphics = json.loads((gen/'level_manifest.json').read_text())
    free = {}
    for bank in range(graphics['first_bank'],graphics['last_bank']+1):
        source = (gen/f'level_bank_{bank}.c').read_bytes()
        values = source.split(b'{',1)[1].split(b'}',1)[0].strip().rstrip(b',')
        free[bank] = 16384-(1+values.count(b',') if values else 0)
    tables = {}
    out = ['.module wheel_terrain_rows', '.area _CODE_9',
           '.globl _wheel_terrain_levels', f'_wheel_terrain_levels = {len(levels)}', '_wheel_terrain_patterns::']
    for pat in patterns:
        out.extend(data_lines(pat))
    out.append('_wheel_terrain_maps::')
    for i, level in enumerate(levels):
        w,h = level['grid']
        out.extend([f' .db {w},{h}', f' .dw wheel_rows_{i}'])
    starts = {bank: 0x8000 - room for bank, room in free.items()}
    for i, level in enumerate(prepared):
        out.append(f'wheel_rows_{i}:')
        for j,(cells, variants) in enumerate(level):
            layouts = dict.fromkeys(c for c in cells if c != bytes(18))
            if not layouts:
                out += [' .dw 0',' .db 0']
                continue
            # Point the row label between the two layout sets. Positive
            # indices keep the normal 16-byte format. Negative indices run
            # backwards over 18-byte layouts with a 16-bit page selector.
            plain = [c for c in layouts if c[-2:] == bytes(2)]
            extended = [c for c in layouts if c[-2:] != bytes(2)]
            if len(plain) > 127 or len(extended) > 128:
                out += [' .dw 1',' .db 0']
                continue
            # Keep low six bits for plain layout indices. Spill unusually
            # diverse rows into the existing 18-byte representation.
            extended += plain[63:]
            plain = plain[:63]
            if len(extended) > 128:
                out += [' .dw 1',' .db 0']
                continue
            ids = {cell:k+1 for k,cell in enumerate(plain)}
            plain_data = []
            for cell in plain:
                alts = variants.get(cell, ())
                alt = bytes(128+quarter_codes[v] if v in quarter_codes else orig
                            for v,orig in zip(alts,cell[:16]))
                if alt and alt != cell[:16]:
                    ids[cell] |= 64
                    plain_data.append(alt)
                else:
                    plain_data.append(cell[:16])
            ids.update((cell,255-k) for k,cell in enumerate(extended))
            prefix = b''.join(reversed(extended))
            payload = bytes(ids.get(cell,0) for cell in cells) + b''.join(plain_data)
            size = len(prefix) + len(payload)
            # First fit in numerical order. A missing row always uses the
            # general query if an alternate graphics pack has less free room.
            bank = next((b for b in free if free[b] >= size), None)
            if bank is None:
                out += [' .dw 1',' .db 0']
                continue
            name = f'wheel_row_{i}_{j}'
            out += [f' .dw {name}'+('+0x8000' if bank>=256 else ''), f' .db {bank&255}']
            tables.setdefault(bank,[]).extend([*data_lines(prefix),name+'::',*data_lines(payload)])
            free[bank] -= size
    for bank,lines in tables.items():
        out += [f'.globl _wheel_graphics_end_{bank}', f'_wheel_graphics_end_{bank} = {starts[bank]}',
                f'.area _CODE_{bank}',f'_wheel_terrain_tail_{bank}::',*lines,
                f'_wheel_terrain_end_{bank}::']
    out += ['.area _CODE_5', '_wheel_quarter_patterns::']
    for pattern in quarter_patterns:
        out.extend(data_lines(pattern))
    out += ['_wheel_quarter_patterns_end::']
    out += refinement_tables(levels, banks, rows, codes, patterns)
    path = dest/'wheel_terrain_rows.s'
    write_if_changed(path,'\n'.join(out)+'\n')
    return path


def validate_layout(symbols):
    if (symbols.get('_riding_wheel_lookup', 0) >> 16 != 9
            or symbols.get('_riding_wheel_cached_plane', 0) >> 16 != 9
            or symbols.get('_riding_wheel_cached_window', 0) >> 16 != 9
            or symbols.get('_riding_wheel_read_map', 65535) >= 0x4000):
        raise ValueError('Wheel terrain requires its caller in bank 9 and a fixed-ROM reader')
    if '_riding_leaf_dispatch' in symbols and (symbols['_riding_leaf_dispatch'] >= 0x4000 or
            symbols['_riding_leaf_classify'] >> 16 != 31 or symbols['_riding_leaf_general'] >> 16 != 9):
        raise ValueError('Wheel neighborhood queries require a fixed reader and classifiers in banks 31 and 9')
    if '_riding_wheel_refinement' in symbols:
        begin = symbols['_riding_wheel_refinement']
        levels = symbols['_wheel_refinement_levels']
        rows = symbols['_wheel_refinement_rows']
        end = symbols['_wheel_refinement_end']
        directory_end = levels + 3*symbols['_wheel_terrain_levels']
        if (begin >> 16 != 20 or not begin < levels <= directory_end <= rows < end <= 0x148000
                or (rows-directory_end) % 8 or (end-rows) % 4 or end-rows > 512*4
                or end != symbols['s__CODE_20']+symbols['l__CODE_20']):
            raise ValueError('Wheel refinement directory and rows must fit the tail of bank 20')
    start = symbols['_wheel_quarter_patterns']
    end = symbols['_wheel_quarter_patterns_end']
    if (start >> 16 != 5 or not 0 <= end-start <= 2048 or end > 0x58000
            or symbols['_riding_wheel_read_quarter'] >= 0x4000):
        raise ValueError('Wheel quarter patterns require a bank 5 table and a fixed reader')
    for name, addr in symbols.items():
        match = re.fullmatch(r'_wheel_terrain_tail_(\d+)',name)
        if match:
            bank = int(match[1])
            end = symbols[f'_wheel_terrain_end_{bank}']
            graphics = symbols.get(f'_level_bank_{bank}')
            if (graphics != (bank<<16)+0x4000 or addr != (bank<<16)+symbols[f'_wheel_graphics_end_{bank}'] or end <= addr
                    or addr >> 16 != bank or end > (bank<<16)+0x8000):
                raise ValueError(f'Wheel terrain overlaps graphics or exceeds ROM bank {bank}')
