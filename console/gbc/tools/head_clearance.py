"""Build the 1 m swept-head certificates from the packed collision directories."""
import argparse
import hashlib
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
import struct

FIRST_BANK = 506
BANK_BYTES = 16384
RADIUS = 244
TILE = 1024
GROUP = 4  # Four neighbouring 4 m cells share one eight-byte dictionary entry.


def touches_tile(edge, x, y):
    """Does a finite segment come strictly within RADIUS of the closed square?"""
    ax, ay, dx, dy = edge
    bx, by = ax + dx, ay + dy
    x1, y1 = x + TILE, y + TILE
    if (x1 + RADIUS <= min(ax, bx) or x - RADIUS >= max(ax, bx) or
            y1 + RADIUS <= min(ay, by) or y - RADIUS >= max(ay, by)):
        return False
    # The box axes and the segment normal are all separating axes.
    cross = (x - ax) * dy - (y - ay) * dx
    lo = cross + min(0, TILE * dy) + min(0, -TILE * dx)
    hi = cross + max(0, TILE * dy) + max(0, -TILE * dx)
    if (x1 >= min(ax, bx) and x <= max(ax, bx) and
            y1 >= min(ay, by) and y <= max(ay, by) and lo <= 0 <= hi):
        return True
    # Disjoint convex polygons attain their minimum at a vertex against
    # an edge. The two segment endpoints also cover zero-length edges.
    rr = RADIUS * RADIUS
    for ex, ey in ((ax, ay), (bx, by)):
        vx, vy = max(x - ex, ex - x1, 0), max(y - ey, ey - y1, 0)
        if vx * vx + vy * vy < rr:
            return True
    length2 = dx * dx + dy * dy
    for tx, ty in ((x, y), (x1, y), (x, y1), (x1, y1)):
        vx, vy = tx - ax, ty - ay
        if 0 < vx * dx + vy * dy < length2 and (vx * dy - vy * dx) ** 2 < rr * length2:
            return True
    return False


def packed_inputs(gen):
    manifest = json.loads((gen / 'physics_bank_manifest.json').read_text())
    digest = hashlib.sha256()
    digest.update((gen / 'physics_bank_manifest.json').read_bytes())
    banks = {}
    for bank in manifest['banks']:
        source = (gen / f'physics_bank_{bank}.c').read_bytes()
        digest.update(source)
        banks[bank] = bytes(map(int, source.split(b'={', 1)[1].split(b'}', 1)[0].split(b',')))
        if len(banks[bank]) != BANK_BYTES:
            raise ValueError(f'Unexpected collision bank size in bank {bank}')
    return manifest['levels'], banks, digest.hexdigest()


def cell_masks(level, banks):
    base = level['base_bank']
    def pointer(bank, address):
        return struct.unpack_from('<HBB', banks[bank], address - 0x4000)

    def leaf_records(ptr):
        address, bank_offset, count = ptr
        if not count:
            return []
        data = banks[base + bank_offset]
        return [struct.unpack_from('<4h', data, address - 0x4000 + i * 18) for i in range(count)]

    w, h = level['grid']
    for i in range(w * h):
        ptr = pointer(level['directory_bank'], level['directory_address'] + i * 4)
        if ptr[2] == 255:
            leaves = [leaf_records(pointer(base + ptr[1], ptr[0] + t * 4)) for t in range(16)]
        else:
            leaves = [leaf_records(ptr)] * 16
        yield sum(1 << t for t, records in enumerate(leaves)
                  if any(touches_tile(edge, (t % 4) * TILE, (t // 4) * TILE) for edge in records))


def encode_level(w, h, cells):
    patterns, directory = {}, bytearray()
    for y in range(h):
        for x in range(0, w, GROUP):
            chunk = cells[y * w + x : y * w + min(w, x + GROUP)]
            block = struct.pack('<4H', *(chunk + [0] * (GROUP - len(chunk))))
            index = patterns.setdefault(block, len(patterns))
            if index > 255:
                raise ValueError('A head-clearance level exceeds its 256-pattern directory')
            directory.append(index)
    return directory, b''.join(patterns)


def write_if_changed(path, source):
    data = source.encode()
    if path.exists() and path.read_bytes() == data:
        return
    with NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        tmp.write(data)
    Path(tmp.name).replace(path)


def generate(gen):
    levels, collision_banks, digest = packed_inputs(gen)
    banks, descriptors = [], []
    for level in levels:
        w, h = level['grid']
        directory, patterns = encode_level(w, h, list(cell_masks(level, collision_banks)))
        size = len(directory) + len(patterns)
        if size > BANK_BYTES:
            raise ValueError('A head-clearance level exceeds one bank')
        # Keep each dictionary in the same bank as its directory.
        for i, data in enumerate(banks):
            if len(data) + size <= BANK_BYTES:
                break
        else:
            i = len(banks)
            data = bytearray()
            banks.append(data)
        address = 0x4000 + len(data)
        descriptors.append((address, address + len(directory), (w + GROUP - 1) // GROUP,
                            (FIRST_BANK + i) & 255, w, h))
        data.extend(directory)
        data.extend(patterns)
    if len(banks) > 2:
        raise ValueError('Head clearance exceeds reserved ROM banks 506..507')
    header = [
        '#pragma bank 4',
        '#include <stdint.h>',
        '#include "riding_constants.h"',
        f'#if R_HEAD != {RADIUS}',
        '#error Head radius differs from the generated terrain certificates',
        '#endif',
        f'const uint8_t riding_head_level_count={len(descriptors)};',
        'typedef struct {uint8_t width,height; const uint16_t *rows; uint16_t patterns; uint8_t bank,pad;} head_map_t;',
        *[f'static const uint16_t head_row_{i}[]={{'+','.join(str(addr+y*stride) for y in range(h))+'};'
          for i,(addr,_,stride,_,_,h) in enumerate(descriptors)],
        'const head_map_t riding_head_maps[]={',
        *[f' {{{w},{h},head_row_{i},{patterns},{bank},0}},'
          for i,(_,patterns,_,bank,w,h) in enumerate(descriptors)],
        '};',
    ]
    write_if_changed(gen / 'physics_head_map.c', '\n'.join(header) + '\n')
    outputs = ['physics_head_map.c']
    for i, data in enumerate(banks):
        bank = FIRST_BANK + i
        rows = [','.join(map(str, data[j:j + 32])) for j in range(0, len(data), 32)]
        name = f'physics_head_bank_{bank}.c'
        write_if_changed(gen / name, f'#include <stdint.h>\n#pragma bank {bank}\n'
                                f'const uint8_t physics_head_bank_{bank}[]={{\n' +
                                ',\n'.join(rows) + '\n};\n')
        outputs.append(name)
    manifest = {'first_bank': FIRST_BANK, 'last_bank': FIRST_BANK + len(banks) - 1,
                'collision_sha256': digest, 'bytes': sum(map(len, banks)),
                'output_sha256': {n: hashlib.sha256((gen / n).read_bytes()).hexdigest() for n in outputs}}
    write_if_changed(gen / 'physics_head_manifest.json', json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gen', required=True, type=Path)
    print(json.dumps(generate(parser.parse_args().gen)))
