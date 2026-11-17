#!/usr/bin/env python3
"""Acceptance semantics: boundaries, units, identity, timing and trace integrity."""
import contextlib
import copy
import io
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

import score_pc_fidelity as score

DT = score.GAME_SECONDS_PER_REAL_SECOND / 30.


def state(t, **updates):
    row = {'t_game': t, 'position': {p: [0., 0.] for p in score.PARTS},
           'velocity': {p: [0., 0.] for p in score.PARTS},
           'angles': {p: 0. for p in score.CIRCLES},
           'angular_velocity': {p: 0. for p in score.CIRCLES},
           'dead': False, 'finished': False, 'turned': 1,
           'gravity': 1, 'gravity_direction': 'down', 'apples_collected': 0}
    row.update(updates)
    return row


def fixture(samples=3):
    reference = [state(i * DT) for i in range(samples + 1)]
    return {'pc': reference, 'gbc': copy.deepcopy(reference), 'events': {'pc': [], 'gbc': []},
            'horizon_game_seconds': samples * DT}


def result(data):
    return score.score_case(data, DT)


def terminal_fixture():
    data = fixture(5)
    data['pc'] = data['pc'][:3] + [state(2.3 * DT, dead=True)]
    data['gbc'] = data['gbc'][:3] + [state(3 * DT, dead=True)]
    data['events'] = {
        'pc': [{'type': 'death', 'object': None, 't_game': 2.3 * DT, 'original_event_time': 2 * DT}],
        'gbc': [{'type': 'death', 'object': None, 't_game': 3 * DT}],
    }
    return data


def sync_contact_states(data, engine):
    for index, row in enumerate(data[engine]):
        modes = [None, None]
        for event in data['contact_events'][engine]:
            if event['t_game'] <= row['t_game'] + score.TIME_EPSILON:
                modes[event['wheel']] = event['count']
        row['wheel_contacts'] = {f'wheel{i}': n for i, n in enumerate(modes)}
        row['contact_observations'] = [index * (3 if engine == 'pc' else 1)] * 2


def contact_fixture():
    data = fixture(4)
    provenance = {'schema': score.CONTACT_SCHEMA, 'observational_only': True,
                  'original_source_sha256': 'a' * 64, 'compiled_source_sha256': 'b' * 64,
                  'library_sha256': 'c' * 64, 'state_identity': {'match': 'bit exact', 'checkpoints': 121}}
    data['contact_instrumentation'] = {k: copy.deepcopy(provenance) for k in ('pc', 'gbc')}
    data['contact_events'] = {}
    for engine in ('pc', 'gbc'):
        first, second = (.25 * DT, 1.5 * DT) if engine == 'pc' else (DT, 2 * DT)
        data['contact_events'][engine] = [
            {'wheel': 0, 'from': None, 'count': 0, 't_game': first},
            {'wheel': 1, 'from': None, 'count': 0, 't_game': first},
            {'wheel': 0, 'from': 0, 'count': 1, 't_game': second},
        ]
        sync_contact_states(data, engine)
    return data


