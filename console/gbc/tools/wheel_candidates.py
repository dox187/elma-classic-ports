"""Ordered record programs for dense collision leaves on measured routes."""
from collections import defaultdict

from corner_samples import RADIUS, cell_records, q14, record_contact

# Solver-unit rectangles, aligned to 16-unit tiles within a single packed leaf.
REGIONS = (
    (39, 23488, 23936, 256, 192),
    (31, 25552, 39312, 16, 16), (31, 25344, 39472, 16, 16),
    (31, 25280, 39520, 16, 16), (31, 27328, 39712, 32, 16),
    (31, 23536, 38960, 16, 16), (31, 25280, 39552, 16, 16),
    (31, 23536, 38912, 16, 16), (31, 25568, 39408, 16, 16),
    (31, 23504, 38944, 16, 16), (31, 25296, 39472, 16, 16),
)


def tile_program(records, x, y):
    candidates = []
    for i, record in enumerate(records):
        px, py, dx, dy, ex, ey, flags, bx, bx1, by, by1 = record
        if not (bx <= 128+x//64 <= bx1 and by <= 128+y//64 <= by1):
            continue
        # The native projection and end-cap vector differences are signed16.
        # Keep the regular iterator if a future packed leaf exceeds its range.
        if (max(abs(x-px), abs(x+15-px))+max(abs(y-py), abs(y+15-py)) > 32767 or
                max(abs(x-px-dx), abs(x+15-px-dx), abs(y-py-dy), abs(y+15-py-dy)) > 32767 or
                max(abs(ex), abs(ey)) > 16384):
            return None
        found = set()
        near = [0, 0]
        hits = 0
        for yy in range(y,y+16):
            for xx in range(x,x+16):
                vx, vy = xx-px, yy-py
                near[0] += vx*vx+vy*vy < RADIUS*RADIUS
                near[1] += (vx-dx)**2+(vy-dy)**2 < RADIUS*RADIUS
                if record_contact(record, xx, yy) is None:
                    continue
                hits += 1
                along = q14(ex*vx+ey*vy)
                found.add(1 if along < 0 else 2 if along > (flags & 16383) else 0)
        if hits:
            op = next(iter(found)) if len(found) == 1 else 0
            # Only remove the projection guards if every point in the disk
            # actually produced this cap. All 256 centers have been tested.
            if op and near[op-1] != hits:
                op = 0
            vertex = ((px,py) if op == 1 else (px+dx,py+dy)) if op else None
            candidates.append((i, op, vertex))
    shared = None
    if len(candidates) >= 2 and candidates[0][2] and candidates[0][2] == candidates[1][2]:
        shared = candidates[0][2]
        candidates = candidates[2:]
    # Missing and unprofitable programs retain the native ordered iterator.
    if len(candidates) > 8 or (len(candidates) == len(records) and not shared):
        return None
    return shared, tuple((i,op) for i,op,_ in candidates)


def tables(levels, banks):
    leaves = defaultdict(list)
    programs = {}
    program_bytes = 0
    for course, x, y, width, height in REGIONS:
        if course >= len(levels):
            continue
        assert (x | y | width | height) % 16 == 0
        assert x//4096 == (x+width-1)//4096 and y//4096 == (y+height-1)//4096
        records = cell_records(levels[course], banks, x, y)
        if not records:
            continue
        key = (course, x//4096, y//4096, len(records))
        indices = []
        for yy in range(y, y+height, 16):
            for xx in range(x, x+width, 16):
                program = (tile_program(records, xx & 4095, yy & 4095)
                           if records == cell_records(levels[course], banks, xx, yy) else None)
                if program is not None and program not in programs:
                    vertex, steps = program
                    size = 4 + 4*bool(vertex) + 2*len(steps)  # pointer, header, vertex, records
                    if len(programs) < 15 and program_bytes + size <= 256:
                        programs[program] = len(programs)+1
                        program_bytes += size
                indices.append(programs.get(program, 0))
        if any(indices):
            leaves[key].append((x//16 & 255, y//16 & 255, width//16, height//16, indices))
    # Other courses pay only the inexpensive admission comparisons, without
    # a ROM switch or touching any wheel/contact state.
    courses = sorted({key[0] for key in leaves})
    lines = ['.area _CODE_9', '_riding_candidate_gate::']
    if courses:
        lines += [' ld a,(#_physics_level_index)']
        for course in courses[:-1]:
            lines += [f' cp #{course}', ' jr z,candidate_probe']
        lines += [f' cp #{courses[-1]}', ' jp nz,_riding_leaf_dispatch', 'candidate_probe:',
                  ' ld e,#5', ' ld hl,#_riding_candidate_select', ' call ___sdcc_bcall_ehl',
                  ' or a', ' jp nz,_riding_candidate_solve']
    lines += [' jp _riding_leaf_dispatch', '.area _CODE_5', '_riding_candidate_leaves::']
    for index,(key, regions) in enumerate(leaves.items()):
        lines += [' .db '+','.join(map(str,key)), f' .dw candidate_regions_{index}']
    lines += [' .db 255']
    for index, regions in enumerate(leaves.values()):
        lines += [f'candidate_regions_{index}:']
        for n,(x,y,w,h,ids) in enumerate(regions):
            lines += [f' .db {w},{x},{y},{h}', f' .dw candidate_tiles_{index}_{n}']
        lines += [' .db 0']
        for n,(_,_,w,h,ids) in enumerate(regions):
            lines += [f'candidate_tiles_{index}_{n}:']
            for row in range(h):
                values = ids[row*w:(row+1)*w]+[0]
                packed = [values[k] | (values[k+1] << 4) for k in range(0,w,2)]
                lines += [' .db '+','.join(map(str,packed))]
    lines += ['.area _CODE_7', '_riding_candidate_programs::']
    for i in range(1,len(programs)+1):
        lines += [f' .dw candidate_program_{i}']
    for (vertex, records),i in programs.items():
        lines += [f'candidate_program_{i}:',f' .db {int(bool(vertex))}']
        if vertex:
            lines += [f' .dw {vertex[0]},{vertex[1]}']
        lines += [f' .db {len(records)}']
        for rank,op in records:
            lines += [f' .db {rank},{op}']
    return lines
