#!/usr/bin/env python3
"""Add an exact Q8 object prefilter to a frozen complete C Q44 solver.

For nonnegative radius R, |floor(256*x)-floor(256*y)| greater than
floor(256*R)+1 proves |x-y|>R. Rejected objects cannot pass the original
strict rounded squared-distance test. The near path and object order stay
unchanged. Signed Q44 inputs reduce to Q8 values in [-2**27,2**27), so the
coordinate differences and radius limit fit signed32 arithmetic.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


HELPER = r'''
/* Coarse coordinates only reject impossible contacts; never calculate a
 * contact point, normal, force or event. No physical state is quantized. */
static int32_t wp_filter_q8(const wp_scalar* value){
#ifdef WIDE_TARGET_SNES
    union {uint16_t word[2];int32_t value;} result;
    result.word[0]=(value->word[2]>>4)|(value->word[3]<<12);
    result.word[1]=((int16_t)value->word[3])>>4;
    return result.value;
#else
    return (int32_t)(*value>>36);
#endif
}
'''


SEGMENT_HELPER=r'''
static int wp_filter_radius_ok(const wp_scalar* radius){
#ifdef WIDE_TARGET_SNES
    if(radius->word[3])return 0;
    if(radius->word[2]!=1638)return radius->word[2]<1638;
    if(radius->word[1]!=26214)return radius->word[1]<26214;
    return radius->word[0]<=26214;
#else
    return *radius>=0 && *radius<=7036874417766LL;
#endif
}
static int wp_filter_line(const wp_vec* r,const wp_scalar* radius,const wp_line* line){
    int32_t a,b,c,low,high;
    if(!wp_filter_radius_ok(radius))return 0;
    a=wp_filter_q8(&line->r.x);b=wp_filter_q8(&line->wide_endpoint.x);
    low=a<b?a:b;high=a>b?a:b;c=wp_filter_q8(&r->x);
    if(c<low-WP_FILTER_MARGIN||c>high+WP_FILTER_MARGIN)return 1;
    a=wp_filter_q8(&line->r.y);b=wp_filter_q8(&line->wide_endpoint.y);
    low=a<b?a:b;high=a>b?a:b;c=wp_filter_q8(&r->y);
    return c<low-WP_FILTER_MARGIN||c>high+WP_FILTER_MARGIN;
}
'''


def segment_margin(levels):
    """Enclose the proven quantized projection strip and endpoint circles.

    Derive a level-set-specific Q8 padding around the cached endpoint pair.
    This needs no extra ROM bounds or RAM cache. It is a conservative bound,
    not a claim that a rounded unit normal has mathematically unit length.
    """
    maximum=0;count=0;hashes={};radius=7036874417766;quantum=1<<36
    ceil=lambda n,d:-((-n)//d)
    for path in sorted(levels.glob('lev*.json')):
        data=json.loads(path.read_text());assert data['bits']==44
        hashes[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
        for line in data['lines']:
            ex,ey=line[4:6];norm=ex*ex+ey*ey;length=line[10]
            assert norm>0
            for e,n,start,end in zip((ex,ey),(-ey,ex),line[:2],line[6:8]):
                transverse=(radius+1)*abs(n)
                qlo=-e if e>=0 else (length+1)*e
                qhi=(length+1)*e if e>=0 else -e
                lower=start//quantum+(256*(qlo-transverse))//norm-1
                upper=ceil(start,quantum)+ceil(256*(qhi+transverse),norm)+1
                for point in (start,end):
                    lower=min(lower,(point-radius)//quantum-1)
                    upper=max(upper,ceil(point+radius,quantum)+1)
                maximum=max(maximum,min(start,end)//quantum-lower,upper-max(start,end)//quantum)
            count+=1
    if not count:raise ValueError('No exact segment snapshots')
    return {'segments':count,'q8_padding':maximum,'radius_raw':radius,'snapshot_sha256':hashes,
            'proof':'Derived endpoint box encloses the existing exact quantized-strip/endpoint bounds for every exported segment; no runtime state rounding'}


def hoist_controller_globals(source):
    # 816-TCC corrupts helper frame sizes (or crashes) with global declarations
    # interleaved after function bodies. Keep globals first and preserve the
    # order and complete text of every function. Public prototypes are already
    # in wide_port.h; private helpers remain before their callers.
    blocks=[]
    pattern=r'(?m)^(?:static )?(?:int32_t|int|void|wp_scalar|wp_vec|wp_line \*|wp_node \*|wp_object \*) (\w+)\([^\n;{]*\)\s*\{'
    for match in re.finditer(pattern,source):
        depth=1;end=match.end()
        while depth:
            depth+=(source[end]=='{')-(source[end]=='}');end+=1
        blocks.append((match.start(),end))
    declarations=source
    for start,end in reversed(blocks):declarations=declarations[:start]+declarations[end:]
    return declarations+'\n'+'\n'.join(source[start:end] for start,end in blocks)+'\n'


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--segments',action='store_true',help='Also reject impossible segment contacts with an audited endpoint box')
    args=ap.parse_args();base=args.base.resolve();out=args.out.resolve()
    if out.exists():raise ValueError('Use a fresh output directory')
    report=json.loads((base/'build.json').read_text())
    if report['bits']!=44:raise ValueError('The word prefilter currently requires Q44')
    out.mkdir(parents=True)
    for path in base.iterdir():
        if path.is_file() and path.suffix.lower() in ('.c','.h','.cpp','.inc','.json'):
            shutil.copy2(path,out/path.name)
    path=out/'wide_controller.c';source=path.read_text()
    proof=segment_margin(Path(report['levels'])) if args.segments else None
    helpers=HELPER
    if proof:helpers+='\n#define WP_FILTER_MARGIN '+str(proof['q8_padding'])+'L\n'+SEGMENT_HELPER
    source=source.replace('#include "wide_port.h"','#include "wide_port.h"\n'+helpers,1)
    anchor='int wp_utkozikesprite(wp_vec r,wp_scalar sugar){'
    if source.count(anchor)!=1:raise ValueError('Unknown object query declaration')
    source=source.replace(anchor,anchor+'''
wp_scalar max_range=wp_add(sugar,Objektumsugar);
int32_t rx=wp_filter_q8(&r.x),ry=wp_filter_q8(&r.y);
int32_t coarse_range=wp_filter_q8(&max_range),limit=coarse_range+1;
''')
    anchor='wp_vec diff=wp_sub_v(r,(pker)->r);\nwp_scalar maxtav=wp_add(sugar,Objektumsugar);'
    if source.count(anchor)!=1:raise ValueError('Unknown object distance expression')
    source=source.replace(anchor,'''if(coarse_range>=0){
    int32_t dx=rx-wp_filter_q8(&pker->r.x);
    int32_t dy=ry-wp_filter_q8(&pker->r.y);
    if(dx>limit||dx<-limit||dy>limit||dy<-limit)continue;
}
wp_vec diff=wp_sub_v(r,(pker)->r);
wp_scalar maxtav=max_range;''')
    if proof:
        anchor='int wp_gombszakasz(wp_vec r,wp_scalar sugar,wp_line * pv,wp_vec * pt){'
        if source.count(anchor)!=1:raise ValueError('Unknown segment query declaration')
        source=source.replace(anchor,anchor+'\nif(wp_filter_line(&r,&sugar,pv))return 0;')
    path.write_text(hoist_controller_globals(source))
    commands=[[arg.replace(str(base),str(out)) for arg in command]
              for command in report['commands']]
    native=[arg.replace(str(base),str(out)) for arg in report['native_loader_command']]
    native=[arg.replace('wide_level_loader','wide_controller') for arg in native]
    for i,command in enumerate(commands+[native]):
        result=subprocess.run(command,capture_output=True,text=True)
        (out/('filter-compile-%d.txt'%i)).write_text(result.stdout+result.stderr)
        result.check_returncode()
    frames={name:int(size) for name,size in re.findall(r'^\.define\s+(\S+_locals)\s+(\d+)',(out/'wide_controller.ps').read_text(),re.M)}
    if any(size>=8192 for size in frames.values()):raise ValueError('Invalid native stack frame: '+str(frames))
    report.update(commands=commands,base=str(base),change=__doc__,
                  segment_bounds=proof,
                  native_filter_command=native,
                  native_stack_frames=frames,
                  native_loader_command=[arg.replace(str(base),str(out)) for arg in report['native_loader_command']],
                  filter_generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out/'build.json').write_text(json.dumps(report,indent=2)+'\n')
    print(out/'widecheck')


if __name__=='__main__':main()
