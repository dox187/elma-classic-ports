"""Check original brush and collision-grid exits at GBC precision and substep timing."""
import argparse
import ctypes as C
import json
from pathlib import Path
import sys

import compare_pc_physics as comparison

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'tools'))
import physics_level


def check_thresholds(pc, levels, out):
    unit = 1 << 18
    probe = pc.f.compare_pc_level_exit
    probe.argtypes = [C.c_double, C.c_double]
    packer = physics_level.BankPacker(physics_level.FIRST_BANK)
    count = 0
    for index, level in enumerate(levels):
        descriptor, record = physics_level.pack_level(level, index, packer)
        gx, gy, x0, x1, y0, y1 = descriptor[9:]
        ox, oy = record['origin_m']
        path = out / f'level-{index}.txt'
        comparison.write_level(path, level)
        pc.reset(path)
        sx, sy = level.start()
        for axis, limit in ((0, gx), (1, gy), (0, x0), (0, x1), (1, y0), (1, y1)):
            for offset in (-1, 0, 1):
                point = [round((sx - ox) * unit), round((sy - oy) * unit)]
                point[axis] = limit + offset
                x, y = point
                expected = int(x >= gx or y >= gy) | (int(not (x0 <= x < x1 and y0 <= y < y1)) << 1)
                actual = probe(ox + x / unit, oy + y / unit)
                assert actual == expected, (level.name, axis, limit, offset, actual, expected)
                count += 1
    return count


def check_trajectories(pc, host, fixtures, directory, settings):
    results = []
    pc.f.compare_pc_record_substeps(1)
    for index, level in enumerate(fixtures):
        ys = [y for grass, polygon in level.polygons if not grass for _, y in polygon]
        top, bottom = max(ys), min(ys)
        # x=72 is the first invalid grid coordinate for both synthetic courses.
        # The returning right wheel crosses back in before the first substep ends.
        # The outgoing right wheel starts inside and is first queried outside on substep 2.
        cases = (
            ('right-grid', -.85, top+4, 210, 0),
            ('left-brush', -.85, top+4, -330, 0),
            ('upper-grid', -.85, top+2, 0, 20),
            ('lower-brush', -.85, bottom-2, 0, -10),
            ('returning-wheel', 70.5, top+3, -120, 0),
            ('outgoing-wheel', 70.1, top+3, 120, 0),
            ('upward-head', -.85, top+4, 0, 120),
            ('downward-body', -.85, bottom-14, 0, -120),
        )
        for name, x, y, vx, vy in cases:
            host.reset(index, True, (x,y))
            raw_x, raw_y = (round(v * settings['velocity_scale']) for v in (vx, vy))
            for part in (host.b.body, *host.b.wheel):
                part.vx, part.vy = raw_x, raw_y
            host.b.rider_vx, host.b.rider_vy = raw_x, raw_y
            pc.reset(directory / f'fixture{index}.txt', host.seed_values(), True)
            for step in range(1, 121):
                previous = host.b.steps
                host.f.physics_step(0)
                pc.step(0, settings['dt'])
                substeps = (host.b.steps - previous) & 255
                assert substeps == pc.f.compare_pc_substep_count(), (index, name, step, substeps)
                dead = pc.snapshot()['dead']
                assert dead == (not host.p.alive), (index, name, step)
                if dead:
                    break
            else:
                raise AssertionError((level.name, name, 'never exited'))
            if name in ('returning-wheel', 'outgoing-wheel'):
                assert (step, substeps) == (1, 1 if name == 'returning-wheel' else 2)
            results.append(dict(level=index, case=name, update=step, substep=substeps))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gen', type=Path, required=True, help='generated scheduled physics constants')
    parser.add_argument('--res', type=Path, help='also check each threshold of all original internal levels')
    parser.add_argument('--out', type=Path, default=BASE/'build/level-exit-check')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    constants = args.gen/'riding_constants.h'
    settings = comparison.constants(constants)
    assert settings['pc_schedule'], 'requires the scheduled physics profile'
    pc = comparison.Pc(comparison.build_pc(out))
    library, directory, fixtures = comparison.build_fixtures(out, constants, BASE/'src', 'fixture')
    levels = list(fixtures)
    if args.res:
        levels.extend(comparison.internal_levels(comparison.Resource(args.res)))
    report = {'threshold_probes': check_thresholds(pc, levels, out),
              'trajectories': check_trajectories(pc, comparison.Gbc(library, settings), fixtures, directory, settings)}
    (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f"{report['threshold_probes']} original-PC boundary probes and {len(report['trajectories'])} exit trajectories passed")


if __name__ == '__main__':
    main()
