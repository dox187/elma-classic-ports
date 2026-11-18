#!/usr/bin/env python3
"""Generate exact signed Q24 coefficient tables for the scheduled GBC core."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

def table(m):
 pages=[]
 # Keep each coefficient at 29 pages, with the second starting at $5d00.
 # The rounded low byte initializes the complete 56-bit accumulator.
 # Higher nodes omit their identically zero low product bytes.
 for node,bias in ((0,1<<23),(1,0),(1,-65536*m),(2,0),(3,0)):
  rows=[[]for _ in range(7-node)]
  for byte in range(256):
   value=(byte-256 if node==3 and byte>=128 else byte)<<(8*node)
   raw=((value*m+bias)&((1<<56)-1)).to_bytes(7,'little')
   for j in range(node,7):rows[j-node].append(raw[j])
  pages.extend(bytes(row)for row in rows)
 metadata=bytearray(256)
 for index,value in enumerate((-65536,-16777216)):
  q,f=divmod(value*m+(1<<23),1<<24)
  metadata[index*7:index*7+7]=f.to_bytes(3,'little')+(q&0xffffffff).to_bytes(4,'little')
 low=-(1<<31)*(1<<24)-(1<<23)
 high=(1<<31)*(1<<24)-1-(1<<23)
 ceildiv=lambda a,b:-((-a)//b)
 if m>0:lo,hi=ceildiv(low,m),high//m
 elif m<0:lo,hi=ceildiv(high,m),low//m
 else:lo,hi=-(1<<31),(1<<31)-1
 lo=max(-(1<<31),lo);hi=min((1<<31)-1,hi)
 metadata[14]=int(lo>-(1<<31)or hi<(1<<31)-1)
 metadata[15:19]=lo.to_bytes(4,'little',signed=True)
 metadata[19:23]=hi.to_bytes(4,'little',signed=True)
 metadata[23]=int(m<0)
 return b''.join(pages)+metadata

USED = ('C_ELLIPSE','C_NEW','C_BRAKE_GW','C_OMS','C_FRIC_W','C_OLD',
        'C_RREST','C_ROLL_W','C_LANDING_EXTRA','C_RIDER_F','C_FREE',
        'C_RIDER_S','C_ROLL_T','C_SPRING_FW','C_H_Y','C_BRAKE_A',
        'C_ROLL_DW','C_REACT','C_FRIC_T','C_H_X','C_SPRING_T',
        'C_SEAT_NX','C_ROLL_DV','C_BRAKE_W','C_SEAT_NY')
def generate(constants,out,first_bank):
    raw=constants.read_bytes()
    def unit(name):
        match=re.search(r'^#define '+name+r' ([\d.eE+-]+)$',raw.decode(),re.M)
        if not match:raise ValueError('Missing scheduled unit metadata: '+name)
        return float(match[1])
    q=lambda value:math.floor(value*(1<<24)+.5)
    # Match the canonical operation order: quantize the time ratio before
    # applying the fixed position/angle scale. Anchors retain F precision.
    fixed={'Q24_ANCHOR_X':q(.85*16),'Q24_ANCHOR_Y':q(.6*16),
           'Q24_MOVE':q(unit('PH_REMAINDER_TIME')/unit('PH_VELOCITY_UNIT_TIME'))*4,
           'Q24_ANGLE':q(unit('PH_REMAINDER_TIME')/unit('PH_ANGULAR_UNIT_TIME'))*128}
    coefficients={name:[int(a),int(b)] for name,a,b in re.findall(
        r'q24_(C_\w+)\[2\]=\{(-?\d+),(-?\d+)\}',raw.decode())}
    missing=set(USED)-coefficients.keys()
    if missing:raise ValueError('Missing scheduled coefficients: '+str(sorted(missing)))
    values=sorted({v for k in USED for v in coefficients[k]}|set(fixed.values()))
    if any(not -(1<<31)<=v<(1<<31) for v in values):
        raise ValueError("Q24 coefficients must fit signed32")
    index={v:i for i,v in enumerate(values)}
    count=(len(values)+1)//2
    if first_bank<256 or first_bank+count-1>507:
        raise ValueError('Q24 tables must stay in physical banks256..507')
    out.mkdir(parents=True,exist_ok=True)
    for old in out.glob('physics_q24_table_*.c'):old.unlink()
    tables=[]
    for offset in range(count):
        bank=first_bank+offset
        data=b''.join(table(m) for m in values[offset*2:offset*2+2])
        name=f'physics_q24_table_{bank}.c';tables.append(name)
        (out/name).write_text('#include <stdint.h>\n#pragma bank '+str(bank)+
            '\nconst uint8_t physics_q24_table_'+str(bank)+'[]={\n'+
            ','.join(map(str,data))+'\n};\n')
    header=['#ifndef PHYSICS_Q24_COEFFICIENTS_H','#define PHYSICS_Q24_COEFFICIENTS_H',
            '#include <stdint.h>','int32_t q24_apply(int32_t,uint8_t);']
    definitions=[]
    for name in sorted(USED):
        header.append('extern const uint8_t q24_index_'+name+'[2];')
        definitions.append('const uint8_t q24_index_'+name+'[2]={'+
            ','.join(str(index[v]) for v in coefficients[name])+'};')
    for name,value in fixed.items():header.append('#define '+name+' '+str(index[value]))
    header.append('#endif')
    (out/'physics_q24_coefficients.h').write_text('\n'.join(header)+'\n')
    (out/'physics_q24_dispatch.c').write_text('#ifdef __SDCC\n#include "physics_q24.h"\n'
        'const uint8_t q24_first_bank_low='+str(first_bank&255)+';\n'
        +'\n'.join(definitions)+'\n#endif\n')
    manifest={'kind':'q24-table-v2','first_bank':first_bank,'last_bank':first_bank+count-1,
        'constants_sha256':hashlib.sha256(raw).hexdigest(),'coefficient_values':values,
        'coefficient_count':len(values),'tables':tables,
        'dispatch':'physics_q24_dispatch.c','header':'physics_q24_coefficients.h'}
    (out/'physics_q24_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--constants',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--first-bank',type=int,default=481)
    a=p.parse_args();print(json.dumps(generate(a.constants,a.out,a.first_bank)))
if __name__=='__main__':main()
