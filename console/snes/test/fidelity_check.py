"""Measure complete original-PC/SNES trajectories with a terminal-gated metric.

  python test/fidelity_check.py --out build/fidelity-baseline

Primary comparisons use identical 80Hz inputs and dt=0.4368/80 game units.
At least99% means EVERY case has>=99% fully accepted samples AND identical
apple/gravity/turn/death/finish chronology. Aggregate body averages do not
satisfy that target. The native-PC0.0055 cap is clipped to the same target
schedule as LEJATSZO.CPP; it is a separate sensitivity result.
"""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import subprocess

from finish_test import read_script

ROOT = Path(__file__).resolve().parent.parent
POSITION_PAIRS = [(0, 1), (6, 7), (12, 13), (18, 19), (22, 23)]
VELOCITY_PAIRS = [(2, 3), (8, 9), (14, 15), (20, 21)]
ANGLES = [4, 10, 16]
OMEGAS = [5, 11, 17]
FIELDS = ['body.x', 'body.y', 'body.vx', 'body.vy', 'body.angle', 'body.omega',
          'wheel2.x', 'wheel2.y', 'wheel2.vx', 'wheel2.vy', 'wheel2.angle', 'wheel2.omega',
          'wheel4.x', 'wheel4.y', 'wheel4.vx', 'wheel4.vy', 'wheel4.angle', 'wheel4.omega',
          'rider.x', 'rider.y', 'rider.vx', 'rider.vy', 'head.x', 'head.y']
TOLERANCES = {'position_m': .01, 'velocity_m_per_real_second': .01,
              'angle_radians': math.radians(.5), 'omega_radians_per_real_second': math.radians(.5)}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scripted_cases(path):
    cases = []
    for line in Path(path).read_text().splitlines():
        line = line.split('#')[0].strip()
        if line:
            level, script = line.split(maxsplit=1)
            cases.append({'id': 'existing_%02d' % len(cases), 'level': int(level),
                          'script': script, 'kind': 'existing'})
    return cases


def seeded_script(seed, seconds, hz=80):
    rng = random.Random(seed)
    # Long holds resemble normal play; never inject warps or invalid inputs.
    options = [('G', 45), ('N', 18), ('B', 10), ('GL', 10), ('GR', 10), ('L', 3), ('R', 3)]
    remaining, tokens = int(seconds * hz), []
    while remaining:
        key = rng.choices([x[0] for x in options], weights=[x[1] for x in options])[0]
        n = min(remaining, rng.randint(8, 120))
        if rng.random() < .06:
            key += 'T'
        tokens.append(key + str(n))
        remaining -= n
    return ' '.join(tokens)


def wrapped_error(a, b):
    return abs((a - b + math.pi) % (2 * math.pi) - math.pi)


def errors(row):
    a, b = row['snes'], row['pc']
    return {'position': max(math.hypot(a[x] - b[x], a[y] - b[y]) for x, y in POSITION_PAIRS),
            'body_position': math.hypot(a[0] - b[0], a[1] - b[1]),
            'velocity': max(math.hypot(a[x] - b[x], a[y] - b[y]) for x, y in VELOCITY_PAIRS),
            'angle': max(wrapped_error(a[i], b[i]) for i in ANGLES),
            'omega': max(abs(a[i] - b[i]) for i in OMEGAS)}


def critical_difference(row):
    if (row['snes_event'] & 7) != (row['pc_event'] & 7):
        return 'apple/death/finish_event'
    if row['snes_apple_object'] != row['pc_apple_object']:
        return 'apple_identity'
    if row['snes_discrete'] != row['pc_discrete']:
        return 'turn/gravity/apple_count'
    if row['snes_objects'] != row['pc_objects']:
        return 'object_active_state'
    if row['snes_stopped'] != row['pc_stopped']:
        return 'termination'
    return None


