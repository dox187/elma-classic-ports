#!/usr/bin/env python3
"""Measure level-ground and inclined landings against the original PC sources.

Run from any directory; generated assets are read, never regenerated in place:
  python3 console/gbc/test/check_landing_response.py --gen console/gbc/build/gen-8m

The default matrix covers wheel-center heights 1/4/8 m, initial horizontal
speeds 0/4/8 model m/s, and held coast/gas/brake (27 cases).
Optional --baseline-source/--baseline-constants rebuild an immutable source
snapshot into the private output directory. Preserve its console/gbc and
console/nes include layout. --source selects an experiment; --slope-degrees
rotates the ground while keeping the motorcycle upright at the start.

This is a differential measurement, not a universal fidelity score. Optional
--bounds JSON supplies justified, case-specific regression limits, for example:
  {"h4-vx0-coast": {"candidate.wheel0.first_airtime_wall_s": {"max": 0.6},
                     "candidate.dead": {"equals": false}}}
Paths address the per-case report; missing/null metrics fail numeric bounds.
All case traces and the report are saved before any assertion is raised.
"""
import argparse
import bisect
import json
import math
from pathlib import Path

import compare_pc_physics as comparison


WHEELS = ('wheel0', 'wheel1')
WHEEL_RADIUS = .4
GAME_SPEED = .4368
IMPACT_WINDOW_WALL_S = 2.


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def measure(rows, events, slope_degrees=0.):
    """Each wheel has its own landing/flight; never mix the two contact clocks."""
    angle = math.radians(slope_degrees)
    normal_height = lambda row, wheel: (
        row['position'][wheel][1] * math.cos(angle)
        - row['position'][wheel][0] * math.sin(angle) - WHEEL_RADIUS)
    end = rows[-1]['t_game']
    times = [row['t_game'] for row in rows]
    deaths = [row['t_wall'] for row in rows if row['dead']]
    result = {'samples': len(rows), 'dead': bool(deaths),
              'death_wall_s': deaths[0] if deaths else None,
              'observed_wall_s': end / GAME_SPEED}
    first_hits = []
    for wheel_index, wheel in enumerate(WHEELS):
        changes = [e for e in events if e['wheel'] == wheel_index]
        hit = next((e['t_game'] for e in changes if e['count'] > 0), None)
        if hit is None:
            result[wheel] = {'never_contacted': True}
            continue
        first_hits.append(hit)
        release = next((e['t_game'] for e in changes
                        if e['t_game'] >= hit and e['from'] in (1, 2)
                        and e['count'] == 0), None)
        recontact = next((e['t_game'] for e in changes
                          if release is not None and e['t_game'] > release
                          and e['count'] > 0), None)
        contact_duration = 0.
        for index, event in enumerate(changes):
            if event['count'] > 0:
                stop = changes[index + 1]['t_game'] if index + 1 < len(changes) else end
                contact_duration += max(0., stop - event['t_game'])
        loss_count = sum(e['from'] in (1, 2) and e['count'] == 0 for e in changes)
        lost_intervals = []
        for index, event in enumerate(changes):
            if event['t_game'] >= hit and event['count'] == 0:
                stop = changes[index + 1]['t_game'] if index + 1 < len(changes) else end
                lost_intervals.append(max(0., stop - event['t_game']))
        window_end = min(end, hit + IMPACT_WINDOW_WALL_S * GAME_SPEED)
        window_contact = 0.
        window_lost = []
        window_losses = 0
        for index, event in enumerate(changes):
            stop = changes[index + 1]['t_game'] if index + 1 < len(changes) else end
            duration = max(0., min(window_end, stop) - max(hit, event['t_game']))
            if event['count'] > 0:
                window_contact += duration
            elif duration:
                window_lost.append(duration)
            if hit <= event['t_game'] < window_end and event['from'] in (1, 2) and event['count'] == 0:
                window_losses += 1
        window_rows = [row for row in rows if hit - 1e-10 <= row['t_game'] <= window_end + 1e-10]
        flight = []
        peak = None
        if release is not None:
            # Positions are only sampled at frame targets. Do not invent a peak
            # for a PC release/recontact wholly between two frame samples.
            stop = recontact if recontact is not None else end
            flight = [row for row in rows if release <= row['t_game'] <= stop + 1e-10]
            if flight:
                peak = max(normal_height(row, wheel) for row in flight)
        result[wheel] = {
            'never_contacted': False,
            'first_contact_wall_s': hit / GAME_SPEED,
            'first_release_wall_s': release / GAME_SPEED if release is not None else None,
            'first_recontact_wall_s': recontact / GAME_SPEED if recontact is not None else None,
            'first_contact_duration_wall_s': ((release if release is not None else end) - hit) / GAME_SPEED,
            'first_airtime_wall_s': ((recontact if recontact is not None else end) - release) / GAME_SPEED
                                   if release is not None else 0.,
            'first_airtime_censored': release is not None and recontact is None,
            'first_flight_peak_bottom_m': peak,
            'first_flight_position_samples': len(flight),
            'post_contact_peak_bottom_m': max(normal_height(row, wheel)
                                              for row in rows if row['t_game'] >= hit - 1e-10),
            'longest_contact_loss_wall_s': max(lost_intervals, default=0.) / GAME_SPEED,
            'total_contact_wall_s': contact_duration / GAME_SPEED,
            'total_contact_loss_wall_s': max(0., end - hit - contact_duration) / GAME_SPEED,
            'contact_loss_count': loss_count,
            'impact_window': {
                'requested_wall_s': IMPACT_WINDOW_WALL_S,
                'observed_wall_s': (window_end - hit) / GAME_SPEED,
                'censored': end + 1e-10 < hit + IMPACT_WINDOW_WALL_S * GAME_SPEED,
                'peak_bottom_m': max((normal_height(row, wheel) for row in window_rows), default=None),
                'contact_wall_s': window_contact / GAME_SPEED,
                'air_wall_s': sum(window_lost) / GAME_SPEED,
                'longest_air_wall_s': max(window_lost, default=0.) / GAME_SPEED,
                'contact_loss_count': window_losses,
            },
        }
    # Vertical body-to-wheel-midpoint clearance is an observable compression
    # proxy, not spring length. Tilt can also reduce this clearance.
    clearance = lambda row: row['position']['body'][1] - sum(
        row['position'][wheel][1] for wheel in WHEELS) / 2
    result['initial_body_clearance_m'] = clearance(rows[0])
    if first_hits:
        landing = bisect.bisect_left(times, min(first_hits) - 1e-10)
        alive_rows = [row for row in rows[landing:] if not row['dead']]
        if alive_rows:
            minimum = min(alive_rows, key=clearance)
            result['body_peak_compression_m'] = max(0., clearance(rows[0]) - clearance(minimum))
            result['body_min_clearance_m'] = clearance(minimum)
            result['body_peak_compression_wall_s'] = minimum['t_wall']
    return result


