"""Ordered record programs for dense collision leaves on measured routes."""
from collections import defaultdict

from head_clearance import write_if_changed
from corner_samples import RADIUS, cell_records, q14, record_contact

# Solver-unit rectangles, aligned to 16-unit tiles within a single packed leaf.
TILED_REGIONS = (
    (39, 23488, 23936, 256, 192),
    (31, 25552, 39312, 16, 16), (31, 25344, 39472, 16, 16),
    (31, 25280, 39520, 16, 16), (31, 27328, 39712, 32, 16),
    (31, 23536, 38960, 16, 16), (31, 25280, 39552, 16, 16),
    (31, 23536, 38912, 16, 16), (31, 25568, 39408, 16, 16),
    (31, 23504, 38944, 16, 16), (31, 25296, 39472, 16, 16),
    (31, 25168, 39376, 48, 48), (31, 27280, 39712, 48, 48),
)

# Wider rectangles preserve ordered candidate records outside the fine-grained tiles.
UNIFORM_REGIONS = (
    (31, 25216, 39376, 96, 64),
    (31, 25280, 39440, 80, 112), (31, 25280, 39552, 32, 16),
    (31, 25536, 39296, 48, 144), (31, 23488, 38912, 64, 144), (31, 23552, 38912, 16, 144),
    (31, 26944, 39392, 64, 64), (31, 27168, 39488, 64, 64),
    (31, 27168, 39696, 208, 128),
    (31, 25152, 39360, 192, 128), (31, 26880, 39360, 192, 128),
    (31, 27136, 39424, 128, 128), (31, 27136, 39680, 256, 192),
    (31, 23296, 39360, 256, 128), (31, 23168, 39744, 128, 128),
)
REGIONS = TILED_REGIONS + UNIFORM_REGIONS


# The wheel reader has 314 bytes for its ordered programs in bank 5.
# Bank 93 stores five bytes per affine operand beside the projection code.
PROGRAM_BYTES = 314
PLANE_OPERANDS = 31


