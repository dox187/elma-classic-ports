#!/usr/bin/env python3
"""Integer convergence/width probe for an exact corrected Q44 contact normal.

This is a host prototype, not a native-cycle or PC-fidelity claim. Narrow Newton
iterates estimate distance and direction; final exact square/residue correction
returns the frozen wp_abs residual-corrected length and exact raw64 division.
No float is used.
"""
import argparse
import json
import math
from pathlib import Path
import random


def rounded_shift(n, bits):
    if bits <= 0: return n << -bits
    return (n + (1 << (bits-1))) >> bits


def rounded_div(n, d):
    q,r=divmod(n,d)
    return q+int(2*r>=d)


def seed_table():
    seeds=[]
    for i in range(256):
        n,d=512<<16,515+6*i
        q=math.isqrt(n//d)
        q += int(4*n>=d*(2*q+1)**2)
        seeds.append(q)
    return seeds


SEEDS=seed_table()
CORRECTION_SEEDS=[rounded_div(1<<31,(i<<8)+128) for i in range(128,256)]


def residual_jump(residue, divisor, half, widths,method='table'):
    """Coarse quotient from a 256B leading-mantissa table; exact cleanup follows."""
    if method=='divider':
        shift=divisor.bit_length()-8
        numerator=abs(residue)>>shift
        denominator=divisor>>shift
        bucket=widths.setdefault('correction_divider',{'numerator_bits':0,'denominator_bits':0,'seven_bit_divisors':0,'fallback_jumps':0})
        if numerator>65535:
            numerator>>=1;denominator>>=1;bucket['seven_bit_divisors']+=1
        if numerator>65535:
            bucket['fallback_jumps']+=1
            return 0
        q,r=divmod(numerator,denominator)
        delta=(q+1)//2 if half else q+int(2*r>=denominator)
        bucket['numerator_bits']=max(bucket['numerator_bits'],numerator.bit_length())
        bucket['denominator_bits']=max(bucket['denominator_bits'],denominator.bit_length())
        return delta*(-1 if residue<0 else 1)
    shift=divisor.bit_length()-16
    mantissa=divisor>>shift
    coefficient=CORRECTION_SEEDS[(mantissa>>8)-128]
    reduced=residue>>shift
    product=reduced*coefficient
    bits=32 if half else 31
    delta=rounded_shift(abs(product),bits)*(-1 if product<0 else 1)
    bucket=widths.setdefault('correction',{'reduced_operand_bits':0,'product_bits':0})
    bucket['reduced_operand_bits']=max(bucket['reduced_operand_bits'],abs(reduced).bit_length())
    bucket['product_bits']=max(bucket['product_bits'],abs(product).bit_length())
    return delta


def estimate(n, widths, estimate_fraction=48):
    """Return root estimate and reciprocal sqrt at the selected precision."""
    exponent=((n.bit_length()-1)//2)*2
    index=min(255,((n-(1<<exponent))*256)//(3<<exponent))
    r=SEEDS[index]
    previous=8
    for fraction in (16,32,estimate_fraction):
        scale=1<<fraction
        m=rounded_shift(n,exponent-fraction)
        r <<= fraction-previous
        products=(r*r,)
        square=rounded_shift(products[0],fraction)
        products+=(m*square,)
        term=3*scale-rounded_shift(products[1],fraction)
        products+=(r*term,)
        r=rounded_shift(products[2],fraction+1)
        for name,a,b,p in (('square',r,r,products[0]),('scaled_square',m,square,products[1]),('update',r,term,products[2])):
            # Record actual product bits; operands are diagnostic estimates.
            bucket=widths.setdefault(str(fraction),{}).setdefault(name,{'product_bits':0})
            bucket['product_bits']=max(bucket['product_bits'],p.bit_length())
        previous=fraction
    m=rounded_shift(n,exponent-estimate_fraction)
    root=rounded_shift(m*r,2*estimate_fraction-exponent//2)
    return root,r,exponent


def normalized(dx,dy,fraction,widths,estimate_fraction=48,corrections=None,correction='linear'):
    """Mirror separate rounded scalar squares, sqrt, then Q44 divisions."""
    square=rounded_shift(dx*dx,fraction)+rounded_shift(dy*dy,fraction)
    n=square<<fraction
    if n==0: return 0,0,0,0,0
    root,r,exponent=estimate(n,widths,estimate_fraction)
    distance_adjust=0
    residue=n-root*root
    distance_jump=0
    if correction!='linear':
        distance_jump=residual_jump(residue,root,True,widths,correction)
        residue-=distance_jump*(2*root+distance_jump)
        root+=distance_jump
    # One wide verification product, then only exact additions/subtractions.
    while residue<0:
        residue+=2*root-1;root-=1;distance_adjust+=1
    while residue>=2*root+1:
        residue-=2*root+1;root+=1;distance_adjust+=1
    if residue>root:
        residue-=2*root+1;root+=1
    # Match the frozen wp_abs Newton residual correction after nearest sqrt.
    # This is deliberately retained instead of assuming sqrt alone is wp_abs.
    if residue>=0 and 2*residue>=root:root+=1
    normals=[];normal_adjust=0;normal_jumps=0
    for raw in (dx,dy):
        magnitude=abs(raw)
        numerator=magnitude<<fraction
        q=rounded_shift(magnitude*r,estimate_fraction+exponent//2-fraction)
        residue=numerator-q*root
        if correction!='linear':
            delta=residual_jump(residue,root,False,widths,correction)
            residue-=delta*root;q+=delta;normal_jumps+=abs(delta)
        while residue<0:q-=1;residue+=root;normal_adjust+=1
        while residue>=root:q+=1;residue-=root;normal_adjust+=1
        q+=int(2*residue>=root)
        normals.append(-q if raw<0 else q)
    if corrections is not None:
        corrections.append((distance_adjust,normal_adjust,abs(distance_jump),normal_jumps))
    return root,*normals,distance_adjust,normal_adjust


def run(count, estimate_fraction=48, domain='wide',correction='linear'):
    rng=random.Random(413089)
    fraction=44
    unit=1<<fraction
    component_limit=4*unit if domain=='wide' else unit//2
    edges=(-component_limit+1,-component_limit//2,-1,0,1,component_limit//2,component_limit-1)
    cases=[(x,y) for x in edges for y in edges]
    for _ in range(count):
        # Guard mirrors measured contact domain; tiny vectors use wide fallback.
        x=rng.randrange(-component_limit,component_limit);y=rng.randrange(-component_limit,component_limit)
        if x*x+y*y >= (unit//64)**2:cases.append((x,y))
    failures=0;fallback=0;maxdist=0;maxnormal=0;widths={};corrections=[]
    for x,y in cases:
        if x*x+y*y<(unit//64)**2:
            fallback+=1;continue
        root,nx,ny,dc,nc=normalized(x,y,fraction,widths,estimate_fraction,corrections,correction)
        target=(rounded_shift(x*x,fraction)+rounded_shift(y*y,fraction))<<fraction
        reference=math.isqrt(target)
        reference+=int(target-reference*reference>reference)
        residue=target-reference*reference
        if residue>=0 and 2*residue>=reference:reference+=1
        expected=[rounded_div(abs(raw)<<fraction,reference)*(-1 if raw<0 else 1) for raw in (x,y)]
        if (root,nx,ny)!=(reference,*expected):failures+=1
        maxdist=max(maxdist,dc);maxnormal=max(maxnormal,nc)
    def distribution(index):
        values=sorted(c[index] for c in corrections)
        histogram={}
        for value in values:histogram[str(value)]=histogram.get(str(value),0)+1
        return {'histogram':histogram,'median':values[len(values)//2],
                'p95':values[(len(values)-1)*95//100],
                'p99':values[(len(values)-1)*99//100],'max':values[-1],
                'mean':sum(values)/len(values)}
    return {'cases':len(cases),'failures':failures,'fallback_cases':fallback,'input_domain':domain,
            'correction_method':correction,'correction_seed_bytes':256 if correction=='table' else 0,
            'correction_distribution':{'distance':distribution(0),'normals_combined':distribution(1),
                                      'distance_jump_magnitude':distribution(2),'normal_jump_magnitude_combined':distribution(3)},
            'hypothetical_bounded_path':{'max_distance_iterations':256,'max_normal_iterations_combined':64,
                'exceeded_budget_cases':sum(c[0]>256 or c[1]>64 for c in corrections),
                'on_exceeded_budget':'leave output unchanged and call exact wide fallback'},
            'max_distance_floor_adjustments':maxdist,'max_normal_floor_adjustments':maxnormal,
            'seed_bytes':512,'newton_fractions':[16,32,estimate_fraction],
            'newton_products_per_vector':9,'newton_product_widths':widths,
            'native_cycles_measured':False,
            'contract':'Q44 raw offsets |x|,|y|<4m, length>=1/64m; frozen wp_abs scalar-square/nearest-sqrt/Newton-residual correction and exact Q44 division'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--count',type=int,default=100000)
    p.add_argument('--estimate-fraction',type=int,choices=(40,44,48),default=48,
                   help='Internal estimate precision; final corrected output remains Q44')
    p.add_argument('--domain',choices=('wide','contact'),default='wide',
                   help='contact samples offsets within +/-0.5m; wide within +/-4m')
    p.add_argument('--correction',choices=('linear','table','divider'),default='linear')
    p.add_argument('--out',type=Path,default=Path('build/wide-normalize/probe.json'))
    args=p.parse_args();report=run(args.count,args.estimate_fraction,args.domain,args.correction)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return int(bool(report['failures']))
if __name__=='__main__':raise SystemExit(main())
