"""Append independently measured iterations and reject unsupported success.

  python test/iteration_ledger.py --ledger build/iterations.json --iteration 1 \
      --change "describe concrete change" --fidelity FILE --benchmark FILE

A successful iteration requires strict99% fidelity and every benchmark case
passing fresh-presentation and submission-deadline checks. At least five distinct
measured source/ROM versions are required before the user goal is achieved.
"""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--ledger', required=True)
    ap.add_argument('--iteration', type=int, required=True)
    ap.add_argument('--change', required=True)
    ap.add_argument('--fidelity', required=True)
    ap.add_argument('--benchmark', required=True)
    a = ap.parse_args()
    path = Path(a.ledger)
    ledger = json.loads(path.read_text()) if path.exists() else {'iterations': []}
    f = json.loads(Path(a.fidelity).read_text())
    b = json.loads(Path(a.benchmark).read_text())
    protocol = hashlib.sha256(json.dumps({'levels': [r['level'] for r in b['runs']],
                          'script': b['script'], 'warmup': b['warmup_nmis_excluded']}, sort_keys=True).encode()).hexdigest()
    row = {'benchmark_protocol_sha256': protocol, 'iteration': a.iteration, 'change': a.change,
           'fidelity_path': str(Path(a.fidelity).resolve()), 'fidelity_artifact_sha256': sha(a.fidelity),
           'benchmark_path': str(Path(a.benchmark).resolve()), 'benchmark_artifact_sha256': sha(a.benchmark),
           'strict_fidelity': f['strict_fidelity'],
           'continuous_component_fractions': f['component_sample_pass_fractions'],
           'critical_event_failing_cases': f['critical_event_failing_cases'],
           'critical_failing_case_ids': [r['id'] for r in f['runs'] if not r['critical_events_match']],
           'pc_source_sha256': f['original_sources_sha256'], 'phys_spec_sha256': f['phys_spec_sha256'],
           'host_sha256': f['host_sha256'], 'corpus_sha256': f['corpus_sha256'],
           'rom_sha256': sorted(set(r['rom_sha256'] for r in b['runs'])),
           'benchmark_ok': b['ok'], 'benchmark_runs': b['runs']}
    if any(x['iteration'] == a.iteration for x in ledger['iterations']):
        raise ValueError('Iteration already recorded; preserve its historical evidence')
    if ledger['iterations'] and any(x['corpus_sha256'] != row['corpus_sha256'] for x in ledger['iterations']):
        raise ValueError('Corpus changed; iterations would not be comparable')
    previous = max(ledger['iterations'], key=lambda r: r['iteration']) if ledger['iterations'] else None
    if previous:
        if 'critical_failing_case_ids' in previous:
            old_bad = set(previous['critical_failing_case_ids'])
        else:
            old_fidelity = json.loads(Path(previous['fidelity_path']).read_text())
            old_bad = {r['id'] for r in old_fidelity['runs'] if not r['critical_events_match']}
        new_bad = set(row['critical_failing_case_ids'])
        row['critical_fixed_case_ids'] = sorted(old_bad-new_bad)
        row['critical_regressed_case_ids'] = sorted(new_bad-old_bad)
        row['preserves_previously_matching_critical_cases'] = not bool(new_bad-old_bad)
        old_rate = sum(r['missed_presentations'] for r in previous['benchmark_runs']) / max(1, sum(r['steady_nmis'] for r in previous['benchmark_runs']))
        new_rate = sum(r['missed_presentations'] for r in row['benchmark_runs']) / max(1, sum(r['steady_nmis'] for r in row['benchmark_runs']))
        old_work = max(r.get('frame_active_master_clocks', r['frame_work_master_clocks'])['max']
                       for r in previous['benchmark_runs'] if r['frame_work_master_clocks'])
        new_work = max(r.get('frame_active_master_clocks', r['frame_work_master_clocks'])['max']
                       for r in row['benchmark_runs'] if r['frame_work_master_clocks'])
        physics_better = (row['critical_event_failing_cases'] < previous['critical_event_failing_cases'] or
                          row['continuous_component_fractions']['all'] > previous['continuous_component_fractions']['all'] + 1e-12)
        physics_not_worse = (row['critical_event_failing_cases'] <= previous['critical_event_failing_cases'] and
                             row['continuous_component_fractions']['all'] >= previous['continuous_component_fractions']['all'] - 1e-12)
        runtime_better = new_rate < old_rate - 1e-12 or new_work < old_work
        row['measured_improvement'] = bool(physics_not_worse and (physics_better or runtime_better))
        row['improvement_evidence'] = {'old_miss_fraction': old_rate, 'new_miss_fraction': new_rate,
                                       'old_max_work': old_work, 'new_max_work': new_work,
                                       'physics_better': physics_better, 'physics_not_worse': physics_not_worse}
    else:
        row['measured_improvement'] = False  # Baseline is evidence, never an improving iteration.
    if ledger['iterations'] and any(r['benchmark_protocol_sha256'] != protocol for r in ledger['iterations']):
        raise ValueError('Benchmark protocol changed; iterations would not be comparable')
    ledger['iterations'].append(row)
    ledger['iterations'].sort(key=lambda x: x['iteration'])
    distinct = {(r['phys_spec_sha256'], tuple(r['rom_sha256'])) for r in ledger['iterations']}
    ledger['separately_measured_versions'] = len(distinct)
    improving = {(r['phys_spec_sha256'], tuple(r['rom_sha256'])) for r in ledger['iterations']
                 if r['iteration'] > 0 and r['measured_improvement']}
    ledger['separately_measured_improving_iterations'] = len(improving)
    ledger['goal_achieved'] = bool(len(improving) >= 5 and row['strict_fidelity'] >= .99 and row['benchmark_ok'])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2) + '\n')
    print('Recorded iteration%d; %d distinct measured versions; goal achieved=%s' %
          (a.iteration, len(distinct), ledger['goal_achieved']))
    return 0


if __name__ == '__main__':
    main()
