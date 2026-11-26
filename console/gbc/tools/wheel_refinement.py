"""Quarter-metre refinements of dense ordered wheel-contact windows."""
import struct

# The standard and extended controller corpus determines which visited metres
# have the most remaining candidate work. These are coverage keys only. Every
# answer is rebuilt from the packed geometry, including for alternate assets.
OBSERVED_METRES = (
    ((2, 0, 15), (2, 1, 0), (2, 0, 12), (2, 1, 1), (0, 1, 3), (1, 1, 3), (1, 1, 0)),
    ((15, 1, 0), (17, 0, 12)),
    ((10, 2, 1), (9, 2, 6), (10, 2, 6), (11, 2, 4), (9, 2, 5), (9, 2, 3)),
    ((1, 3, 1), (1, 3, 0), (1, 3, 2), (0, 3, 3), (2, 3, 0), (1, 3, 3)),
    ((34, 2, 8),),
    ((9, 6, 1), (12, 6, 8), (8, 6, 6), (2, 1, 10), (8, 6, 7), (11, 6, 11), (6, 6, 11), (6, 6, 10), (2, 1, 9)),
    ((7, 1, 10), (8, 1, 8), (7, 1, 11), (7, 1, 12), (7, 1, 9)),
    ((6, 4, 5), (6, 3, 8), (6, 4, 11), (6, 3, 9), (6, 4, 1)),
    ((13, 3, 3), (12, 3, 3)),
    ((14, 3, 10), (13, 3, 9)),
    ((10, 7, 10), (10, 7, 8), (10, 7, 9), (10, 7, 11), (10, 7, 5), (11, 7, 8)),
    ((10, 3, 6), (10, 3, 4), (9, 3, 1), (10, 3, 5), (9, 3, 2), (10, 3, 0)),
    ((6, 5, 8), (7, 5, 4), (6, 5, 5), (6, 5, 9)),
    ((15, 2, 15),),
    ((18, 12, 14),),
    ((7, 18, 10),),
    ((5, 10, 1), (5, 9, 12), (4, 9, 14)),
    ((4, 11, 9),),
    ((21, 16, 4), (19, 16, 7), (19, 16, 6), (19, 16, 5)),
    ((20, 22, 15), (20, 22, 14), (20, 22, 10), (19, 22, 5)),
    ((6, 4, 4), (6, 4, 5), (5, 4, 11), (3, 4, 6)),
    ((4, 3, 14), (4, 3, 15), (4, 4, 1), (4, 4, 5)),
    ((8, 3, 13),),
    ((26, 4, 6), (25, 4, 9)),
    ((7, 6, 10), (8, 6, 5)),
    ((8, 6, 12), (7, 7, 3), (7, 6, 15)),
    ((6, 4, 0),),
    ((2, 8, 0), (1, 7, 15)),
    ((1, 25, 9), (1, 25, 10), (2, 24, 11), (2, 24, 10)),
    ((24, 13, 13),),
    ((8, 11, 10), (9, 11, 8), (8, 11, 4), (8, 11, 11), (7, 11, 7), (8, 11, 9), (8, 11, 5)),
    ((5, 9, 9), (6, 9, 12), (5, 9, 15), (6, 10, 1), (5, 9, 8)),
    ((1, 6, 1), (2, 5, 12), (1, 6, 4)),
    ((16, 16, 8), (16, 16, 12), (15, 15, 6), (15, 15, 9), (15, 16, 11)),
    ((9, 19, 1), (9, 19, 7)),
    ((10, 8, 0), (9, 8, 5)),
    ((4, 8, 13),),
    ((15, 9, 7), (14, 9, 6), (14, 9, 7), (14, 9, 8), (14, 9, 9)),
    ((38, 7, 3), (37, 6, 11)),
    ((5, 5, 15), (5, 5, 11), (5, 5, 14), (4, 5, 8)),
    ((7, 7, 11),),
    ((9, 7, 14), (10, 7, 12), (9, 7, 15), (9, 7, 13)),
    ((29, 12, 3), (27, 12, 3), (25, 10, 12)),
    ((1, 34, 10), (1, 34, 11), (1, 34, 9), (2, 34, 9), (2, 34, 8), (2, 34, 5)),
    ((1, 33, 12), (1, 34, 0), (1, 33, 3), (1, 33, 2)),
    ((42, 16, 1), (42, 16, 3), (42, 16, 0), (42, 16, 7), (42, 16, 2), (42, 15, 12)),
    (),
    ((25, 34, 6), (25, 34, 5), (25, 34, 4), (24, 33, 15), (24, 33, 10)),
    ((22, 17, 8), (21, 17, 11)),
    ((7, 7, 14), (5, 7, 15), (6, 7, 14)),
    ((1, 3, 5),),
    ((15, 5, 15), (16, 6, 12), (16, 6, 8), (16, 6, 9), (16, 6, 13), (16, 5, 12)),
    ((12, 8, 6), (13, 8, 8), (12, 8, 7), (12, 8, 5), (12, 8, 4), (12, 8, 12)),
    ((7, 9, 10), (6, 9, 2), (6, 9, 1)),
)
PAYLOAD_BYTES = 4496


