"""Compare linked corner lookups and their fallback with the previous wheel iterator."""
import argparse
from collections import Counter
import json
from pathlib import Path
import random
import struct
import sys

from check_normal_atlas import Cartridge


class WheelQueries(Cartridge):
    def time_scheduled_frames(self):
        self.invoke('_cpu_fast')
        assert self.m[0xff4d] & 128
        main = self.sym['_main']
        addr = self.sym['_riding_scheduled_frame'] & 65535
        # Hook a single return in fixed ROM. The idle loop and PyBoy's display
        # frame boundary must stay outside the measured physics interval.
        self.m[0, main:main+6] = struct.pack('<BHBH', 0xcd, addr, 0xc3, self.code+3)
        self.p.hook_register(0, main+3, self.end_schedule, None)

    def end_schedule(self, _):
        self.solver_cycles = self.p._cycles() - self.schedule_start - 24  # CALL

    def invoke(self, name, de=0, a=0, bc=0, stack_arg=None):
        address = self.sym[name]
        bank = address >> 16 or 9
        assert bank in (8, 9), (name, hex(address))
        self.m[0x2000] = self.m[self.sym['__current_bank']] = bank
        self.m[self.code:self.code+5] = bytes((0xcd, address & 255, address >> 8 & 255, 0x18, 0xfe))
        self.reg.PC, self.reg.SP = self.code, self.stack
        self.reg.D, self.reg.E, self.reg.A = de >> 8, de & 255, a
        self.reg.B, self.reg.C = bc >> 8, bc & 255
        if stack_arg is not None:
            self.m[self.stack-1] = stack_arg
            self.reg.SP = self.stack-1  # seg_query pops its one-byte third argument
        if name == '_riding_scheduled_frame':
            self.reg.PC = self.sym['_main']
            self.schedule_start = self.p._cycles()
            self.solver_cycles = 0
        for _ in range(12):
            self.p.tick(1, False)
            if self.reg.PC == self.code+3:
                break
        assert (self.reg.PC, self.reg.SP) == (self.code+3, self.stack), name
        assert self.m[self.sym['__current_bank']] == bank
        assert bytes(self.m[0x4000:0x4020]) == self.image[bank*16384:bank*16384+32], name
        self.m[0x2000] = self.m[self.sym['__current_bank']] = 9
        return self.reg.A

    def read(self, name, length):
        address = self.sym[name]
        return bytes(self.m[address:address+length])

    def full_query(self, x, y):
        # The wheel's _contacts fallback binds its collision leaf and runs
        # its ordered iterator. Only the low 12 bits enter the geometry.
        cx = x >> 12 if 0 <= x < 1 << 20 else 255
        cy = y >> 12 if 0 <= y < 1 << 20 else 255
        qx, qy = x & 4095, y & 4095
        self.invoke('_seg_query', de=cy, a=cx, stack_arg=(qx >> 10) | ((qy >> 8) & 12))
        return self.invoke('_riding_contacts_loop', de=qx, bc=qy)

    def prepare(self, slot, position, poison):
        wheel = self.sym['_Bike'] + 24*(slot+1)
        other = self.sym['_Bike'] + 24*(2-slot)
        self.m[wheel:wheel+8] = position
        self.m[other:other+8] = struct.pack('<ii', -0x1020304, -0x56789a)
        ct = self.sym['_Ct']
        self.m[ct:ct+20] = poison
        return wheel

    def fallback_state(self):
        return tuple(self.read(name, length) for name, length in (
            ('_Bike', 119), ('_Seg_cur', 2), ('_Seg_left', 1), ('_Seg_subcell', 1),
            ('_wheel_surface_cache', 58), ('_riding_window_valid', 2),
            ('_riding_contact_qx', 2), ('_riding_contact_qy', 2),
            ('_riding_leaf_regions_dirty', 1), ('_riding_contact_regions_dirty', 1),
            ('_riding_leaf_regions', 128), ('_riding_contact_regions', 128)))

    def result(self, count):
        # The single-contact solver consumes nx, ny and l. With a pair it
        # also reads both contact points when choosing the support pivot.
        assert count in (0, 1, 2), count
        if count == 0:
            return 0, b''
        return count, self.read('_Ct', 6 if count == 1 else 20)


