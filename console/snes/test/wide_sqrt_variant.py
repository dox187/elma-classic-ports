#!/usr/bin/env python3
"""Replace fixed-point gyok's Newton division with an exact residual test.

Original negative and zero branches remain. After nearest integer sqrt r of
N=a.raw*scale, nearest division N/r is r-1, r, or r+1. The final positive
round-half-away average only advances r when N-r*r >= ceil(r/2).
This is an integer-kernel identity, not a change to original PC thresholds.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from wide_probe import ROOT, UNITS

OLD='return wide_scalar::literal(".5")*(x1+a/x1);'
NEW='''// Exactly the original rounded Newton average, without division.
    unsigned __int128 n=(unsigned __int128)a.raw << wide_scalar::fractional_bits;
    unsigned __int128 square=(unsigned __int128)x1.raw*x1.raw;
    if(n>=square && 2*(n-square)>=(uint64_t)x1.raw)
        return wide_scalar::from_raw(x1.raw+1);
    return x1;'''

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base-build',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();base=a.base_build.resolve();out=a.out.resolve()
    if out.exists():raise ValueError('Use a fresh isolated output directory')
    out.mkdir(parents=True)
    for p in base.iterdir():
        if p.is_file() and p.suffix.lower() in ('.h','.cpp'):shutil.copy2(p,out/p.name)
    p=out/'VEKT2.CPP';s=p.read_text()
    if s.count(OLD)!=1:raise ValueError('Expected one original gyok Newton average')
    p.write_text(s.replace(OLD,NEW))
    bits=json.loads((base/'build.json').read_text())['bits']
    command=['c++','-std=c++17','-O2','-w','-DWIDE_BITS=%d'%bits,'-I'+str(out),'-I'+str(ROOT/'test'),'-o',str(out/'widecheck'),str(out/'wide_harness.cpp'),str(out/'pcphys.cpp'),*[str(out/name) for name in UNITS]]
    result=subprocess.run(command,capture_output=True,text=True)
    (out/'compile.txt').write_text(result.stdout+result.stderr)
    (out/'build.json').write_text(json.dumps({'bits':bits,'command':command,'base_build':str(base),'change':'exact gyok Newton residual identity','extra_raw_multiply_per_gyok':1},indent=2)+'\n')
    if result.returncode:print(result.stdout+result.stderr);raise SystemExit(result.returncode)
    print(out/'widecheck')
if __name__=='__main__':main()
