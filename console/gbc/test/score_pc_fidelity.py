#!/usr/bin/env python3
"""Strict, reusable scoring of compare_pc_physics.py report/trace files.

Primary: at least 99.9% of post-initial, time-aligned live samples in EVERY
case must satisfy ALL position (Euclidean distance <= .01 world meters),
circle angle (wrapped error <= .1 degree), and linear velocity (Euclidean
distance <= .01 meters/REAL-second) limits. Trace velocities are per game
second, so both linear and angular velocities are multiplied by .4368.
Body, both wheels, rider and head positions are measured; body and both wheel
angles are mandatory. Rider/head have no independent physical angle: their
orientation inherits the body. Four direct velocities are mandatory; head
sample finite-difference velocity is also scored whenever either trace has it.
Angular velocity has no approved primary tolerance and is diagnostic only.

An entire case scores zero on any discrete state, covered event sequence,
object identity, terminal outcome or event interval mismatch, or invalid/
incomplete trace. Initial poses never earn matches. The live reference window
ends before its first terminal interval, otherwise at the requested horizon;
candidate truncation cannot shrink it. Terminal poses are not time-aligned
when PC substeps terminate early, so terminal samples are checked as events
and discrete states, not continuous samples. Any rows following the first
terminal state are rejected, never counted as frozen successful samples.
Event intervals are ((n-1)*dt, n*dt], using observed step-completion t_game;
the PC fixture's original substep-start event timestamps are retained too.

Secondary .1% relative diagnostics are reported after the primary result.
Their limit is max(primary absolute tolerance, .001 * reference magnitude).
The explicit absolute floor prevents division by near-zero values. Position
magnitude is displacement from that part's initial REFERENCE pose, not the
world origin; angular magnitude is wrapped displacement from its initial
reference angle. These diagnostics never override the primary result.

Contact-capable traces also require the ordered resolved-wheel contact count
transitions in the same frame intervals, with per-sample modes consistent with
their event streams. Coverage requires both engines' instrumented-source
provenance and bit-identical state validation. Legacy traces remain incomplete.

  python3 console/gbc/test/score_pc_fidelity.py path/to/report.json --run both
  python3 console/gbc/test/score_pc_fidelity.py path/to/report.json --require-target
"""
import argparse
import json
import math
from pathlib import Path
import re

GAME_SECONDS_PER_REAL_SECOND = .4368
TARGET_FRACTION = .999
RELATIVE_LIMIT = .001
POSITION_LIMIT_M = .01
ANGLE_LIMIT_DEG = .1
VELOCITY_LIMIT_M_S = .01
PARTS = ('body', 'wheel0', 'wheel1', 'rider', 'head')
CIRCLES = PARTS[:3]
DIRECT_VELOCITIES = PARTS[:4]
DISCRETE_FIELDS = ('dead', 'finished', 'turned', 'gravity_direction', 'apples_collected')
GRAVITY_DIRECTIONS = ('up', 'down', 'left', 'right')
TIME_EPSILON = 1e-8
CONTACT_SCHEMA = 'resolved-wheel-contacts-v1'
DEFAULT_REPORT = Path(__file__).resolve().parents[1] / 'build/pc-comparison-v090/report.json'


class InvalidTrace(ValueError):
    pass


class Problems:
    """Keep JSON output bounded while preserving the total and first failures."""
    def __init__(self):
        self.count = 0
        self.examples = []

    def add(self, kind, **details):
        self.count += 1
        item = {'kind': kind, **details}
        if len(self.examples) < 20:
            self.examples.append(item)
        return item

    def result(self):
        return {'matches': self.count == 0, 'failure_count': self.count,
                'failures': self.examples, 'omitted_failures': self.count - len(self.examples)}


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise InvalidTrace('expected a finite number')
    return value


def wrapped_degrees(a, b):
    # remainder avoids cancellation around zero; both inputs are radians.
    return math.degrees(math.remainder(a - b, 2 * math.pi))


def within(error, limit):
    # Roundoff at an inclusive boundary must not turn .1 degrees into a failure.
    return error <= limit or math.isclose(error, limit, rel_tol=1e-12, abs_tol=1e-14)


