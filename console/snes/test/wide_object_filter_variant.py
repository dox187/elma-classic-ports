#!/usr/bin/env python3
"""Exact axis rejection before the original object squared-distance test.

For nonnegative R, |x|>=R implies round(x*x)>=round(R*R). The other rounded
square is nonnegative, so the original strict squared-distance comparison
cannot succeed. The remaining path and object processing order are intact.
This operates before square evaluation; it assumes the normal level domain,
where the preceding reference's checked arithmetic does not overflow.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from wide_probe import ROOT,UNITS


def change(path,old,new):
    text=path.read_text()
    if text.count(old)!=1:raise ValueError('Unexpected anchor in '+str(path))
    path.write_text(text.replace(old,new))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--coarse',action='store_true',help='also reject using conservative Q8 coordinates before wide subtraction')
    a=ap.parse_args();base=a.base.resolve();out=a.out.resolve()
    if out.exists():raise ValueError('Use a fresh output directory')
    out.mkdir(parents=True)
    for p in base.iterdir():
        if p.is_file() and p.suffix.lower() in ('.h','.cpp'):shutil.copy2(p,out/p.name)
    change(out/'UTKOZES2.CPP','#include\t"all.h"','#include\t"all.h"\nuint64_t wide_object_tested=0,wide_object_rejected=0;')
    old='\t\twide_scalar maxtav = sugar + Objektumsugar;'
    new=old+'''
        ++wide_object_tested;
        if(maxtav.raw>=0 && (wide_magnitude(diff.x.raw)>=uint64_t(maxtav.raw) ||
                           wide_magnitude(diff.y.raw)>=uint64_t(maxtav.raw))){
            ++wide_object_rejected;continue;
        }'''
    if a.coarse:
        new=new.replace('        ++wide_object_tested;\n','')
    change(out/'UTKOZES2.CPP',old,new)
    if a.coarse:
        unit=out/'UTKOZES2.CPP'
        change(unit,'\tfor( int i = 0; i < MAXKEREK; i++ ) {','''    // Arithmetic right-shift is floor division for the signed raw coordinates.
    const int64_t rx=r.x.raw>>(WIDE_BITS-8),ry=r.y.raw>>(WIDE_BITS-8);
    const wide_scalar max_range=sugar+Objektumsugar;
    const int64_t limit=(max_range.raw>>(WIDE_BITS-8))+1;
    for( int i = 0; i < MAXKEREK; i++ ) {''')
        change(unit,'\t\tvekt2 diff = r-pker->r;','''        ++wide_object_tested;
        if(max_range.raw>=0){
            const int64_t dx=rx-(pker->r.x.raw>>(WIDE_BITS-8));
            const int64_t dy=ry-(pker->r.y.raw>>(WIDE_BITS-8));
            if(wide_magnitude(dx)>uint64_t(limit)||wide_magnitude(dy)>uint64_t(limit)){
                ++wide_object_rejected;continue;
            }
        }
        vekt2 diff = r-pker->r;''')
        change(unit,'wide_scalar maxtav = sugar + Objektumsugar;','wide_scalar maxtav = max_range;')
    change(out/'wide_harness.cpp','#include "pcphys.h"','#include "pcphys.h"\nextern uint64_t wide_object_tested,wide_object_rejected;')
    change(out/'wide_harness.cpp','wide_print_stats("simulation",wide_stats);','wide_print_stats("simulation",wide_stats);\n fprintf(stderr,"WIDE_OBJECTS %llu %llu\\n",wide_object_tested,wide_object_rejected);')
    bits=json.loads((base/'build.json').read_text())['bits']
    cmd=['c++','-std=c++17','-O2','-w','-DWIDE_BITS='+str(bits),'-I'+str(out),'-I'+str(ROOT/'test'),'-o',str(out/'widecheck'),str(out/'wide_harness.cpp'),str(out/'pcphys.cpp'),*[str(out/n) for n in UNITS]]
    p=subprocess.run(cmd,capture_output=True,text=True);(out/'compile.txt').write_text(p.stdout+p.stderr);p.check_returncode()
    (out/'build.json').write_text(json.dumps({'bits':bits,'command':cmd,'base_build':str(base),'change':__doc__,'coarse_prefilter':a.coarse},indent=2)+'\n');print(out/'widecheck')


if __name__=='__main__':main()
