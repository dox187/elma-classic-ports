#!/usr/bin/env python3
"""Cache the identical ordered gravity-vector/mass/G products in private units."""
import argparse,json,re,shutil,subprocess
from pathlib import Path
from wide_probe import ROOT,UNITS
HELPER=r'''
#pragma once
#include "all.h"
inline uint64_t wide_gravity_hits=0,wide_gravity_misses=0,wide_gravity_key_tests=0;
inline uint64_t wide_zero_guard_hits=0,wide_zero_guard_fallbacks=0;
inline bool wide_safe_axle_distance(vekt2 koto){
 static_assert(WIDE_BITS>=4 && WIDE_BITS<=56, "4x bounds and 32x square sum must fit signed64");
 uint64_t x=wide_magnitude(koto.x.raw),y=wide_magnitude(koto.y.raw);
 bool safe=x<4*wide_scalar::scale&&y<4*wide_scalar::scale&&(x>=wide_scalar::scale/4||y>=wide_scalar::scale/4);
 if(safe)++wide_zero_guard_hits;else ++wide_zero_guard_fallbacks;return safe;
}
inline vekt2 wide_gravity_force(vekt2 direction,wide_scalar mass){
 struct item{bool valid=false;int64_t x=0,y=0,m=0,g=0;vekt2 result;};static item cache[16];static unsigned next=0;
 for(auto& c:cache){++wide_gravity_key_tests;if(c.valid&&c.x==direction.x.raw&&c.y==direction.y.raw&&c.m==mass.raw&&c.g==G.raw){++wide_gravity_hits;return c.result;}}
 ++wide_gravity_misses;auto result=direction*mass*G;cache[next]={true,direction.x.raw,direction.y.raw,mass.raw,G.raw,result};next=(next+1)%16;return result;
}
inline void wide_print_gravity_stats(){fprintf(stderr,"WIDE_GRAVITY_STATS {\"hits\":%llu,\"misses\":%llu,\"cache_entry_tests\":%llu,\"zero_guard_hits\":%llu,\"zero_guard_fallbacks\":%llu}\n",(unsigned long long)wide_gravity_hits,(unsigned long long)wide_gravity_misses,(unsigned long long)wide_gravity_key_tests,(unsigned long long)wide_zero_guard_hits,(unsigned long long)wide_zero_guard_fallbacks);}
'''
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--base-build',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--quarter-turn-identity',action='store_true');ap.add_argument('--zero-torque-reaction',action='store_true');ap.add_argument('--guarded-zero-torque',action='store_true');a=ap.parse_args();base=a.base_build.resolve();out=a.out.resolve()
 if out.exists():raise ValueError('Use fresh isolated directory')
 out.mkdir(parents=True)
 for p in base.iterdir():
  if p.is_file() and p.suffix.lower() in ('.h','.cpp'):shutil.copy2(p,out/p.name)
 (out/'wide_gravity_helpers.h').write_text(HELPER)
 p=out/'LEPTET.CPP';s=p.read_text();s,n=re.subn(r'(Vekt2[ij])\*(pmot->kor[124]\.m)\*G',lambda m:'wide_gravity_force('+m[1]+','+m[2]+')',s)
 if n!=15:raise ValueError('Expected15ordered expressions including original commented3, got'+str(n))
 if a.quarter_turn_identity:
  old='vekt2 joirany( cos( pmot->kor1.alfa-K_pip2 ), sin( pmot->kor1.alfa-K_pip2 ) );'
  if s.count(old)!=1:raise ValueError('Expected one original rider orientation')
  s=s.replace(old,'vekt2 joirany( sin( pmot->kor1.alfa ), -cos( pmot->kor1.alfa ) );')
 if a.zero_torque_reaction or a.guarded_zero_torque:
  old='vekt2 Ftestnyom = kotomer*(*pMkerek/absnegyzet(koto));'
  if s.count(old)!=1:raise ValueError('Expected one force reaction expression')
  new='wide_scalar wide_distance_squared=absnegyzet(koto);\n    vekt2 Ftestnyom;\n    if(pMkerek->raw==0){\n        if(wide_distance_squared.raw==0)wide_fail("divide by zero");\n        Ftestnyom=vekt2();\n    }else Ftestnyom=kotomer*(*pMkerek/wide_distance_squared);'
  if a.guarded_zero_torque:
   new='vekt2 Ftestnyom;\n    if(pMkerek->raw==0&&wide_safe_axle_distance(koto)){Ftestnyom=vekt2();}else{\n'+new.replace('    vekt2 Ftestnyom;\n','')+'\n    }'
  s=s.replace(old,new)
 p.write_text('#include "wide_gravity_helpers.h"\n'+s)
 p=out/'BEALLIT.CPP';s=p.read_text();old='gravitacio*pmot->kor1.m*G'
 if s.count(old)!=1:raise ValueError('Expected1ridergravity')
 p.write_text('#include "wide_gravity_helpers.h"\n'+s.replace(old,'wide_gravity_force(gravitacio,pmot->kor1.m)'))
 p=out/'wide_harness.cpp';s=p.read_text().replace('#include "pcphys.h"','#include "pcphys.h"\n#include "wide_gravity_helpers.h"').replace('wide_print_stats("simulation",wide_stats);','wide_print_stats("simulation",wide_stats);wide_print_gravity_stats();');p.write_text(s)
 bits=json.loads((base/'build.json').read_text())['bits'];command=['c++','-std=c++17','-O2','-w','-DWIDE_BITS=%d'%bits,'-I'+str(out),'-I'+str(ROOT/'test'),'-o',str(out/'widecheck'),str(out/'wide_harness.cpp'),str(out/'pcphys.cpp'),*[str(out/name) for name in UNITS]]
 result=subprocess.run(command,capture_output=True,text=True);(out/'compile.txt').write_text(result.stdout+result.stderr);(out/'build.json').write_text(json.dumps({'bits':bits,'command':command,'base_build':str(base),'change':'memoize exact ordered gravity-vector/mass/G product','cache_capacity':16,'quarter_turn_identity':a.quarter_turn_identity,'zero_torque_reaction':a.zero_torque_reaction,'guarded_zero_torque':a.guarded_zero_torque},indent=2)+'\n')
 if result.returncode:print(result.stdout+result.stderr);raise SystemExit(result.returncode)
 print(out/'widecheck')
if __name__=='__main__':main()
