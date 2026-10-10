"""Run the fixed fidelity corpus's two seeded scripts on every level.

Uses the sustained benchmark's fresh-NMI, submission-deadline and DMA gates.
Short terminal cases retain observed failures but do not claim sustained
coverage. Every case keeps its ROM hash, script and raw timing/state evidence.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import fidelity_check

ROOT = Path(__file__).resolve().parent.parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--rom', required=True)
    ap.add_argument('--corpus', default='build/fidelity-baseline/corpus.json')
    ap.add_argument('--out', required=True)
    ap.add_argument('--workers', type=int, default=2)
    args = ap.parse_args()
    rom = Path(args.rom).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    corpus = Path(args.corpus).resolve()
    cases = [c for c in json.loads(corpus.read_text()) if c['kind'] == 'seeded_normal']
    if len(cases) != 108 or any(sum(c['level'] == lv for c in cases) != 2 for lv in range(54)):
        raise ValueError('Expected two fixed seeded cases on each of 54 levels')
    for c in cases:
        if c['script'] != fidelity_check.seeded_script(c['seed'], 30):
            raise ValueError('Fixed corpus does not match its 30-second seeded inputs')
    rom_hash = digest(rom)
    (out / 'corpus.json').write_text(json.dumps(cases, indent=2) + '\n')

    def run(case):
        folder = out / case['id']
        folder.mkdir(exist_ok=True)
        command = [sys.executable, str(ROOT / 'test/benchmark_check.py'), '--rom', str(rom),
                   '--levels', str(case['level']), '--script', case['script'], '--out', str(folder)]
        try:
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=360)
            (folder / 'runner.txt').write_text(result.stdout + result.stderr)
            report = json.loads((folder / 'benchmark.json').read_text())
            row = report['runs'][0]
            if row['rom_sha256'] != rom_hash:
                raise ValueError('ROM changed during corpus evaluation')
            latency = row['submission_to_nmi_master_clocks']
            sample = json.loads((folder / ('level%02d' % case['level']) / 'summary.json').read_text())
            issues = []
            if row['missed_presentations']:
                issues.append('missed_NMI')
            if latency and latency['max'] > row['frame_budget_master_clocks']:
                issues.append('submission_deadline')
            for metric in ('reused_submissions', 'unmatched_presentations', 'overwritten_pending_submissions'):
                if row[metric]:
                    issues.append(metric)
            for metric in ('physics_dropped_steps', 'dma_overruns', 'dma_budget_overruns'):
                if sample[metric] not in (None, 0):
                    issues.append(metric)
            short = not row['sufficient_duration']
            status = 'SHORT_FAIL' if short and issues else 'SHORT' if short else 'FAIL' if issues else 'PASS'
            return {**case, 'status': status, 'observed_issues': issues,
                    'sustained_coverage_sufficient': not short, 'benchmark': row,
                    'outcome': sample['outcome'], 'artifact': str(folder / 'benchmark.json')}
        except Exception as e:
            return {**case, 'status': 'ERROR', 'error': str(e)}

    results = []

    def save():
        rows = sorted(results, key=lambda c: c['id'])
        report = {'rom': str(rom), 'rom_sha256': rom_hash, 'corpus_sha256': digest(corpus),
                  'planned_cases': len(cases), 'completed_cases': len(rows),
                  'complete': len(rows) == len(cases),
                  'all_sufficient_cases_pass': not any(r['status'] in ('FAIL', 'SHORT_FAIL', 'ERROR') for r in rows),
                  'sustained_pass_cases': sum(r['status'] == 'PASS' for r in rows),
                  'short_cases': sum(r['status'].startswith('SHORT') for r in rows),
                  'failing_cases': [r['id'] for r in rows if r['status'] in ('FAIL', 'SHORT_FAIL', 'ERROR')],
                  'runs': rows}
        temporary = out / 'summary.tmp.json'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(out / 'summary.json')
        return report

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run, case): case for case in cases}
        for future in as_completed(futures):
            row = future.result()
            results.append(row)
            report = save()
            b = row.get('benchmark', {})
            print('%s: %s; %d steps, %d/%d missed; %s (%d/108)' %
                  (row['id'], row['status'], b.get('physics_steps', 0), b.get('missed_presentations', 0),
                   b.get('steady_nmis', 0), ','.join(row.get('observed_issues', [])) or row.get('error', ''), len(results)), flush=True)
    if digest(rom) != rom_hash:
        raise ValueError('ROM changed after corpus evaluation')
    print('Complete: %d sustained passes, %d short cases, %d failures' %
          (report['sustained_pass_cases'], report['short_cases'], len(report['failing_cases'])))
    return 0 if report['all_sufficient_cases_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
