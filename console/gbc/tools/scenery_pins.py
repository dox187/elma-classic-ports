"""Install immutable scenery patterns into an unused graphics-bank range."""
import json
import struct

from head_clearance import write_if_changed

BANK = 447
OFFSET = 4608
PIN_COUNT = 52
COURSES = 54
SIZE = COURSES * PIN_COUNT * 2


def check_allocation(manifest):
    first = BANK * 16384 + OFFSET
    limit = first + SIZE
    def check(pointer, length):
        bank, address = pointer
        start = (bank & 511)*16384 + address - 0x4000
        if length and start < limit and first < start+length:
            raise ValueError(f'Scenery pins overlap existing asset at {pointer}')
    if manifest['map_codec'] != 'raw-packed-high32x16' or len(manifest['levels']) != COURSES:
        raise ValueError('Scenery pins require the packed original course catalogue')
    for level in manifest['levels']:
        for bank, address in level['chunks']:
            check((bank,address), 1024 if bank & 0xc000 else 1536)
        check(level['patterns'], 16*level['pattern_count'])
        check(level['palette'], 56)
        check(level['chunk_directory'], 4*len(level['chunks']))
        check(level['objects_pointer'], 14*len(level['objects']))
    rider = manifest['rider_product_first_bank']
    if BANK in manifest['rolling_map_banks'] or rider <= BANK < rider+8:
        raise ValueError('Scenery pins overlap numeric tables')


def generate(gen, original, dest=None):
    import numpy as np
    manifest = json.loads((gen/'level_manifest.json').read_text())
    check_allocation(manifest)
    data = bytearray()
    for level in manifest['levels']:
        with np.load(gen/'levels'/f"{level['index']+1:02}"/'tiles.npz') as source:
            ids = source['ids']
            counts = np.bincount(ids.ravel().astype(int), minlength=level['pattern_count'])
        if len(counts) != level['pattern_count']:
            raise ValueError('Scenery tile ID exceeds the linked dictionary')
        # Coordinate slots repeat every 22 columns and 20 rows. A different
        # tile at the preceding occupant needs a pattern transfer as well as
        # a directory lookup. Count both directions on both axes.
        scores = 4*counts
        for here, there in ((ids[:,22:],ids[:,:-22]), (ids[20:,:],ids[:-20,:])):
            changed = here != there
            for side in (here, there):
                scores += 5*np.bincount(side[changed], minlength=len(counts))
        used = set()
        pins = []
        for tile in np.argsort(-scores, kind='stable'):
            key = int(tile) & 255
            if key not in used:
                used.add(key)
                pins.append(int(tile))
            if len(pins) == PIN_COUNT:
                break
        if len(pins) != PIN_COUNT:
            if len(counts) > 492:
                raise ValueError('Insufficient distinct low bytes for scenery pins')
            pins += [0]*(PIN_COUNT-len(pins))
        data.extend(struct.pack('<52H', *pins))
    source = original.read_text()
    payload = bytes(map(int,source.split('{',1)[1].split('}',1)[0].strip().rstrip(',').split(',')))
    if OFFSET+SIZE>len(payload):
        raise ValueError('Scenery pin range exceeds packed graphics')
    asm = [f'.module scenery_{BANK}', f'.area _CODE_{BANK}', f'_level_bank_{BANK}::']
    for label, block in ((None,payload[:OFFSET]),('_world_scenery_pins',data),
                         ('_world_scenery_pins_end',payload[OFFSET+SIZE:])):
        if label:
            asm.append(label+'::')
        asm.extend(' .db '+','.join(map(str,block[i:i+40])) for i in range(0,len(block),40))
    output = (dest or gen)/f'scenery_pins_{BANK}.s'
    write_if_changed(output,'\n'.join(asm)+'\n')
    return output


def validate_layout(symbols):
    first = (BANK<<16)+0x4000+OFFSET
    if (symbols.get('_world_scenery_pins') != first or
            symbols.get('_world_scenery_pins_end') != first+SIZE or
            symbols.get('_level_bank_447') != first-OFFSET or
            symbols.get('_normal_atlas_tail_447',first+16384) < first+SIZE):
        raise ValueError('Scenery pin table moved outside its certified bank range')