def sample_interval(t, interval):
    """Positive observed event time -> enclosing right-closed sample interval."""
    quotient = t / interval
    nearest = round(quotient)
    if abs(t - nearest * interval) <= TIME_EPSILON:
        return nearest
    return math.ceil(quotient)


def measurement(row, field, part):
    try:
        value = row[field][part]
        if field in ('position', 'velocity'):
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                raise InvalidTrace('expected an xy vector')
            return [number(x) for x in value]
        return number(value)
    except (KeyError, TypeError) as exc:
        raise InvalidTrace(f'missing {field}.{part}') from exc


def discrete(row):
    try:
        result = {key: row[key] for key in DISCRETE_FIELDS if key != 'gravity_direction'}
        for key in ('dead', 'finished', 'turned'):
            if result[key] not in (False, True, 0, 1):
                raise InvalidTrace(f'invalid {key}')
            result[key] = bool(result[key])
        apples = result['apples_collected']
        if isinstance(apples, bool) or not isinstance(apples, int) or apples < 0:
            raise InvalidTrace('apples_collected must be a nonnegative integer')
        gravity = row.get('gravity_direction')
        if gravity is None:
            code = row['gravity']
            if isinstance(code, bool) or not isinstance(code, int) or code not in range(4):
                raise InvalidTrace('invalid gravity enum')
            gravity = GRAVITY_DIRECTIONS[code]
        if gravity not in GRAVITY_DIRECTIONS:
            raise InvalidTrace('invalid gravity direction')
        if 'gravity' in row and row['gravity'] != GRAVITY_DIRECTIONS.index(gravity):
            raise InvalidTrace('gravity enum and direction disagree')
        result['gravity_direction'] = gravity
        if result['dead'] and result['finished']:
            raise InvalidTrace('both dead and finished')
        return result
    except (KeyError, TypeError) as exc:
        raise InvalidTrace(f'missing discrete state: {exc}') from exc


def metric(unit, tolerance=None):
    return {'unit': unit, 'tolerance': tolerance, 'samples': 0, 'matched_samples': 0,
            'failing_samples': 0, 'missing_samples': 0, 'max_error': None,
            'first_failure': None}


def record(stat, error, t, limit=None, **details):
    stat['samples'] += 1
    if error is None:
        stat['missing_samples'] += 1
    else:
        stat['max_error'] = max(stat['max_error'] or 0., error)
    matched = error is not None and (limit is None or within(error, limit))
    stat['matched_samples' if matched else 'failing_samples'] += 1
    if not matched and stat['first_failure'] is None:
        stat['first_failure'] = {'t_game': t, 't_wall': t / GAME_SECONDS_PER_REAL_SECOND,
                                 'error': error, 'limit': limit, **details}
    return matched


def prepare_trace(rows, engine, interval, horizon, specs, problems):
    result = {'live': {}, 'terminal': None, 'initial': None, 'rows': [],
              'excluded_terminal_rows': 0, 'rejected_post_terminal_rows': 0}
    if not isinstance(rows, list) or not rows:
        problems.add('empty_or_missing_trace', engine=engine, t_game=0.)
        return result
    previous = None
    for index, row in enumerate(rows):
        if result['terminal'] is not None:
            result['rejected_post_terminal_rows'] += 1
            continue
        try:
            t = number(row['t_game'])
            state = discrete(row)
        except (InvalidTrace, KeyError, TypeError) as exc:
            problems.add('invalid_sample', engine=engine, row=index, detail=str(exc))
            continue
        result['rows'].append(row)
        if index == 0:
            result['initial'] = row
            if abs(t) > TIME_EPSILON:
                problems.add('missing_initial_time_zero', engine=engine, t_game=t)
        elif previous is not None and t <= previous + TIME_EPSILON:
            problems.add('nonincreasing_sample_time', engine=engine, row=index, t_game=t)
        previous = t
        if t < -TIME_EPSILON or t > horizon + TIME_EPSILON:
            problems.add('sample_outside_horizon', engine=engine, row=index, t_game=t)
        for field, part, _, _ in specs:
            try:
                measurement(row, field, part)
            except InvalidTrace as exc:
                problems.add('missing_or_invalid_measurement', engine=engine, row=index,
                             t_game=t, component=f'{field}.{part}', detail=str(exc))
        terminal = 'death' if state['dead'] else 'finish' if state['finished'] else None
        if terminal:
            result['excluded_terminal_rows'] = 1
            result['terminal'] = {'outcome': terminal, 't_game': t,
                                  'interval': sample_interval(t, interval), 'state': row}
            if index == 0 or t <= TIME_EPSILON:
                problems.add('terminal_initial_state', engine=engine, t_game=t)
        elif index:
            tick = round(t / interval)
            if tick < 1 or abs(t - tick * interval) > TIME_EPSILON:
                problems.add('sample_not_time_aligned', engine=engine, row=index, t_game=t)
            elif tick in result['live']:
                problems.add('duplicate_live_interval', engine=engine, row=index, t_game=t)
            else:
                result['live'][tick] = row
    if result['rejected_post_terminal_rows']:
        problems.add('post_terminal_padding', engine=engine,
                     t_game=result['terminal']['t_game'],
                     rejected_rows=result['rejected_post_terminal_rows'])
    if result['terminal'] is None and (previous is None or abs(previous - horizon) > TIME_EPSILON):
        problems.add('incomplete_live_trace', engine=engine, t_game=previous,
                     required_horizon_game_seconds=horizon)
    return result


