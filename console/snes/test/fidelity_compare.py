#!/usr/bin/env python3
"""Compare fixed-corpus fidelity measurements, including individual regressions."""
import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('reference', type=Path)
    ap.add_argument('candidates', nargs='+', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--require-preservation', action='store_true', help='fail if any previously matching critical case regresses')
    a = ap.parse_args()
    base = json.loads(a.reference.read_text())
    old = {r['id']: r for r in base['runs']}
    results = []
    for path in a.candidates:
        candidate = json.loads(path.read_text())
        if candidate['corpus_sha256'] != base['corpus_sha256']:
            raise ValueError(f'Corpus changed: {path}')
        new = {r['id']: r for r in candidate['runs']}
        if old.keys() != new.keys() or candidate['tolerances'] != base['tolerances'] or candidate['schedule'] != base['schedule']:
            raise ValueError(f'Measurement protocol changed: {path}')
        fixes = [k for k in old if not old[k]['critical_events_match'] and new[k]['critical_events_match']]
        regressions = [k for k in old if old[k]['critical_events_match'] and not new[k]['critical_events_match']]
        results.append({'artifact': str(path.resolve()), 'source_sha256': candidate['phys_spec_sha256'],
                        'strict_fidelity': candidate['strict_fidelity'], 'critical_failures': candidate['critical_event_failing_cases'],
                        'critical_fixed_cases': fixes, 'critical_regressed_cases': regressions,
                        'preserves_previously_matching_critical_cases': not regressions,
                        'component_pass_fractions': candidate['component_sample_pass_fractions'],
                        'component_deltas': {k: v-base['component_sample_pass_fractions'][k]
                                             for k, v in candidate['component_sample_pass_fractions'].items()},
                        'sample_count': candidate['samples'],
                        'case_all_fields_deltas': {k: new[k]['component_pass_fractions']['all']-old[k]['component_pass_fractions']['all'] for k in old}})
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps({'reference': str(a.reference.resolve()), 'corpus_sha256': base['corpus_sha256'],
                                 'note': 'Aggregate component denominators include samples until both engines terminate; per-case and strict terminal gates remain authoritative.',
                                 'candidates': results}, indent=2)+'\n')
    for r in results:
        print(f"{r['artifact']}: critical failures {r['critical_failures']}; fixed {len(r['critical_fixed_cases'])}, newly failing {len(r['critical_regressed_cases'])}; all-fields {100*r['component_pass_fractions']['all']:.3f}%")
    return int(a.require_preservation and any(r['critical_regressed_cases'] for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