def run_case(pc, host, level_path, height, velocity, keys, steps, slope_degrees=0.):
    host.reset(0, True, (-.85, height))
    scaled_velocity = round(velocity * host.settings['velocity_scale'])
    for part in (host.b.body, *host.b.wheel):
        part.vx = scaled_velocity
    host.b.rider_vx = scaled_velocity
    seed = host.seed_values()
    pc.reset(level_path, seed, True)
    traces = {'pc': [pc.snapshot()], 'gbc': [host.snapshot()]}
    for _ in range(steps):
        if not traces['pc'][-1]['dead']:
            pc.step(keys, host.settings['dt'])
            traces['pc'].append(pc.snapshot())
        if not traces['gbc'][-1]['dead']:
            host.step(keys)
            traces['gbc'].append(host.snapshot())
        if traces['pc'][-1]['dead'] and traces['gbc'][-1]['dead']:
            break
    events = {'pc': pc.contact_events(), 'gbc': host.contact_events}
    return {'initial_state': seed, 'traces': traces, 'contact_events': events,
            'runtime_events': {'pc': pc.events(), 'gbc': host.events},
            'metrics': {name: measure(rows, events[name], slope_degrees) for name, rows in traces.items()}}


def differences(candidate, reference):
    """Signed physical-unit differences only; categorical/censored states stay explicit."""
    result = {}
    for key, value in candidate.items():
        other = reference.get(key)
        if isinstance(value, dict) and isinstance(other, dict):
            result[key] = differences(value, other)
        elif type(value) in (int, float) and type(other) in (int, float):
            result[key] = value - other
    return result


