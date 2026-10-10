#!/usr/bin/env python3
"""Feasibility probe: untouched PC equations with state quantized each step.

This measures a numerical precision ceiling, not an implemented SNES solver.
Original equation internals remain host double precision. Baseline PC traces
are the independent untouched reference. Collision thresholds stay unchanged.
"""
import argparse
import copy
import gzip
import json
import re
from pathlib import Path
import subprocess

from fidelity_check import ROOT, digest, measure

UNITS = ['LEPTET.CPP', 'BEALLIT.CPP', 'UTKOZES.CPP', 'UTKOZES2.CPP', 'SZAKASZ.CPP', 'VEKT2.CPP']


def run(args, **kw):
    return subprocess.run(list(map(str, args)), check=True, **kw)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--baseline', type=Path, default=ROOT/'build/fidelity-baseline')
    ap.add_argument('--out', type=Path, default=ROOT/'build/precision-probe')
    ap.add_argument('--bits', default='16,20,24,28,32')
    ap.add_argument('--velocity-bits', type=int, help='optional actual game-unit velocity fractional bits')
    ap.add_argument('--angle-bits', type=int, help='optional angle and actual game-unit omega fractional bits')
    ap.add_argument('--geometry-bits', type=int, help='optional level vertices/object coordinate quantization before grid generation')
    ap.add_argument('--vector-bits', type=int, help='optional unit-normal and trigonometric component fractional bits')
    ap.add_argument('--gen', type=Path, default=ROOT/'build/gen')
    ap.add_argument('--levdump', type=Path, default=ROOT/'build/host/levdump')
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    corpus = json.loads((a.baseline/'corpus.json').read_text())
    source = (ROOT/'test/physcheck.cpp').read_text()
    anchor = 'int ev = pc_step(keys[i], pc_dt);'
    assert source.count(anchor) == 1
    for unit in UNITS:
        unit_source = (ROOT/'../../src'/unit).read_text(errors='surrogateescape')
        if a.vector_bits is not None:
            nb = a.vector_bits
            helper = f'\nstatic double phy_quant(double v) {{return ldexp(round(ldexp(v,{nb})),-{nb});}}\nstatic vekt2 phy_quant_vec(vekt2 v) {{return vekt2(phy_quant(v.x),phy_quant(v.y));}}\n'
            unit_source, changed = re.subn(r'#include\s*"all.h"', lambda m:m.group(0)+helper, unit_source, count=1)
            assert changed == 1
            unit_source = re.sub(r'(vekt2 (n|i|i1|joirany)(?: = [^;]+|\([^;]+);)', lambda m:m.group(1)+' '+m.group(2)+'=phy_quant_vec('+m.group(2)+');', unit_source)
            unit_source = unit_source.replace('return a*(1/abs( a ));','return phy_quant_vec(a*(1/abs( a )));')
            unit_source = unit_source.replace('double a = sin( alfa );','double a = phy_quant(sin( alfa ));').replace('double b = cos( alfa );','double b = phy_quant(cos( alfa ));')
        (a.out/unit).write_text(unit_source, errors='surrogateescape')
    pc_source = (ROOT/'test/pcphys/pcphys.cpp').read_text()
    if a.geometry_bits is not None:
        gb = a.geometry_bits
        polygon_anchor = 'Ptop = &Top;'
        assert pc_source.count(polygon_anchor) == 1
        quant_geometry = f'''for(int i=0;i<npoly;i++) for(int j=0;j<Gyuruk[i].pontszam;j++) {{
 Gyuruk[i].ponttomb[j].x=ldexp(round(ldexp(Gyuruk[i].ponttomb[j].x,{gb})),-{gb});
 Gyuruk[i].ponttomb[j].y=ldexp(round(ldexp(Gyuruk[i].ponttomb[j].y,{gb})),-{gb}); }}
 for(int i=0;i<nobj;i++) {{Kerekek[i].r.x=ldexp(round(ldexp(Kerekek[i].r.x,{gb})),-{gb}); Kerekek[i].r.y=ldexp(round(ldexp(Kerekek[i].r.y,{gb})),-{gb});}}
'''
        pc_source = pc_source.replace(polygon_anchor, quant_geometry+polygon_anchor)
    (a.out/'pcphys.cpp').write_text(pc_source)
    variants = []
    for bits in map(int, a.bits.split(',')):
        out = a.out / ('p'+str(bits))
        out.mkdir(exist_ok=True)
        quant = f'''pc_state q; pc_get(&q);
 for(int j=0;j<3;j++) {{q.c[j].r.x=ldexp(round(ldexp(q.c[j].r.x,{bits})),-{bits}); q.c[j].r.y=ldexp(round(ldexp(q.c[j].r.y,{bits})),-{bits});}}
 q.rider_r.x=ldexp(round(ldexp(q.rider_r.x,{bits})),-{bits}); q.rider_r.y=ldexp(round(ldexp(q.rider_r.y,{bits})),-{bits});
'''
        if a.velocity_bits is not None:
            vb = a.velocity_bits
            quant += f'''for(int j=0;j<3;j++) {{q.c[j].v.x=ldexp(round(ldexp(q.c[j].v.x,{vb})),-{vb}); q.c[j].v.y=ldexp(round(ldexp(q.c[j].v.y,{vb})),-{vb});}}
 q.rider_v.x=ldexp(round(ldexp(q.rider_v.x,{vb})),-{vb}); q.rider_v.y=ldexp(round(ldexp(q.rider_v.y,{vb})),-{vb});
'''
        if a.angle_bits is not None:
            ab = a.angle_bits
            quant += f'''for(int j=0;j<3;j++) {{q.c[j].alfa=ldexp(round(ldexp(q.c[j].alfa,{ab})),-{ab});q.c[j].omega=ldexp(round(ldexp(q.c[j].omega,{ab})),-{ab});}}
'''
        (out/'physcheck.cpp').write_text(source.replace(anchor, anchor+'\n'+quant+'pc_set(&q);'))
        host = out/'physcheck'
        run(['c++', '-O2', '-w', '-fpermissive', '-I'+str(ROOT/'test'), '-I'+str(ROOT/'test/pcphys'), '-I'+str(a.gen),
             '-o', host, out/'physcheck.cpp', a.out/'pcphys.cpp', *[a.out/u for u in UNITS], ROOT/'build/host/phys_spec.o'])
        measured = []
        for case in corpus:
            result = run([host, a.gen, a.levdump, case['level'], case['script'], '--trace-json'], capture_output=True, text=True)
            candidate = [json.loads(s) for s in result.stdout.splitlines()]
            with gzip.open(a.baseline/(case['id']+'.jsonl.gz'), 'rt') as f:
                reference = [json.loads(s) for s in f]
            rows = []
            for step in range(max(len(reference), len(candidate))):
                ref = copy.deepcopy(reference[min(step,len(reference)-1)])
                cand = candidate[min(step,len(candidate)-1)]
                ref['step'] = step
                for suffix in ['', '_event', '_stopped', '_discrete', '_objects', '_apple_object']:
                    ref['snes'+suffix] = cand['pc'+suffix]
                if step >= len(candidate):
                    ref['snes_event'] = 0; ref['snes_apple_object'] = -1
                if step >= len(reference):
                    ref['pc_event'] = 0; ref['pc_apple_object'] = -1
                ref.pop('snes_raw', None)
                rows.append(ref)
            trace = out/(case['id']+'.jsonl.gz')
            with gzip.open(trace, 'wt') as f:
                f.write(''.join(json.dumps(r, separators=(',', ':'))+'\n' for r in rows))
            measured.append(measure(case, rows, trace))
        count = sum(r['samples'] for r in measured)
        components = {k:sum(r['samples']*r['component_pass_fractions'][k] for r in measured)/count for k in measured[0]['component_pass_fractions']}
        report = {'experiment': 'PC double equation internals, per-step quantized positions; not an SNES implementation',
                  'position_fractional_bits': bits, 'geometry_fractional_bits': a.geometry_bits, 'unit_vector_fractional_bits': a.vector_bits, 'game_velocity_fractional_bits': a.velocity_bits, 'angle_omega_fractional_bits': a.angle_bits,
                  'host_sha256': digest(host), 'harness_sha256': digest(out/'physcheck.cpp'), 'pc_loop_harness_sha256': digest(a.out/'pcphys.cpp'), 'corpus_sha256': digest(a.baseline/'corpus.json'),
                  'strict_fidelity': min(r['terminal_gated_fidelity'] for r in measured),
                  'critical_failing_cases': [r['id'] for r in measured if not r['critical_events_match']],
                  'component_pass_fractions': components, 'runs': measured}
        (out/'probe.json').write_text(json.dumps(report, indent=2)+'\n')
        variants.append({k:v for k,v in report.items() if k!='runs'})
        print(f"Q{bits} positions, velocity={a.velocity_bits}, angle={a.angle_bits}, geometry={a.geometry_bits}: strict {100*report['strict_fidelity']:.3f}%, critical failures {len(report['critical_failing_cases'])}, all-fields {100*components['all']:.3f}%", flush=True)
    (a.out/'summary.json').write_text(json.dumps(variants, indent=2)+'\n')


if __name__ == '__main__':
    main()