def tile_program(records, x, y, width=16, height=16, planes=None):
    candidates = []
    for i, record in enumerate(records):
        px, py, dx, dy, ex, ey, flags, bx, bx1, by, by1 = record
        if (bx > 128+(x+width-1)//64 or bx1 < 128+x//64 or
                by > 128+(y+height-1)//64 or by1 < 128+y//64):
            continue
        # The native projection and end-cap vector differences are signed16.
        # Keep the regular iterator if a future packed leaf exceeds its range.
        if (max(abs(x-px), abs(x+width-1-px))+max(abs(y-py), abs(y+height-1-py)) > 32767 or
                max(abs(x-px-dx), abs(x+width-1-px-dx), abs(y-py-dy), abs(y+height-1-py-dy)) > 32767 or
                max(abs(ex), abs(ey)) > 16384):
            return None
        found = set()
        near = [0, 0]
        hits = 0
        plane = planes is not None and width <= 256 and height <= 256
        for yy in range(y,y+height):
            for xx in range(x,x+width):
                vx, vy = xx-px, yy-py
                near[0] += vx*vx+vy*vy < RADIUS*RADIUS
                near[1] += (vx-dx)**2+(vy-dy)**2 < RADIUS*RADIUS
                if record_contact(record, xx, yy) is None:
                    if plane and abs(q14(-ey*vx + ex*vy)) < RADIUS:
                        plane = False
                    continue
                hits += 1
                along = q14(ex*vx+ey*vy)
                found.add(1 if along < 0 else 2 if along > (flags & 16383) else 0)
        if hits:
            op = next(iter(found)) if len(found) == 1 else 0
            # Only remove the projection guards if every point in the disk
            # actually produced this cap. All centers have been tested.
            if op and near[op-1] != hits:
                op = 0
            vertex = ((px,py) if op == 1 else (px+dx,py+dy)) if op else None
            if plane and found == {0}:
                # Every accepted center is interior, and the infinite plane
                # misses at every rejected center. Use byte coordinates from
                # one origin across the rectangle, even at a page boundary.
                xbase = x & ~255 if x >> 8 == (x+width-1) >> 8 else x
                ybase = y & ~255 if y >> 8 == (y+height-1) >> 8 else y
                raw = -ey*(xbase+255-px) + ex*(ybase-py)
                operand = (xbase & 255, ybase & 255, raw)
                if operand in planes or len(planes) < PLANE_OPERANDS:
                    op = planes.setdefault(operand, 3 + len(planes))
            candidates.append((i, op, vertex))
    shared = None
    if len(candidates) >= 2 and candidates[0][2] and candidates[0][2] == candidates[1][2]:
        shared = candidates[0][2]
        candidates = candidates[2:]
    # Missing and unprofitable programs retain the native ordered iterator.
    if len(candidates) > 8 or (len(candidates) == len(records) and not shared):
        return None
    return shared, tuple((i,op) for i,op,_ in candidates)


def tables(levels, banks, output_dir):
    leaves = defaultdict(list)
    programs = {}
    planes = {}
    payload_bytes = 0
    for region in REGIONS:
        course, x, y, width, height = region
        if course >= len(levels):
            continue
        assert (x | y | width | height) % 16 == 0
        assert x//4096 == (x+width-1)//4096 and y//4096 == (y+height-1)//4096
        records = cell_records(levels[course], banks, x, y)
        if not records:
            continue
        key = (course, x//4096, y//4096, len(records))
        uniform = region in UNIFORM_REGIONS
        if uniform and any(records != cell_records(levels[course], banks, xx, yy)
                           for yy in range(y, y+height, 16) for xx in range(x, x+width, 16)):
            continue
        step_x, step_y = (width, height) if uniform else (16, 16)
        indices = []
        for yy in range(y, y+height, step_y):
            for xx in range(x, x+width, step_x):
                program = (tile_program(records, xx & 4095, yy & 4095, step_x, step_y,
                                        planes if uniform else None)
                           if records == cell_records(levels[course], banks, xx, yy) else None)
                if program is not None and program not in programs:
                    vertex, steps = program
                    size = 1 + 4*bool(vertex) + 2*len(steps)  # packed header, vertex, records
                    new_payload_size = payload_bytes + size
                    # Each program has a byte offset into a single 256-byte payload.
                    if (len(programs) < (127 if uniform else 15) and new_payload_size <= 256
                            and len(programs) + 1 + new_payload_size <= PROGRAM_BYTES):
                        programs[program] = len(programs)+1
                        payload_bytes = new_payload_size
                indices.append(programs.get(program, 0))
        if any(indices):
            leaves[key].append((x//16 & 255, y//16 & 255, width//16, height//16, indices))
    # Work backwards so the first matching rectangle keeps its exact program.
    # A rectangle already covered by identical later programs needs no test.
    for regions in leaves.values():
        covered = {}
        for n in range(len(regions) - 1, -1, -1):
            x, y, w, h, ids = regions[n]
            tiles = {(x+xx, y+yy): ids[0] if len(ids) == 1 else ids[yy*w+xx]
                     for yy in range(h) for xx in range(w)}
            if all(covered.get(tile) == code for tile, code in tiles.items()):
                del regions[n]
            covered.update(tiles)
    # Other courses pay only the inexpensive admission comparisons, without
    # a ROM switch or touching any wheel/contact state.
    courses = sorted({key[0] for key in leaves})
    lines = ['.area _CODE_9', '_riding_candidate_gate::']
    if courses:
        lines += [' ld a,(#_physics_level_index)']
        for course in courses[:-1]:
            lines += [f' cp #{course}', ' jr z,candidate_probe']
        lines += [f' cp #{courses[-1]}', ' jp nz,_riding_leaf_dispatch', 'candidate_probe:',
                  ' ld e,#80', ' ld hl,#_riding_candidate_select', ' call ___sdcc_bcall_ehl',
                  ' or a', ' jp nz,_riding_candidate_solve']
    lines += [' jp _riding_leaf_dispatch', '.area _CODE_80', '_riding_candidate_leaves::']
    for index,(key, regions) in enumerate(leaves.items()):
        lines += [' .db '+','.join(map(str,key)), f' .dw candidate_regions_{index}']
    lines += [' .db 255']
    for index, regions in enumerate(leaves.values()):
        lines += [f'candidate_regions_{index}:']
        for n,(x,y,w,h,ids) in enumerate(regions):
            # A value below 256 encodes one program for the entire rectangle.
            dest = str(ids[0]) if len(set(ids)) == 1 else f'candidate_tiles_{index}_{n}'
            lines += [f' .db {w},{x},{y},{h}', f' .dw {dest}']
        lines += [' .db 0']
        for n,(_,_,w,h,ids) in enumerate(regions):
            if len(set(ids)) == 1:
                continue
            lines += [f'candidate_tiles_{index}_{n}:']
            for row in range(h):
                values = ids[row*w:(row+1)*w]+[0]
                packed = [values[k] | (values[k+1] << 4) for k in range(0,w,2)]
                lines += [' .db '+','.join(map(str,packed))]
    lines += ['.area _CODE_5', '_riding_candidate_programs::']
    for i in range(1,len(programs)+1):
        lines += [f' .db candidate_program_{i}-_riding_candidate_payload']
    lines += ['_riding_candidate_payload::']
    for (vertex, records),i in programs.items():
        lines += [f'candidate_program_{i}:',f' .db {len(records) | (128 if vertex else 0)}']
        if vertex:
            lines += [f' .dw {vertex[0]},{vertex[1]}']
        for rank,op in records:
            lines += [f' .db {rank},{op}']
    operands = ['.area _CODE_93', '_riding_candidate_intercepts::']
    for xbase, ybase, raw in planes:
        # Every region origin is a multiple of sixteen in both directions.
        operands += [f' .db {xbase | ybase >> 4}',
                     ' .db '+','.join(str((raw >> shift) & 255) for shift in (0,8,16,24))]
    write_if_changed(output_dir/'wheel_candidate_planes.s', '\n'.join(operands)+'\n')
    return lines
