"""Aggregate solver-only integer kernel counters retained by strict comparison."""
import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('fidelity', type=Path)
    ap.add_argument('--out', type=Path)
    ap.add_argument('--trig-kernel', choices=('q48-cubic','native-horner'), default='q48-cubic')
    args = ap.parse_args()
    measured = json.loads((args.fidelity / 'fidelity.json').read_text())
    rows = []
    for case in measured['runs']:
        phases = {}
        steps = 0
        for line in (args.fidelity / (case['id'] + '.stderr.txt')).read_text().splitlines():
            if line.startswith('WIDE_STATS '):
                stats = json.loads(line[len('WIDE_STATS '):])
                phases[stats['phase']] = stats
            elif line.startswith('WIDE_STEPS '):
                steps = int(line.split()[1])
        if not steps or 'simulation' not in phases:
            raise ValueError('Missing integer solver counters: ' + case['id'])
        rows.append({'id': case['id'], 'level': case['level'], 'steps': steps, **phases})
    operations = ['add', 'sub', 'mul', 'div', 'compare', 'sqrt', 'trig',
                  'integer_multiply', 'power_two_divide', 'trig_q48_multiply']
    total_steps = sum(r['steps'] for r in rows)
    counts = {k: sum(r['simulation'][k] for r in rows) for k in operations}
    histogram = {name: [sum(r['simulation'][name][i] for r in rows) for i in range(65)]
                 for name in ('mul_operand_bits', 'div_operand_bits')}
    peak = {name: max(r['simulation'][name] for r in rows) for name in
            ('max_abs_raw', 'max_trig_abs_raw', 'max_product_bits', 'max_dividend_bits')}
    minimum_divisor = min(r['simulation']['min_divisor_raw'] for r in rows)
    report = {'host_reference_only': True, 'cases': len(rows), 'steps': total_steps,
              'fractional_bits': rows[0]['simulation']['bits'], 'strict_fidelity': measured['strict_fidelity'],
              'critical_failing_cases': measured['critical_event_failing_cases'],
              'overflow_count': sum(r['simulation']['overflow'] + r['initialization']['overflow'] for r in rows),
              'counts': counts, 'mean_operations_per_step': {k: v / total_steps for k, v in counts.items()},
              'maximum_case_mean_operations_per_step': {k: max(r['simulation'][k] / r['steps'] for r in rows) for k in operations},
              'ranges': {**peak, 'min_divisor_raw': minimum_divisor},
              'operand_magnitude_bit_histograms': histogram,
              'trig_additional_constant_operations': {'power_two_divisions_or_shifts': counts['trig'] * 7,
                                                     'other_constant_divisions_or_modulos': counts['trig'] * 3},
              'notes': ['Initialization and JSON normalization excluded from simulation counts.',
                        'Integer sqrt is a separate bitwise algorithm; internal iterations are not scalar multiplies/divides.',
                        'Q48 local trig uses four checked integer products per call, reported separately.',
                        'With power-of-two table intervals, each trig call also uses seven power-of-two scales and three constant divisions/modulos.',
                        'Aggregate ranges measure scalar intermediates, not solely stored physical state.'],
              'runs': rows}
    if args.trig_kernel == 'native-horner':
        report['trig_additional_constant_operations'] = {
            'range_reductions': counts['trig'] // 2,
            'table_index_and_remainder': 'one shift/mask per pair',
            'note': 'Structural counts; hardware cycle cost must be measured separately.'}
        report['notes'][2:4] = [
            'Paired Horner trig uses narrow-coefficient products reported by trig_q48_multiply; its degree is variant-specific.',
            'One shared phase reduction per pair; power-of-two radian table indexing needs no division.']
    report['trig_kernel'] = args.trig_kernel
    out = args.out or args.fidelity / 'operations.json'
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('runs', 'operand_magnitude_bit_histograms')}, indent=2))


if __name__ == '__main__':
    main()