def check_dispatch(target, cells):
    # Traverse a new quarter-square through the real wheel cache. Test both
    # call operands independently even when a controller replay never visits
    # the selected tile on this course.
    by_course = {}
    for level, x, y in sorted(cells):
        by_course.setdefault(level, (x, y))
    assert set(by_course) == set(range(54))
    for level, (x, y) in by_course.items():
        assert target.invoke('_physics_collision_select', a=level) == 1
        thunk = target.sym['step_solve_wheels']
        def readers():
            return [int.from_bytes(bytes(target.m[thunk+k:thunk+k+2]), 'little') for k in (4, 10)]
        if level == 10:
            assert readers() == [target.sym['_riding_corner_wheel_inputs'] & 65535] * 2
            continue
        plain = target.sym['_riding_wheel_inputs'] & 65535
        fast = target.sym['_riding_sparse_wheel_inputs'] & 65535
        assert readers() == [plain, plain]
        for wheel, xpos, expected in ((0, x, [fast, plain]), (1, x, [fast, fast]),
                                      (0, x+256, [plain, fast]), (1, x-256, [plain, plain])):
            addr = target.prepare(wheel, struct.pack('<ii', xpos*256, y*256), bytes(20))
            target.invoke('_riding_cert_hit', addr)
            assert readers() == expected, (level, wheel, readers(), expected)


def query_points(cells):
    # Exact centers are integer physics units. Include the one-point ring
    # across every edge and diagonal, even where adjacent cells share it.
    points = set()
    for level, x, y in cells:
        for dy in range(-1, 17):
            for dx in range(-1, 17):
                points.add((level, x+dx, y+dy))
        # The same low coordinate bits also occur elsewhere on the course,
        # outside the signed map, and on an unrelated course.
        for displacement in (-65536, 65536, -1048576, 1048576):
            points.add((level, x+displacement, y))
            points.add((level, x, y+displacement))
        points.add(((level+1) % 54, x, y))
    return sorted(points)


