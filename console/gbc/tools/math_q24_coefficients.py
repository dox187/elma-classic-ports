#!/usr/bin/env python3
"""Generate exact signed Q24 coefficient tables for the scheduled GBC core."""
import argparse
from bisect import bisect_left
import hashlib
import json
import math
from pathlib import Path
import re

def table(m):
 pages=[]
 # Keep each coefficient at 32 pages, with the second starting at $6000.
 # The low-byte quotient fits signed16, so its two sign bytes are implicit.
 # The rounded low byte initializes the complete 56-bit accumulator.
 # Higher nodes omit their identically zero low product bytes.
 for node,bias in ((0,1<<23),(1,0),(1,-65536*m),(2,0),(3,0)):
  rows=[[]for _ in range((5 if node==0 else 7)-node)]
  for byte in range(256):
   value=(byte-256 if node==3 and byte>=128 else byte)<<(8*node)
   raw=((value*m+bias)&((1<<56)-1)).to_bytes(7,'little')
   for j in range(node,5 if node==0 else 7):rows[j-node].append(raw[j])
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
 # Direct negative-byte results (-255..-1) also fit signed16.
 # Slot zero is unused: -256 takes the complete narrow path.
 negative=[bytearray() for _ in range(5)]
 for byte in range(256):
  raw=(((byte-256)*m+(1<<23))&((1<<40)-1)).to_bytes(5,'little')
  for j in range(5):negative[j].append(raw[j])
 return b''.join(pages)+metadata+b''.join(negative)

USED = ('C_ELLIPSE','C_NEW','C_BRAKE_GW','C_OMS','C_FRIC_W','C_OLD',
        'C_RREST','C_ROLL_W','C_LANDING_EXTRA','C_RIDER_F','C_FREE',
        'C_RIDER_S','C_ROLL_T','C_SPRING_FW','C_H_Y','C_BRAKE_A',
        'C_ROLL_DW','C_REACT','C_FRIC_T','C_H_X','C_SPRING_T',
        'C_SEAT_NX','C_ROLL_DV','C_BRAKE_W','C_SEAT_NY')

