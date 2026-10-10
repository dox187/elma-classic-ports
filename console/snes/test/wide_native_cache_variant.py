#!/usr/bin/env python3
"""Restore exact memoization and fold literals in the native word-C facade.

Keys include every input. Hits reuse the identical ordered raw result; misses
call the existing arithmetic unchanged. Constant folding only replaces calls
with exact Q44 word initializers. This is separate from native ROM timings.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
from wide_port_filter_variant import hoist_controller_globals


HELPERS=r'''
static int wp_cache_same(const wp_scalar* a,const wp_scalar* b){
 return a->word[0]==b->word[0]&&a->word[1]==b->word[1]&&
        a->word[2]==b->word[2]&&a->word[3]==b->word[3];
}
static int wp_cache_vec_same(const wp_vec* a,const wp_vec* b){
 return wp_cache_same(&a->x,&b->x)&&wp_cache_same(&a->y,&b->y);
}
wp_scalar wp_wide_constant_reciprocal(wp_scalar a){
 static struct{unsigned valid;wp_scalar key,value;} entries[8];
 static unsigned next;unsigned i;wp_scalar result;
 for(i=0;i<8;++i)if(entries[i].valid&&wp_cache_same(&entries[i].key,&a))return entries[i].value;
 result=wp_div(wp_int(1),a);entries[next].key=a;entries[next].value=result;
 entries[next].valid=1;next=(next+1)&7;return result;
}
wp_vec wp_wide_contact_normal(wp_kor* circle,wp_vec point,wp_scalar* length){
 static struct{unsigned valid;wp_vec r,point,normal;wp_scalar length;} entries[16];
 static unsigned next;unsigned i;wp_vec d,normal;wp_scalar h;
 for(i=0;i<16;++i)if(entries[i].valid&&wp_cache_vec_same(&entries[i].r,&circle->r)&&
    wp_cache_vec_same(&entries[i].point,&point)){*length=entries[i].length;return entries[i].normal;}
 d=wp_sub_v(circle->r,point);h=wp_abs(d);
 normal=wp_scale(wp_sub_v(circle->r,point),wp_div(wp_int(1),h));
 entries[next].r=circle->r;entries[next].point=point;entries[next].normal=normal;
 entries[next].length=h;entries[next].valid=1;next=(next+1)&15;*length=h;return normal;
}
wp_vec wp_wide_gravity_force(wp_vec direction,wp_scalar mass){
 static struct{unsigned valid;wp_vec direction,result;wp_scalar mass,g;} entries[16];
 static unsigned next;unsigned i;wp_vec result;wp_scalar g=*wp_ptr_G();
 for(i=0;i<16;++i)if(entries[i].valid&&wp_cache_vec_same(&entries[i].direction,&direction)&&
    wp_cache_same(&entries[i].mass,&mass)&&wp_cache_same(&entries[i].g,&g))return entries[i].result;
#if WIDE_GRAVITY_MASS_FOLDED
 result=wp_scale(direction,g);
#else
 result=wp_scale(wp_scale(direction,mass),g);
#endif
 entries[next].direction=direction;entries[next].mass=mass;entries[next].g=g;
 entries[next].result=result;entries[next].valid=1;next=(next+1)&15;return result;
}
'''


def remove_definition(source,name):
    match=re.search(r'(?m)^(?:wp_scalar|wp_vec) '+name+r'\([^\n{;]*\)\s*\{',source)
    if not match:raise ValueError('Unknown function '+name)
    depth=1;end=match.end()
    while depth:
        if source[end]=='{':depth+=1
        elif source[end]=='}':depth-=1
        end+=1
    return source[:match.start()]+source[end:]


def fold_literals(source,bits,constants):
    values={};counts={'integer_calls':0,'constant_calls':0}
    def value(raw):
        if raw not in values:values[raw]='wp_folded_'+str(len(values))
        return values[raw]
    def integer(m):counts['integer_calls']+=1;return value(int(m[1])<<bits)
    def constant(m):counts['constant_calls']+=1;return value(constants[int(m[1])])
    source=re.sub(r'\bwp_int\((-?\d+)\)',integer,source)
    source=re.sub(r'\bwp_constant\((\d+)\)',constant,source)
    declarations=[]
    for raw,name in values.items():
        assert -(1<<63)<=raw<(1<<63)
        words=','.join(str((raw>>(16*i))&65535) for i in range(4))
        declarations.append('static const wp_scalar '+name+'={{'+words+'}};')
    source=source.replace('#include "wide_port.h"','#include "wide_port.h"\n'+'\n'.join(declarations),1)
    return source,{**counts,'unique_scalars':len(values),'native_ram_bytes':8*len(values)}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();base=a.port.resolve();out=a.out.resolve()
    if out.exists():raise ValueError('Use a fresh output directory')
    report=json.loads((base/'native_port.json').read_text());bits=report['bits']
    out.mkdir(parents=True)
    for path in base.iterdir():
        if path.is_file() and path.suffix.lower() in ('.c','.cpp','.h','.inc','.json'):shutil.copy2(path,out/path.name)
    path=out/'wide_port_native_math.c';source=path.read_text()
    for name in ('wp_wide_constant_reciprocal','wp_wide_contact_normal','wp_wide_gravity_force'):
        source=remove_definition(source,name)
    path.write_text(source+'\n'+HELPERS)
    raw=re.search(r'wl_constants\[\]\s*=\s*\{([^}]+)',(out/'wide_level_config.h').read_text())[1]
    data=bytes(int(x) for x in raw.split(','));constants=list(struct.unpack('<'+'q'*(len(data)//8),data));folds={}
    for name in ('wide_controller.c','wide_port_native_math.c','wide_level_loader.c'):
        path=out/name;source,folds[name]=fold_literals(path.read_text(),bits,constants)
        if name=='wide_controller.c':source=hoist_controller_globals(source)
        path.write_text(source)
    for kind in ('host_commands','native_commands'):
        commands=[[arg.replace(str(base),str(out)) for arg in cmd] for cmd in report[kind]]
        for index,command in enumerate(commands):
            result=subprocess.run(command,capture_output=True,text=True)
            (out/('cache-'+kind+'-%d.log'%index)).write_text(result.stdout+result.stderr)
            result.check_returncode()
        report[kind]=commands
    report.update(base=str(base),cache_change=__doc__,folded_literals=folds,
                  native_linked=False,generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out/'native_port.json').write_text(json.dumps(report,indent=2)+'\n')
    print(out/'widecheck')


if __name__=='__main__':main()
