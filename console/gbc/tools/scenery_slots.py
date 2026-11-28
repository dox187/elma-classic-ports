"""Assign medium-course scenery IDs to slots shared by disjoint viewports."""
import json

import numpy as np


BANK = 504
CAPACITY = 15360


def assign(ids, count):
    # The old and entering strips together span at most 22 by 20 cells,
    # including diagonal motion. Two patterns within this distance need
    # distinct slots even if a predicted scroll is subsequently cancelled.
    neighbours = [set() for _ in range(count - 256)]
    for y, x in zip(*np.where(ids >= 256)):
        source = int(ids[y, x])
        around = ids[max(0,y-19):y+20, max(0,x-21):x+22]
        neighbours[source-256].update(int(other)-256 for other in np.unique(around)
                                      if other >= 256 and other != source)
    slots = [-1] * len(neighbours)
    for source in sorted(range(len(slots)), key=lambda i: -len(neighbours[i])):
        used = {slots[j] for j in neighbours[source]}
        slot = next((i for i in range(236) if i not in used), None)
        if slot is None:
            return None
        slots[source] = slot
    assert all(slots[i] != slots[j] for i, row in enumerate(neighbours) for j in row)
    return bytes(slots)


def generate(gen, capacity):
    levels = json.loads((gen/'level_manifest.json').read_text())['levels']
    pointers = ['0'] * len(levels)
    records = []
    used = 2*len(levels)
    for level in levels:
        count = level['pattern_count']
        if not 492 < count <= 1024 or used + count-256 > capacity:
            continue
        index = level['index']
        with np.load(gen/'levels'/f'{index+1:02}'/'tiles.npz') as data:
            slots = assign(data['ids'], count)
        if slots is None:
            continue
        used += len(slots)
        pointers[index] = f'scenery_slots_{index}'
        records.append(pointers[index]+':')
        records.extend(' .db '+','.join(map(str, slots[i:i+32])) for i in range(0,len(slots),32))
    return ['_world_scenery_slots::', *(' .dw '+p for p in pointers), *records,
            '_world_scenery_slots_end::']
