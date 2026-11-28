"""Pack exact tile ranges for body pose transitions in the compact head bank."""
from collections import Counter
from bike_frames16 import array, read_array
from head_clearance import write_if_changed
from projection_tables import byte_lines

FULL = (15, 255)


def transfer_ranges(previous, current):
    changed = [i for i, tile in enumerate(current) if previous[i] != tile]
    if not changed:
        return (255, 255)
    first, last = changed[0], changed[-1]
    def span(lo, hi):
        return (lo << 4) | (hi-lo)
    # Skip the largest unchanged interior run when doing so also saves an
    # HBlank DMA burst. The normal reader can transfer three tiles per burst.
    for left, right in sorted(zip(changed, changed[1:]), key=lambda p:p[1]-p[0], reverse=True):
        bursts = (left-first+3)//3 + (last-right+3)//3
        if right-left > 1 and bursts < (last-first+3)//3:
            return (span(first, left), span(right, last))
    return (span(first, last), 255)


def generate(gen, reader):
    parts = gen/'riding16_parts.c'
    heads, wheels = (read_array(parts, name) for name in ('riding_heads','riding_wheels'))
    assert len(heads) == 256*32 and all(heads[i:i+16] == bytes(16) for i in range(16,len(heads),32))
    compact = gen/'riding_compact_parts.c'
    write_if_changed(compact, '#include <stdint.h>\n#pragma bank 13\n'
                     + array('riding_heads', b''.join(heads[i:i+16] for i in range(0,len(heads),32)))
                     + array('riding_wheels', wheels))

    data = b''.join(read_array(gen/f'riding16_body_{i}.c', f'riding_body_{i}') for i in range(3))
    assert len(data) == 192*256
    frames = [tuple(data[i+j:i+j+16] for j in range(0,256,16)) for i in range(0,len(data),256)]
    # Rank XOR values that occur between adjacent angles or suspension poses.
    # A selected column still compares the actual two frames, including turns.
    votes = Counter()
    for pose in range(192):
        for angle_step in (-1, 0, 1):
            for compression in range(3):
                other = (pose//96)*96 + 32*compression + ((pose+angle_step)&31)
                if other != pose:
                    votes[pose^other] += 1
    columns = sorted(votes, key=lambda d:(-votes[d],d))[:16]
    patterns = {FULL:0}
    ids = bytearray()
    for i, frame in enumerate(frames):
        for delta in columns:
            old = i^delta
            spans = transfer_ranges(frames[old],frame) if old < len(frames) else FULL
            if spans not in patterns and len(patterns) < 256:
                patterns[spans] = len(patterns)
            ids.append(patterns.get(spans,0))
        ids.extend(bytes(16-len(columns)))
    classes = bytes(columns.index(i) if i in columns else 255 for i in range(256))
    # Adjacent transition IDs often repeat as a pair. The packed reader needs
    # one dictionary index per two columns and two bytes per distinct pair.
    pairs = list(dict.fromkeys(zip(ids[::2], ids[1::2])))
    packed = len(pairs) <= 256
    tables = [('body_xor_slots', classes)]
    if packed:
        lookup = {pair: i for i, pair in enumerate(pairs)}
        tables.append(('body_plan_ids', bytes(lookup[p] for p in zip(ids[::2], ids[1::2]))))
        tables.append(('body_plan_pairs', bytes(value for pair in pairs for value in pair)))
    else:
        tables.append(('body_plan_ids', ids))
    tables.append(('body_spans', bytes(value for pair in patterns for value in pair)))

    # Mid-compression poses on gentle slopes cover frequent changes of angle.
    # Slot bit 7 selects the VRAM bank and its low bits select a 256-byte page.
    resident = dict(zip((*range(32, 37), *range(58, 64)), (*range(7), *range(128, 132))))
    tables.append(('_body_preload_poses', bytes(value for entry in resident.items() for value in entry)))
    tables.append(('body_resident_slots', bytes(resident.get(p, 0x84) for p in range(32, 64))))
    text = ['.module bike_body_transfers', '.area _CODE_13']
    if packed:
        text.append('BODY_PACKED_PLANS = 1')
    text.append(reader.read_text())
    for name, blob in tables:
        text.extend([name + '::', *byte_lines(blob)])
    plans = gen/'bike_body_transfers.s'
    write_if_changed(plans,'\n'.join(text)+'\n')
    return compact, plans