def score_events(streams, interval, horizon):
    problems = Problems()
    normalized = {}
    for engine in ('pc', 'gbc'):
        events = streams.get(engine) if isinstance(streams, dict) else None
        if not isinstance(events, list):
            problems.add('missing_event_stream', engine=engine, t_game=0.)
            events = []
        normalized[engine] = []
        previous = 0.
        for index, event in enumerate(events):
            try:
                t = number(event['t_game'])
                if not isinstance(event['type'], str) or not event['type'] or 'object' not in event:
                    raise InvalidTrace('event type/object identity missing')
                if t <= 0 or t > horizon + TIME_EPSILON or t < previous - TIME_EPSILON:
                    raise InvalidTrace('event time outside horizon or out of sequence')
                original = number(event.get('original_event_time', t))
                previous = t
                normalized[engine].append({**event, 'interval': sample_interval(t, interval),
                                           't_wall': t / GAME_SECONDS_PER_REAL_SECOND,
                                           'original_event_time': original,
                                           'original_event_wall_time': original / GAME_SECONDS_PER_REAL_SECOND})
            except (InvalidTrace, KeyError, TypeError) as exc:
                problems.add('invalid_event', engine=engine, event_index=index, detail=str(exc))
                normalized[engine].append(None)
    comparisons = []
    for index in range(max(map(len, normalized.values()))):
        a, b = (normalized[k][index] if index < len(normalized[k]) else None for k in ('pc', 'gbc'))
        same_identity = bool(a and b and (a['type'], a['object']) == (b['type'], b['object']))
        same_interval = bool(a and b and a['interval'] == b['interval'])
        row = {'event_index': index, 'pc': a, 'gbc': b, 'same_type_and_object': same_identity,
               'same_interval': same_interval, 'matches': same_identity and same_interval,
               'signed_game_time_delta': b['t_game'] - a['t_game'] if a and b else None}
        comparisons.append(row)
        if not row['matches']:
            problems.add('event_mismatch', event_index=index,
                         t_game=min(e['t_game'] for e in (a, b) if e) if a or b else None,
                         pc=a, gbc=b)
    return {**problems.result(), 'events': comparisons}, normalized


