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
    names = ('C_H_X', 'C_H_Y', 'C_RREST')
    if any(coefficients[name][0] != coefficients[name][1] for name in names):
        raise ValueError('Pose coefficients vary between substeps')
    factors = [coefficients[name][0] for name in names]
    factors.extend((fixed['Q24_ANCHOR_X'], fixed['Q24_ANCHOR_Y']))

    def products(value):
        return tuple((value * scale + (1 << 23)) >> 24 for scale in factors)

    # A 1600-unit head period includes a half tie at either endpoint.
    # Use the negative endpoint on negative pages and the positive one on
    # positive pages. The interior rows work for both signs. Rest and both
    # anchor products each advance by an integer every 25 trig units.
    pages = []
    for high in range(-64, 65):
        start = high * 256
        head = (start + 800) % 1600 - 800
        if high < 0 and head + 255 >= 800:
            head -= 1600
        rest = start % 25
        pages.append((head, rest, products(start - head)[:2], products(start - rest)[2:]))
    first_head = min(page[0] for page in pages)
    last_head = max(page[0] for page in pages) + 255
    heads = [(hx + 8, hy + 64) for hx, hy, *_ in map(products, range(first_head, last_head + 1))]
    # Both signs here are unsigned residuals against their own signed bases.
    # The sine uses -rest and +ay. The cosine uses +rest and -ay.
    suspension = [(rest, 128 - rest, ax, ay, 4096 - ay)
                  for _, _, rest, ax, ay in map(products, range(25 + 255))]

    def array(kind, name, records):
        body = ',\n'.join('{' + ','.join(map(str, row)) + '}' for row in records)
        return f'const {kind} {name}[]={{\n{body}\n}};\n'

    if any(not (0 <= hx <= 255 and 0 <= hy <= 255) for hx, hy in heads):
        raise ValueError('Pose head residual exceeds its unsigned byte')
    for rest, neg_rest, ax, ay, neg_ay in suspension:
        if (min(rest, neg_rest, ax, ay, neg_ay) < 0 or max(rest, neg_rest) > 255 or
                max(ax, ay, neg_ay) > 65535):
            raise ValueError('Pose suspension residual exceeds its packed width')

    text = 'static ' + array('pose_head_row_t', 'pose_heads', heads)
    text += 'static ' + array('pose_suspension_row_t', 'pose_suspension', suspension)
    for sine in (False, True):
        output = []
        for high, (head, row, (hx, hy), (rest, ax, ay)) in enumerate(pages, -64):
            x_bias, y_bias = hx - 8, hy - 64
            rest_bias = -rest - 128 if sine else rest
            ay_bias = ay if sine else -ay - 4096
            if not all(-32768 <= n <= 32767 for n in (x_bias, y_bias, rest_bias)):
                raise ValueError('Pose head or rider base exceeds signed16')
            if not all(-(1 << 23) <= n < (1 << 23) for n in (ax, ay_bias)):
                raise ValueError('Pose anchor base exceeds signed24')
            output.append((f'pose_heads+{head-first_head}', f'pose_suspension+{row}',
                           x_bias, y_bias, rest_bias, ax & 65535, ax >> 16,
                           ay_bias & 65535, ay_bias >> 16))
            for low in range(256):
                value = high * 256 + low
                if value > 16384:
                    break
                dx, dy = heads[head - first_head + low]
                rp, rn, xa, yp, yn = suspension[row + low]
                decoded = (x_bias + dx, y_bias + dy, rest_bias + (rn if sine else rp),
                           ax + xa, ay_bias + (yp if sine else yn))
                hxq, hyq, rq, axq, ayq = products(value)
                if decoded != (hxq, hyq, -rq if sine else rq, axq, ayq if sine else -ayq):
                    raise ValueError(f'Pose table loses precision at {value}')
        text += array('pose_page_t', 'riding_pose_' + ('sin' if sine else 'cos') + '_pages', output)
    (out / 'physics_pose_rows.h').write_text(text)


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
    def array(name, values):
        return 'const uint8_t ' + name + '[]={\n' + ','.join(map(str, values)) + '};\n'

    text = ''
    for pos, width in enumerate((2, 3, 4, 4)):
        pairs = [piece(pos, byte) for byte in range(256)]
        if pos == 0:
            # Fold the round-to-nearest bias into this byte's remainder.
            pages = [[(r + 640) & 255 for _, r in pairs], [(r + 640) >> 8 for _, r in pairs]]
        else:
            if any(r & 255 for _, r in pairs):
                raise ValueError('Upper angle digits must have byte-aligned remainders')
            pages = [[r >> 8 for _, r in pairs]]
        if pos < 2 and any(q >= 1 << (width * 8) for q, _ in pairs):
            raise ValueError('Angular quotient exceeds its stored width')
        pages.extend([(q >> (8 * digit)) & 255 for q, _ in pairs] for digit in range(width))
        text += array(f'riding_angle_digit{pos}', [v for page in pages for v in page])
    # With high word 0xffff, the two upper digits together subtract 65536.
    q, r = divmod(-65536 * 27007, 1280)
    text += array('riding_angle_negative', [r >> 8] + [(q >> (8 * i)) & 255 for i in range(4)])
    text += array('riding_angle_carry', [(n // 5) & 255 for n in range(-64, 80)])
    for pos in range(3):
        terms = [(b - 256 if pos == 2 and b >= 128 else b) * 27007 for b in range(256)]
        shifts = (8, 16) if pos == 0 else (0, 8, 16)
        text += array(f'riding_angle_frac{pos}', [(v >> shift) & 255 for shift in shifts for v in terms])
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
        manifest['geometry_format'] = 'signed-pose-ranked-angle-pages-v1'
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
