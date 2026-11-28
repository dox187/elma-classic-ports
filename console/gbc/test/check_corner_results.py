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

    def observe_substeps(self, fields):
        # There is one near CALL to ph_step inside the scheduler's shared interval.
        begin = self.sym['_riding_scheduled_frame']
        bank, address = begin >> 16, begin & 65535
        offset = bank*16384 + (address & 16383)
        block = self.image[offset:offset+144]
        call = struct.pack('<BH', 0xcd, self.sym['_ph_step'] & 65535)
        assert block.count(call) == 1
        self.substeps = []
        self.profiling = False
        ranges = [(self.sym[field], self.sym[field]+size) for field, size in fields]
        def returned(_):
            if self.profiling:
                self.profile_return('head')
            state = b''.join(bytes(self.m[lo:hi]) for lo, hi in ranges)
            self.substeps.append((self.reg.A, state))
        self.p.hook_register(bank, address+block.index(call)+3, returned, None)

    def install_profile(self):
        self.profiling = True
        self.profile_hooks = []
        self.started, self.elapsed, self.calls = {}, Counter(), Counter()
        step = self.sym['_ph_step']
        # The head routine is a tail call from ph_step. Its return is
        # already observed by the scheduler hook above.
        lo = (step >> 16)*16384 + (step & 16383)
        block = self.image[lo:lo+256]
        tail = struct.pack('<BH', 0xc3, self.sym['_riding_step_head'] & 65535)
        block = block[:block.index(tail)]
        for name, label in (('_riding_suspension_scheduled', 'suspension'),
                            ('_riding_step_wheels', 'wheels'), ('_riding_step_head', 'head')):
            addr = self.sym[name]
            self.profile_hooks.append((addr >> 16, addr & 65535, self.profile_entry, label))
            if label == 'head':
                continue
            call = struct.pack('<BH', 0xcd, addr & 65535)
            assert block.count(call) == 1
            self.profile_hooks.append((step >> 16, (step & 65535)+block.index(call)+3,
                                       self.profile_return, label))
        for hook in self.profile_hooks:
            self.p.hook_register(*hook)

    def remove_profile(self):
        for bank, address, _, _ in self.profile_hooks:
            self.p.hook_deregister(bank, address)
        self.profiling = False

    def profile_entry(self, label):
        if self.profiling:
            assert label not in self.started
            self.started[label] = self.p._cycles()
            self.calls[label] += 1

    def profile_return(self, label):
        if self.profiling and label in self.started:
            self.elapsed[label] += self.p._cycles() - self.started.pop(label)

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
        # At normal CPU speed the first course selection also constructs the
        # cartridge RAM product rows. Scheduled-frame timing starts separately.
        limit = 32 if name == '_physics_collision_select' else 12
        for _ in range(limit):
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


def check_terrain_dots(cart):
    """Exercise the linked signed products, including overflow before Q14 rounding."""
    rng = random.Random(0xD047)
    limits = (-32768, -16384, -513, -256, -1, 0, 1, 255, 512, 16384, 32767)
    cases = [(x, y, a, b) for x in limits for y in limits
             for a, b in ((32767, -32768), (-32768, -32768), (16383, 1), (-1, 16384))]
    cases += [tuple(rng.randrange(-32768, 32768) for _ in range(4)) for _ in range(2048)]
    # Exercise every signed high-digit pair supported by the short path and
    # the adjacent values that dispatch back to the general product kernel.
    for hx in range(-5, 6):
        for hy in range(-5, 6):
            for lx, ly in ((0, 255), (255, 0), (128, 127), (37, 209)):
                for a, b in ((-32768, 32767), (32767, -32767), (-1, 1)):
                    cases.append((256*hx+lx, 256*hy+ly, a, b))
    addr = cart.sym['terrain_record_dot']
    bank = addr >> 16
    cart.m[0x2000] = cart.m[cart.sym['__current_bank']] = bank
    cart.m[cart.code:cart.code+5] = struct.pack('<BHBB', 0xcd, addr & 65535, 0x18, 0xfe)
    for x, y, a, b in cases:
        cart.reg.PC, cart.reg.SP = cart.code, cart.stack
        cart.reg.D, cart.reg.E = (x >> 8) & 255, x & 255
        cart.reg.B, cart.reg.C = (y >> 8) & 255, y & 255
        cart.m[cart.stack:cart.stack+4] = struct.pack('<hh', a, b)
        cart.p.tick(1, False)
        raw = ((x*a + y*b + 8192 + (1 << 31)) % (1 << 32)) - (1 << 31)
        want = max(-32768, min(32767, raw >> 14)) & 65535
        assert (cart.reg.B << 8 | cart.reg.C) == want, (x, y, a, b, want)
        assert (cart.reg.PC, cart.reg.SP) == (cart.code+3, cart.stack+4)
        assert bytes(cart.m[0x4000:0x4010]) == cart.image[bank*16384:bank*16384+16]
    cart.m[0x2000] = cart.m[cart.sym['__current_bank']] = 9
    print(f'{len(cases)} signed terrain projections matched the integer reference.')