def score_contacts(data, traces, interval, horizon):
    """Verify observation provenance/data separately from cross-engine fidelity."""
    raw_provenance, raw_streams = data.get('contact_instrumentation'), data.get('contact_events')
    provenance = raw_provenance if isinstance(raw_provenance, dict) else {}
    streams = raw_streams if isinstance(raw_streams, dict) else {}
    present = (any(value is not None and not isinstance(value, dict) for value in (raw_provenance, raw_streams)) or
               any(provenance.get(engine) or streams.get(engine) or
                   any('wheel_contacts' in row for row in traces[engine]['rows']) for engine in traces))
    if not present:
        return {'instrumented': False, 'coverage_complete': False, 'matches': None,
                'failure_count': 0, 'failures': [], 'events': [],
                'coverage_limitation': 'Missing validated resolved-wheel contact instrumentation/data.'}
    validation, normalized = {}, {}
    for engine, trace in traces.items():
        problems = Problems()
        meta = provenance.get(engine)
        proof = meta.get('state_identity') if isinstance(meta, dict) else None
        hashes = ('original_source_sha256', 'compiled_source_sha256', 'library_sha256')
        if (not isinstance(meta, dict) or meta.get('schema') != CONTACT_SCHEMA or
                meta.get('observational_only') is not True or
                any(not isinstance(meta.get(key), str) or not re.fullmatch(r'[0-9a-f]{64}', meta[key]) for key in hashes) or
                meta.get('original_source_sha256') == meta.get('compiled_source_sha256') or
                not isinstance(proof, dict) or proof.get('match') != 'bit exact' or
                not isinstance(proof.get('checkpoints'), int) or proof['checkpoints'] < 2):
            problems.add('missing_or_invalid_contact_instrumentation', engine=engine, t_game=0.)
        raw = streams.get(engine)
        if not isinstance(raw, list):
            problems.add('missing_contact_event_stream', engine=engine, t_game=0.)
            raw = []
        normalized[engine] = []
        modes, previous = [None, None], 0.
        end = trace['rows'][-1]['t_game'] if trace['rows'] else 0.
        for index, event in enumerate(raw):
            try:
                t, wheel, count, before = number(event['t_game']), event['wheel'], event['count'], event['from']
                if type(wheel) is not int or wheel not in (0, 1) or type(count) is not int or count not in (0, 1, 2):
                    raise InvalidTrace('contact wheel/count must be 0..1 / 0..2')
                if before is not None and (type(before) is not int or before not in (0, 1, 2)):
                    raise InvalidTrace('invalid previous contact count')
                if before != modes[wheel] or before == count:
                    raise InvalidTrace('contact transition does not follow the previous resolved count')
                if t <= 0 or t > min(end, horizon) + TIME_EPSILON or t < previous - TIME_EPSILON:
                    raise InvalidTrace('contact time outside observed trace or out of sequence')
                modes[wheel], previous = count, t
                normalized[engine].append({**event, 'interval': sample_interval(t, interval)})
            except (InvalidTrace, KeyError, TypeError) as exc:
                problems.add('invalid_contact_event', engine=engine, event_index=index, detail=str(exc))
                normalized[engine].append(None)
        modes, observed, cursor = [None, None], [0, 0], 0
        for index, row in enumerate(trace['rows']):
            t = row['t_game']
            while cursor < len(normalized[engine]):
                event = normalized[engine][cursor]
                if event and event['t_game'] > t + TIME_EPSILON: break
                if event: modes[event['wheel']] = event['count']
                cursor += 1
            actual, calls = row.get('wheel_contacts'), row.get('contact_observations')
            valid_calls = (isinstance(calls, list) and len(calls) == 2 and
                           all(type(n) is int and n >= 0 for n in calls))
            if (not isinstance(actual, dict) or set(actual) != {'wheel0', 'wheel1'} or
                    any(actual.get(f'wheel{i}') != modes[i] or
                        (index > 0 and (type(actual.get(f'wheel{i}')) is not int or actual[f'wheel{i}'] not in (0, 1, 2)))
                        for i in range(2))):
                problems.add('contact_event_state_mismatch', engine=engine, row=index, t_game=t)
            if (not valid_calls or (index == 0 and calls != [0, 0]) or
                    (index > 0 and any(calls[i] <= observed[i] for i in range(2))) or
                    (valid_calls and calls[0] != calls[1])):
                problems.add('missing_or_invalid_contact_observations', engine=engine, row=index, t_game=t)
            if valid_calls: observed = calls
        if not trace['rows']:
            problems.add('missing_contact_samples', engine=engine, t_game=0.)
        validation[engine] = problems.result()
    comparisons, mismatches = [], Problems()
    for index in range(max(map(len, normalized.values()))):
        a, b = (normalized[k][index] if index < len(normalized[k]) else None for k in ('pc', 'gbc'))
        same_identity = bool(a and b and (a['wheel'], a['from'], a['count']) == (b['wheel'], b['from'], b['count']))
        same_interval = bool(a and b and a['interval'] == b['interval'])
        comparisons.append({'event_index': index, 'pc': a, 'gbc': b,
                            'same_wheel_and_count': same_identity, 'same_interval': same_interval,
                            'matches': same_identity and same_interval})
        if not same_identity or not same_interval:
            mismatches.add('contact_event_mismatch', event_index=index,
                           t_game=min(e['t_game'] for e in (a, b) if e) if a or b else None, pc=a, gbc=b)
    for tick in sorted(set(traces['pc']['live']) & set(traces['gbc']['live'])):
        left, right = (traces[k]['live'][tick].get('wheel_contacts') for k in ('pc', 'gbc'))
        if left != right:
            mismatches.add('contact_mode_mismatch', t_game=tick * interval, pc=left, gbc=right)
    complete = all(v['matches'] for v in validation.values())
    failures = [failure for value in validation.values() for failure in value['failures']] + mismatches.examples
    return {'instrumented': True, 'coverage_complete': complete,
            'matches': complete and mismatches.count == 0,
            'failure_count': sum(v['failure_count'] for v in validation.values()) + mismatches.count,
            'failures': failures[:20], 'validation': validation, 'events': comparisons,
            'coverage_limitation': None if complete else 'Contact instrumentation or observation data failed validation.'}


