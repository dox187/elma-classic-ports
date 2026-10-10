#!/usr/bin/env python3
"""Private exact geometry/constant-reciprocal caches for the wide host kernel."""
import argparse
import json
import re
from pathlib import Path
import shutil
import subprocess

from wide_probe import ROOT, UNITS

HELPER = r'''
#pragma once
#include "all.h"
struct wide_geometry_stats_t {uint64_t normal_hits=0,normal_misses=0,reciprocal_hits=0,reciprocal_misses=0,fixed_divide=0,fixed_divide_mul=0,fixed_divide_correction=0;};
inline wide_geometry_stats_t wide_geometry_stats;
inline wide_scalar wide_constant_reciprocal(wide_scalar value){
 struct item {bool valid=false;int64_t key=0;wide_scalar result;}; static item cache[8];static unsigned next=0;
 for(auto& c:cache)if(c.valid&&c.key==value.raw){++wide_geometry_stats.reciprocal_hits;return c.result;}
 ++wide_geometry_stats.reciprocal_misses;auto result=1/value;cache[next]={true,value.raw,result};next=(next+1)%8;return result;
}
inline wide_scalar wide_constant_divide(wide_scalar numerator,wide_scalar denominator){
 struct item{bool valid=false;int64_t key=0;uint64_t reciprocal=0;};static item cache[8];static unsigned next=0;
 ++wide_geometry_stats.fixed_divide;
 uint64_t d=wide_magnitude(denominator.raw);if(!d)wide_fail("constant divide by zero");
 uint64_t reciprocal=0;bool found=false;
 for(auto& c:cache)if(c.valid&&c.key==denominator.raw){reciprocal=c.reciprocal;found=true;break;}
 if(!found){unsigned __int128 r=((unsigned __int128)wide_scalar::scale<<60)/d;
  if(r>UINT64_MAX)return numerator/denominator;
  reciprocal=(uint64_t)r;cache[next]={true,denominator.raw,reciprocal};next=(next+1)%8;}
 unsigned __int128 n=(unsigned __int128)wide_magnitude(numerator.raw)*wide_scalar::scale;
 unsigned __int128 q=((unsigned __int128)wide_magnitude(numerator.raw)*reciprocal)>>60;
 unsigned __int128 remainder=n-q*d;wide_geometry_stats.fixed_divide_mul+=2;
 while(remainder>=d){remainder-=d;++q;++wide_geometry_stats.fixed_divide_correction;}
 if(remainder>=d-remainder)++q;
 bool negative=(numerator.raw<0)!=(denominator.raw<0);
 return wide_scalar::from_raw(wide_checked(negative?-(__int128)q:(__int128)q,"exact constant reciprocal division"));
}
inline vekt2 wide_contact_normal(kor* circle,vekt2 point,wide_scalar* length){
 struct item {bool valid=false;int64_t x=0,y=0,tx=0,ty=0;wide_scalar h;vekt2 n;};static item cache[16];static unsigned next=0;
 for(auto& c:cache)if(c.valid&&c.x==circle->r.x.raw&&c.y==circle->r.y.raw&&c.tx==point.x.raw&&c.ty==point.y.raw){++wide_geometry_stats.normal_hits;*length=c.h;return c.n;}
 ++wide_geometry_stats.normal_misses;auto h=abs(circle->r-point);auto normal=(circle->r-point)*(1/h);
 cache[next]={true,circle->r.x.raw,circle->r.y.raw,point.x.raw,point.y.raw,h,normal};next=(next+1)%16;*length=h;return normal;
}
inline void wide_print_geometry_stats(){
 fprintf(stderr,"WIDE_GEOMETRY_STATS {\"normal_hits\":%llu,\"normal_misses\":%llu,\"reciprocal_hits\":%llu,\"reciprocal_misses\":%llu,\"fixed_divide\":%llu,\"fixed_divide_multiply\":%llu,\"fixed_divide_correction\":%llu}\n",
 (unsigned long long)wide_geometry_stats.normal_hits,(unsigned long long)wide_geometry_stats.normal_misses,(unsigned long long)wide_geometry_stats.reciprocal_hits,(unsigned long long)wide_geometry_stats.reciprocal_misses,(unsigned long long)wide_geometry_stats.fixed_divide,(unsigned long long)wide_geometry_stats.fixed_divide_mul,(unsigned long long)wide_geometry_stats.fixed_divide_correction);
}
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base-build',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--rider-spring',action='store_true',help='Algebraically cancel rider spring normalization; independently validate')
    a=ap.parse_args();base=a.base_build.resolve();out=a.out.resolve()
    if out.exists() or base==out:raise ValueError('Use a new isolated directory')
    shutil.copytree(base,out)
    (out/'widecheck').unlink(missing_ok=True)
    for name in ['wide_fixed.h','wide_harness.cpp']:
        if not (out/name).exists():shutil.copy2(ROOT/'test'/name,out/name)
    (out/'wide_geometry_helpers.h').write_text(HELPER)
    source=(out/'BEALLIT.CPP').read_text();source='#include "wide_geometry_helpers.h"\n'+source
    pattern=r'wide_scalar hossz = abs\( pk->r\s*-\s*(\*pt|t2|t1) \);\n\tvekt2 n = \(pk->r-\1\)\*\(wide_scalar::literal\("1.0"\)/hossz\);'
    source,replacements=re.subn(pattern,lambda m:'wide_scalar hossz;\n\tvekt2 n = wide_contact_normal(pk, '+m[1]+', &hossz);',source)
    if replacements!=5:raise ValueError('Expected five original contact normal sites, found '+str(replacements))
    if a.rider_spring:
        begin=source.index('\twide_scalar rugoerohossz = abs( rugoeroirany );')
        end=source.index('\n\n\t// Surlodasi',begin)
        source=source[:begin]+'\tvekt2 Frugo = rugoeroirany*(Drsugar*wide_scalar::literal("5.0"));'+source[end:]
    source=source.replace('wide_scalar::literal("1.0")/pk->m','wide_constant_reciprocal(pk->m)').replace('wide_scalar::literal("1.0")/pk->sugar','wide_constant_reciprocal(pk->sugar)').replace('wide_scalar::literal("1.0")/pmot->kor1.m','wide_constant_reciprocal(pmot->kor1.m)')
    source=source.replace('wide_scalar beta = M/pk->theta;','wide_scalar beta = wide_constant_divide(M,pk->theta);')
    (out/'BEALLIT.CPP').write_text(source)
    header=(out/'szakasz.h').read_text();old='vekt2 r, v, egyseg;';assert header.count(old)==1
    (out/'szakasz.h').write_text(header.replace(old,old+'\n\tvekt2 wide_endpoint, wide_normal;'))
    source=(out/'SZAKASZ.CPP').read_text();old='pv->egyseg = egys( pv->v );';assert source.count(old)==1
    (out/'SZAKASZ.CPP').write_text(source.replace(old,old+'\n\tpv->wide_endpoint=pv->r+pv->egyseg*pv->hossz;\n\tpv->wide_normal=forgatas90fokkal(pv->egyseg);'))
    source=(out/'UTKOZES.CPP').read_text();source=source.replace('pv->r+pv->egyseg*pv->hossz','pv->wide_endpoint').replace('forgatas90fokkal( pv->egyseg )','pv->wide_normal');(out/'UTKOZES.CPP').write_text(source)
    source=(out/'wide_harness.cpp').read_text();source=source.replace('#include "pcphys.h"','#include "pcphys.h"\n#include "wide_geometry_helpers.h"')
    source=source.replace('wide_print_stats("simulation",wide_stats);','wide_print_stats("simulation",wide_stats);wide_print_geometry_stats();')
    (out/'wide_harness.cpp').write_text(source)
    build=json.loads((base/'build.json').read_text());bits=build['bits']
    command=['c++','-std=c++17','-O2','-w','-DWIDE_BITS=%d'%bits,'-I'+str(out),'-I'+str(ROOT/'test'),'-o',str(out/'widecheck'),str(out/'wide_harness.cpp'),str(out/'pcphys.cpp'),*[str(out/name) for name in UNITS]]
    (out/'build.json').write_text(json.dumps({'bits':bits,'command':command,'base_build':str(base),'rider_spring':a.rider_spring},indent=2)+'\n')
    result=subprocess.run(command,capture_output=True,text=True);(out/'compile.txt').write_text(result.stdout+result.stderr)
    (out/'geometry_variant.json').write_text(json.dumps({'base':str(base),'bits':build['bits'],'command':command,'contact_normal_cache':'exact raw argument key','constant_divide':'exact quotient with reciprocal and integer remainder correction','thresholds':'unchanged'},indent=2)+'\n')
    if result.returncode:print(result.stdout+result.stderr);raise SystemExit(result.returncode)
    print(out/'widecheck')


if __name__=='__main__':main()
