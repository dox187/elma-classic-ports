"""Compile full integer contact tiles selected from costly wheel queries."""
import json
from pathlib import Path

from corner_samples import cell_samples
from head_clearance import write_if_changed
from projection_tables import byte_lines
from wheel_direct_tiles import dispatch, tile_reader

SIDE = 8
BANKS = (465, 466, 467, 468)
PROFILE = Path(__file__).with_name('wheel_extended_tiles.json')

PARAMS = """extended_course_params::
 ld a,(#_physics_level_index)
 cp #54
 jr nc,extended_uncovered
 ld c,a
 ld b,#0
 ld hl,#extended_course_rows
 add hl,bc
 sla c
 sla c
 add hl,bc
 ld a,(hl+)
 or a
 jr z,extended_uncovered
 ld (#extended_span_y),a
 ld a,(hl+)
 ld (#extended_min_y),a
 ld a,(hl+)
 ld (#extended_bank),a
 ld a,(hl+)
 ld (#extended_reader),a
 ld a,(hl)
 ld (#extended_reader+1),a
 ret
extended_uncovered:
 ld hl,#_riding_extended_contacts
 ld (hl),#0xc3
 inc hl
 ld (hl),#<_riding_contacts_fallback
 inc hl
 ld (hl),#>_riding_contacts_fallback
 ret
extended_course_rows:
"""


def generate(gen, template, levels, terrain_banks):
    chosen = json.loads(PROFILE.read_text())
    payload = {}
    routes = {}
    for bank, courses in zip(BANKS, chosen, strict=True):
        blobs = {}

        def blob(data):
            return f'extended_bytes_{bank}_{blobs.setdefault(bytes(data), len(blobs))}'

        prefix = f'extended_{bank}'
        lines = [f'.area _CODE_{bank}', f'{prefix}_start::', ' jp (hl)']
        for level, tiles in courses:
            name = f'{prefix}_{level}'
            pages = {(y >> 8) & 255 for x, y in tiles}
            span, start = min((max((page-start) & 255 for page in pages)+1, start) for start in pages)
            route = span, start, bank, f'direct_{name}_tiles'
            assert level not in routes and route[0] <= 255
            routes[level] = route
            reader = dispatch(name, tiles, SIDE)
            # The wheel's fraction-aware certificate already ran before
            # this fallback. Use the shared native decoder without querying it again.
            lines.extend(line.replace('direct_miss', f'{prefix}_miss')
                         .replace('direct_known', 'direct_read') for line in reader)
            for i, (x, y) in enumerate(tiles):
                lines.extend([f'direct_{name}_{i}:', *tile_reader(blob, cell_samples(
                    levels[level], terrain_banks, x, y, SIDE), SIDE)])
        # The decoder, its unpackers and local miss live in the active data bank.
        lines = [line.replace('direct_read', f'{prefix}_read')
                 .replace('direct_decoded', f'{prefix}_decoded')
                 .replace('direct_unpack', f'{prefix}_unpack') for line in lines]
        shared = (template.parent/'direct_wheel.inc').read_text().split('direct_read::\n')[1]
        shared = ('direct_read::\n' + shared).replace(' and #15', ' and #7', 2).replace(' swap a', ' rlca\n rlca\n rlca', 1)
        shared = shared.replace('direct_read', f'{prefix}_read')
        shared = shared.replace('direct_decoded', f'{prefix}_decoded').replace('direct_miss', f'{prefix}_miss')
        lines.extend(shared.splitlines())
        for bits, shift in ((1, 3), (2, 2), (4, 1)):
            name = f'{prefix}_unpack{bits}'
            lines.extend([name+':', ' ld a,c', *[' srl a']*shift, ' ld e,a', ' add hl,de', ' ld a,(hl)'])
            for j in range(shift):
                rotates = [' swap a'] if bits << j == 4 else [' rrca'] * (bits << j)
                lines.extend([f' bit {j},c', f' jr z,{name}_{j}', *rotates, f'{name}_{j}:'])
            lines.extend([f' and #{(1<<bits)-1}', ' ret'])
        for data, index in blobs.items():
            lines.extend([f'extended_bytes_{bank}_{index}:', *byte_lines(data)])
        payload[bank] = lines
    directory = payload[BANKS[0]]
    directory.extend(PARAMS.splitlines())
    for level in range(54):
        if level not in routes:
            directory.append(' .db 0,0,0')
            directory.append(' .dw 0')
        else:
            span, start, bank, reader = routes[level]
            directory.append(f' .db {span},{start},{bank & 255}')
            directory.append(f' .dw {reader}')
    paths = []
    for bank, lines in payload.items():
        lines += [f'extended_{bank}_end::', '']
        path = gen/f'extended_wheel_{bank}.s'
        write_if_changed(path, '\n'.join(lines))
        paths.append(path)
    runtime = gen/'extended_wheel_runtime.s'
    write_if_changed(runtime, template.read_text())
    return [*paths, runtime]