def check_dispatch(target, cells):
    # Traverse a new quarter-square through the real wheel cache. Test both
    # call operands independently even when a controller replay never visits
    # the selected tile on this course.
    assert {level for level, _, _ in cells} == set(range(54))
    # The two dense banks share one course-wide reader. Each sparse tile
    # has its own strip, including a course's secondary geometry address.
    sparse = [row for row in sorted(cells) if row[0] != 10]
    for level, x, y in [next(row for row in cells if row[0] == 10), *sparse]:
        assert target.invoke('_physics_collision_select', a=level) == 1
        thunk = target.sym['step_solve_wheels']
        def readers():
            return [int.from_bytes(bytes(target.m[thunk+k:thunk+k+2]), 'little') for k in (4, 10)]
        course_reader = None
        if level == 10:
            course_reader = target.sym['_riding_corner_wheel_inputs']
        elif level == 31 and 'direct_steep' in target.sym:
            course_reader = target.sym['direct_steep']
        elif level == 47 and 'direct_course48' in target.sym:
            course_reader = target.sym['direct_course48']
        elif level == 37 and '_riding_patch_wheel_inputs' in target.sym:
            course_reader = target.sym['_riding_patch_wheel_inputs']
        elif level == 38 and '_haircut_wheel_inputs' in target.sym:
            course_reader = target.sym['_haircut_wheel_inputs']
        elif ((level == 45 and '_bowling_flat' in target.sym) or
              (level == 51 and '_hang_query' in target.sym)):
            course_reader = target.sym['_riding_sparse_bind'] + 1
        if course_reader:
            expected = [course_reader & 65535] * 2
            assert readers() == expected, (level, readers(), expected)
            for wheel, xpos in ((0, x), (1, x+256)):
                addr = target.prepare(wheel, struct.pack('<ii', xpos*256, y*256), bytes(20))
                target.invoke('_riding_cert_hit', addr)
                assert readers() == expected, (level, wheel, readers(), expected)
            continue
        plain = target.sym['_riding_wheel_inputs'] & 65535
        fast = target.sym['_riding_sparse_wheel_inputs'] & 65535
        initial = fast if '_riding_corner_pair_map' in target.sym else plain
        assert readers() == [initial, initial]
        for wheel, xpos, expected in ((0, x-256, [plain, initial]), (1, x+256, [plain, plain]),
                                      (0, x, [fast, plain]), (1, x, [fast, fast]),
                                      (0, x+256, [plain, fast]), (1, x-256, [plain, plain])):
            addr = target.prepare(wheel, struct.pack('<ii', xpos*256, y*256), bytes(20))
            target.invoke('_riding_cert_hit', addr)
            assert readers() == expected, (level, wheel, readers(), expected)


def check_pair_certificate(cart, slot, wheel, position, pair):
    # A live native pair may also retain filtered lengths and support signs.
    # The table must defer to an exact-center hit, and an alias one quarter
    # away with the same two low words must never restore the saved pair.
    cache = cart.sym['_wheel_surface_cache'] + 29*slot
    saved = bytes(cart.m[cache:cache+29])
    upper = position[2:4] + position[6:8]
    lower = position[:2] + position[4:6]
    ct = cart.sym['_Ct']
    poison = bytes(a ^ 255 for a in pair)
    try:
        for alias in (0, 1):
            cart.m[cache:cache+29] = bytes([upper[0] ^ alias]) + upper[1:] + bytes([9]) + lower + pair
            cart.m[ct:ct+20] = poison
            before = cart.fallback_state()
            assert cart.invoke('_riding_corner_lookup', wheel) == 255
            assert cart.fallback_state() == before and cart.read('_Ct', 20) == poison
            result = cart.invoke('_riding_cert_hit', wheel)
            if alias:
                assert result != 254
            else:
                assert result == 254 and cart.read('_Ct', 20) == pair
        # A different X fraction needs fresh filtering of the same integer
        # pair. Returning to the original center must still restore the
        # prepared record, even when its contents differ from the raw table.
        prepared = upper + bytes([9]) + lower + poison
        cart.m[cache:cache+29] = prepared
        cart.m[wheel] = position[0] ^ 1
        assert cart.invoke('_riding_corner_lookup', wheel) == 2
        assert cart.read('_Ct', 20) == pair and bytes(cart.m[cache:cache+29]) == prepared
        cart.m[wheel] = position[0]
        assert cart.invoke('_riding_corner_lookup', wheel) == 255
        assert cart.invoke('_riding_cert_hit', wheel) == 254 and cart.read('_Ct', 20) == poison
    finally:
        cart.m[wheel] = position[0]
        cart.m[cache:cache+29] = saved
        cart.m[ct:ct+20] = pair


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


