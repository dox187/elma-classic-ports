"""Compare warmed shared-vertex windows to the cold ordered cartridge iterator."""
import argparse
from collections import Counter
from pathlib import Path
import struct

from check_normal_atlas import Cartridge


def edge(vertex, direction, end, bounds):
    x, y = vertex
    dx, dy = direction
    if end:
        dx, dy = -dx, -dy
        x, y = x - dx, y - dy
    return struct.pack('<7h4B', x, y, dx, dy, dx * 16, dy * 16, 1024, *bounds)


def read_contacts(cart, records, x, y, seed, cold):
    m, symbols, reg = cart.m, cart.sym, cart.reg
    source = 0xde00
    m[source:source + len(records)] = records
    if cold:
        m[symbols['_riding_leaf_regions_dirty']] = 1
        m[symbols['_riding_contact_regions_dirty']] = 1
    cur, left, ct = (symbols[s] for s in ('_Seg_cur', '_Seg_left', '_Ct'))
    m[cur:cur + 2] = struct.pack('<H', source)
    m[left] = len(records) // 18
    m[ct:ct + 20] = seed
    address = symbols['_riding_contacts_loop'] & 65535
    m[cart.code:cart.code + 5] = bytes((0xcd, address & 255, address >> 8, 0x18, 0xfe))
    reg.PC, reg.SP = cart.code, cart.stack
    reg.D, reg.E, reg.B, reg.C = x >> 8, x & 255, y >> 8, y & 255
    for _ in range(8):
        cart.p.tick(1, False)
        if reg.PC == cart.code + 3:
            break
    assert (reg.PC, reg.SP) == (cart.code + 3, cart.stack)
    assert m[symbols['__current_bank']] == 9
    assert bytes(m[0x4000:0x4020]) == cart.signature
    return reg.A, bytes(m[ct:ct + 20]), bytes(m[cur:cur + 2]), m[left]


def check(rom, reference):
    target, oracle = Cartridge(rom), Cartridge(reference)
    stats = Counter()
    entered = [0]

    def observed(_):
        entered[0] += 1

    address = target.sym['_riding_shared_cap']
    target.p.hook_register(address >> 16, address & 65535, observed, None)
    visible, hidden = (0, 255, 0, 255), (0, 0, 0, 0)
    skipped = edge((768, 768), (1024, 0), False, hidden)
    try:
        for sx in (-1, 1):
            for sy in (-1, 1):
                for ends in range(4):
                    for split in (0, 1, 104):
                        v = (1792, 1792)
                        a = edge(v, (sx * 1024, 0), ends & 1, visible)
                        b = edge((v[0] + split, v[1]), (0, sy * 1024), ends & 2, visible)
                        for reverse in (False, True):
                            pair = b + a if reverse else a + b
                            records = skipped + pair + skipped
                            for dx, dy in ((24, 24), (288, 280), (321, 240), (300, 300),
                                           (388, 130), (410, 0), (0, 410), (409, 1)):
                                before = entered[0]
                                for visit, adjust in enumerate((0, 1, 2, 3, 0, 1, 33, 2)):
                                    x = v[0] - sx * (dx + adjust)
                                    y = v[1] - sy * dy
                                    seed = bytes((visit * 31 + i) & 255 for i in range(20))
                                    want = read_contacts(oracle, records, x, y, seed, True)
                                    got = read_contacts(target, records, x, y, seed, visit == 0)
                                    assert got == want, (sx, sy, ends, split, reverse, dx, dy, visit, got, want)
                                    stats['ordered queries'] += 1
                                if split:
                                    # Geometrically distinct caps must keep their separate vectors.
                                    assert entered[0] == before
                                elif entered[0] != before:
                                    stats[f'shared vertex orientation {ends}'] += entered[0] - before
        assert all(stats[f'shared vertex orientation {ends}'] for ends in range(4)), stats
        print(dict(stats))
    finally:
        target.p.stop(save=False)
        oracle.p.stop(save=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    args = parser.parse_args()
    check(args.rom, args.reference)
