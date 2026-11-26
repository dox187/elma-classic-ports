"""Check the linked swept-head lanes against the original course geometry."""
import argparse
import json
from pathlib import Path
import re
import struct

from check_head_map_rom import HeadProbe
from check_head_quarters import Resource, geometry, internal_levels
from check_physics_sweep import oracle


def linked_bytes(image, symbol, size):
    offset = (symbol >> 16) * 16384 + (symbol & 16383)
    return image[offset:offset + size]


def expected_lane(lanes, origin_x, origin_y, segment):
    px, py, qx, qy = segment
    first, last = sorted((px // 256 - origin_x, qx // 256 - origin_x))
    if min(segment) < 0 or first < 0 or last >= 56 or last - first > 1:
        return 0
    low, high = sorted((py // 32 - origin_y, qy // 32 - origin_y))
    return int(all(lanes[2*i] <= low <= high <= lanes[2*i + 1]
                   for i in range(first, last + 1)))


def check_rectangle(edges, x, bottom, top):
    vertices = ((x, bottom), (x + 256, bottom), (x + 256, top), (x, top))
    radius = 244
    for ax, ay, dx, dy, *_ in edges:
        if (min(ax, ax + dx) - radius >= x + 256 or max(ax, ax + dx) + radius <= x or
                min(ay, ay + dy) - radius >= top or max(ay, ay + dy) + radius <= bottom):
            continue
        assert not (x <= ax <= x + 256 and bottom <= ay <= top), (ax, ay, vertices)
        for start, end in zip(vertices, vertices[1:] + vertices[:1]):
            assert not oracle((*start, *end, ax, ay, dx, dy, radius)), (start, end, ax, ay, dx, dy)


def check(rom, resource):
    symbols = {name: int(value, 16) for name, value in
               re.findall(r'^DEF (\w+) 0x(\w+)$', rom.with_suffix('.noi').read_text(), re.M)}
    image = rom.read_bytes()
    origins = list(struct.iter_unpack('<HH', linked_bytes(image, symbols['_riding_head_lane_origins'], 54*4)))
    data = linked_bytes(image, symbols['_riding_head_lane_data'], 54*112)
    rectangles = probes = accepted = 0
    probe = HeadProbe(rom)
    try:
        # Return the native filter's predicate at the normal banked entry.
        # This leaves the register and stack convention of the game intact.
        entry = symbols['_head_strip_filtered'] & 65535
        for i, value in enumerate(struct.pack('<H', entry)):
            probe.rom.memory[0, probe.sweep + 3 + i] = value
        assert probe.rom.memory[4, entry + 8] == 0xb7
        probe.rom.memory[4, entry + 8] = 0xc9
        for level_index, level in enumerate(internal_levels(Resource(resource))):
            probe.select_level(level_index)
            ox, quarter_y = origins[level_index]
            oy = quarter_y * 8
            lanes = data[112*level_index:112*(level_index + 1)]
            _, _, _, _, edges, _, _ = geometry(level)
            for i in range(56):
                low, high = lanes[2*i:2*i + 2]
                x = (ox + i) * 256
                bottom, top = (oy + low) * 32, (oy + high + 1) * 32
                if low <= high:
                    check_rectangle(edges, x, bottom, top)
                    rectangles += 1
                for y in (bottom - 1, bottom, bottom + 1, (bottom + top)//2, top - 1, top, top + 1):
                    segments = ((x, y, x + 255, y), (x + 255, y, x + 256, y + 1),
                                (x, y, x - 1, y - 1), (x, y, x + 512, y))
                    for segment in segments:
                        answer = probe.check(segment)
                        assert expected_lane(lanes, ox, oy, segment) == answer, (level_index, i, segment)
                        probes += 1
                        accepted += answer
        outside = ((-1, 0, 0, 0), (0, 0, -1, 0), (1 << 24, 1, 1 << 24, 1), (-1, -1, -1, -1))
        for segment in outside:
            assert probe.check(segment) == 0
    finally:
        probe.close()
    return dict(proven_closed_rectangles=rectangles, native_boundary_probes=probes,
                out_of_bounds_probes=len(outside), certified_native_answers=accepted)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--res', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.rom, args.res)))