def measure(case, records, trace_path):
    counts = dict.fromkeys(['position', 'body_position', 'velocity', 'angle', 'omega', 'discrete', 'all'], 0)
    maxima = dict.fromkeys(['position', 'body_position', 'velocity', 'angle', 'omega'], 0.0)
    first, first_event, terminal = None, None, {'pc': None, 'snes': None}
    n = 0
    events = {'pc': [], 'snes': []}
    for row in records:
        if row['step'] == 0:
            continue
        n += 1
        e = errors(row)
        for k in maxima:
            maxima[k] = max(maxima[k], e[k])
        flags = {'position': e['position'] <= TOLERANCES['position_m'],
                 'body_position': e['body_position'] <= TOLERANCES['position_m'],
                 'velocity': e['velocity'] <= TOLERANCES['velocity_m_per_real_second'],
                 'angle': e['angle'] <= TOLERANCES['angle_radians'],
                 'omega': e['omega'] <= TOLERANCES['omega_radians_per_real_second']}
        difference = critical_difference(row)
        flags['discrete'] = difference is None
        flags['all'] = all(v for k, v in flags.items() if k != 'body_position')
        for k, v in flags.items():
            counts[k] += bool(v)
        if first is None and not flags['all']:
            first = {'step': row['step'], 'wall_seconds': row['step'] / 80,
                     'failed_components': [k for k, v in flags.items() if not v],
                     'errors': e, 'state': row}
        if first_event is None and difference:
            first_event = {'step': row['step'], 'wall_seconds': row['step'] / 80,
                           'reason': difference, 'state': row}
        for engine in events:
            event = row[engine + '_event'] & 7
            if event:
                events[engine].append({'step': row['step'], 'mask': event,
                                      'apple_object': row[engine + '_apple_object'],
                                      'gravity': row[engine + '_discrete'][1]})
            if event & 3 and terminal[engine] is None:
                terminal[engine] = {'step': row['step'], 'event_mask': event & 3}
    fractions = {k: v / max(1, n) for k, v in counts.items()}
    gated = fractions['all'] if first_event is None else 0.0
    return {**case, 'samples': n, 'component_pass_fractions': fractions,
            'terminal_gated_fidelity': gated, 'critical_events_match': first_event is None,
            'maximum_errors': maxima, 'first_continuous_divergence': first,
            'first_critical_divergence': first_event, 'events': events,
            'terminal': terminal, 'trace': str(trace_path)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--host', default=str(ROOT / 'build/host/physcheck'))
    ap.add_argument('--spec-source', default=str(ROOT / 'test/phys_spec.c'),
                    help='actual C specification source compiled into --host (including isolated variants)')
    ap.add_argument('--gen', default=str(ROOT / 'build/gen'))
    ap.add_argument('--levdump', default=str(ROOT / 'build/host/levdump'))
    ap.add_argument('--cases', default=str(ROOT / 'test/physcases.txt'))
    ap.add_argument('--out', default=str(ROOT / 'build/fidelity-baseline'))
    ap.add_argument('--seed', type=int, default=187)
    ap.add_argument('--seeded-levels', default=','.join(map(str, range(54))))
    ap.add_argument('--seeds-per-level', type=int, default=2)
    ap.add_argument('--seconds', type=int, default=30)
    ap.add_argument('--pc-cap', type=float, help='sensitivity: original PC maximum dt, clipped to sample target')
    ap.add_argument('--require-target', action='store_true', help='exit1 unless strict fidelity>=99%%')
    a = ap.parse_args()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    corpus = scripted_cases(a.cases)
    corpus.append({'id': 'warmup_full', 'level': 0, 'kind': 'full_finish',
                   'script': read_script(ROOT / 'test/warmup_finish.txt')[1]})
    for level in [int(x) for x in a.seeded_levels.split(',') if x]:
        for k in range(a.seeds_per_level):
            seed = a.seed + level * 1009 + k * 7919
            corpus.append({'id': 'seeded_%02d_%d' % (level, k), 'level': level,
                           'kind': 'seeded_normal', 'seed': seed,
                           'script': seeded_script(seed, a.seconds)})
    (out / 'corpus.json').write_text(json.dumps(corpus, indent=2) + '\n')
    runs = []
    for case in corpus:
        cmd = [a.host, a.gen, a.levdump, str(case['level']), case['script'], '--trace-json']
        if a.pc_cap:
            cmd += ['-t', str(a.pc_cap)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if proc.returncode:
            raise RuntimeError('%s: %s' % (case['id'], proc.stderr))
        records = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        if not records or any(len(r['snes']) != 24 or len(r['pc']) != 24 for r in records):
            raise RuntimeError('Incomplete trace: ' + case['id'])
        trace = out / (case['id'] + '.jsonl.gz')
        with gzip.open(trace, 'wt') as f:
            f.write(proc.stdout)
        run = measure(case, records, trace)
        runs.append(run)
        if case['id'] == 'warmup_full':
            print('Warm Up terminal:', run['terminal'], flush=True)
    n = sum(r['samples'] for r in runs)
    aggregate = {k: sum(r['component_pass_fractions'][k] * r['samples'] for r in runs) / max(1, n)
                 for k in runs[0]['component_pass_fractions']}
    worst = min(runs, key=lambda r: r['terminal_gated_fidelity'])
    fidelity = worst['terminal_gated_fidelity']
    report = {'schema': 1, 'strict_fidelity': fidelity, 'target': .99,
              'target_met': fidelity >= .99, 'worst_case': worst['id'],
              'critical_event_failing_cases': sum(not r['critical_events_match'] for r in runs),
              'cases': len(runs), 'samples': n, 'component_sample_pass_fractions': aggregate,
              'minimum_case_component_fractions': {k: min(r['component_pass_fractions'][k] for r in runs)
                                                  for k in aggregate},
              'tolerances': TOLERANCES, 'trace_fields': FIELDS,
              'discrete_fields': ['turned', 'gravity', 'apples'],
              'reference': 'original six physics CPP units plus extracted single-player loop harness, compiled on host',
              'metric': 'minimum per-case all-component sample fraction, gated to zero by any critical event/state mismatch',
              'schedule': {'physics_hz': 80, 'game_units_per_wall_second': .4368,
                           'matched_dt_game': .4368 / 80, 'pc_cap': a.pc_cap,
                           'terminal_turns': 'not applied', 'native_cap_clips_to_target': True},
              'host_sha256': digest(a.host), 'pc_harness_sha256': digest(ROOT / 'test/pcphys/pcphys.cpp'),
              'phys_spec_sha256': digest(a.spec_source),
              'generated_constants_sha256': digest(Path(a.gen) / 'phys_const.h'),
              'generated_tables_sha256': digest(Path(a.gen) / 'phys_tables.h'),
              'original_sources_sha256': {p.name: digest(p) for p in sorted((ROOT / '../../src').glob('*.CPP'))
                                           if p.name in ['LEPTET.CPP', 'BEALLIT.CPP', 'UTKOZES.CPP', 'UTKOZES2.CPP', 'SZAKASZ.CPP', 'VEKT2.CPP']},
              'corpus_sha256': digest(out / 'corpus.json'), 'runs': runs}
    (out / 'fidelity.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print('Strict fidelity %.3f%%; %d/%d critical-event cases fail; continuous all-fields %.2f%%' %
          (100 * fidelity, report['critical_event_failing_cases'], len(runs), 100 * aggregate['all']))
    print('Report:', out / 'fidelity.json')
    return 1 if a.require_target and not report['target_met'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
