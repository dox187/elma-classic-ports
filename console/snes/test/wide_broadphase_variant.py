#!/usr/bin/env python3
"""Conservative coarse AABB before original high-precision segment contact.

Static bounds enclose the exact quantized projection strip and both endpoint
circles. Dot products have <=1 raw ULP rounding error. Bounds use that error,
the actual quantized normal length, and an additional1/256m outward cell.
No contact order, contact threshold, or successful-contact result changes.
The radius guard leaves larger-radius callers on the original path.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

from wide_probe import ROOT,UNITS

HELPERS=r'''
inline __int128 wide_box_floor(__int128 n,__int128 d){
    __int128 q=n/d;if(n<0&&n%d)--q;return q;
}
inline __int128 wide_box_ceil(__int128 n,__int128 d){return -wide_box_floor(-n,d);}
inline void wide_prepare_box(vonal* line){
    const int64_t quantum=int64_t(1)<<(WIDE_BITS-8);
    const int64_t radius=wide_scalar::literal("0.4").raw;
    const int64_t ex=line->egyseg.x.raw,ey=line->egyseg.y.raw;
    const __int128 norm=(__int128)ex*ex+(__int128)ey*ey;
    if(!norm)wide_fail("broadphase zero line normal");
    const int64_t length=line->hossz.raw;
    int64_t directions[2]={ex,ey},normals[2]={-ey,ex};
    int64_t start[2]={line->r.x.raw,line->r.y.raw};
    int64_t end[2]={line->wide_endpoint.x.raw,line->wide_endpoint.y.raw};
    for(unsigned axis=0;axis<2;++axis){
        const int64_t e=directions[axis],n=normals[axis];
        const __int128 transverse=(__int128)(radius+1)*wide_magnitude(n);
        const __int128 qlo=e>=0?-(__int128)e:(__int128)(length+1)*e;
        const __int128 qhi=e>=0?(__int128)(length+1)*e:-(__int128)e;
        __int128 lo=wide_box_floor(start[axis],quantum)+wide_box_floor(256*(qlo-transverse),norm)-1;
        __int128 hi=wide_box_ceil(start[axis],quantum)+wide_box_ceil(256*(qhi+transverse),norm)+1;
        for(int64_t endpoint:{start[axis],end[axis]}){
            __int128 lower=wide_box_floor((__int128)endpoint-radius,quantum)-1;
            __int128 upper=wide_box_ceil((__int128)endpoint+radius,quantum)+1;
            if(lower<lo)lo=lower;if(upper>hi)hi=upper;
        }
        line->wide_box[2*axis]=wide_checked(lo,"broadphase minimum");
        line->wide_box[2*axis+1]=wide_checked(hi,"broadphase maximum");
    }
}
inline uint64_t wide_box_tested=0,wide_box_rejected=0;
inline bool wide_box_excludes(vekt2 r,wide_scalar radius,const vonal* line){
    ++wide_box_tested;
    if(radius.raw>wide_scalar::literal("0.4").raw||radius.raw<0)return false;
    constexpr int64_t quantum=int64_t(1)<<(WIDE_BITS-8);
    int64_t x=(int64_t)wide_box_floor(r.x.raw,quantum),y=(int64_t)wide_box_floor(r.y.raw,quantum);
    bool outside=x<line->wide_box[0]||x>line->wide_box[1]||y<line->wide_box[2]||y>line->wide_box[3];
    if(outside)++wide_box_rejected;return outside;
}
'''


def change(path,old,new):
    text=path.read_text()
    if text.count(old)!=1:raise ValueError('Unexpected anchor in '+str(path)+': '+old)
    path.write_text(text.replace(old,new))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();base=a.base.resolve();out=a.out.resolve()
    if out.exists():raise ValueError('Use a fresh output directory')
    out.mkdir(parents=True)
    for p in base.iterdir():
        if p.is_file() and p.suffix.lower() in ('.h','.cpp'):shutil.copy2(p,out/p.name)
    change(out/'szakasz.h','struct vonal {','struct vonal {\n int64_t wide_box[4];')
    (out/'wide_broadphase.h').write_text('#pragma once\n#include <initializer_list>\n'+HELPERS)
    for unit in ['SZAKASZ.CPP','UTKOZES.CPP']:
        change(out/unit,'#include\t"all.h"','#include\t"all.h"\n#include "wide_broadphase.h"')
    change(out/'SZAKASZ.CPP','pv->wide_normal=forgatas90fokkal(pv->egyseg);','pv->wide_normal=forgatas90fokkal(pv->egyseg);\n wide_prepare_box(pv);')
    change(out/'UTKOZES.CPP','\tvekt2 rel = r-pv->r;','\tif(wide_box_excludes(r,sugar,pv))return 0;\n\tvekt2 rel = r-pv->r;')
    change(out/'wide_harness.cpp','#include "pcphys.h"','#include "pcphys.h"\n#include "wide_broadphase.h"')
    change(out/'wide_harness.cpp','wide_print_stats("simulation",wide_stats);','wide_print_stats("simulation",wide_stats);\n fprintf(stderr,"WIDE_BOX %llu %llu\\n",wide_box_tested,wide_box_rejected);')
    bits=json.loads((base/'build.json').read_text())['bits']
    cmd=['c++','-std=c++17','-O2','-w','-DWIDE_BITS='+str(bits),'-I'+str(out),'-I'+str(ROOT/'test'),'-o',str(out/'widecheck'),str(out/'wide_harness.cpp'),str(out/'pcphys.cpp'),*[str(out/n) for n in UNITS]]
    p=subprocess.run(cmd,capture_output=True,text=True);(out/'compile.txt').write_text(p.stdout+p.stderr);p.check_returncode()
    (out/'build.json').write_text(json.dumps({'bits':bits,'command':cmd,'base_build':str(base),'change':__doc__},indent=2)+'\n')
    print(out/'widecheck')


if __name__=='__main__':main()
