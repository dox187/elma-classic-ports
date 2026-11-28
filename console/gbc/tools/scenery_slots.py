"""Assign medium-course scenery IDs to slots shared by disjoint viewports."""
import json
import heapq

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
    counts = np.bincount(ids.ravel(), minlength=count)[256:]
    groups = [[] for _ in range(max(slots)+1)]
    for source, slot in enumerate(slots):
        groups[slot].append(source)
    # Dedicate spare VRAM slots to frequently visible patterns. Removing
    # the most frequent member makes the runner-up resident in its place.
    splits = []
    for slot, members in enumerate(groups):
        members.sort(key=lambda i: (counts[i], -i))
        if len(members)>1:
            heapq.heappush(splits, (-counts[members[-2]], slot))
    while len(groups)<236 and splits:
        _, slot = heapq.heappop(splits)
        members = groups[slot]
        source = members.pop()
        slots[source] = len(groups)
        groups.append([source])
        if len(members)>1:
            heapq.heappush(splits, (-counts[members[-2]], slot))
    preload = bytearray((len(slots)+7)//8)
    for members in groups:
        source = members[-1]
        preload[source//8] |= 1 << (source%8)
    return bytes(slots) + preload


def generate(gen, capacity):
    levels = json.loads((gen/'level_manifest.json').read_text())['levels']
    pointers = ['0'] * len(levels)
    records = []
    used = 2*len(levels)
    for level in levels:
        count = level['pattern_count']
        entries = count-256
        if not 492 < count <= 1024 or used + entries + (entries+7)//8 > capacity:
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
