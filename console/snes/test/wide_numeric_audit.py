#!/usr/bin/env python3
"""Independent integer reference checks for the experimental wide scalar."""
import argparse
import json
import math
from pathlib import Path
import random
import subprocess

from fidelity_check import ROOT

DRIVER = r'''
#include <iostream>
#include <string>
#include "wide_fixed.h"
int main(){std::string op;int64_t a,b;while(std::cin>>op>>a>>b){auto x=wide_scalar::from_raw(a),y=wide_scalar::from_raw(b);wide_scalar z;
if(op=="mul")z=x*y;else if(op=="div")z=x/y;else if(op=="sqrt")z=sqrt(x);else if(op=="floor")z=floor(x);else if(op=="sin")z=sin(x);else if(op=="cos")z=cos(x);else if(op=="neg")z=-x;else return2;
std::cout<<z.raw<<"\n";}return 0;}
'''.replace('return2','return 2')


def rounded(n, d):
    negative = (n < 0) != (d < 0)
    n, d = abs(n), abs(d)
    q, r = divmod(n, d)
    return (-1 if negative else 1)*(q+(r >= d-r))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build', type=Path, required=True, help='directory containing generated wide_trig_table.h')
    ap.add_argument('--scalar', type=Path, default=ROOT/'test/wide_fixed.h')
    ap.add_argument('--bits', type=int, default=32)
    ap.add_argument('--out', type=Path, default=ROOT/'build/wide-numeric-audit')
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    source = a.out/'audit.cpp';source.write_text(DRIVER)
    (a.out/'wide_fixed.h').write_bytes(a.scalar.read_bytes())
    (a.out/'wide_trig_table.h').write_bytes((a.build/'wide_trig_table.h').read_bytes())
    host = a.out/'audit'
    subprocess.run(['c++','-std=c++17','-O2','-DWIDE_BITS='+str(a.bits),'-I'+str(a.out),str(source),'-o',str(host)],check=True)
    scale = 1 << a.bits
    rng = random.Random(187)
    cases = []
    for _ in range(2000):
        x,y = rng.randint(-100*scale,100*scale),rng.randint(-100*scale,100*scale) or 1
        cases.extend([('mul',x,y,rounded(x*y,scale)),('div',x,y,rounded(x*scale,y)),('floor',x,0,(x//scale)*scale)])
        raw = rng.randint(0,100000*scale)
        n = raw*scale; root = math.isqrt(n);cases.append(('sqrt',raw,0,root+(n-root*root>root)))
    for x in [1,3,scale//2,-scale//2,scale-1,-scale+1,-1,-3]:
        for y in [scale//2,scale,3*scale,-scale//2,-scale,-3*scale]:
            cases.append(('mul',x,y,rounded(x*y,scale)))
            cases.append(('div',x,y,rounded(x*scale,y)))
    anchors = [0,math.pi/2,math.pi,2*math.pi,-math.pi/2,-math.pi,-2*math.pi,1000*math.pi,-1000*math.pi]
    for x in anchors+[rng.uniform(-10000,10000) for _ in range(2000)]:
        raw = round(x*scale)
        for offset in [-1,0,1]:
            for op, f in [('sin',math.sin),('cos',math.cos)]:
                value = raw+offset;cases.append((op,value,0,round(f(value/scale)*scale)))
    result = subprocess.run([str(host)],input=''.join(f'{op} {x} {y}\n' for op,x,y,_ in cases),capture_output=True,text=True,check=True)
    actual = [int(s) for s in result.stdout.splitlines()]
    assert len(actual)==len(cases)
    failures=[]; maximum_trig_ulps=0
    for (op,x,y,expected),got in zip(cases,actual):
        error=abs(got-expected)
        if op in ['sin','cos']:maximum_trig_ulps=max(maximum_trig_ulps,error)
        if error > (1 if op in ['sin','cos'] else 0):failures.append({'operation':op,'a':x,'b':y,'expected':expected,'actual':got})
    domain_results=[]
    for text in [f'div {scale} 0\n',f'sqrt {-scale} 0\n',f'neg {-2**63} 0\n',f'mul {2**63-1} {2**63-1}\n']:
        p=subprocess.run([str(host)],input=text,capture_output=True,text=True)
        domain_results.append({'case':text.strip(),'failed_explicitly':p.returncode!=0 and 'WIDE_OVERFLOW_OR_DOMAIN' in p.stderr})
    report={'bits':a.bits,'cases':len(cases),'arithmetic_failures':failures,'max_trig_error_raw_ulps':maximum_trig_ulps,'domain_failures':domain_results,
            'note':'Arithmetic references use Python arbitrary integers, nearest signed half-away division, exact isqrt. Trig uses host libm only as independent audit reference; one output ULP is allowed.'}
    (a.out/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'{len(cases)} cases; arithmetic/trig failures {len(failures)}; max trig {maximum_trig_ulps} ULP; domain checks {sum(x["failed_explicitly"] for x in domain_results)}/{len(domain_results)}')
    return int(bool(failures) or not all(x['failed_explicitly'] for x in domain_results))


if __name__=='__main__':
    raise SystemExit(main())
