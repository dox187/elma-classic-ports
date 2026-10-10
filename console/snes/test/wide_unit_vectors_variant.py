#!/usr/bin/env python3
"""Probe narrower normalized vectors while retaining wide state arithmetic."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from wide_probe import ROOT,UNITS


def change(path,old,new):
    source=path.read_text()
    if source.count(old)!=1:raise ValueError('Unexpected anchor in '+str(path)+': '+old)
    path.write_text(source.replace(old,new))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--bits',type=int,default=32)
    a=ap.parse_args();base=a.base.resolve();out=a.out.resolve()
    if out.exists():raise ValueError('Use a fresh output directory')
    out.mkdir(parents=True)
    for p in base.iterdir():
        if p.is_file() and p.suffix.lower() in ('.h','.cpp'):shutil.copy2(p,out/p.name)
    bits=json.loads((base/'build.json').read_text())['bits']
    if not 24<=a.bits<=bits:raise ValueError('Expected a narrower24..WIDE_BITS precision')
    helper='''inline wide_scalar wide_unit_quantize(wide_scalar value){
    constexpr int64_t quantum=int64_t(1)<<(WIDE_BITS-UNIT_BITS);
    return wide_scalar::from_raw(wide_checked(wide_round_div(value.raw,quantum)*quantum,"normalized vector precision"));
}
'''.replace('UNIT_BITS',str(a.bits))
    header=out/'wide_fixed.h'
    change(header,'inline wide_scalar sin(wide_scalar x){return wide_trig(x,false);}',helper+'inline wide_scalar sin(wide_scalar x){return wide_unit_quantize(wide_trig(x,false));}')
    change(header,'inline wide_scalar cos(wide_scalar x){return wide_trig(x,true);}','inline wide_scalar cos(wide_scalar x){return wide_unit_quantize(wide_trig(x,true));}')
    change(out/'VEKT2.CPP','return a*(1/abs( a ));','auto unit=a*(1/abs(a));return vekt2(wide_unit_quantize(unit.x),wide_unit_quantize(unit.y));')
    change(out/'VEKT2.CPP','\tx *= recabs;\n\ty *= recabs;','\tx = wide_unit_quantize(x*recabs);\n\ty = wide_unit_quantize(y*recabs);')
    change(out/'wide_geometry_helpers.h','auto normal=(circle->r-point)*(1/h);','auto normal=(circle->r-point)*(1/h);normal.x=wide_unit_quantize(normal.x);normal.y=wide_unit_quantize(normal.y);')
    cmd=['c++','-std=c++17','-O2','-w','-DWIDE_BITS='+str(bits),'-I'+str(out),'-I'+str(ROOT/'test'),'-o',str(out/'widecheck'),str(out/'wide_harness.cpp'),str(out/'pcphys.cpp'),*[str(out/n) for n in UNITS]]
    p=subprocess.run(cmd,capture_output=True,text=True);(out/'compile.txt').write_text(p.stdout+p.stderr);p.check_returncode()
    (out/'build.json').write_text(json.dumps({'bits':bits,'command':cmd,'base_build':str(base),'change':__doc__,'unit_vector_bits':a.bits},indent=2)+'\n');print(out/'widecheck')


if __name__=='__main__':main()