def score_case(data, interval_game_seconds, horizon_game_seconds=None):
    """Score one loaded per-case trace object; no importing/building game code."""
    interval = number(interval_game_seconds)
    horizon = number(horizon_game_seconds if horizon_game_seconds is not None else data['horizon_game_seconds'])
    if interval <= 0 or horizon <= 0 or abs(horizon - round(horizon / interval) * interval) > TIME_EPSILON:
        raise InvalidTrace('positive interval and a whole-interval horizon are required')
    planned = round(horizon / interval)
    rows = {engine: data.get(engine) for engine in ('pc', 'gbc')}
    head_velocity = any(isinstance(row, dict) and 'head' in row.get('velocity', {})
                        for trace in rows.values() if isinstance(trace, list) for row in trace)
    specs = [('position', p, 'm', POSITION_LIMIT_M) for p in PARTS]
    specs += [('angles', p, 'degrees', ANGLE_LIMIT_DEG) for p in CIRCLES]
    specs += [('velocity', p, 'm/s (real time)', VELOCITY_LIMIT_M_S)
              for p in DIRECT_VELOCITIES + (('head',) if head_velocity else ())]
    problems = Problems()
    traces = {engine: prepare_trace(rows[engine], engine, interval, horizon, specs, problems)
              for engine in ('pc', 'gbc')}
    events, streams = score_events(data.get('events'), interval, horizon)
    contacts = score_contacts(data, traces, interval, horizon)
    terminals = {k: traces[k]['terminal'] for k in traces}
    a, b = terminals['pc'], terminals['gbc']
    terminal_matches = (a is None and b is None) or bool(a and b and
                        (a['outcome'], a['interval']) == (b['outcome'], b['interval']))
    terminal = {'matches': terminal_matches,
                **{k: {x: v[x] for x in ('outcome', 't_game', 'interval')} if v else None
                   for k, v in terminals.items()}}
    event_consistency = Problems()
    for engine, trace in traces.items():
        valid_events = [e for e in streams[engine] if e]
        terminal_events = [e for e in valid_events if e['type'] in ('death', 'finish')]
        end = trace['terminal']
        if (end is None and terminal_events) or (end is not None and
                (not terminal_events or (terminal_events[-1]['type'], terminal_events[-1]['interval']) !=
                 (end['outcome'], end['interval']))):
            event_consistency.add('terminal_event_state_mismatch', engine=engine,
                                  t_game=end['t_game'] if end else horizon)
        if trace['initial']:
            initial_apples = trace['initial']['apples_collected']
            for row in trace['rows']:
                collected = sum(e['type'] == 'apple' and e['t_game'] <= row['t_game'] + TIME_EPSILON
                                for e in valid_events)
                if row['apples_collected'] - initial_apples != collected:
                    event_consistency.add('apple_event_state_mismatch', engine=engine, t_game=row['t_game'])
    # Reference determines the live evaluation window; an early candidate death
    # or truncated file must never remove difficult reference samples.
    eligible = min(planned, max(0, a['interval'] - 1)) if a else planned
    if eligible == 0:
        problems.add('no_post_initial_live_samples', t_game=0.)
    primary = {field: {} for field in ('position', 'angles', 'velocity')}
    secondary = {field: {} for field in primary}
    omega = {p: {'unit': 'rad/s (real time)', 'samples': 0, 'measured_samples': 0,
                 'missing_samples': 0, 'max_error': None, 'sum_squared_error': 0.}
             for p in CIRCLES}
    for field, part, unit, limit in specs:
        primary[field][part] = metric(unit, limit)
        secondary[field][part] = {**metric(unit), 'absolute_floor': limit,
                                   'relative_limit': RELATIVE_LIMIT, 'floor_applied_samples': 0,
                                   'max_effective_relative_error': None}
    discrete_checks = Problems()
    discrete_counts = {key: {'samples': 0, 'mismatches': 0} for key in DISCRETE_FIELDS}

    def compare_discrete(left, right, t):
        if left is None or right is None:
            return
        ls, rs = discrete(left), discrete(right)
        for key in DISCRETE_FIELDS:
            discrete_counts[key]['samples'] += 1
            if ls[key] != rs[key]:
                discrete_counts[key]['mismatches'] += 1
                discrete_checks.add('discrete_state_mismatch', component=key, t_game=t,
                                    pc=ls[key], gbc=rs[key])

    compare_discrete(traces['pc']['initial'], traces['gbc']['initial'], 0.)
    matched_samples = relative_matches = 0
    for tick in range(1, eligible + 1):
        t = tick * interval
        left, right = (traces[k]['live'].get(tick) for k in ('pc', 'gbc'))
        for engine, row in (('pc', left), ('gbc', right)):
            if row is None:
                problems.add('missing_time_aligned_live_sample', engine=engine, interval=tick, t_game=t)
        compare_discrete(left, right, t)
        all_match = all_relative = True
        for field, part, _, limit in specs:
            error = scale = None
            try:
                ref = measurement(left, field, part)
                candidate = measurement(right, field, part)
                if field == 'angles':
                    error = abs(wrapped_degrees(candidate, ref))
                    initial = measurement(traces['pc']['initial'], field, part)
                    scale = abs(wrapped_degrees(ref, initial))
                else:
                    factor = GAME_SECONDS_PER_REAL_SECOND if field == 'velocity' else 1.
                    error = math.hypot(*(factor * (v - u) for u, v in zip(ref, candidate)))
                    origin = measurement(traces['pc']['initial'], field, part) if field == 'position' else (0., 0.)
                    scale = math.hypot(*(factor * (v - u) for u, v in zip(origin, ref)))
            except InvalidTrace:
                pass
            component = f'{field}.{part}'
            all_match = record(primary[field][part], error, t, limit, component=component) and all_match
            relative = secondary[field][part]
            relative_threshold = max(limit, RELATIVE_LIMIT * scale) if scale is not None else limit
            if scale is not None:
                relative['floor_applied_samples'] += RELATIVE_LIMIT * scale <= limit
            if error is not None and scale is not None:
                effective = error / max(scale, limit / RELATIVE_LIMIT)
                relative['max_effective_relative_error'] = max(relative['max_effective_relative_error'] or 0., effective)
            all_relative = record(relative, error, t, relative_threshold, component=component,
                                  reference_magnitude=scale) and all_relative
        matched_samples += all_match
        relative_matches += all_relative
        for part in CIRCLES:
            stat = omega[part]
            stat['samples'] += 1
            try:
                error = abs(measurement(right, 'angular_velocity', part) -
                            measurement(left, 'angular_velocity', part)) * GAME_SECONDS_PER_REAL_SECOND
            except InvalidTrace:
                stat['missing_samples'] += 1
            else:
                stat['measured_samples'] += 1
                stat['max_error'] = max(stat['max_error'] or 0., error)
                stat['sum_squared_error'] += error * error
    for stat in omega.values():
        squared_error = stat.pop('sum_squared_error')
        stat['rmse'] = math.sqrt(squared_error / stat['measured_samples']) if stat['measured_samples'] else None
    if a and b and a['interval'] == b['interval']:
        compare_discrete(a['state'], b['state'], max(a['t_game'], b['t_game']))
    numeric_fraction = matched_samples / eligible if eligible else 0.
    covered_events_match = (events['matches'] and terminal_matches and discrete_checks.count == 0 and
                            event_consistency.count == 0 and (not contacts['instrumented'] or contacts['matches']))
    hard_gate = problems.count != 0 or not covered_events_match
    fraction = 0. if hard_gate else numeric_fraction
    failures = [item for group in primary.values() for stat in group.values()
                if (item := stat['first_failure']) is not None]
    failures += problems.examples + events['failures'] + discrete_checks.examples + event_consistency.examples + contacts['failures']
    if not terminal_matches:
        failures.append({'kind': 'terminal_mismatch', 't_game': min(v['t_game'] for v in terminals.values() if v),
                         **terminal})
    def failure_time(failure):
        return failure.get('t_game') if isinstance(failure.get('t_game'), (int, float)) else -1.
    first_failure = min(failures, key=failure_time) if failures else None
    numerical_met = problems.count == 0 and numeric_fraction >= TARGET_FRACTION
    return {
        'primary': {'target_fraction': TARGET_FRACTION, 'eligible_samples': eligible,
                    'matched_samples': matched_samples, 'numeric_match_fraction': numeric_fraction,
                    'score_fraction': fraction, 'hard_gate_failed': hard_gate,
                    'numerical_target_met': numerical_met, 'covered_event_target_met': covered_events_match,
                    'primary_target_met': fraction >= TARGET_FRACTION, 'components': primary,
                    'first_failure': first_failure},
        'coverage_complete': contacts['coverage_complete'],
        'target_met': contacts['coverage_complete'] and fraction >= TARGET_FRACTION,
        'contacts': contacts,
        'events': events, 'event_state_consistency': event_consistency.result(), 'terminal': terminal,
        'discrete': {**discrete_checks.result(), 'components': discrete_counts},
        'trace_validation': problems.result(),
        'window': {'horizon_game_seconds': horizon, 'interval_game_seconds': interval,
                   'first_scored_game_time': interval if eligible else None,
                   'last_scored_game_time': eligible * interval if eligible else None,
                   'initial_samples_excluded': {k: int(v['initial'] is not None) for k, v in traces.items()},
                   'terminal_samples_excluded': {k: v['excluded_terminal_rows'] for k, v in traces.items()},
                   'post_terminal_rows_rejected': {k: v['rejected_post_terminal_rows'] for k, v in traces.items()}},
        'secondary': {'diagnostic_only': True, 'relative_limit': RELATIVE_LIMIT,
                      'primary_target_met_first': fraction >= TARGET_FRACTION,
                      'absolute_floor_rule': 'max(primary absolute tolerance, .001 * reference magnitude)',
                      'position_reference': 'displacement from each part\'s initial PC position; shared reference origin',
                      'angle_reference': 'wrapped displacement from each circle\'s initial PC angle',
                      'matched_samples': relative_matches,
                      'numeric_match_fraction': relative_matches / eligible if eligible else 0.,
                      'components': secondary},
        'angular_velocity_diagnostics': {'has_primary_tolerance': False, 'components': omega},
        'head_velocity_measured': head_velocity,
    }


