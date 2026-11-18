#!/usr/bin/env python3
"""Keep artificial subdivisions flat while preserving original polygon vertices.

Queries production-packed long edges around every subdivision and samples real
corners separately. Native contact iteration is also checked against the scalar
reference by check_physics_contact_loop.py, including endpoint flags.
"""
import argparse
import ctypes as C
import json
from pathlib import Path
import shutil

import compare_pc_physics as comparison


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gen',type=Path,default=comparison.BASE/'build/gen-8m')
    parser.add_argument('--out',type=Path,default=comparison.BASE/'build/collision-seams')
    args=parser.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    source=out/'source/gbc/src'
    shutil.copytree(comparison.BASE/'src',source,dirs_exist_ok=True)
    nes=out/'source/nes/src';nes.mkdir(parents=True,exist_ok=True)
    for name in ('recip.inc','rsqrt.inc'):
        shutil.copy2(comparison.ROOT/'console/nes/src'/name,nes/name)
    path=source/'physics_contacts.c'
    path.write_text(path.read_text()+'''
uint8_t fixture_contacts(int32_t cx,int32_t cy,int16_t *out) {
 uint8_t n=contacts(cx,cy),i;
 for(i=0;i<n;++i){out[i*3]=Ct[i].nx;out[i*3+1]=Ct[i].ny;out[i*3+2]=Ct[i].l;}
 return n;
}
''')
    library,gen,_=comparison.build_fixtures(out,args.gen/'riding_constants.h',source,'seams')
    host=C.CDLL(str(library));host.physics_select_level(0)
    host.fixture_contacts.argtypes=[C.c_int32,C.c_int32,C.POINTER(C.c_int16)]
    host.fixture_contacts.restype=C.c_uint8
    ox=C.c_int32.in_dll(host,'physics_level_origin_x').value//64
    oy=C.c_int32.in_dll(host,'physics_level_origin_y').value//64
    result=(C.c_int16*6)();rows=[];failures=[]
    def query(x,y):
        count=host.fixture_contacts(round(x*1024)-ox,round(y*1024)-oy,result)
        return [list(result[i*3:i*3+3]) for i in range(count)]
    # Original128m edge is subdivided into17 pieces. Test both sides and the
    # exact quantized seam, at compressed and just-touching wheel heights.
    for seam in range(1,17):
        x=round((-64+128*seam/17)*1024)/1024
        for offset in (-.35,-.2,-.08,-1/1024,0,1/1024,.08,.2,.35):
            for y in (.395,.399):
                got=query(x+offset,y);rows.append({'x':x+offset,'y':y,'contacts':got})
                if len(got)!=1 or got[0][:2]!=[0,16384]:
                    failures.append(rows[-1])
    corners=[]
    for x,expected_sign in ((64.2,1),(-64.2,-1)):
        got=query(x,.2);corners.append({'x':x,'y':.2,'contacts':got})
        if len(got)!=1 or got[0][0]*expected_sign<=0 or got[0][1]<=0:
            failures.append(corners[-1])
    report={'flat_queries':len(rows),'real_corner_queries':len(corners),
            'failures':failures,'flat':rows,'corners':corners,
            'source':'Production packer and HOST contact implementation',
            'native_companion':'check_physics_contact_loop.py'}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items()if k not in ('flat','corners')}))
    assert not failures,'Artificial seam or genuine corner regression; see report.json'


if __name__=='__main__':main()
