"""Pack exact terrain-vertex normals into spare MBC5 graphics tails."""
import json
from math import isqrt
import re
import struct

from head_clearance import write_if_changed
from head_refinement import ROOM

INNER = 396
OUTER = 410
GROUPS = 145
RECORD = struct.Struct('<HHBBH')


def encode(x, y, roots):
    d2 = x*x + y*y
    root = roots[min((d2-16384) >> 9, len(roots)-1)]
    px, py = x*root, y*root
    nx, ny = px >> 4, py >> 4
    base = (nx*x + ny*y + 8192) >> 14
    # Negative nonintegral products take one's complement, exact ones negate.
    flags = (int(px % 16 == 0) << 4) | (int(py % 16 == 0) << 5)
    projected_errors = []
    for signs in range(4):
        ax = nx + bool(signs & 1 and px % 16)
        ay = ny + bool(signs & 2 and py % 16)
        extra = ((ax*x + ay*y + 8192) >> 14) - base
        assert extra in (0, 1)
        flags |= extra << signs
        length = base + extra
        sx = -1 if signs & 1 else 1
        sy = -1 if signs & 2 else 1
        projected_x = (sx * ax * length + 8192) >> 14
        projected_y = (sy * ay * length + 8192) >> 14
        projected_errors.append((sx * projected_x - x, sy * projected_y - y))
    # A certified vector reconstructs its source point in every octant,
    # optionally displaced one unit along the larger coordinate.
    if len(set(projected_errors)) == 1:
        flags |= {(0, 0): 0x40, (0, -1): 0x80, (0, 1): 0xc0}.get(projected_errors[0], 0)
    assert 256 <= base < 511 and d2 >> 16 == 2
    base_byte = base & 255
    assert not base_byte & 64
    if not flags & 0xc0 and len(set(projected_errors)) == 1:
        delta = projected_errors[0]
        if delta in ((-1, -1), (1, 1)):
            flags |= 0x80 if delta[1] < 0 else 0xc0
            base_byte |= 64
    return RECORD.pack(nx, ny, base_byte, flags, d2 & 65535)


def generate(gen, roots_path, wheel_rows, dest=None):
    roots = [int(x) for x in re.findall(r'\d+', roots_path.read_text().split('\n',1)[1])]
    groups = []
    for group in range(GROUPS):
        rows = []
        for small in (2*group, 2*group+1):
            values = [big for big in range(small, OUTER) if INNER**2 <= small**2 + big**2 < OUTER**2]
            assert values and 256 <= values[0] and values == list(range(values[0], values[-1]+1))
            rows.append((values[0]-256, b''.join(encode(small, b, roots) for b in values)))
        groups.append(rows)
    assert 2*(2*GROUPS)**2 >= OUTER**2
    graphics = json.loads((gen/'level_manifest.json').read_text())
    wheel_banks = set(map(int,re.findall(r'^_wheel_terrain_tail_(\d+)::',wheel_rows.read_text(),re.M)))
    capacity = {}
    for bank in range(max(256,graphics['first_bank']),graphics['last_bank']+1):
        if bank in wheel_banks or bank in ROOM:
            continue
        contents = (gen/f'level_bank_{bank}.c').read_bytes().split(b'{',1)[1].split(b'}',1)[0].strip().rstrip(b',')
        capacity[bank] = 16384 - (1+contents.count(b',') if contents else 0)
    room = capacity.copy()
    placement = {}
    sizes = [8+sum(len(payload) for _,payload in group) for group in groups]
    for i in sorted(range(GROUPS),key=lambda i:-sizes[i]):
        fits = [bank for bank in room if room[bank]>=sizes[i]]
        if not fits:
            # Alternate level packs can still use the exact arithmetic fallback.
            continue
        bank = min(fits,key=lambda b:(room[b],b))
        placement[i] = bank
        room[bank] -= sizes[i]
    # The two rows share their outer bound. An offset below both row
    # starts can skip the banked annulus lookup entirely.
    miss_span = 1 + max(isqrt(OUTER**2-1-(2*g)**2) - max(s, isqrt(INNER**2-1-s*s)+1)
                        for g in range(GROUPS) for s in (2*g, 2*g+1))
    out = ['.module normal_atlas_data', '.globl normal_ring_miss_span',
           f'normal_ring_miss_span = {miss_span}', '.area _CODE_9', '_riding_normal_groups::']
    for i in range(GROUPS):
        # Both sorted rows lie below the outer limit of the even row.
        out.append(f' .db {isqrt(OUTER*OUTER - 1 - (2*i)**2)-256}')
        if i in placement:
            out += [f' .dw normal_group_{i}',f' .db {placement[i]&255}']
        else:
            out += [' .dw 0',' .db 0']
    out += ['_riding_normal_groups_end::']
    for bank in sorted(set(placement.values())):
        out += [f'.globl _normal_graphics_end_{bank}',f'_normal_graphics_end_{bank} = {32768-capacity[bank]}',
                f'.area _CODE_{bank}',f'_normal_atlas_tail_{bank}::']
        for i in sorted(i for i,b in placement.items() if b==bank):
            group = groups[i]
            out += [f'normal_group_{i}:']
            for j,(start,data) in enumerate(group):
                out += [f' .db {start},{len(data)//RECORD.size}',f' .dw normal_row_{2*i+j}']
            for j,(_,data) in enumerate(group):
                out += [f'normal_row_{2*i+j}:']
                out += [' .db '+','.join(map(str,data[k:k+32])) for k in range(0,len(data),32)]
        out += [f'_normal_atlas_end_{bank}::']
    path = (dest or gen)/'normal_atlas_data.s'
    write_if_changed(path,'\n'.join(out)+'\n')
    return path


def validate_layout(symbols):
    if (symbols['_riding_normal_groups'] >> 16 != 9 or
            symbols['_riding_normal_groups_end']-symbols['_riding_normal_groups'] != 4*GROUPS or
            symbols['_riding_normal_ring'] >> 16 != 9 or symbols['_riding_normal_ring_read'] >= 0x4000):
        raise ValueError('Vertex normal atlas requires bank 9 callers and a fixed-ROM reader')
    for name in ('_riding_ring_equal_points', '_riding_ring_cached_point', '_riding_contact_merge'):
        if symbols[name] >> 16 != 9:
            raise ValueError(f'{name} requires the wheel contact solver in bank 9')
    for name, start in symbols.items():
        match = re.fullmatch(r'_normal_atlas_tail_(\d+)',name)
        if match:
            bank = int(match[1])
            end = symbols[f'_normal_atlas_end_{bank}']
            bank_end = symbols[f's__CODE_{bank}'] + symbols[f'l__CODE_{bank}']
            if bank == 476 and '_riding_pivot_bound' in symbols:
                if symbols['_riding_pair_bound_end'] != bank_end:
                    raise ValueError('Pivot bounds must finish immediately after the bank 476 normal atlas')
                bank_end = symbols['_riding_pivot_bound']
            if (not 256 <= bank < 508 or bank in ROOM or f'_wheel_terrain_tail_{bank}' in symbols
                    or symbols[f'_level_bank_{bank}'] != (bank<<16)+0x4000
                    or start != (bank<<16)+symbols[f'_normal_graphics_end_{bank}']
                    or end != bank_end
                    or not start < end <= (bank<<16)+0x8000):
                raise ValueError(f'Vertex normals overlap another asset or overflow bank {bank}')