def score_report(report_path, runs=('candidate',)):
    """Read a harness report and its per-case traces; return a JSON-safe score."""
    report_path = Path(report_path).resolve()
    report = json.loads(report_path.read_text())
    interval = report['scheduler']['interval_game_seconds']
    cases = report['cases']
    if not cases:
        raise InvalidTrace('report has no cases')
    if 'case_count' in report and report['case_count'] != len(cases):
        raise InvalidTrace('declared case_count does not match the cases in the report')
    if not runs:
        raise InvalidTrace('at least one run must be selected')
    result = {
        'schema_version': 2, 'source_report': str(report_path), 'case_count': len(cases),
        'acceptance': {'priority': ['primary absolute tolerances and covered event identity/timing',
                                    'secondary .1% relative diagnostics'],
                       'target_fraction': TARGET_FRACTION, 'aggregation': 'minimum case score; no pooled acceptance',
                       'position_tolerance_m': POSITION_LIMIT_M, 'angle_tolerance_degrees': ANGLE_LIMIT_DEG,
                       'velocity_tolerance_m_per_real_second': VELOCITY_LIMIT_M_S,
                       'velocity_conversion_from_trace': GAME_SECONDS_PER_REAL_SECOND,
                       'vector_error': 'Euclidean xy distance',
                       'angle_error': 'shortest wrapped angular difference',
                       'rider_head_angles': 'inherit body orientation; no independent angle',
                       'event_interval': '((n-1)*dt, n*dt] using observed t_game; original timestamps retained'},
        'event_coverage': {'death': True, 'apple': True, 'finish': True, 'nonfatal_collision_contacts': False},
        'coverage_complete': False,
        'coverage_limitation': 'At least one trace lacks validated resolved-wheel contact instrumentation/data.',
        'runs': {},
    }
    for label in runs:
        scored = {}
        for name, case in cases.items():
            try:
                path = Path(case['runs'][label]['trace'])
                if not path.is_absolute():
                    path = report_path.parent / path
                data = json.loads(path.read_text())
                scored[name] = score_case(data, interval, case['horizon_game_seconds'])
            except (OSError, ValueError, KeyError, TypeError) as exc:
                scored[name] = {'primary': {'score_fraction': 0., 'numerical_target_met': False,
                                           'covered_event_target_met': False, 'primary_target_met': False,
                                           'first_failure': {'kind': 'unscorable_trace', 'detail': str(exc)}},
                                'coverage_complete': False, 'target_met': False}
        worst = min(scored, key=lambda key: scored[key]['primary']['score_fraction'])
        result['runs'][label] = {
            'worst_case': worst, 'worst_case_fraction': scored[worst]['primary']['score_fraction'],
            'numerical_target_met': all(c['primary']['numerical_target_met'] for c in scored.values()),
            'covered_event_target_met': all(c['primary']['covered_event_target_met'] for c in scored.values()),
            'primary_target_met': all(c['primary']['primary_target_met'] for c in scored.values()),
            'primary_passing_cases': sum(c['primary']['primary_target_met'] for c in scored.values()),
            'coverage_complete': all(c['coverage_complete'] for c in scored.values()),
            'target_met': all(c['target_met'] for c in scored.values()), 'cases': scored,
        }
    result['coverage_complete'] = all(run['coverage_complete'] for run in result['runs'].values())
    result['event_coverage']['nonfatal_collision_contacts'] = result['coverage_complete']
    if result['coverage_complete']: result['coverage_limitation'] = None
    result['target_met'] = all(run['target_met'] for run in result['runs'].values())
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('report', nargs='?', type=Path, default=DEFAULT_REPORT)
    parser.add_argument('--run', choices=('candidate', 'baseline', 'both'), default='candidate')
    parser.add_argument('--out', type=Path, help='score JSON path; default: report directory/fidelity-score.json')
    parser.add_argument('--require-target', action='store_true',
                        help='exit nonzero unless primary limits/events and complete collision coverage pass')
    args = parser.parse_args(argv)
    runs = ('baseline', 'candidate') if args.run == 'both' else (args.run,)
    try:
        result = score_report(args.report, runs)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    output = args.out or args.report.resolve().parent / 'fidelity-score.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'score': str(output.resolve()), 'case_count': result['case_count'],
                      'coverage_complete': result['coverage_complete'], 'target_met': result['target_met'],
                      'runs': {k: {key: value for key, value in run.items() if key != 'cases'}
                               for k, run in result['runs'].items()}}, indent=2))
    return int(args.require_target and not result['target_met'])


if __name__ == '__main__':
    raise SystemExit(main())
