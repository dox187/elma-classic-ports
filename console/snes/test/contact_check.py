#!/usr/bin/env python3
"""Diagnose a rolling contact divergence without changing collision thresholds.

Builds temporary instrumented copies of the original PC physics and C spec.
Runs accumulated trajectories and a probe quantizing the PC prior kinematic
state into the C engine immediately before the selected step. Existing hidden
C control state is retained; this is a kinematic contact probe, not a claim that
all hidden state of both implementations has been made identical.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
UNITS = ['LEPTET.CPP', 'BEALLIT.CPP', 'UTKOZES.CPP', 'UTKOZES2.CPP', 'SZAKASZ.CPP', 'VEKT2.CPP']


def replace(source, old, new):
    assert source.count(old) == 1, old
    return source.replace(old, new)


def run(args, **kw):
    return subprocess.run(list(map(str, args)), check=True, **kw)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--step', type=int, default=256)
    ap.add_argument('--level', type=int, default=0)
    ap.add_argument('--wheel', type=int, choices=[1, 2], default=1, help='circle index: 1=kor2, 2=kor4')
    ap.add_argument('--script', default='GT160 N32 B32 G32')
    ap.add_argument('--out', type=Path, default=ROOT / 'build/contact-diagnosis')
    ap.add_argument('--spec-source', type=Path, default=ROOT / 'test/phys_spec.c')
    ap.add_argument('--gen', type=Path, default=ROOT / 'build/gen')
    ap.add_argument('--levdump', type=Path, default=ROOT / 'build/host/levdump')
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    selected = f'phydebug_step == {a.step}'
    spec_wheel = f'k==&PS.c[{a.wheel}]'
    pc_wheel = 'pk==&Pmot1->kor2' if a.wheel == 1 else 'pk==&Pmot1->kor4'
    spec = '#include <stdio.h>\nextern int phydebug_step;\n' + a.spec_source.read_text()
    spec = replace(spec, 'int n = contacts( k->rx, k->ry, R_WHEEL_P, R_WHEEL_SQ, ct );',
                   'int n = contacts( k->rx, k->ry, R_WHEEL_P, R_WHEEL_SQ, ct );\n'
                   f'if({spec_wheel} && {selected}) fprintf(stderr,"SPEC contacts r%d,%d v%d,%d F%d,%d count%d\\n",k->rx,k->ry,k->vx,k->vy,Fx,Fy,n);')
    spec = replace(spec, 'if( d2 >= RSQ )',
                   f'if({selected} && R==R_WHEEL_P) fprintf(stderr,"SPEC endpoint line%d d%d,%d square%u radius_square%u\\n",L,dx,dy,d2,RSQ);\nif( d2 >= RSQ )')
    spec = replace(spec, 'if( nv > -ELSZ_V && mq24( Fx, c->nx )+mq24( Fy, c->ny ) > 0 )',
                   f'if({spec_wheel} && {selected}) fprintf(stderr,"SPEC holds normal%d,%d h%d nv%d limit%d force_dot%d\\n",c->nx,c->ny,c->h,nv,-ELSZ_V,mq24(Fx,c->nx)+mq24(Fy,c->ny));\n'
                   'if( nv > -ELSZ_V && mq24( Fx, c->nx )+mq24( Fy, c->ny ) > 0 )')
    (a.out / 'phys_spec.c').write_text(spec)
    for unit in UNITS:
        pc = (ROOT / '../../src' / unit).read_text(errors='surrogateescape')
        if unit == 'BEALLIT.CPP':
            pc = '#include <stdio.h>\nextern "C" int phydebug_step;\n' + pc
            pc = replace(pc, '// Egy kis ellenorzes:',
                         f'if({pc_wheel} && {selected}) fprintf(stderr,"PC contacts r%.17g,%.17g count%d\\n",pk->r.x,pk->r.y,talppontszam);\n// Egy kis ellenorzes:')
            pc = replace(pc, 'if( n*pk->v > -Elszakadasisebhat && n*F > 0 )',
                         f'if({pc_wheel} && {selected}) fprintf(stderr,"PC holds normal%.17g,%.17g h%.17g nv%.17g limit%.17g force_dot%.17g\\n",n.x,n.y,hossz,n*pk->v,-Elszakadasisebhat,n*F);\n'
                         'if( n*pk->v > -Elszakadasisebhat && n*F > 0 )')
        (a.out / unit).write_text(pc, errors='surrogateescape')
    run(['cc', '-O2', '-I'+str(ROOT/'test'), '-I'+str(a.gen), '-c', a.out/'phys_spec.c', '-o', a.out/'phys_spec.o'])
    report = {'step': a.step, 'level': a.level, 'wheel': a.wheel, 'script': a.script,
              'source_sha256': hashlib.sha256(a.spec_source.read_bytes()).hexdigest(), 'runs': {}}
    for mode in ['accumulated', 'pc_prior_kinematics']:
        harness = (ROOT/'test/physcheck.cpp').read_text()
        harness = replace(harness, 'struct item {', 'extern "C" { int phydebug_step = 0; }\nstruct item {')
        probe = f'if(i+1=={a.step}) sync(dt);' if mode == 'pc_prior_kinematics' else ''
        harness = replace(harness, 'sev = ps_step((uint16_t)keys[i]);',
                          f'phydebug_step = (int)i+1; {probe}\nsev = ps_step((uint16_t)keys[i]);')
        (a.out/'physcheck.cpp').write_text(harness)
        host = a.out / ('physcheck_'+mode)
        run(['c++', '-O2', '-w', '-fpermissive', '-I'+str(ROOT/'test'), '-I'+str(ROOT/'test/pcphys'), '-I'+str(a.gen),
             '-o', host, a.out/'physcheck.cpp', ROOT/'test/pcphys/pcphys.cpp',
             *[a.out/u for u in UNITS], a.out/'phys_spec.o'])
        result = run([host, a.gen, a.levdump, a.level, a.script, '--trace-json'], capture_output=True, text=True)
        (a.out/(mode+'.jsonl')).write_text(result.stdout)
        (a.out/(mode+'.log')).write_text(result.stderr)
        rows = [json.loads(s) for s in result.stdout.splitlines()]
        report['runs'][mode] = {'diagnostics': result.stderr.splitlines(), 'prior': rows[a.step-1], 'after': rows[a.step]}
    (a.out/'diagnosis.json').write_text(json.dumps(report, indent=2)+'\n')
    print(a.out/'diagnosis.json')


if __name__ == '__main__':
    main()
