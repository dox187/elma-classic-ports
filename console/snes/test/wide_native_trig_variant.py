#!/usr/bin/env python3
"""Isolated power-of-two radian LUT and narrow Horner trig experiment.

Grid spacing, remainder precision, coefficient precision and degree are
explicit experimental parameters. Index/remainder are shifts/masks; each
pair shares range reduction. This is a host specification for a native
implementation, not a SNES performance claim. Validate every composition.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess

from wide_probe import ROOT, UNITS

CODE = r'''
inline int64_t wide_native_trig_product(int64_t a,uint64_t u){
    ++wide_stats.trig_q48_multiply; // Counts these raw helper products too.
    return wide_trig_checked(wide_round_div((__int128)a*u,(__int128)1<<WIDE_NATIVE_TRIG_U_BITS),"native trig Horner");
}
inline void wide_native_trig_pair(wide_scalar x,wide_scalar* output){
    wide_stats.trig+=2;
    const int64_t pi=WIDE_PI_Q48,quarter=pi/2;
    __int128 phase=(__int128)x.raw*(int64_t(1)<<(48-WIDE_BITS));
    int64_t a=(int64_t)(phase%(2*pi));if(a<0)a+=2*pi;
    bool negsin=a>pi;if(negsin)a-=pi;
    bool negcos=a>quarter;if(negcos)a=pi-a;
    if(negsin)negcos=!negcos;
    unsigned index=unsigned(a>>(48-WIDE_NATIVE_TRIG_SHIFT));
    int64_t d=a-((int64_t)index<<(48-WIDE_NATIVE_TRIG_SHIFT));
    uint64_t u=uint64_t(wide_round_div(d,int64_t(1)<<(48-WIDE_NATIVE_TRIG_SHIFT-WIDE_NATIVE_TRIG_U_BITS)));
    if(u==(uint64_t(1)<<WIDE_NATIVE_TRIG_U_BITS)){++index;u=0;}
    for(unsigned function=0;function<2;++function){
        const auto* c=wide_native_trig_coeff[index][function];
        int64_t result=c[2];
#if WIDE_NATIVE_TRIG_DEGREE == 3
        result+=wide_native_trig_product(c[3],u);
#endif
        result=c[1]+wide_native_trig_product(result,u);
        result=c[0]+wide_native_trig_product(result,u);
        int64_t raw=wide_checked(wide_round_div(result,int64_t(1)<<(WIDE_NATIVE_TRIG_COEFFICIENT_BITS-WIDE_BITS)),"native trig output");
        output[function]=wide_scalar::from_raw((function?negcos:negsin)?-raw:raw);
    }
}
// Same two-angle pure cache as the preceding reference; each miss computes
// the pair from one common range reduction and LUT index.
inline wide_scalar wide_trig(wide_scalar x,bool cosine){
    struct entry {int64_t angle=0;wide_scalar value[2];bool valid=false;};
    static entry entries[2];static unsigned next=0;
    for(auto& item:entries)if(item.valid&&item.angle==x.raw)return item.value[cosine];
    auto& item=entries[next];next^=1;item.angle=x.raw;item.valid=true;
    wide_native_trig_pair(x,item.value);return item.value[cosine];
}
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--remainder-bits',type=int,choices=[16,20,24,28,32],default=32)
    ap.add_argument('--grid-shift',type=int,choices=[10,12],default=10)
    ap.add_argument('--coefficient-bits',type=int,choices=[40,48],default=48)
    ap.add_argument('--degree',type=int,choices=[2,3],default=3)
    a=ap.parse_args();base=a.base.resolve();out=a.out.resolve()
    if out.exists():raise ValueError('Use a fresh isolated output directory')
    out.mkdir(parents=True)
    for p in base.iterdir():
        if p.is_file() and p.suffix.lower() in ('.h','.cpp'):shutil.copy2(p,out/p.name)
    header=out/'wide_fixed.h';source=header.read_text()
    start=source.index('inline wide_scalar wide_trig_uncached(')
    end=source.index('inline wide_scalar sin(',start)
    header.write_text(source[:start]+CODE+source[end:])
    shift=a.grid_shift;h=2.0**-shift;n=math.floor(math.pi/2/h)+1;scale=2**a.coefficient_bits
    lines=['#pragma once','#define WIDE_NATIVE_TRIG_SHIFT '+str(shift),
           '#define WIDE_NATIVE_TRIG_COEFFICIENT_BITS '+str(a.coefficient_bits),
           '#define WIDE_NATIVE_TRIG_DEGREE '+str(a.degree),
           '#define WIDE_NATIVE_TRIG_U_BITS '+str(a.remainder_bits),
           'static constexpr int64_t WIDE_PI_Q48='+str(round(math.pi*2**48))+';',
           'static constexpr int64_t wide_native_trig_coeff[][2][4]={']
    max_coeff=[0]*4
    for i in range(n):
        s,c=math.sin(i*h),math.cos(i*h)
        pair=[[s,c*h,-s*h*h/2,-c*h*h*h/6],
              [c,-s*h,-c*h*h/2,s*h*h*h/6]]
        coefficients=[[round(v*scale) for v in row] for row in pair]
        if a.degree==2:
            for row in coefficients:row[3]=0
        for row in coefficients:
            for k,v in enumerate(row):max_coeff[k]=max(max_coeff[k],abs(v))
        lines.append('{'+','.join('{'+','.join(str(v) for v in row)+'}' for row in coefficients)+'},')
    lines+=['};',''];(out/'wide_trig_table.h').write_text('\n'.join(lines))
    bits=json.loads((base/'build.json').read_text())['bits']
    if bits>a.coefficient_bits:raise ValueError("Coefficient precision must cover the scalar output")
    cmd=['c++','-std=c++17','-O2','-w','-DWIDE_BITS='+str(bits),'-I'+str(out),
         '-I'+str(ROOT/'test'),'-o',str(out/'widecheck'),str(out/'wide_harness.cpp'),
         str(out/'pcphys.cpp'),*[str(out/name) for name in UNITS]]
    p=subprocess.run(cmd,capture_output=True,text=True);(out/'compile.txt').write_text(p.stdout+p.stderr);p.check_returncode()
    meta={'bits':bits,'command':cmd,'base_build':str(base),'change':__doc__,
          'trig_rows':n,'remainder_bits':a.remainder_bits,'grid_shift':shift,
          'coefficient_bits':a.coefficient_bits,'polynomial_degree':a.degree,'max_coefficient_magnitude_bits':[v.bit_length() for v in max_coeff],
          'proposed_packed_table_bytes':n*2*sum((v.bit_length()+1+7)//8 for v in max_coeff[:a.degree+1]),
          'scalar_header_sha256':hashlib.sha256(header.read_bytes()).hexdigest()}
    (out/'build.json').write_text(json.dumps(meta,indent=2)+'\n')
    print(out/'widecheck')


if __name__=='__main__':main()
