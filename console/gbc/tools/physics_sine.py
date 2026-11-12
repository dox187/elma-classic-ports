"""Tabulate the existing integer Sintab interpolation exactly, without floats.

Four complete 16 KiB banks 16..19 hold separate positive/negative quarter waves.
Negative interpolation rounds downward; negating the positive table loses one
unit for many phases. Both reflected quarters and every endpoint are verified.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

BASE=Path(__file__).resolve().parents[1]


def read_sintab(source):
    match=re.search(r'\bSintab\s*\[\s*257\s*\]\s*=\s*\{(.*?)\};',Path(source).read_text(),re.S)
    if not match:raise ValueError('Missing original 257-entry Sintab')
    values=[int(v)for v in re.findall(r'-?\d+',match[1])]
    if len(values)!=257 or values[0]!=0 or values[-1]!=0:raise ValueError('Invalid Sintab layout')
    return values


def interpolate(table,angle):
    angle&=65535;i=angle>>8;fraction=angle&255
    return table[i]+((table[i+1]-table[i])*fraction>>8)


def generate(source,out):
    source=Path(source);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    table=read_sintab(source)
    positive=[interpolate(table,t)for t in range(16384)]
    negative=[interpolate(table,32768+t)for t in range(16384)]
    for angle in range(65536):
        phase=angle&32767
        if phase>16384:phase=32768-phase
        value=(-16384 if angle&32768 else 16384)if phase==16384 else(negative if angle&32768 else positive)[phase]
        if value!=interpolate(table,angle):raise AssertionError(('Quarter reflection changed interpolation',angle,value))
    records=[]
    for bank in range(16,20):
        values=(positive if bank<18 else negative)[(bank&1)*8192:(bank&1)*8192+8192]
        data=b''.join(value.to_bytes(2,'little',signed=True)for value in values)
        name='physics_sine_%d'%bank
        rows=[','.join(str(value)for value in values[i:i+16])for i in range(0,len(values),16)]
        (out/(name+'.c')).write_text('#include <stdint.h>\n#pragma bank %d\n'%bank+'const int16_t '+name+'[]={\n'+',\n'.join(rows)+'\n};\n')
        records.append({'bank':bank,'entries':len(values),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    report={'source':'original Sintab integer interpolation','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'phases_verified':65536,'bytes':65536,'banks':records,'endpoint_values':[16384,-16384],
            'negative_values_differ_from_negated_positive':sum(n!=-p for p,n in zip(positive,negative))}
    (out/'physics-sine-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Exact sine: 64 KiB in MBC5 banks 16..19; all 65536 phases verified')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=BASE/'src/physics_math.c')
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();generate(a.source,a.out)
