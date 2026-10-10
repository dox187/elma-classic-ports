#!/usr/bin/env python3
"""Read-only native LUT/Horner audit against80-digit mpmath within +/-128rad.

Install mpmath in an isolated path if needed; pass --mpmath-path. This audit
never modifies the candidate or runs the gameplay fidelity corpus.
"""
import argparse,hashlib,json,random,re,shutil,subprocess,sys
from pathlib import Path


def rounded(n,d):
 neg=n<0;n=abs(n);q,r=divmod(n,d);return (-1 if neg else 1)*(q+(2*r>=d))


def signed_width(lo,hi):
 return next(n for n in range(1,129) if -(1<<(n-1))<=lo and hi<(1<<(n-1)))


def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--build',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--mpmath-path',type=Path);ap.add_argument('--output-bits',type=int);ap.add_argument('--dense',type=int,default=64);a=ap.parse_args()
 if a.mpmath_path:sys.path.insert(0,str(a.mpmath_path.resolve()))
 import mpmath as mp
 mp.mp.dps=80;build=a.build.resolve();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
 header=(build/'wide_fixed.h').read_text();table=(build/'wide_trig_table.h').read_text();bits=json.loads((build/'build.json').read_text())['bits'];scale=1<<bits;output_bits=a.output_bits or bits;output_scale=1<<output_bits;cbits_match=re.search(r'TRIG_COEFFICIENT_BITS (\d+)',table);cbits=int(cbits_match[1]) if cbits_match else 48
 pi=int(re.search(r'WIDE_PI_Q48=(\d+)',table)[1]);shift=int(re.search(r'TRIG_SHIFT (\d+)',table)[1]);u_match=re.search(r'TRIG_U_BITS (\d+)',table);ubits=int(u_match[1]) if u_match else 32;carry='++index;u=0;' in header
 coeff=[json.loads('['+line.strip().rstrip(',').replace('{','[').replace('}',']')+']')[0] for line in table.splitlines() if line.startswith('{{')]
 step=1<<(48-shift);quantum=1<<(48-bits);raw=set();limit=128*scale
 def add(value):
  if -limit<=value<=limit:raw.add(value)
 for i in range(len(coeff)):
  for j in range(a.dense):
   anchor=rounded((i*step*a.dense+j*step),a.dense*quantum);add(anchor)
   midpoint_bits=bits-shift-ubits-1
   if midpoint_bits>=0:
    for offset in [-1,0,1]:add(anchor+(1<<midpoint_bits)+offset)
  for k in [-20,-10,0,10,20]:
   for phase in [i*step,pi-i*step,pi+i*step,2*pi-i*step]:
    anchor=rounded(phase+2*pi*k,quantum)
    for offset in [-2,-1,0,1,2]:add(anchor+offset)
 rng=random.Random(840187)
 for _ in range(10000):add(rng.randint(-limit,limit))
 for anchor in [-limit,limit,0,rounded(pi,quantum),rounded(pi//2,quantum)]:
  for offset in [-129,-128,-127,-2,-1,0,1,2,127,128,129]:add(anchor+offset)
 for i in [0,1,400,800,1200,1607]:
  for k in range(-20,21):
   for phase in [i*step,pi-i*step,pi+i*step,2*pi-i*step]:
    anchor=rounded(phase+2*pi*k,quantum)
    for offset in range(-4,5):add(anchor+offset)
 values=sorted(raw);print('Auditing',len(values),'angles at80decimal digits',flush=True)
 for name in ['wide_fixed.h','wide_trig_table.h']:shutil.copy2(build/name,out/name)
 cpp='#include <iostream>\n#include "wide_fixed.h"\nint main(){int64_t raw;while(std::cin>>raw){wide_scalar p[2];wide_native_trig_pair(wide_scalar::from_raw(raw),p);std::cout<<int64_t(wide_round_div(p[0].raw,int64_t(1)<<OUTPUT_SHIFT))<<" "<<int64_t(wide_round_div(p[1].raw,int64_t(1)<<OUTPUT_SHIFT))<<"\\n";}}\n'
 (out/'audit.cpp').write_text(cpp);subprocess.run(['c++','-std=c++17','-O2','-DWIDE_BITS='+str(bits),'-DOUTPUT_SHIFT='+str(bits-output_bits),'-I'+str(out),str(out/'audit.cpp'),'-o',str(out/'audit')],check=True)
 result=subprocess.run([str(out/'audit')],input=''.join(str(x)+'\n' for x in values),capture_output=True,text=True,check=True);actual=[tuple(map(int,line.split())) for line in result.stdout.splitlines()];assert len(actual)==len(values)
 ranges=[[0,0] for _ in range(3)];coeff_ranges=[[0,0] for _ in range(4)];maxabs=[mp.mpf(0),mp.mpf(0)];maxulps=[0,0];worst=[None,None];model_fail=0;carry_cases=0;carry_difference=0;maxcarrydiff=0;largest_index=0
 for row in coeff:
  for function in row:
   for i,v in enumerate(function):coeff_ranges[i][0]=min(coeff_ranges[i][0],v);coeff_ranges[i][1]=max(coeff_ranges[i][1],v)
 def model(index,u):
  output=[]
  for function in coeff[index]:
   h=function[2]+rounded(function[3]*u,1<<ubits);ranges[0][0]=min(ranges[0][0],function[3]);ranges[0][1]=max(ranges[0][1],function[3]);ranges[1][0]=min(ranges[1][0],h);ranges[1][1]=max(ranges[1][1],h)
   h=function[1]+rounded(h*u,1<<ubits);ranges[2][0]=min(ranges[2][0],h);ranges[2][1]=max(ranges[2][1],h);h=function[0]+rounded(h*u,1<<ubits);output.append(rounded(rounded(h,1<<(cbits-bits)),1<<(bits-output_bits)))
  return output
 for count,(x,got) in enumerate(zip(values,actual)):
  phase=x*quantum%(2*pi);ns=phase>pi
  if ns:phase-=pi
  nc=phase>pi//2
  if nc:phase=pi-phase
  if ns:nc=not nc
  index,d=divmod(phase,step);u=rounded(d,1<<(48-shift-ubits));largest_index=max(largest_index,index)
  if u==1<<ubits:
   carry_cases+=1;old=model(index,u);new=model(index+1,0);delta=max(abs(v-w) for v,w in zip(old,new));carry_difference+=delta!=0;maxcarrydiff=max(maxcarrydiff,delta)
   if carry:index+=1;u=0
  expected=model(index,u);expected=[-expected[0] if ns else expected[0],-expected[1] if nc else expected[1]];model_fail+=tuple(expected)!=got
  angle=mp.mpf(x)/scale;refs=[mp.sin(angle),mp.cos(angle)]
  for f in range(2):
   absolute=abs(mp.mpf(got[f])/output_scale-refs[f]);reference_integer=int(mp.floor(abs(refs[f])*output_scale+mp.mpf('.5')))*(-1 if refs[f]<0 else 1);ulps=abs(got[f]-reference_integer);maxulps[f]=max(maxulps[f],ulps)
   if absolute>maxabs[f]:maxabs[f]=absolute;worst[f]={'input_raw':x,'angle':mp.nstr(angle,35),'actual_raw':got[f],'rounded_reference_raw':reference_integer,'error_output_ulps':mp.nstr(absolute*output_scale,30)}
  if count and count%50000==0:print('Reference samples',count,flush=True)
 report={'range_radians':[-128,128],'reference':'mpmath'+mp.__version__+' at80decimal digits; exact integer raw input/scale','angles':len(values),'bits':bits,'coefficient_bits':cbits,'output_bits':output_bits,'remainder_bits':ubits,'carry_in_candidate':carry,'model_mismatches':model_fail,'maximum_absolute_error':{f:mp.nstr(maxabs[i],40) for i,f in enumerate(['sin','cos'])},'maximum_error_in_output_ulps':{f:mp.nstr(maxabs[i]*output_scale,30) for i,f in enumerate(['sin','cos'])},'max_rounded_reference_ulp_difference':dict(zip(['sin','cos'],maxulps)),'worst':dict(zip(['sin','cos'],worst)),'carry_cases':carry_cases,'carry_output_differing_pairs':carry_difference,'maximum_carry_change_output_ulps':maxcarrydiff,'largest_index':largest_index,'table_rows':len(coeff),'coefficient_signed_bits':[signed_width(*r) for r in coeff_ranges],'horner_operand_signed_bits':[signed_width(*r) for r in ranges],'horner_operand_ranges':ranges,'max_product_signed_bits':[signed_width(*r)+ubits for r in ranges],'pi_q48_error_radians':mp.nstr(mp.mpf(pi)/(1<<48)-mp.pi,40),'source_sha256':{str(build/name):hashlib.sha256((build/name).read_bytes()).hexdigest() for name in ['wide_fixed.h','wide_trig_table.h']},'limitations':'Numerical samples, not a proof of global approximation bound or an SNES timing measurement.'}
 (out/'audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return int(model_fail!=0)
if __name__=='__main__':raise SystemExit(main())