def exercise_corners(target, oracle, points, profile=None, both_wheels=False):
    # Relocate a freshly initialized bike as a unit. Run the regular three-
    # substep scheduler with contact, motion, rider, head and audio enabled.
    fields = (('_Bike', 119), ('_gbc_bike', 51), ('_angular_residual', 4),
              ('_move_residual', 32), ('_force_residual', 16),
              ('_riding_landing_contact', 2), ('_riding_landing_nx', 4),
              ('_riding_landing_ny', 4), ('_riding_audio_impact', 2),
              ('_riding_audio_contact', 2))
    updates = substeps = 0
    course_time = [Counter(), Counter()]
    measurements = []
    late = [Counter(), Counter()]
    peak = [(0,), (0,)]
    for cart in (target, oracle):
        cart.time_scheduled_frames()
        cart.observe_substeps(fields + (('_riding_subphase', 1),))
    if both_wheels:
        starts = [(point, wheel) for point in sorted(points) for wheel in (24, 48)]
    else:
        starts = [(point, (24, 48)[i % 2]) for i, point in enumerate(sorted(points))]
    for (level, x, y), wheel in starts:
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
                cart.substeps.clear()
                # Limit component breakpoints to the requested input. A PyBoy
                # hook on a banked tail call can re-fire without advancing the
                # CPU at a display boundary, including on unrelated placements.
                if profile == (level+1, x, y, buttons):
                    cart.install_profile()
                cart.invoke('_riding_scheduled_frame', a=buttons)
                if cart.profiling:
                    assert not cart.started
                    parts = ', '.join(f'{label} {ticks} T ({cart.calls[label]} calls)'
                                      for label, ticks in cart.elapsed.items())
                    rest = cart.solver_cycles - sum(cart.elapsed.values())
                    print(f'{("ROM", "reference")[j]} profile (wheel {wheel // 24}): {parts}, other {rest} T.')
                    cart.remove_profile()
                course_time[j][level+1] += cart.solver_cycles
                assert cart.solver_cycles > 0
                peak[j] = max(peak[j], (cart.solver_cycles, level+1, x, y, buttons, wheel // 24))
                if cart.solver_cycles > 280896:
                    late[j][level+1] += 1
            assert target.substeps and target.substeps == oracle.substeps, (
                'corner substep', level, x, y, buttons)
            substeps += len(target.substeps)
            measurements.append((oracle.solver_cycles, target.solver_cycles, level+1, x, y, buttons))
            for field, length in fields:
                assert target.read(field, length) == oracle.read(field, length), (
                    'scheduled corner state', level, x, y, buttons, field)
            updates += 1
            if not target.read('_gbc_bike', 51)[50]:
                break
    print(f'{updates} updates and {substeps} substeps matched from {len(starts)} corner placements.')
    old, new, course, x, y, control = max(measurements)
    if profile:
        assert any(row[2:] == profile for row in measurements), ('unvisited placement', profile)
    print(f'Slowest reference update: course {course} at ({x}, {y}), input {control}, {old} -> {new} T.')
    faster = sum(course_time[0][course] < total for course, total in course_time[1].items())
    print(f'Corner placements faster in aggregate on {faster}/{len(course_time[1])} courses, '
          f'{sum(course_time[1].values())} -> {sum(course_time[0].values())} T.')
    for course, old in sorted(course_time[1].items()):
        if course_time[0][course] >= old:
            print(f'Course {course}: {old} -> {course_time[0][course]} T over its placements.')
    for name, courses, worst in zip(('ROM', 'reference'), late, peak):
        print(f'{name} physics alone exceeded 280896 T on {sum(courses.values())} updates '
              f'across {len(courses)} courses, worst {worst[0]} T on course {worst[1]} '
              f'from ({worst[2]}, {worst[3]}) with input {worst[4]}, wheel {worst[5]}.')


def check(rom, reference, cells, holdout, profile=None, placements=None, pair_blocks=(), both_wheels=False):
    assert cells and all(x % 16 == y % 16 == 0 for _, x, y in cells), cells
    target, oracle = WheelQueries(rom), WheelQueries(reference)
    stats = Counter()
    rng = random.Random(0xC047)
    last_level = None
    checked_certificates = set()
    try:
        if 'terrain_record_dot' in target.sym:
            check_terrain_dots(target)
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
                block = (*cell, x & 12, y & 12)
                should_hit = cell in cells and (expected[0] < 2 or block in pair_blocks)
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
                    if count == 2:
                        offset = target.sym['_wheel_surface_cache'] + 29*slot
                        assert bytes(target.m[offset:offset+4]) == position[2:4]+position[6:8], where
                    stats['corner', count] += 1
                actual = target.result(count)
                assert actual == expected, (where, actual, expected)
                if count == 2 and should_hit and (level, slot) not in checked_certificates:
                    check_pair_certificate(target, slot, wheel, position, actual[1])
                    checked_certificates.add((level, slot))
                if (level, x, y) in holdout:
                    stats['unlisted', expected[0]] += 1
                if cell in cells:
                    stats['selected positions', slot] += 1
        assert all(stats['selected positions', slot] == len(cells)*256 for slot in range(2))
        assert stats['outside fallback'] and stats['corner', 1], stats
        if pair_blocks:
            assert stats['corner', 2] > 0 and stats['corner', 2] % 2 == 0, stats
            assert checked_certificates == {(level, slot) for level, *_ in pair_blocks for slot in (0, 1)}
        # The sorted placement number selects the wheel. Adding a tile can
        # change subsequent starts, so use the same manifest for timing history.
        if placements is None:
            placements = holdout | {(level, x+8, y+8) for level, x, y in cells}
        exercise_corners(target, oracle, placements, profile, both_wheels)
        print(f'{len(holdout)} unlisted two-edge points on 54 courses, both wheels: '
              f"{stats['unlisted', 1]} merged and {stats['unlisted', 2]} distinct pairs.")
        assert sum(stats['unlisted', i] for i in (1, 2)) == len(holdout)*2
        print(f'{len(cells)} cells, {len(cells)*256} centers per wheel. '
              f"{stats['corner', 0]} empty and {stats['corner', 1]} single-contact hits, "
              f"{stats['corner', 2]} ordered-pair hits, {stats['pair fallback']} in-cell pair fallbacks and "
              f"{stats['outside fallback']} boundary, level or coordinate fallbacks.")
    finally:
        target.p.stop(save=False)
        oracle.p.stop(save=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    starts = parser.add_mutually_exclusive_group()
    starts.add_argument('--neighborhood', type=int, nargs=3, metavar=('COURSE', 'X', 'Y'),
                        help='test a 5 by 5 grid of physics starts at 24-unit spacing')
    starts.add_argument('--placement-manifest', type=Path,
                       help='use the corner cells from an earlier build for identical physics starts')
    parser.add_argument('--both-wheels', action='store_true',
                        help='repeat each scheduled start on each wheel, independent of tile ordering')
    parser.add_argument('--profile', type=int, nargs=4, metavar=('COURSE', 'X', 'Y', 'BUTTONS'),
                        help='break down one scheduled update in both cartridges')
    args = parser.parse_args()
    data = json.loads(args.manifest.read_text())
    cells = {tuple(row) for row in data['cells']}
    assert len(cells) == len(data['cells']), 'duplicate manifest cells'
    placements = None
    if args.neighborhood:
        course, x, y = args.neighborhood
        if not 1 <= course <= 54:
            parser.error('neighborhood COURSE must be between 1 and 54')
        placements = {(course-1, x+dx, y+dy)
                      for dx in range(-48, 49, 24) for dy in range(-48, 49, 24)}
    if args.placement_manifest:
        placed = {tuple(row) for row in json.loads(args.placement_manifest.read_text())['cells']}
        placements = unlisted_corners(args.manifest.parent, placed) | {(l, x+8, y+8) for l,x,y in placed}
    holdout = unlisted_corners(args.manifest.parent, cells)
    check(args.rom, args.reference, cells, holdout, tuple(args.profile) if args.profile else None,
          placements, {tuple(row) for row in data.get('pair_blocks', [])}, args.both_wheels)