class FidelityScoreTests(unittest.TestCase):
    def test_resolved_contacts_match_in_same_interval_and_certify_coverage(self):
        actual = result(contact_fixture())
        self.assertTrue(actual['coverage_complete'])
        self.assertTrue(actual['contacts']['matches'])
        self.assertTrue(actual['target_met'])
        self.assertEqual(len(actual['contacts']['events']), 3)

    def test_contact_wheel_count_order_and_interval_mismatches_hard_fail(self):
        for change in ('wheel', 'count', 'order', 'interval'):
            with self.subTest(change=change):
                data = contact_fixture()
                events = data['contact_events']['gbc']
                if change == 'wheel': events[-1]['wheel'] = 1
                elif change == 'count': events[-1]['count'] = 2
                elif change == 'order': events[0], events[1] = events[1], events[0]
                else: events[-1]['t_game'] = 2 * DT + 1e-6
                sync_contact_states(data, 'gbc')
                actual = result(data)
                self.assertTrue(actual['coverage_complete'])  # Complete observation can reveal a mismatch.
                self.assertFalse(actual['contacts']['matches'])
                self.assertEqual(actual['primary']['numeric_match_fraction'], 1.)
                self.assertEqual(actual['primary']['score_fraction'], 0.)

    def test_missing_contact_proof_stream_modes_or_observations_cannot_certify(self):
        for missing in ('engine', 'proof', 'hash', 'stream', 'mode', 'observation'):
            with self.subTest(missing=missing):
                data = contact_fixture()
                if missing == 'engine': del data['contact_instrumentation']['gbc']
                elif missing == 'proof': del data['contact_instrumentation']['gbc']['state_identity']
                elif missing == 'hash': data['contact_instrumentation']['gbc']['compiled_source_sha256'] = 'bad'
                elif missing == 'stream': del data['contact_events']['gbc']
                elif missing == 'mode': del data['gbc'][2]['wheel_contacts']['wheel1']
                else: data['gbc'][2]['contact_observations'] = [1, 1]
                actual = result(data)
                self.assertFalse(actual['coverage_complete'])
                self.assertFalse(actual['target_met'])
                self.assertEqual(actual['primary']['score_fraction'], 0.)

    def test_contact_stream_cannot_disagree_with_modes_or_repeat_nontransition(self):
        for change in ('state', 'previous_count', 'repeat', 'after_observed_end'):
            data = contact_fixture()
            if change == 'state': data['gbc'][2]['wheel_contacts']['wheel0'] = 0
            elif change == 'previous_count': data['contact_events']['gbc'][-1]['from'] = 2
            elif change == 'repeat':
                data['contact_events']['gbc'].append({'wheel': 0, 'from': 1, 'count': 1, 't_game': 3 * DT})
            else: data['contact_events']['gbc'][-1]['t_game'] = 5 * DT
            self.assertFalse(result(data)['coverage_complete'])

    def test_report_certifies_only_when_every_case_has_complete_contact_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = {'scheduler': {'interval_game_seconds': DT}, 'cases': {}}
            for name in ('one', 'two'):
                (root / (name + '.json')).write_text(json.dumps(contact_fixture()))
                report['cases'][name] = {'horizon_game_seconds': 4 * DT,
                                        'runs': {'candidate': {'trace': name + '.json'}}}
            path = root / 'report.json'; path.write_text(json.dumps(report))
            actual = score.score_report(path)
            self.assertTrue(actual['coverage_complete'])
            self.assertTrue(actual['target_met'])
            self.assertTrue(actual['event_coverage']['nonfatal_collision_contacts'])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(score.main([str(path), '--require-target']), 0)
            (root / 'two.json').write_text(json.dumps(fixture(4)))
            actual = score.score_report(path)
            self.assertFalse(actual['coverage_complete'])
            self.assertFalse(actual['target_met'])

    @unittest.skipUnless(shutil.which('cc') and shutil.which('c++'), 'HOST C/C++ compilers required')
    def test_actual_contact_hooks_preserve_all_pc_and_host_state_bits(self):
        import compare_pc_physics as comparison

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            constants_path = root / 'riding_constants.h'
            subprocess.run([sys.executable, str(comparison.BASE / 'tools/riding_constants.py'),
                            str(constants_path), '30', 'exponential'], check=True)
            sources = [comparison.ROOT / 'src/BEALLIT.CPP', comparison.BASE / 'src/physics_contacts.c']
            before = [comparison.sha256(path) for path in sources]
            library, gen, _ = comparison.build_fixtures(root, constants_path, comparison.BASE / 'src',
                                                       'fixture', contacts=True)
            host = comparison.Gbc(library, comparison.constants(constants_path))
            plain_host = comparison.Gbc(comparison.build_contact_control(library), host.settings)
            pc = comparison.Pc(comparison.build_pc(root, contacts=True))
            plain_pc = comparison.Pc(comparison.build_contact_control(pc.library))
            self.assertFalse(plain_pc.contacts)
            self.assertFalse(plain_host.contacts)
            inputs = [1] * 40 + [2] * 40 + [4] + [0] * 39
            proof = comparison.validate_contact_identity(pc, plain_pc, host, plain_host,
                gen / 'fixture0.txt', 0, inputs, start=(-.85, .4))
            self.assertEqual(proof['match'], 'bit exact')
            self.assertEqual(proof['checkpoints'], {'pc': 121, 'gbc': 121})
            self.assertEqual(before, [comparison.sha256(path) for path in sources])
            self.assertTrue(any(e['count'] > 0 for e in pc.contact_events()))
            self.assertTrue(any(e['count'] > 0 for e in host.contact_events))
            self.assertTrue(any(abs(e['t_game'] / host.settings['dt'] - round(e['t_game'] / host.settings['dt'])) > 1e-6
                                for e in pc.contact_events()))
            self.assertTrue(all(abs(e['t_game'] / host.settings['dt'] - round(e['t_game'] / host.settings['dt'])) < 1e-8
                                for e in host.contact_events))
            trace = comparison.compare_case(pc, host, gen / 'fixture0.txt', 0, inputs, start=(-.85, .4))
            self.assertTrue(score.score_case(trace, host.settings['dt'])['coverage_complete'])

    def test_snapshot_adapters_expose_all_rotations_and_normalize_collected_apples(self):
        import compare_pc_physics as comparison

        host = comparison.Gbc.__new__(comparison.Gbc)
        host.b, host.p = comparison.Bike(), comparison.Public()
        host.settings = {'angle': 4096, 'velocity_scale': 100., 'omega_scale': 10.}
        host.t, host.dead, host.finished = 0., False, False
        host.b.gravity = 2
        host.objects = [(2, 0, 0, 0, index) for index in range(3)]
        host.apples = 1  # Three initial apples, one still remaining: two collected.
        for index, circle in enumerate((host.b.body, *host.b.wheel)):
            circle.alfa = (index + 1) * 1024
            circle.omega = (index + 1) * 10

        def pc_get(values, flags):
            for index in range(3):
                values[index * 6 + 4] = (index + 1) * math.pi / 2
                values[index * 6 + 5] = index + 1
            flags[3], flags[4] = 2, 2  # PC counter is already collected, not remaining.

        pc = comparison.Pc.__new__(comparison.Pc)
        pc.f, pc.t = SimpleNamespace(compare_pc_get=pc_get), 0.
        actual_host, actual_pc = host.snapshot(), pc.snapshot()
        self.assertEqual(actual_host['apples_collected'], 2)
        self.assertEqual(actual_host['apples_collected'], actual_pc['apples_collected'])
        self.assertEqual(actual_host['gravity_direction'], 'left')
        self.assertEqual(actual_host['gravity_direction'], actual_pc['gravity_direction'])
        for field in ('angles', 'angular_velocity'):
            self.assertEqual(set(actual_host[field]), set(score.CIRCLES))
            self.assertEqual(actual_host[field], actual_pc[field])

    def test_identical_live_samples_exclude_initial_and_do_not_certify_missing_contacts(self):
        data = fixture(3)
        # An initial-position disagreement is not an earned or failed live sample.
        data['gbc'][0]['position']['body'][0] = 100.
        actual = result(data)
        self.assertEqual(actual['primary']['eligible_samples'], 3)
        self.assertEqual(actual['primary']['matched_samples'], 3)
        self.assertTrue(actual['primary']['primary_target_met'])
        self.assertFalse(actual['coverage_complete'])
        self.assertFalse(actual['target_met'])

    def test_inclusive_physical_boundaries_and_real_second_velocity_conversion(self):
        data = fixture(1)
        candidate = data['gbc'][1]
        for part in score.PARTS:
            candidate['position'][part] = [.006, .008]  # Euclidean norm .01 m.
            candidate['velocity'][part][0] = .01 / score.GAME_SECONDS_PER_REAL_SECOND
        for part in score.CIRCLES:
            candidate['angles'][part] = math.radians(.1)
        actual = result(data)
        self.assertTrue(actual['primary']['primary_target_met'])
        self.assertAlmostEqual(actual['primary']['components']['velocity']['body']['max_error'], .01)
        candidate['velocity']['rider'][0] += .000001
        self.assertFalse(result(data)['primary']['primary_target_met'])

    def test_every_part_and_both_wheel_angles_can_independently_fail(self):
        for field, parts, error in (('position', score.PARTS, .010001),
                                   ('velocity', score.PARTS, .010001 / score.GAME_SECONDS_PER_REAL_SECOND),
                                   ('angles', score.CIRCLES, math.radians(.100001))):
            for part in parts:
                with self.subTest(field=field, part=part):
                    data = fixture(1)
                    if field == 'angles':
                        data['gbc'][1][field][part] = error
                    else:
                        data['gbc'][1][field][part][0] = error
                    actual = result(data)
                    self.assertEqual(actual['primary']['matched_samples'], 0)
                    self.assertEqual(actual['primary']['first_failure']['component'], f'{field}.{part}')

    def test_position_and_velocity_use_vector_distance(self):
        for field, scale in (('position', 1.), ('velocity', score.GAME_SECONDS_PER_REAL_SECOND)):
            data = fixture(1)
            data['gbc'][1][field]['body'] = [.008 / scale, .008 / scale]
            self.assertFalse(result(data)['primary']['primary_target_met'])

    def test_angles_wrap_across_pi_and_angular_velocity_has_no_primary_limit(self):
        data = fixture(1)
        data['pc'][1]['angles']['wheel1'] = math.radians(179.97)
        data['gbc'][1]['angles']['wheel1'] = math.radians(-179.97)
        data['gbc'][1]['angular_velocity']['wheel0'] = 1e6
        actual = result(data)
        self.assertTrue(actual['primary']['primary_target_met'])
        self.assertAlmostEqual(actual['primary']['components']['angles']['wheel1']['max_error'], .06)
        self.assertAlmostEqual(actual['angular_velocity_diagnostics']['components']['wheel0']['max_error'], 436800.)
        self.assertFalse(actual['angular_velocity_diagnostics']['has_primary_tolerance'])

    def test_exact_999_of_1000_boundary(self):
        data = fixture(1000)
        data['gbc'][1]['position']['head'][0] = 1.
        actual = result(data)
        self.assertEqual(actual['primary']['score_fraction'], .999)
        self.assertTrue(actual['primary']['primary_target_met'])
        data['gbc'][2]['position']['head'][0] = 1.
        self.assertFalse(result(data)['primary']['primary_target_met'])

    def test_missing_wheel_angle_fails_even_if_only_one_sample_of_1000(self):
        data = fixture(1000)
        del data['gbc'][1]['angles']['wheel0']
        actual = result(data)
        self.assertEqual(actual['primary']['numeric_match_fraction'], .999)
        self.assertEqual(actual['primary']['score_fraction'], 0.)
        self.assertFalse(actual['primary']['numerical_target_met'])
        self.assertEqual(actual['primary']['components']['angles']['wheel0']['missing_samples'], 1)

    def test_head_velocity_is_optional_only_when_absent_from_both_traces(self):
        data = fixture(2)
        for trace in (data['pc'], data['gbc']):
            for row in trace:
                del row['velocity']['head']
        self.assertTrue(result(data)['primary']['primary_target_met'])
        self.assertFalse(result(data)['head_velocity_measured'])
        data['pc'][1]['velocity']['head'] = [0., 0.]
        self.assertEqual(result(data)['primary']['score_fraction'], 0.)

    def test_same_terminal_interval_allows_different_exact_substep_times(self):
        actual = result(terminal_fixture())
        self.assertEqual(actual['primary']['eligible_samples'], 2)
        self.assertEqual(actual['primary']['matched_samples'], 2)
        self.assertTrue(actual['primary']['primary_target_met'])
        event = actual['events']['events'][0]
        self.assertTrue(event['same_interval'])
        self.assertEqual(event['pc']['original_event_time'], 2 * DT)
        self.assertEqual(event['pc']['t_game'], 2.3 * DT)
        self.assertNotEqual(event['signed_game_time_delta'], 0.)

    def test_event_interval_is_right_closed_at_frame_boundary(self):
        self.assertEqual(score.sample_interval(3 * DT, DT), 3)
        self.assertEqual(score.sample_interval(3 * DT + 1e-6, DT), 4)
        data = terminal_fixture()
        data['events']['gbc'][0]['t_game'] = 3 * DT + 1e-6
        actual = result(data)
        self.assertFalse(actual['events']['matches'])
        self.assertEqual(actual['primary']['score_fraction'], 0.)

    def test_event_object_and_sequence_mismatch_zero_the_case(self):
        for alteration in ('object', 'sequence', 'missing'):
            with self.subTest(alteration=alteration):
                data = fixture(3)
                events = [{'type': 'apple', 'object': i, 't_game': (i + 1) * DT} for i in range(2)]
                data['events'] = {'pc': copy.deepcopy(events), 'gbc': copy.deepcopy(events)}
                for trace in (data['pc'], data['gbc']):
                    for i, row in enumerate(trace):
                        row['apples_collected'] = min(i, 2)
                if alteration == 'object':
                    data['events']['gbc'][0]['object'] = 100
                elif alteration == 'sequence':
                    data['events']['gbc'][0]['object'], data['events']['gbc'][1]['object'] = 1, 0
                else:
                    data['events']['gbc'].pop()
                actual = result(data)
                self.assertEqual(actual['primary']['numeric_match_fraction'], 1.)
                self.assertEqual(actual['primary']['score_fraction'], 0.)
                self.assertFalse(actual['primary']['covered_event_target_met'])

    def test_different_terminal_kind_or_interval_zero_the_case(self):
        for change in ('kind', 'interval'):
            data = terminal_fixture()
            if change == 'kind':
                data['gbc'][-1].update(dead=False, finished=True)
                data['events']['gbc'][0]['type'] = 'finish'
            else:
                data['gbc'][-1]['t_game'] = 4 * DT
                data['events']['gbc'][0]['t_game'] = 4 * DT
            actual = result(data)
            self.assertFalse(actual['terminal']['matches'])
            self.assertEqual(actual['primary']['score_fraction'], 0.)

    def test_discrete_mismatch_hard_fails_even_when_numerical_samples_match(self):
        for field, value in (('turned', 0), ('gravity_direction', 'up'), ('apples_collected', 1)):
            data = fixture(3)
            data['gbc'][2][field] = value
            if field == 'gravity_direction':
                data['gbc'][2]['gravity'] = 0
            actual = result(data)
            self.assertEqual(actual['primary']['numeric_match_fraction'], 1.)
            self.assertEqual(actual['primary']['score_fraction'], 0.)
            self.assertEqual(actual['discrete']['components'][field]['mismatches'], 1)

    def test_short_candidate_does_not_shrink_reference_window_or_earn_padding_matches(self):
        data = fixture(1000)
        data['gbc'].pop()
        actual = result(data)
        self.assertEqual(actual['primary']['eligible_samples'], 1000)
        self.assertEqual(actual['primary']['matched_samples'], 999)
        self.assertEqual(actual['primary']['score_fraction'], 0.)
        self.assertEqual(actual['primary']['components']['position']['head']['missing_samples'], 1)

    def test_early_candidate_terminal_does_not_shrink_reference_window(self):
        data = fixture(5)
        data['gbc'] = data['gbc'][:3]
        data['gbc'][-1]['dead'] = True
        data['events']['gbc'] = [{'type': 'death', 'object': None, 't_game': 2 * DT}]
        actual = result(data)
        self.assertEqual(actual['primary']['eligible_samples'], 5)
        self.assertEqual(actual['primary']['matched_samples'], 1)
        self.assertEqual(actual['primary']['score_fraction'], 0.)

    def test_frozen_terminal_padding_is_rejected_and_never_counted(self):
        for advance_timestamps in (False, True):
            data = terminal_fixture()
            last = data['gbc'][-1]
            for i in range(100):
                padded = copy.deepcopy(last)
                if advance_timestamps:
                    padded['t_game'] += (i + 1) * DT
                data['gbc'].append(padded)
            actual = result(data)
            self.assertEqual(actual['primary']['eligible_samples'], 2)
            self.assertEqual(actual['primary']['matched_samples'], 2)
            self.assertEqual(actual['primary']['score_fraction'], 0.)
            self.assertEqual(actual['window']['post_terminal_rows_rejected']['gbc'], 100)

    def test_misaligned_duplicate_and_missing_reference_times_fail(self):
        for mode in ('misaligned', 'duplicate', 'missing_reference'):
            data = fixture(3)
            if mode == 'misaligned':
                data['gbc'][1]['t_game'] += DT / 4
            elif mode == 'duplicate':
                data['gbc'].insert(2, copy.deepcopy(data['gbc'][1]))
            else:
                data['pc'].pop(2)
            self.assertEqual(result(data)['primary']['score_fraction'], 0.)

    def test_relative_position_is_origin_independent_and_floor_is_explicit(self):
        data = fixture(1)
        data['pc'][1]['position']['body'][0] = 20.
        data['gbc'][1]['position']['body'][0] = 20.015
        before = result(data)
        for engine in ('pc', 'gbc'):
            for row in data[engine]:
                for part in score.PARTS:
                    row['position'][part][0] += 100000.
        after = result(data)
        first = before['secondary']['components']['position']['body']
        shifted = after['secondary']['components']['position']['body']
        self.assertAlmostEqual(first['max_effective_relative_error'], shifted['max_effective_relative_error'])
        self.assertEqual(first['floor_applied_samples'], 0)
        self.assertEqual(first['absolute_floor'], .01)
        self.assertEqual(before['secondary']['numeric_match_fraction'], 1.)
        self.assertFalse(before['primary']['primary_target_met'])
        zero = result(fixture(1))['secondary']['components']['position']['body']
        self.assertEqual(zero['floor_applied_samples'], 1)
        self.assertEqual(zero['max_effective_relative_error'], 0.)

    def test_report_uses_worst_case_not_easy_case_pool_and_cli_rejects_missing_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = {'scheduler': {'interval_game_seconds': DT}, 'cases': {}}
            for name, samples in (('easy', 1000), ('hard', 1)):
                data = fixture(samples)
                if name == 'hard':
                    data['gbc'][1]['position']['body'][0] = 1.
                (root / (name + '.json')).write_text(json.dumps(data))
                report['cases'][name] = {'horizon_game_seconds': samples * DT,
                                         'runs': {'candidate': {'trace': name + '.json'}}}
            path = root / 'report.json'
            path.write_text(json.dumps(report))
            actual = score.score_report(path)['runs']['candidate']
            self.assertEqual(actual['worst_case'], 'hard')
            self.assertEqual(actual['worst_case_fraction'], 0.)
            self.assertEqual(actual['primary_passing_cases'], 1)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(score.main([str(path), '--require-target']), 1)
            # Even a perfect numerical/event result cannot certify missing contacts.
            del report['cases']['hard']
            path.write_text(json.dumps(report))
            self.assertTrue(score.score_report(path)['runs']['candidate']['primary_target_met'])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(score.main([str(path), '--require-target']), 1)
                self.assertEqual(score.main([str(path)]), 0)

    def test_missing_angle_legacy_report_and_absent_trace_fail_closed(self):
        data = fixture(2)
        for engine in ('pc', 'gbc'):
            for row in data[engine]:
                del row['angles']
        actual = result(data)
        self.assertEqual(actual['primary']['score_fraction'], 0.)
        self.assertEqual(actual['primary']['components']['angles']['wheel1']['missing_samples'], 2)
        data['gbc'] = []
        self.assertEqual(result(data)['primary']['score_fraction'], 0.)


if __name__ == '__main__':
    unittest.main()
