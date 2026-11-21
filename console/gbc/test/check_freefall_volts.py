"""Compare two ordinary controller volts with PC at identical physics updates.

Only the PC is initialized from the Game Boy's state. Both ROM runs enter
Freefall using the menu and receive directional button presses during descent.
"""
import argparse
import json
import math
from pathlib import Path

from check_airborne_spin import open_freefall, pc_seed
from compare_pc_physics import Pc, Resource, build_pc, constants, internal_levels, write_level
from play import Driver, RIDING, angle_delta


def route(rom, gen, out, level, pc, directions):
    d = Driver(rom, out, gen)
    settings = constants(gen/'riding_constants.h')
    start, length = 260, 70
    accepted, samples = [], []
    last = None

    def observe(_):
        nonlocal last
        try:
            step = d.word('game_steps')
            if d.level_index() != 43 or not start <= step <= start+length or last == step:
                return
            if last is None:
                assert step == start
                pc.reset(level, pc_seed(d, settings), d.bike()['turned'])
            else:
                assert step == last+1
                ref, bike = pc.snapshot(), d.bike()
                assert not ref['dead'] and bike['alive'], step
                samples.append({
                    'step': step-start,
                    'angle_error_deg': abs(math.degrees(angle_delta(bike['body']['angle'], ref['body_angle']))),
                    'position_error_m': max(math.dist((bike[k]['x'], bike[k]['y']), pos)
                                            for k, pos in ref['position'].items()),
                    'pc_body_omega_rad_s': ref['body_omega'],
                })
            last = step
            if step < start+length:
                # ph_step receives the accepted physics mask; the PC adapter
                # consumes the outer runtime mask with left/right bits swapped.
                mask = d.p.register_file.A
                if mask & 12:
                    accepted.append((step-start, mask & 12))
                pc.step((mask & 3) | ((mask & 4) << 1) | ((mask & 8) >> 1), settings['dt'])
        except Exception as error:
            d.observer_errors.append(error)

    address = d.symbols['_ph_step']
    d.p.hook_register(address >> 16, address & 65535, observe, None)
    try:
        open_freefall(d)
        for _ in range(10*(start+length)):
            if len(samples) == length or d.byte('game_state') != RIDING:
                break
            offset = d.word('game_steps') - start
            held = (directions[0],) if 4 <= offset < 7 else (directions[1],) if 40 <= offset < 43 else ()
            d.tick(1, held)
        assert len(samples) == length, (directions, len(samples))
        assert [mask for _, mask in accepted] == [8 if key == 'left' else 4 for key in directions], accepted
        return dict(rom_sha256=d.rom_sha256, directions=directions, impulses=accepted, samples=samples,
                    max_angle_error_deg=max(row['angle_error_deg'] for row in samples),
                    max_position_error_m=max(row['position_error_m'] for row in samples))
    finally:
        d.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('rom', 'gen', 'out', 'res'):
        parser.add_argument('--'+name, required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    level = args.out/'freefall.txt'
    write_level(level, internal_levels(Resource(args.res))[43])
    pc = Pc(build_pc(args.out))
    results = [route(args.rom, args.gen, args.out/keys[0], level, pc, keys)
               for keys in [('left','right'), ('right','left')]]
    (args.out/'report.json').write_text(json.dumps(results, indent=2)+'\n')
    for result in results:
        print({key: value for key, value in result.items() if key != 'samples'})


if __name__ == '__main__':
    main()
