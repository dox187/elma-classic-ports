"""Summarize measured compact integration fidelity, ranges and native cost.

Separates the host PC-unit compatibility conversion from native step-unit
integration; the native estimate is component arithmetic, not a frame result.
"""
import argparse
import json
from pathlib import Path
import re


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('build',type=Path)
    ap.add_argument('--native',type=Path,default=Path('build/wide-integrate-48-fixed/results.json'))
    a=ap.parse_args()
    metadata=json.loads((a.build/'build.json').read_text())
    step_units=metadata.get('integration_rate_units')=='step'
    report={'layout':{'state':'signed48 Q32, positions and unwrapped angles',
                      'per_step_rate':'signed48 Q40, velocity and omega'},
            'native_component':json.loads(a.native.read_text()),'corpora':{}}
    for name in ('fidelity','holdout'):
        directory=a.build/name
        fidelity=json.loads((directory/'fidelity.json').read_text())
        counts={'position':0,'angle':0}
        ranges={key:0 for key in ('max_position_raw','max_angle_raw','max_velocity_raw','max_omega_raw')}
        steps=0
        for path in directory.glob('*.stderr.txt'):
            text=path.read_text()
            matched=re.findall(r'COMPACT_STATS (\{[^\n]+\})',text)
            if len(matched)!=1:raise ValueError('Missing/duplicate compact counters: '+str(path))
            row=json.loads(matched[0])
            for key in counts:counts[key]+=row[key]
            for key in ranges:ranges[key]=max(ranges[key],row[key])
            steps+=int(re.search(r'^WIDE_STEPS (\d+)',text,re.M).group(1))
        calls=sum(counts.values())
        native=report['native_component']['timings_master_clocks']
        report['corpora'][name]={
            'strict_fidelity':fidelity['strict_fidelity'],
            'critical_event_failing_cases':fidelity['critical_event_failing_cases'],
            'cases':fidelity['cases'],'samples':fidelity['samples'],'executed_steps':steps,
            'native_integration_calls':counts,
            'native_calls_per_step':calls/steps,
            'estimated_component_master_clocks_per_step':
                (counts['position']*native['position_wide']['median']+
                 counts['angle']*native['unwrapped_angle_wide']['median'])/steps,
            'observed_maximum_magnitude':{
                'position_m':ranges['max_position_raw']/2**32,
                'angle_rad':ranges['max_angle_raw']/2**32,
                'velocity_m_per_step':ranges['max_velocity_raw']/2**40,
                'omega_rad_per_step':ranges['max_omega_raw']/2**40},
            'compatibility_adapter_products':0 if step_units else calls,
            'compatibility_adapter_rounding_divisions':0 if step_units else 3*calls,
        }
    report['limits']=[
      'Engine stores per-step units directly; no per-step compatibility encoding.' if step_units else 'Host conversion encodes PC velocity into per-step units. Those products/divisions are adapter work and must not be hidden in a complete solver cost estimate.',
      'Native entry-to-end timings include preservation and overflow diagnostics; final RTL and caller overhead excluded.',
      'Only integration is a native implementation; force/contact remain a host Q36 reference. No production physics/FPS claim.',
      'Q29 integration failed a long holdout trajectory; Q32 state is the accepted tested layout.'
    ]
    (a.build/'integration-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report['corpora'],indent=2))


if __name__=='__main__':main()