def write_pose_tables(out, coefficients, fixed):
    # On the Q14 sine domain every 1600 inputs add the same integer vector.
    # Prove the decomposition for these exact generated constants, including
    # negative half ties, before using the small table on the cartridge.
    period = 1600
    names = ('C_H_X', 'C_H_Y', 'C_RREST')
    if any(coefficients[name][0] != coefficients[name][1] for name in names):
        raise ValueError('Pose coefficients vary between substeps')
    factors = [coefficients[name][0] for name in names] + [fixed['Q24_ANCHOR_X'], fixed['Q24_ANCHOR_Y']]
    def products(value):
        return tuple((value * factor + (1 << 23)) >> 24 for factor in factors)
    rows = [products(value) for value in range(period)]
    blocks = [products(block * period) for block in range(16384 // period + 1)]
    def array(type_name, name, records):
        body = ',\n'.join('{' + ','.join(map(str, record)) + '}' for record in records)
        return f'static const {type_name} {name}[]={{\n{body}\n}};\n'
    # Extend only far enough for a low byte of 255 on the last page.
    pages = [divmod(high * 256, period) for high in range(65)]
    end = max(row for _, row in pages) + 256
    extended = rows + [products(i) for i in range(period, end)]
    if any(not 0 <= n <= limit for row in extended for n, limit in zip(row, (255, 255, 65535, 65535, 65535))):
        raise ValueError('Pose coefficient exceeds the packed row width')
    for value in range(-16384, 16385):
        mag = abs(value)
        block, first = pages[mag >> 8]
        row = extended[first + (mag & 255)]
        decoded = tuple((a + b) * (-1 if value < 0 else 1) for a, b in zip(row, blocks[block]))
        if decoded != products(value):
            raise ValueError(f'Pose table loses precision at {value}')
    (out / 'physics_pose_rows.h').write_text(
        array('pose_row_t', 'pose_rows', extended) + array('pose_values_t', 'pose_blocks', blocks)
        + 'const pose_page_t riding_pose_pages[]={\n'
        + ',\n'.join(f'{{pose_rows+{row},pose_blocks+{block}}}' for block, row in pages)
        + '\n};\n')


def write_rider_tables(out, coefficients):
    """Rank byte remainders so one comparison reproduces the rounded sum."""
    unit = 1 << 24
    pages = []
    for name in ('C_RIDER_S', 'C_RIDER_F'):
        for scale in coefficients[name]:
            low = [divmod(b * scale, unit) for b in range(256)]
            fractions = sorted(remainder for _, remainder in low)
            ranks = [bisect_left(fractions, r) for _, r in low]
            high = []
            for raw_high in range(256):
                signed_high = raw_high if raw_high < 128 else raw_high - 256
                whole, remainder = divmod(signed_high * 256 * scale + unit // 2, unit)
                threshold = bisect_left(fractions, unit - remainder)
                # A threshold of 256 never carries. Encode the same sum
                # with a zero threshold (always carries) and a lower base.
                high.append((whole - 1, 0) if threshold == 256 else (whole, threshold))
            if any(not 0 <= q <= 65535 for q, _ in low):
                raise ValueError('Rider low product exceeds two bytes')
            for v in range(-32768, 32768):
                q, threshold = high[(v >> 8) & 255]
                result = q + low[v & 255][0] + (ranks[v & 255] >= threshold)
                if result != (v * scale + unit // 2) // unit or not -(1 << 23) <= result < (1 << 23):
                    raise ValueError(f'Inexact signed rider product at {v}')
            pages.extend((ranks, [q & 255 for q, _ in low], [q >> 8 for q, _ in low],
                          [t for _, t in high]))
            for shift in (0, 8, 16):
                pages.append([(q >> shift) & 255 for q, _ in high])
    output = out / 'physics_rider_rows.c'
    output.write_text('#pragma bank 2\nconst unsigned char riding_rider_rows[]={\n'
                      + ',\n'.join(','.join(map(str, row)) for row in pages) + '\n};\n')
    return hashlib.sha256(output.read_bytes()).hexdigest()


def write_angle_tables(out, oms):
    # For the remainder substep each signed omega unit advances 27007/1280
    # phase units. Divide per byte, then combine all remainders before rounding.
    def piece(pos, byte):
        if pos == 3 and byte >= 128:
            byte -= 256
        return divmod((byte << (pos * 8)) * 27007, 1280)
    def array(type_name, name, values):
        return 'static const ' + type_name + ' ' + name + '[]={\n' + ','.join(map(str, values)) + '};\n'
    text = ''
    for pos in range(4):
        text += array('uint32_t', f'whole{pos}', [f'{piece(pos, b)[0] & 0xffffffff}UL' for b in range(256)])
    text += array('uint16_t', 'low_remainder', [piece(0, b)[1] for b in range(256)])
    for pos in (1, 3):
        text += array('uint8_t', f'high_remainder{pos}', [piece(pos, b)[1] >> 8 for b in range(256)])
    assert all(piece(1, b)[1] == piece(2, b)[1] for b in range(256))
    # floor((f+640+r0)/256) + r1/256 + r2/256 + r3/256 is in [-51,72].
    text += array('int8_t', 'carry_units', [n // 5 for n in range(-64, 80)])
    # Five parallel product-byte pages feed a base-256 multiply of the
    # complete Q24 body angular velocity. Both substeps use the same scale.
    if oms[0] != oms[1] or not 0x40000100 <= oms[0] < 0x80000000:
        raise ValueError('Recheck the body angular velocity saturation bounds')
    pages = [(value * oms[0] >> shift) & 255 for shift in range(0, 40, 8)
             for value in range(256)]
    text += 'const uint8_t riding_oms_product[]={\n' + ','.join(map(str, pages)) + '};\n'
    (out / 'physics_angle_rows.h').write_text(text)


def generate(constants,out,first_bank, *, include_pose=True):
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
    if include_pose:
        write_pose_tables(out, coefficients, fixed)
        write_angle_tables(out, coefficients['C_OMS'])
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
    manifest={'kind':'q24-table-v3','first_bank':first_bank,'last_bank':first_bank+count-1,
        'constants_sha256':hashlib.sha256(raw).hexdigest(),'coefficient_values':values,
        'coefficient_count':len(values),'tables':tables,
        'dispatch':'physics_q24_dispatch.c','header':'physics_q24_coefficients.h'}
    if include_pose:
        manifest['rider_rows_sha256'] = write_rider_tables(out, coefficients)
        manifest['geometry_sha256'] = {name: hashlib.sha256((out/name).read_bytes()).hexdigest()
                                       for name in ('physics_pose_rows.h', 'physics_angle_rows.h')}
    (out/'physics_q24_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--constants',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--first-bank',type=int,default=481)
    a=p.parse_args();print(json.dumps(generate(a.constants,a.out,a.first_bank)))
if __name__=='__main__':main()