def unlisted_corners(gen, cells):
    """Exercise actual two-edge contacts outside the packed tiles on every course."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
    from corner_coverage import ranked_tiles
    from corner_samples import cell_records, record_contact
    from head_clearance import packed_inputs

    levels, banks, _ = packed_inputs(gen)
    points = set()
    for course, level in enumerate(levels):
        ranked = ranked_tiles(level, banks)
        chosen = []
        for quarter in range(4):
            for _, tx, ty in ranked[len(ranked)*quarter//4:]:
                x, y = tx*16, ty*16
                if (course, x, y) in cells or any(abs(x-ax)+abs(y-ay) < 512 for ax, ay in chosen):
                    continue
                records = cell_records(level, banks, x, y)
                offsets = ((8, 8), (2, 2), (13, 13), (13, 2), (2, 13))
                for dx, dy in offsets:
                    n = sum(record_contact(rec, (x & 4095)+dx, (y & 4095)+dy) is not None
                            for rec in records)
                    if n >= 2:
                        points.add((course, x+dx, y+dy))
                        chosen.append((x, y))
                        break
                else:
                    continue
                break
        assert len(chosen) == 4, (course, chosen)
    return points


def exercise_corners(target, oracle, points):
    # Relocate a freshly initialized bike as a unit. Run the regular three-
    # substep scheduler with contact, motion, rider, head and audio enabled.
    fields = (('_Bike', 119), ('_gbc_bike', 51), ('_angular_residual', 4),
              ('_move_residual', 32), ('_force_residual', 16),
              ('_riding_landing_contact', 2), ('_riding_landing_nx', 4),
              ('_riding_landing_ny', 4), ('_riding_audio_impact', 2),
              ('_riding_audio_contact', 2))
    updates = 0
    late = [Counter(), Counter()]
    peak = [(0,), (0,)]
    for cart in (target, oracle):
        cart.time_scheduled_frames()
    for i, (level, x, y) in enumerate(sorted(points)):
        wheel = 24 if i % 2 == 0 else 48
        for cart in (target, oracle):
            cart.invoke('_physics_collision_select', a=level)
            cart.invoke('_physics_reset_current')
            bike = cart.sym['_Bike']
            def position(offset):
                return struct.unpack('<ii', bytes(cart.m[bike+offset:bike+offset+8]))
            wx, wy = position(wheel)
            dx, dy = x*256+127-wx, y*256+128-wy
            for offset in (0, 24, 48, 72, 88):
                px, py = position(offset)
                cart.m[bike+offset:bike+offset+8] = struct.pack('<ii', px+dx, py+dy)
        for buttons in (1, 2, 4, 9):
            for j, cart in enumerate((target, oracle)):
                cart.invoke('_riding_scheduled_frame', a=buttons)
                assert cart.solver_cycles > 0
                peak[j] = max(peak[j], (cart.solver_cycles, level+1, x, y, buttons))
                if cart.solver_cycles > 280896:
                    late[j][level+1] += 1
            for field, length in fields:
                assert target.read(field, length) == oracle.read(field, length), (
                    'scheduled corner state', level, x, y, buttons, field)
            updates += 1
            if not target.read('_gbc_bike', 51)[50]:
                break
    print(f'{updates} scheduled updates matched from {len(points)} corner placements.')
    for name, courses, worst in zip(('ROM', 'reference'), late, peak):
        print(f'{name} physics alone exceeded 280896 T on {sum(courses.values())} updates '
              f'across {len(courses)} courses, worst {worst[0]} T on course {worst[1]} '
              f'from ({worst[2]}, {worst[3]}) with input {worst[4]}.')


def check(rom, reference, cells, holdout):
    assert cells and all(x % 16 == y % 16 == 0 for _, x, y in cells), cells
    target, oracle = WheelQueries(rom), WheelQueries(reference)
    stats = Counter()
    rng = random.Random(0xC047)
    last_level = None
    try:
        check_dispatch(target, cells)
        for level, x, y in sorted(set(query_points(cells)) | holdout):
            if level != last_level:
                for cart in (target, oracle):
                    assert cart.invoke('_physics_collision_select', a=level) == 1
                last_level = level
            cell = (level, x & ~15, y & ~15)
            for slot in range(2):
                # Alternating wheels see distinct low bytes, including the
                # extremes where rounding the center would select a neighbor.
                frac = (x + 3*y + slot) & 3
                fx, fy = ((0, 255), (255, 0), (127, 128), (128, 127))[frac]
                position = struct.pack('<ii', x*256+fx, y*256+fy)
                poison = rng.randbytes(20)
                wheel = target.prepare(slot, position, poison)
                previous_wheel = oracle.prepare(slot, position, poison)
                expected = oracle.result(oracle.invoke('_riding_wheel_surface', previous_wheel))
                state = target.fallback_state()
                count = target.invoke('_riding_corner_lookup', wheel)
                where = level, x, y, slot
                should_hit = cell in cells and expected[0] < 2
                assert (count != 255) == should_hit, (where, count, expected)
                if count == 255:
                    assert (target.reg.D << 8 | target.reg.E) == wheel, ('miss lost wheel pointer', where)
                    assert target.fallback_state() == state, ('lookup changed fallback state', where)
                    assert target.read('_Ct', 20) == poison, ('miss overwrote Ct', where)
                    count = target.invoke('_riding_cert_hit', wheel)
                    if count == 255:
                        count = target.full_query(x, y)
                    stats['pair fallback' if cell in cells else 'outside fallback'] += 1
                else:
                    assert target.read('_Bike', 119) == state[0], ('lookup changed wheel', where)
                    stats['corner', count] += 1
                actual = target.result(count)
                assert actual == expected, (where, actual, expected)
                if (level, x, y) in holdout:
                    stats['unlisted', expected[0]] += 1
                if cell in cells:
                    stats['selected positions', slot] += 1
        assert all(stats['selected positions', slot] == len(cells)*256 for slot in range(2))
        assert stats['outside fallback'] and stats['corner', 1], stats
        exercise_corners(target, oracle, holdout | {(level, x+8, y+8) for level, x, y in cells})
        print(f'{len(holdout)} unlisted two-edge points on 54 courses, both wheels: '
              f"{stats['unlisted', 1]} merged and {stats['unlisted', 2]} distinct pairs.")
        assert sum(stats['unlisted', i] for i in (1, 2)) == len(holdout)*2
        print(f'{len(cells)} cells, {len(cells)*256} centers per wheel. '
              f"{stats['corner', 0]} empty and {stats['corner', 1]} single-contact hits, "
              f"{stats['pair fallback']} in-cell pair fallbacks and "
              f"{stats['outside fallback']} boundary, level or coordinate fallbacks.")
    finally:
        target.p.stop(save=False)
        oracle.p.stop(save=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.manifest.read_text())
    cells = {tuple(row) for row in data['cells']}
    assert len(cells) == len(data['cells']), 'duplicate manifest cells'
    check(args.rom, args.reference, cells, unlisted_corners(args.manifest.parent, cells))