def check_bounds(cases, bounds):
    failures = []
    for name, limits in bounds.items():
        for path, rules in limits.items():
            value = cases.get(name)
            for part in path.split('.'):
                value = value.get(part) if isinstance(value, dict) else None
            for rule, limit in rules.items():
                if rule == 'equals':
                    passed = value == limit
                elif rule in ('min', 'max'):
                    passed = type(value) in (int, float) and (
                        value >= limit if rule == 'min' else value <= limit)
                else:
                    raise ValueError(f'Unknown bound {name}.{path}: {rule}')
                if not passed:
                    failures.append(f'{name}.{path}: {value!r}, expected {rule} {limit!r}')
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--gen', type=Path, default=comparison.BASE / 'build/gen-8m')
    parser.add_argument('--source', type=Path, default=comparison.BASE / 'src')
    parser.add_argument('--out', type=Path, default=comparison.BASE / 'build/landing-response')
    parser.add_argument('--baseline-source', type=Path)
    parser.add_argument('--baseline-constants', type=Path)
    parser.add_argument('--steps', type=int, default=240)
    parser.add_argument('--bounds', type=Path)
    parser.add_argument('--slope-degrees', type=float, default=0.,
                        help='Incline the surface around the origin; bike starts upright')
    args = parser.parse_args()
    if args.steps <= 0:
        parser.error('--steps must be positive')
    if args.baseline_constants and not args.baseline_source:
        parser.error('--baseline-constants requires --baseline-source')
    if not -45 <= args.slope_degrees <= 45:
        parser.error('--slope-degrees must be between -45 and 45')
    if args.slope_degrees:
        original_fixtures = comparison.fixture_levels
        def inclined_fixtures():
            levels = original_fixtures()
            angle = math.radians(args.slope_degrees)
            surface = levels[0].polygons[0]
            levels[0].polygons[0] = (surface[0], [
                (x * math.cos(angle) - y * math.sin(angle),
                 x * math.sin(angle) + y * math.cos(angle))
                for x, y in surface[1]])
            levels[0].name = f'Controlled {args.slope_degrees:g} degree incline'
            return levels
        comparison.fixture_levels = inclined_fixtures
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    constants = (args.gen / 'riding_constants.h').resolve()
    settings = comparison.constants(constants)
    bounds = json.loads(args.bounds.read_text()) if args.bounds else {}
    pc = comparison.Pc(comparison.build_pc(out, contacts=True))
    sources = {'candidate': (args.source, constants)}
    if args.baseline_source:
        sources['baseline'] = (args.baseline_source, args.baseline_constants or constants)
    hosts = {}
    report = {
        'schema': 'landing-response-v1', 'steps': args.steps,
        'slope_degrees': args.slope_degrees, 'settings': settings,
        'math_profile': 'Original PC sources, native double, capped .0055 game-second substeps; not Windows x87',
        'definitions': {
            'coordinates': 'World meters, Y up; surface through origin at slope_degrees; wheel radius .4 m',
            'velocity': 'Initial model m/game-second; display m/wall-second = model speed * .4368',
            'controls': 'Held from t=0: coast=0, gas=1, brake=2; initial turned=true',
            'contact_timing': 'Resolved solver transitions; PC substeps, GBC frame steps. Each wheel measured independently.',
            'first_flight_peak_bottom_m': 'Maximum sampled wheel center distance along surface normal minus .4 between that wheel release and recontact; null if no flight samples',
            'first_airtime_censored': 'True when first release has no observed recontact; airtime is then a lower bound',
            'post_contact_peak_bottom_m': 'Maximum sampled wheel bottom after first contact through death/horizon; catches later bounce after initial chatter, but also throttle wheelies',
            'impact_window': 'Each wheel first contact through 2 wall seconds later; clipped at engine death/horizon and explicitly censored. Contact/air intervals clipped to that same window.',
            'total_contact': 'Sum of resolved contact intervals from first contact through that engine death or requested horizon',
            'body_peak_compression_m': 'Initial body-to-wheel-midpoint vertical clearance minus minimum live clearance after first landing; includes tilt',
            'differences': 'Signed candidate minus PC/baseline, physical units; compare censor/death states before interpreting',
        },
        'limits': 'HOST only; sampled peaks can miss inter-frame maxima. Different death times imply different observation windows.',
        'libraries': {'pc': {'path': str(pc.library), 'sha256': comparison.sha256(pc.library)}},
        'bounds': bounds, 'cases': {}, 'failures': [], 'contact_coverage_notes': [],
    }
    plain_pc = comparison.Pc(comparison.build_contact_control(pc.library))
    report['contact_state_identity'] = {}
    for name, (source, const) in sources.items():
        if comparison.constants(const) != settings:
            raise ValueError('Candidate and baseline time/unit scales must match')
        library, gen, _ = comparison.build_fixtures(out, const, source, name, contacts=True)
        host = comparison.Gbc(library, settings)
        hosts[name] = (host, gen / 'fixture0.txt')
        report['libraries'][name] = {'path': str(library), 'sha256': comparison.sha256(library),
                                     'source': str(source.resolve()), 'constants_sha256': comparison.sha256(const)}
        plain = comparison.Gbc(comparison.build_contact_control(library), settings)
        try:
            report['contact_state_identity'][name] = comparison.validate_contact_identity(
                pc, plain_pc, host, plain, gen / 'fixture0.txt', 0, [0] * args.steps,
                start=(-.85, 4.))
        except AssertionError as error:
            report['contact_state_identity'][name] = {'error': str(error)}
            report['failures'].append(f'{name}: contact instrumentation changed state: {error}')
    matrix = [(height, velocity, control, keys)
              for height in (1, 4, 8) for velocity in (0, 4, 8)
              for control, keys in (('coast', 0), ('gas', 1), ('brake', 2))]
    for height, velocity, control, keys in matrix:
        name = f'h{height}-vx{velocity}-{control}'
        case = {'height_m': height, 'requested_velocity_model_m_s': velocity, 'keys': keys}
        reference_trace = None
        for label, (host, level_path) in hosts.items():
            run = run_case(pc, host, level_path, height, velocity, keys, args.steps, args.slope_degrees)
            trace_path = out / f'{name}-{label}.json'
            write_json(trace_path, run)
            case[label] = run['metrics']['gbc']
            case[label]['trace'] = str(trace_path)
            if reference_trace is not None and run['traces']['pc'] != reference_trace:
                report['failures'].append(f'{name}: candidate and baseline PC initial states/trajectories differ')
            reference_trace = run['traces']['pc']
            case['pc'] = run['metrics']['pc']
            for engine, metric in run['metrics'].items():
                for wheel in WHEELS:
                    if metric[wheel]['never_contacted']:
                        note = f'{name}/{label}/{engine}/{wheel}: no contact before horizon/death'
                        # On inclines the bike may tip over before its other
                        # wheel touches; retain this as observed coverage.
                        report['contact_coverage_notes'].append(note)
                        if not args.slope_degrees:
                            report['failures'].append(note)
        case['candidate_minus_pc'] = differences(case['candidate'], case['pc'])
        case['rebound_error'] = {}
        for wheel in WHEELS:
            measured = case['candidate'][wheel]
            reference = case['pc'][wheel]
            metrics = {}
            for field in ('first_flight_peak_bottom_m', 'first_airtime_wall_s'):
                actual, target = measured.get(field), reference.get(field)
                metrics[field] = {
                    'absolute': abs(actual - target) if actual is not None and target is not None else None,
                    'percent': abs(actual - target) / abs(target) * 100.
                               if actual is not None and target is not None and target != 0 else None,
                }
            case['rebound_error'][wheel] = metrics
        if 'baseline' in case:
            if case['candidate']['dead'] and not case['baseline']['dead']:
                report['failures'].append(f'{name}: candidate dies but baseline survives')
            case['candidate_minus_baseline'] = differences(case['candidate'], case['baseline'])
        report['cases'][name] = case
    report['failures'].extend(check_bounds(report['cases'], bounds))
    report['case_count'] = len(report['cases'])
    report['checks'] = 'Contact coverage and fixture identity; explicit metric bounds only when --bounds is supplied'
    write_json(out / 'report.json', report)
    print(json.dumps({'report': str(out / 'report.json'), 'cases': report['case_count'],
                      'failures': report['failures'], 'bounds_supplied': bool(bounds)}))
    if report['failures']:
        raise AssertionError(f'{len(report["failures"])} landing checks failed; see {out / "report.json"}')


if __name__ == '__main__':
    main()
