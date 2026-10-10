#!/usr/bin/env python3
"""Measure a candidate original-equation host kernel against frozen PC traces.

The candidate executable must accept physcheck's GEN LEVDUMP LEVEL SCRIPT
--trace-json arguments and emit its state in the PC fields of that JSON format.
No result here implies an SNES implementation or a performance pass.
"""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import shutil

from fidelity_check import ROOT, TOLERANCES, digest, measure


def combine(reference, candidate, engine='pc', stop_after_both=True):
    rows = []
    for step in range(max(len(reference), len(candidate))):
        ref = copy.deepcopy(reference[min(step, len(reference)-1)])
        cand = candidate[min(step, len(candidate)-1)]
        ref['step'] = step
        for suffix in ['', '_event', '_stopped', '_discrete', '_objects', '_apple_object']:
            ref['snes'+suffix] = cand[engine+suffix]
        if step >= len(candidate):
            ref['snes_event'] = 0; ref['snes_apple_object'] = -1
        if step >= len(reference):
            ref['pc_event'] = 0; ref['pc_apple_object'] = -1
        ref.pop('snes_raw', None)
        rows.append(ref)
        if stop_after_both and ref['pc_stopped'] and ref['snes_stopped']:
            break
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--host', type=Path, required=True)
    ap.add_argument('--source', type=Path, action='append', required=True, help='actual kernel source inputs, repeatable')
    ap.add_argument('--baseline', type=Path, default=ROOT/'build/fidelity-baseline')
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--gen', type=Path, default=ROOT/'build/gen')
    ap.add_argument('--levdump', type=Path, default=ROOT/'build/host/levdump')
    ap.add_argument('--candidate-engine', choices=['pc', 'snes'], default='pc')
    ap.add_argument('--require-target', action='store_true')
    ap.add_argument('--reuse-comparison', type=Path, help='re-evaluate frozen comparison traces without rerunning a candidate')
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    corpus_path = a.baseline/'corpus.json'
    corpus = json.loads(corpus_path.read_text())
    baseline = json.loads((a.baseline/'fidelity.json').read_text())
    source_hashes = {str(p.resolve()): digest(p) for p in a.source}
    host_hash = digest(a.host)
    snapshot = a.out/'candidate-host'
    shutil.copy2(a.host, snapshot)
    runs, legacy_runs = [], []
    for case in corpus:
        if a.reuse_comparison:
            with gzip.open(a.reuse_comparison/(case['id']+'.jsonl.gz'), 'rt') as f:
                candidate = [json.loads(line) for line in f]
            engine = 'snes'
            (a.out/(case['id']+'.stderr.txt')).write_bytes((a.reuse_comparison/(case['id']+'.stderr.txt')).read_bytes())
        else:
            result = subprocess.run([str(snapshot.resolve()), str(a.gen), str(a.levdump), str(case['level']), case['script'], '--trace-json'],
                                    capture_output=True, text=True, timeout=120)
            (a.out/(case['id']+'.stderr.txt')).write_text(result.stderr)
            if result.returncode:
                (a.out/(case['id']+'.failed.stdout.txt')).write_text(result.stdout)
                raise RuntimeError('Candidate failed in '+case['id']+' (exit '+str(result.returncode)+'); '+
                                   'see '+str(a.out/(case['id']+'.stderr.txt')))
            candidate = [json.loads(line) for line in result.stdout.splitlines()]
            engine = a.candidate_engine
        if not candidate or any(row['step'] != i for i, row in enumerate(candidate)):
            raise ValueError('Missing/out-of-order candidate steps in '+case['id'])
        with gzip.open(a.baseline/(case['id']+'.jsonl.gz'), 'rt') as f:
            reference = [json.loads(s) for s in f]
        if len(candidate) < len(reference) and not candidate[-1][engine+'_stopped']:
            raise ValueError('Candidate truncated before terminal state in '+case['id'])
        rows = combine(reference, candidate, engine)
        legacy_rows = combine(reference, candidate, engine, stop_after_both=False)
        trace = a.out/(case['id']+'.jsonl.gz')
        with gzip.open(trace, 'wt') as f:
            f.write(''.join(json.dumps(r, separators=(',', ':'))+'\n' for r in rows))
        runs.append(measure(case, rows, trace))
        legacy_runs.append(measure(case, legacy_rows, trace))
    n = sum(r['samples'] for r in runs)
    components = {k:sum(r['samples']*r['component_pass_fractions'][k] for r in runs)/n for k in runs[0]['component_pass_fractions']}
    report = {'schema': 1, 'experiment': 'Host original-equation kernel fidelity; not an SNES implementation or performance result',
              'strict_fidelity': min(r['terminal_gated_fidelity'] for r in runs), 'target': .99,
              'critical_event_failing_cases': sum(not r['critical_events_match'] for r in runs),
              'cases': len(runs), 'samples': n, 'component_sample_pass_fractions': components,
              'minimum_case_component_fractions': {k:min(r['component_pass_fractions'][k] for r in runs) for k in components},
              'tolerances': TOLERANCES, 'schedule': baseline['schedule'],
              'host_sha256': host_hash,
              'comparison_horizon': 'through first sample where both compared engines stop, inclusive; later duplicate frozen samples excluded',
              'legacy_duplicate_frozen_extension': {'strict_fidelity': min(r['terminal_gated_fidelity'] for r in legacy_runs),
                   'samples': sum(r['samples'] for r in legacy_runs), 'reference': str(a.reuse_comparison) if a.reuse_comparison else None}, 'kernel_sources_sha256': source_hashes,
              'phys_spec_sha256': hashlib.sha256(json.dumps(source_hashes, sort_keys=True).encode()).hexdigest(),
              'original_sources_sha256': baseline['original_sources_sha256'],
              'corpus_sha256': digest(corpus_path), 'runs': runs}
    report['target_met'] = report['strict_fidelity'] >= .99
    (a.out/'fidelity.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f"Strict {100*report['strict_fidelity']:.3f}%; critical failures {report['critical_event_failing_cases']}/{len(runs)}; all-fields {100*components['all']:.3f}%")
    return int(a.require_target and not report['target_met'])


if __name__ == '__main__':
    raise SystemExit(main())
