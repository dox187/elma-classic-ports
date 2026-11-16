"""Exact fixed-coefficient KMUL lookup, following SNES quotient/residue math.

For signed16 x=256*h+l, split its rounded product into a signed32 high
quotient, unsigned16 low quotient and one residue carry. Every input is
verified against the unmodified integer formula. General inputs use the
existing wide implementation; physical coefficients are never changed.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

FIRST_BANK=252
BANK_COUNT=4
NODE_BYTES=2048


def coefficients(path):
    text=Path(path).read_text();pairs={}
    for name,m in re.findall(r'^#define (\w+)_M (\d+)\s*$',text,re.M):
        match=re.search(r'^#define '+re.escape(name)+r'_E (\d+)\s*$',text,re.M)
        if not match:raise ValueError('Missing exponent for '+name)
        pair=int(m),int(match[1])
        if not(0<=pair[0]<=255 and 1<=pair[1]<=16):raise ValueError(('Invalid coefficient',name,pair))
        pairs.setdefault(pair,[]).append(name)
    if not pairs or len(pairs)>BANK_COUNT*8:raise ValueError('Expected between 1 and 32 unique physical coefficients')
    return pairs


def uniform_node(m,e):
    pages=[bytearray(256)for _ in range(8)]
    den=1<<max(0,e-8)
    for byte in range(256):
        high=byte if byte<128 else byte-256
        high_product=high*m*256
        high_q=high_product>>e
        high_r=((high_product% (1<<e))>>8)+256-den
        low_product=byte*m+(1<<(e-1))
        low_q=low_product>>e
        low_r=(low_product% (1<<e))>>8
        for i,value in enumerate((high_q&0xffffffff).to_bytes(4,'little')):pages[i][byte]=value
        pages[4][byte]=high_r
        pages[5][byte]=low_q&255;pages[6][byte]=low_q>>8
        pages[7][byte]=low_r
    # High quotient words and low quotient words are contiguous for SM83.
    high=b''.join(bytes(pages[i][byte]for i in range(4))for byte in range(256))
    low=b''.join(bytes((pages[5][byte],pages[6][byte]))for byte in range(256))
    result=high+pages[4]+low+pages[7]
    assert len(result)==NODE_BYTES
    for x in range(-32768,32768):
        lo=x&255;hi=(x>>8)&255
        hq=int.from_bytes(result[hi*4:hi*4+4],'little',signed=True)
        lq=int.from_bytes(result[1280+lo*2:1282+lo*2],'little')
        carry=(result[1024+hi]+result[1792+lo])>>8
        assert hq+lq+carry==(x*m+(1<<(e-1)))>>e,(x,m,e)
    return result


def node(m,e):
    den=1<<max(0,e-8);period=den//math.gcd(m,den)
    if period>4:return uniform_node(m,e),0,period
    width=4 if e<8 else 2
    high=b''.join(((h if h<128 else h-256)*m*256>>e).to_bytes(width,'little',signed=True)for h in range(256))
    correction=b''.join(((lo*m+(residue*m%den)*256+(1<<(e-1)))>>e).to_bytes(2,'little')
                        for residue in range(period)for lo in range(256))
    data=high+correction
    for x in range(-32768,32768):
        hi=(x>>8)&255;lo=x&255
        hq=int.from_bytes(data[hi*width:hi*width+width],'little',signed=True)
        offset=256*width+((hi&(period-1))*256+lo)*2
        cq=int.from_bytes(data[offset:offset+2],'little')
        assert hq+cq==(x*m+(1<<(e-1)))>>e,(x,m,e)
    return data,(8 if width==4 else 4)|((period-1)<<4),period


def array(name,data):
    rows=[','.join(map(str,data[i:i+32]))for i in range(0,len(data),32)]
    return 'const uint8_t '+name+'[]={\n'+',\n'.join(rows)+'\n};\n'


def generate(constants,out,first_bank=FIRST_BANK):
    constants=Path(constants);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    if not(0<first_bank<=512-BANK_COUNT) or (first_bank&255)+BANK_COUNT>256:
        raise ValueError('Coefficient banks must fit within one MBC5 high-bank half')
    reservations=[]
    for directory in sorted({constants.parent.resolve(),out.resolve()}):
        for filename,key,limit in(('level_manifest.json','last_bank',first_bank-1),('physics_bank_manifest.json','next_free_bank',first_bank)):
            path=directory/filename
            if path.is_file():
                value=json.loads(path.read_text())[key]
                if value>limit:raise ValueError('Level data overlaps reserved coefficient banks: '+str(path))
                reservations.append({'manifest':filename,key:value})
    pairs=coefficients(constants);banks=[bytearray(16384)for _ in range(BANK_COUNT)]
    records=[];bank_index=0;cursor=0
    for i,((m,e),names)in enumerate(sorted(pairs.items())):
        data,mode,period=node(m,e)
        if cursor+len(data)>16384:bank_index+=1;cursor=0
        if bank_index>=BANK_COUNT:raise ValueError('Coefficient nodes exceed reserved banks %d..%d'%(first_bank,first_bank+BANK_COUNT-1))
        bank=first_bank+bank_index
        banks[bank_index][cursor:cursor+len(data)]=data
        records.append({'m':m,'e':e,'names':names,'bank':bank,'address':0x4000+cursor,'bytes':len(data),
                        'mode':'uniform'if not mode else('quotient16'if mode&4 else'quotient32'),
                        'residue_period':period,'descriptor':bank_index|mode,'sha256':hashlib.sha256(data).hexdigest()})
        cursor+=len(data)
    (out/'physics_coefficient_meta.c').unlink(missing_ok=True)
    header=['#ifndef GBC_PHYSICS_COEFFICIENT_CALLS_H','#define GBC_PHYSICS_COEFFICIENT_CALLS_H','#include <stdint.h>']
    calls=['; Generated exact coefficient entries: no runtime coefficient search.','.module physics_coefficient_calls',
           '.globl _riding_coefficient_bank_lo, _riding_coefficient_bank_hi',
           '_riding_coefficient_bank_lo = %d'%(first_bank&255),
           '_riding_coefficient_bank_hi = %d'%(first_bank>>8),'.area _CODE']
    for record in records:
        packed=(record['descriptor']<<8)|(record['address']>>8)
        for name in record['names']:header.append('int32_t riding_coeff32_%s(int32_t x) __sdcccall(0);'%name)
        calls += ['_riding_coeff32_%s::'%name for name in record['names']]
        calls += [' ld bc,#%d'%packed,' ld de,#%d'%((record['e']<<8)|record['m']),' jp _riding_coeff32_known']
        for name in record['names']:header.append('int16_t riding_coeff16_%s(int16_t x) __sdcccall(0);'%name)
        calls += ['_riding_coeff16_%s::'%name for name in record['names']]
        calls += [' ld bc,#%d'%(packed|0x8000),' jp _riding_coefficients_narrow']
    header+=['#endif','']
    (out/'physics_coefficient_calls.h').write_text('\n'.join(header))
    (out/'physics_coefficient_calls.s').write_text('\n'.join(calls)+'\n')
    for path in out.glob('physics_coefficient_*.c'):
        path.unlink()
    for bank,data in enumerate(banks,first_bank):
        (out/('physics_coefficient_%d.c'%bank)).write_text('#include <stdint.h>\n#pragma bank %d\n'%bank+array('physics_coefficient_%d'%bank,data))
    report={'method':'exact high quotient + small-period correction, with general residue carry fallback','constants_sha256':hashlib.sha256(constants.read_bytes()).hexdigest(),
        'unique_coefficients':len(records),'verified_inputs_per_coefficient':65536,'verified_inputs':len(records)*65536,
        'first_bank':first_bank,'last_bank':first_bank+BANK_COUNT-1,'rom_table_bytes':BANK_COUNT*16384,
        'banks':[{'bank':first_bank+i,'sha256':hashlib.sha256(data).hexdigest()}for i,data in enumerate(banks)],'payload_bytes':sum(r['bytes']for r in records),'rom0_entry_bytes':15*len(records),'level_reservations_checked':reservations,'coefficients':records}
    (out/'physics-coefficient-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Exact KMUL coefficient tables: %d coefficients, %d checked inputs, banks %d..%d'%(len(records),len(records)*65536,first_bank,first_bank+BANK_COUNT-1))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--constants',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--first-bank',type=int,default=FIRST_BANK)
    a=p.parse_args();generate(a.constants,a.out,a.first_bank)