def refinement_tables(levels, banks, rows, codes, patterns):
    selected = [[] for _ in levels]
    row_ids = {}
    used = set()
    payload_size = 0

    def install(level, cx, cy, sub, quarters):
        nonlocal payload_size
        key = (level, cx, cy, sub)
        if key in used:
            return
        parts = [quarters[i:i+4] for i in range(0, 16, 4)]
        extra = 8 + 4*len(set(parts).difference(row_ids))
        if payload_size+extra > PAYLOAD_BYTES or len(selected[level]) >= 255:
            return
        if len(row_ids) + len(set(parts).difference(row_ids)) > 512:
            return
        indices = [row_ids.setdefault(part, len(row_ids)) for part in parts]
        flags = sum((index >> 8) << i for i, index in enumerate(indices))
        selected[level].append((cx, cy, sub, flags, *(index & 255 for index in indices)))
        payload_size += extra
        used.add(key)

    for l, (level, grid) in enumerate(zip(levels, rows)):
        w, h = level['grid']
        for cx, cy, sub in OBSERVED_METRES[l] if l < len(OBSERVED_METRES) else ():
            if cx < w and cy < h:
                install(l, cx, cy, sub, grid[cy][cx][sub][2])

    # Rank all remaining metres by the reduction in ordered candidate records
    # across their sixteen quarters. Round-robin selection gives each course
    # a share of the remaining space, including terrain away from the starts.
    ranked = []
    for l, (level, grid) in enumerate(zip(levels, rows)):
        w, _ = level['grid']
        def pointer(bank, address):
            return struct.unpack_from('<HBB', banks[bank], address-0x4000)
        choices = []
        for cy, row in enumerate(grid):
            for cx, cell in enumerate(row):
                address, rel, n = pointer(level['directory_bank'], level['directory_address']+4*(cy*w+cx))
                if not n:
                    continue
                for sub, (old, refined, quarters) in enumerate(cell):
                    if (l, cx, cy, sub) in used:
                        continue
                    count = pointer(level['base_bank']+rel, address+4*sub)[2] if n == 255 else n
                    if count < 2:
                        continue
                    halves = patterns[codes.get(refined, codes.get(old, 1))]
                    def cost(code):
                        if code == 255:
                            return count+4
                        return 0 if code < 64 else 2+(code-64)%4
                    gain = sum(cost(halves[(q//8)*2+(q%4)//2])-cost(code)
                               for q,code in enumerate(quarters))
                    if gain > 0:
                        choices.append((-gain,cx,cy,sub,quarters))
        ranked.append(sorted(choices))
    for rank in range(max(map(len,ranked), default=0)):
        if payload_size + 8 > PAYLOAD_BYTES:
            break
        for l, choices in enumerate(ranked):
            if rank < len(choices):
                _, cx, cy, sub, quarters = choices[rank]
                install(l, cx, cy, sub, quarters)

    lines = ['.area _CODE_20', '_wheel_refinement_levels::']
    for l, entries in enumerate(selected):
        lines += [f' .db {len(entries)}', f' .dw wheel_refinement_{l}']
    for l, entries in enumerate(selected):
        lines.append(f'wheel_refinement_{l}:')
        for entry in sorted(entries):
            lines.append(' .db '+','.join(map(str,entry)))
    lines.append('_wheel_refinement_rows::')
    lines.extend(' .db '+','.join(map(str,row)) for row in row_ids)
    lines.append('_wheel_refinement_end::')
    return lines
