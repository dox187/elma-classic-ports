#!/usr/bin/env python3
"""Compare coarse rejection with the original segment test around all54levels."""
import argparse
import json
from pathlib import Path
import subprocess

from wide_probe import ROOT,UNITS

DRIVER=r'''
#include "all.h"
#include "pcphys.h"
#include "wide_broadphase.h"
#include "UTKOZES.CPP"
ORIGINAL
static uint64_t rng=1870149;
static uint64_t random64(){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return rng;}
static uint64_t cases=0,rejections=0;
static void check(vekt2 r,wide_scalar radius,vonal* line){
    vekt2 a,b;int x=gombszakasz(r,radius,line,&a),y=original_gombszakasz(r,radius,line,&b);
    ++cases;if(wide_box_excludes(r,radius,line))++rejections;
    if(x!=y||(x&&(a.x.raw!=b.x.raw||a.y.raw!=b.y.raw))){
        fprintf(stderr,"BROADPHASE_MISMATCH %llu %lld %lld radius%lld hit%d/%d\n",cases,r.x.raw,r.y.raw,radius.raw,x,y);exit(1);
    }
}
int main(int argc,char**argv){
    if(argc!=2)return2;
    uint64_t lines=0;
    for(int level=0;level<54;++level){char path[1024];snprintf(path,sizeof(path),"%s/lev%02d.txt",argv[1],level);if(!pc_load(path))return3;
        Pszak->felsorolasresetszak();
        while(auto* line=Pszak->getnextszak()){
            ++lines;
            const int64_t q=int64_t(1)<<(WIDE_BITS-8),scale=wide_scalar::scale;
            for(int j=0;j<64;++j){
                int64_t x0=(line->wide_box[0]-256)*q,x1=(line->wide_box[1]+256)*q;
                int64_t y0=(line->wide_box[2]-256)*q,y1=(line->wide_box[3]+256)*q;
                vekt2 r(wide_scalar::from_raw(x0+random64()%uint64_t(x1-x0)),wide_scalar::from_raw(y0+random64()%uint64_t(y1-y0)));
                check(r,wide_scalar::literal(".4"),line);check(r,wide_scalar::literal(".238"),line);
            }
            for(auto radius:{wide_scalar::literal(".4"),wide_scalar::literal(".238")}){
                for(int along=0;along<=4;++along){
                    vekt2 center=line->r+line->egyseg*(line->hossz*along/4);
                    for(int sign:{-1,1})for(int delta:{-2,-1,0,1,2}){
                        auto distance=wide_scalar::from_raw(sign*(radius.raw+delta));
                        check(center+line->wide_normal*distance,radius,line);
                    }
                }
                for(unsigned axis=0;axis<2;++axis)for(int edge=0;edge<2;++edge)for(int delta:{-1,0,1}){
                    vekt2 r=(line->r+line->wide_endpoint)*wide_scalar::literal(".5");
                    auto value=wide_scalar::from_raw(line->wide_box[axis*2+edge]*q+delta);
                    if(axis)r.y=value;else r.x=value;
                    check(r,radius,line);
                }
            }
            for(auto radius:{wide_scalar::literal("-.1"),wide_scalar(0),wide_scalar::literal(".6")})check(line->r,radius,line);
        }
    }
    printf("{\"levels\":54,\"lines\":%llu,\"cases\":%llu,\"rejected\":%llu,\"mismatches\":0}\n",lines,cases,rejections);
}
'''.replace('return2','return 2').replace('return3','return 3')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build',type=Path,required=True)
    a=ap.parse_args();build=a.build.resolve();metadata=json.loads((build/'build.json').read_text());base=Path(metadata['base_build'])
    source=(base/'UTKOZES.CPP').read_text();start=source.index('static int gombszakasz(');end=source.index('\nint talppontkereses(',start)
    original=source[start:end].replace('gombszakasz(','original_gombszakasz(')
    driver=build/'broadphase_audit.cpp';driver.write_text(DRIVER.replace('ORIGINAL',original))
    cmd=['c++','-std=c++17','-O2','-w','-DWIDE_BITS='+str(metadata['bits']),'-I'+str(build),'-I'+str(ROOT/'test'),'-o',str(build/'broadphase_audit'),str(driver),str(build/'pcphys.cpp'),*[str(build/n) for n in UNITS if n!='UTKOZES.CPP']]
    subprocess.run(cmd,check=True)
    p=subprocess.run([str(build/'broadphase_audit'),str(ROOT/'build/host/levdump')],capture_output=True,text=True);(build/'broadphase_audit.log').write_text(p.stdout+p.stderr);p.check_returncode()
    report=json.loads(p.stdout);(build/'broadphase_audit.json').write_text(json.dumps(report,indent=2)+'\n');print(p.stdout,end='')


if __name__=='__main__':main()
