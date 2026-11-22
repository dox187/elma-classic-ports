"""Seed body rotation during Freefall and verify survival and published wheel sprites."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

from compare_pc_physics import Pc, Resource, build_pc, constants, internal_levels, write_level
from play import Driver, RIDING, angle_delta


def pc_seed(d, settings):
    """Convert the native pose and velocities at the injection step to original PC units."""
    def read(address, fmt):
        size = struct.calcsize(fmt)
        return struct.unpack(fmt, bytes(d.p.memory[address:address+size]))

    ox, oy = [read(d.symbols['_physics_level_origin_'+axis], '<i')[0]/65536
              for axis in ('x', 'y')]
    base = d.symbols['_Bike']
    vs = settings['velocity_scale']
    values = []
    for i in range(3):
        x, y, vx, vy, angle, w = read(base+24*i, '<iiiiIi')
        if i == 0 and '_angular_residual' in d.symbols:
            w += read(d.symbols['_angular_residual'], '<i')[0] / (1 << 24)
        values.extend([x/262144+ox, y/262144+oy, vx/vs, vy/vs,
                       (angle % settings['angle'])*math.tau/settings['angle'], w/settings['omega_scale']])
    x, y, vx, vy, hx, hy = read(base+72, '<6i')
    values.extend([x/262144+ox, y/262144+oy, vx/vs, vy/vs, hx/262144+ox, hy/262144+oy])
    return values


def open_freefall(d):
    d.ready()
    d.level_menu()
    for key, times in [('right', 4), ('down', 7)]:
        for _ in range(times):
            d.pulse(key)
    d.pulse('start')
    d.ready()
    assert d.level_index() == 43


def run(rom, gen, out, speed, pc, level, seed_step=260):
    d = Driver(rom, out, gen)
    settings = constants(gen / 'riding_constants.h')
    scale = settings['omega_scale']
    pc_alive = []
    pc_axles = []
    pc_live_poses = []
    pose_errors = []
    pc_live_angles = []
    angle_errors = []
    checked = []
    seeded = False
    wheel_slots = d.symbols['_shadow_OAM'] + 8 * 4

    def observe(_):
        nonlocal seeded
        try:
            Driver._physics_entry(d)
            if d.level_index() != 43:
                return
            step = d.word('game_steps')
            if step == seed_step and not seeded:
                assert d.rom_constant('game_physics_state_bytes', 0) == 119
                addr = d.symbols['_Bike'] + 20
                d.p.memory[addr:addr+4] = struct.pack('<i', round(speed * scale))
                # Seed the same quantized speed in every ROM revision. A build
                # carrying sub-unit angular velocity must replace both parts.
                if '_angular_residual' in d.symbols:
                    residual = d.symbols['_angular_residual']
                    d.p.memory[residual:residual+4] = bytes(4)
                # The debugger replaced Bike after the previous frame's idle
                # preparation. Recompute spring inputs from the injected spin.
                if '_riding_spring_ready' in d.symbols:
                    d.p.memory[d.symbols['_riding_spring_ready']] = 0
                pc.reset(level, pc_seed(d, settings), d.bike()['turned'])
                for _ in range(25):
                    pc.step(0, settings['dt'])
                    state = pc.snapshot()
                    pc_alive.append(not state['dead'])
                    if state['dead']:
                        break
                    pos = state['position']
                    pc_live_poses.append(pos)
                    pc_live_angles.append(state['body_angle'])
                    pc_axles.append(max(abs(pos[wheel][axis]-pos['body'][axis])
                                        for wheel in ('wheel0', 'wheel1') for axis in (0, 1)))
                seeded = True
            if not seeded or step <= seed_step:
                return
            index = step - seed_step - 1
            if index < len(pc_live_poses):
                bike = d.bike()
                error = max(math.dist((bike[part]['x'], bike[part]['y']), reference)
                            for part, reference in pc_live_poses[index].items())
                pose_errors.append((index + 1, error))
                angle_errors.append(abs(math.degrees(angle_delta(bike['body']['angle'], pc_live_angles[index]))))
            public = d.symbols['_gbc_bike']
            world = d.symbols['_game_world'] + 4
            ox, oy = struct.unpack('<ii', bytes(d.p.memory[world:world+8]))
            bx, by = struct.unpack('<ii', bytes(d.p.memory[public:public+8]))
            largest = 0
            for i in range(2):
                addr = public + (i+1)*10
                x, y = struct.unpack('<ii', bytes(d.p.memory[addr:addr+8]))
                largest = max(largest, abs(x-bx), abs(y-by))
                left = (x-ox)*12//65536 - d.word('game_camera_x') - 8
                top = (oy-y)*12//65536 - d.word('game_camera_y') - 8
                for col in range(2):
                    sx = left + 8*col
                    expected = (top+16, sx+8) if -7 <= sx < 160 and -15 <= top < 136 else (0, 0)
                    slot = wheel_slots + 4*(i*2+col)
                    assert tuple(d.p.memory[slot:slot+2]) == expected, (step, i, col, expected)
            checked.append(largest/65536)
        except Exception as error:
            d.observer_errors.append(error)

    entry = d.symbols['_physics_step']
    d.p.hook_deregister(entry >> 16, entry & 65535)
    d.p.hook_register(entry >> 16, entry & 65535, observe, None)
    try:
        open_freefall(d)
        for _ in range(10 * (seed_step + 25)):
            if len(checked) >= 25 or d.byte('game_state') != RIDING:
                break
            d.tick()
        return dict(speed=speed, seeded=seeded, riding=d.byte('game_state') == RIDING,
                    checked=len(checked), max_axis_m=max(checked, default=0),
                    max_position_error_first_19_steps_m=max(
                        (e for i, e in pose_errors if i <= 19), default=0),
                    max_body_angle_error_common_live_deg=max(angle_errors, default=0),
                    max_position_error_common_live_m=max((e for _, e in pose_errors), default=0),
                    elapsed_steps=d.word('game_steps')-seed_step,
                    pc_death_step=next((i for i,v in enumerate(pc_alive,1) if not v), None),
                    pc_live_max_axis_m=max(pc_axles, default=0))
    finally:
        d.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['rom', 'gen', 'out', 'res']:
        parser.add_argument('--'+name, required=True, type=Path)
    parser.add_argument('--seed-step', type=int, default=260)
    args = parser.parse_args()
    if args.seed_step < 1:
        parser.error('--seed-step must be positive')
    args.out.mkdir(parents=True, exist_ok=True)
    pc = Pc(build_pc(args.out))
    level = args.out/'freefall.txt'
    write_level(level, internal_levels(Resource(args.res))[43])
    results = [run(args.rom, args.gen, args.out / str(speed), speed, pc, level, args.seed_step)
               for speed in (-140, -120, 120, 140)]
    report = dict(rom=str(args.rom.resolve()), sha256=hashlib.sha256(args.rom.read_bytes()).hexdigest(),
                  synthetic_seed_step=args.seed_step, cases=results)
    (args.out / 'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
    for r in results:
        assert r['seeded'] and r['max_axis_m'] > 3, 'extended wheel pose must reach the renderer'
        assert r['riding'] == (r['pc_death_step'] is None), r
        assert r['elapsed_steps'] == (r['pc_death_step'] or 25), r
        assert r['checked'] == r['elapsed_steps'] - int(not r['riding']), r
