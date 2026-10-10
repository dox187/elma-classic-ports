#!/usr/bin/env python3
"""Build the complete C solver with the native word-array arithmetic facade.

The host shim substitutes independently-proven raw64 assembly primitives,
so full-corpus checks test the actual word control/adapter before native link.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parent.parent

SHIM=r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
static int64_t get(const uint16_t* p){int64_t r;memcpy(&r,p,8);return r;}
static __int128 rounddiv(__int128 a,__int128 b){int neg=(a<0)!=(b<0);if(a<0)a=-a;if(b<0)b=-b;__int128 q=a/b,r=a%b;if(r>=b-r)++q;return neg?-q:q;}
static void put(__int128 r,uint16_t* out,uint16_t* status){if(r<INT64_MIN||r>INT64_MAX){*status=1;return;}int64_t value=(int64_t)r;memcpy(out,&value,8);*status=0;}
void wide_mul64(const uint16_t*a,const uint16_t*b,uint16_t f,uint16_t*out,uint16_t*status){put(rounddiv((__int128)get(a)*get(b),(__int128)1<<f),out,status);}
void wide_div64(const uint16_t*a,const uint16_t*b,uint16_t f,uint16_t*out,uint16_t*status){if(!get(b)){*status=2;return;}put(rounddiv((__int128)get(a)*((__int128)1<<f),get(b)),out,status);}
void wide_sqrt64(const uint16_t*a,uint16_t f,uint16_t*out,uint16_t*status){int64_t x=get(a);if(x<0){*status=2;return;}unsigned __int128 n=(unsigned __int128)x<<f,rem=n,r=0,bit=(unsigned __int128)1<<126;while(bit>rem)bit>>=2;while(bit){if(rem>=r+bit){rem-=r+bit;r=(r>>1)+bit;}else r>>=1;bit>>=2;}if(n-r*r>r)++r;put(r,out,status);}
void wp_native_host_abort(void){fprintf(stderr,"NATIVE_WORD_DOMAIN\n");abort();}
'''


def run(command,path):
    result=subprocess.run(command,capture_output=True,text=True)
    path.write_text(result.stdout+result.stderr)
    if result.returncode:print(result.stdout+result.stderr);result.check_returncode()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--loaded',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();base=args.loaded.resolve();out=args.out.resolve()
    if out.exists():raise ValueError('Use a fresh output directory')
    out.mkdir(parents=True)
    for p in base.iterdir():
        if p.is_file() and p.suffix.lower() in ('.c','.h','.cpp','.inc'):shutil.copy2(p,out/p.name)
    config=(out/'wide_math_config.h').read_text()
    bits=int(re.search(r'#define WIDE_PORT_BITS (\d+)',config)[1])
    if bits not in (40,44):raise ValueError('Native facade currently supports Q40/Q44')
    if '#define WIDE_HAS_ACCEL 0' not in config:raise ValueError('First native port requires unfused reference equations')
    shutil.copy2(ROOT/'test/wide_port_native_math.c',out/'wide_port_native_math.c')
    (out/'native_host_shim.c').write_text(SHIM)
    # Emit bank-sized plain word tables. The exact quarter endpoint is handled
    # by the adapter; all4096 stored samples preserve the frozen Q48 table.
    table=(out/'wide_trig_table.h').read_text()
    pi=int(re.search(r'WIDE_PI_Q48=(\d+)',table)[1])
    words=lambda n:','.join(str((n>>(16*i))&65535) for i in range(4))
    header=['#pragma once','#include <stdint.h>','static const uint16_t wp_native_pi[4]={'+words(pi)+'};']
    for kind in ('sin','cos'):
        values=[int(s) for s in re.search(r'wide_'+kind+r'_q48\[\]=\{([^}]+)',table)[1].split(',')]
        for chunk in range(8):
            name='wp_native_'+kind+'_'+str(chunk)
            header.append('extern const uint16_t '+name+'[512][4];')
            (out/(name+'.c')).write_text('#include <stdint.h>\nconst uint16_t '+name+'[512][4]={'+','.join('{'+words(v)+'}' for v in values[chunk*512:(chunk+1)*512])+'};\n')
    header+=['static const uint16_t* wp_native_trig_row(unsigned index,int cosine){unsigned slot=index&511;switch(index>>9){']
    for chunk in range(8):header.append('case '+str(chunk)+':return cosine?wp_native_cos_'+str(chunk)+'[slot]:wp_native_sin_'+str(chunk)+'[slot];')
    header+=['default:return wp_native_sin_0[0];}}']
    (out/'wide_native_trig_words.h').write_text('\n'.join(header)+'\n')
    # The flat loader ABI stays word-based on host, rather than reinterpret
    # bridging a class. Only JSON-marshalling sees int64/double.
    adapter=(out/'wide_level_adapter.cpp').read_text()
    adapter=adapter.replace('static wide_scalar scalar(wp_scalar x){return wide_scalar::from_raw(x);}',
        'static int64_t host_raw(wp_scalar x){int64_t v;memcpy(&v,x.word,8);return v;}\nstatic wp_scalar host_word(int64_t x){wp_scalar v;memcpy(v.word,&x,8);return v;}\nstatic wide_scalar scalar(wp_scalar x){return wide_scalar::from_raw(host_raw(x));}')
    adapter=adapter.replace('wp_pc_step(input,dt.raw)','wp_pc_step(input,host_word(dt.raw))')
    adapter=adapter.replace('return {v.x.raw,v.y.raw};','return {host_word(v.x.raw),host_word(v.y.raw)};')
    adapter=adapter.replace('c->alfa=s.alfa.raw;c->omega=s.omega.raw;','c->alfa=host_word(s.alfa.raw);c->omega=host_word(s.omega.raw);')
    (out/'wide_level_adapter.cpp').write_text(adapter)
    sources=['wide_controller','wide_level_loader','wide_port_native_math','native_host_shim']+['wp_native_'+k+'_'+str(i) for k in ('sin','cos') for i in range(8)]
    commands=[]
    for name in sources:
        command=['cc','-std=c11','-O2','-Wall','-DWIDE_TARGET_SNES=1','-DWP_NATIVE_HOST=1','-I'+str(out),'-c',str(out/(name+'.c')),'-o',str(out/(name+'.o'))]
        commands.append(command);run(command,out/('compile-host-'+name+'.txt'))
    levels=json.loads((base/'build.json').read_text())['levels']
    command=['c++','-std=c++17','-O2','-w','-DWIDE_TARGET_SNES=1','-DWIDE_BITS='+str(bits),'-DWIDE_LEVEL_DIRECTORY='+json.dumps(levels),'-I'+str(out),'-I'+str(ROOT/'test'),'-o',str(out/'widecheck'),str(out/'wide_harness.cpp'),str(out/'wide_level_adapter.cpp')]+[str(out/(name+'.o')) for name in sources]
    commands.append(command);run(command,out/'compile-host-link.txt')
    toolkit=Path.home()/'.local/share/elma-snes/pvsneslib-4.6.0/pvsneslib/devkitsnes'
    native=[]
    for name in ['wide_controller','wide_level_loader','wide_port_native_math']+['wp_native_'+k+'_'+str(i) for k in ('sin','cos') for i in range(8)]:
        command=[str(toolkit/'bin/816-tcc'),'-Wall','-F','-DWIDE_TARGET_SNES=1','-I'+str(toolkit/'include'),'-I'+str(out),'-c',str(out/(name+'.c')),'-o',str(out/(name+'.ps'))]
        native.append(command);run(command,out/('compile-native-'+name+'.txt'))
    (out/'native_port.json').write_text(json.dumps({'bits':bits,'base':str(base),'host_commands':commands,'native_commands':native,'native_linked':False,'performance':'Generic exact arithmetic is a correctness fallback, not a60FPS backend'},indent=2)+'\n')
    print(out/'widecheck')


if __name__=='__main__':main()
