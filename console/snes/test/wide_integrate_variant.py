"""Isolate compact integration at actual PC integration sites.

The force/contact solver remains Q36. Accepted tested layout uses signed48
Q32 positions/unwrapped angles and signed48 Q40 instantaneous per-step rates.
Use --state-bits32 --velocity-bits40 --omega-bits40 --rate-width48. Historical
defaults reproduce the rejected Q29 holdout experiment. PC velocity is
converted for this host adapter; native code would store per-step units.
"""
import argparse
import json
import re
from pathlib import Path
import shutil
import subprocess


HEADER = r'''
#pragma once
#include "wide_fixed.h"
struct compact_stats_t {
 uint64_t position=0, angle=0, max_position_raw=0, max_angle_raw=0;
 uint64_t max_velocity_raw=0, max_omega_raw=0;
};
inline compact_stats_t compact_stats;
inline wide_scalar compact_integrate(wide_scalar state,wide_scalar velocity,
                                     wide_scalar dt,bool angle) {
 constexpr unsigned state_bits=COMPACT_STATE_BITS;
 unsigned rate_bits=angle?37:34;
 int64_t p=wide_checked(wide_round_div(state.raw,(__int128)1<<(WIDE_BITS-state_bits)),"compact state conversion");
 // Full integer product before rounding: avoids an unnecessary Q36 rounding.
 int64_t v=wide_checked(wide_round_div((__int128)velocity.raw*dt.raw,
                  (__int128)1<<(2*WIDE_BITS-rate_bits)),"compact per-step conversion");
 if((__int128)p<-((__int128)1<<(COMPACT_STATE_WIDTH-1))||(__int128)p>=((__int128)1<<(COMPACT_STATE_WIDTH-1)))wide_fail("compact state range");
 if(v<-(int64_t(1)<<(COMPACT_RATE_WIDTH-1))||v>=(int64_t(1)<<(COMPACT_RATE_WIDTH-1)))wide_fail("compact rate range");
 auto& count=angle?compact_stats.angle:compact_stats.position;
 auto& maxstate=angle?compact_stats.max_angle_raw:compact_stats.max_position_raw;
 auto& maxrate=angle?compact_stats.max_omega_raw:compact_stats.max_velocity_raw;
 ++count;if(wide_magnitude(p)>maxstate)maxstate=wide_magnitude(p);
 if(wide_magnitude(v)>maxrate)maxrate=wide_magnitude(v);
 int64_t delta=wide_checked(wide_round_div(v,(__int128)1<<(rate_bits-state_bits)),"compact rounded rate");
 int64_t result=wide_checked((__int128)p+delta,"compact addition");
 if((__int128)result<-((__int128)1<<(COMPACT_STATE_WIDTH-1))||(__int128)result>=((__int128)1<<(COMPACT_STATE_WIDTH-1)))wide_fail("compact integration overflow");
 return wide_scalar::from_raw(wide_checked((__int128)result*(int64_t(1)<<(WIDE_BITS-state_bits)),"compact decode"));
}
inline void compact_print_stats() {
 fprintf(stderr,"COMPACT_STATS {\"position\":%llu,\"angle\":%llu,\"max_position_raw\":%llu,\"max_angle_raw\":%llu,\"max_velocity_raw\":%llu,\"max_omega_raw\":%llu}\n",
 compact_stats.position,compact_stats.angle,compact_stats.max_position_raw,
 compact_stats.max_angle_raw,compact_stats.max_velocity_raw,compact_stats.max_omega_raw);
}
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base',type=Path,default=Path('build/wide-trig-q36'))
    ap.add_argument('--out',type=Path,default=Path('build/wide-compact-q36'))
    ap.add_argument('--velocity-bits',type=int,default=34)
    ap.add_argument('--omega-bits',type=int,default=37)
    ap.add_argument('--state-bits',type=int,choices=(29,32,36,38,40,44),default=29)
    ap.add_argument('--state-width',type=int,choices=(48,56,64),default=48)
    ap.add_argument('--rate-width',type=int,choices=(40,48),default=40)
    ap.add_argument('--step-units',action='store_true',help='Input engine already stores per-step rates; no compatibility encoding')
    a=ap.parse_args()
    base,out=a.base.resolve(),a.out.resolve()
    if out.exists():raise ValueError('Use a fresh isolated output directory')
    shutil.copytree(base,out,ignore=shutil.ignore_patterns('fidelity','holdout','widecheck'))
    config='#define COMPACT_STATE_BITS %d\n#define COMPACT_STATE_WIDTH %d\n#define COMPACT_RATE_WIDTH %d\n'%(a.state_bits,a.state_width,a.rate_width)
    helper=HEADER.replace('angle?37:34','angle?%d:%d'%(a.omega_bits,a.velocity_bits))
    if a.step_units:
        assert a.velocity_bits==a.omega_bits==json.loads((base/'build.json').read_text())['bits']
        start=helper.index(' // Full integer product')
        end=helper.index('\n if((__int128)p<',start)
        helper=helper[:start]+'\n int64_t v=velocity.raw; // Engine already stores per-step rate; no encoding.'+helper[end:]
    (out/'wide_compact.h').write_text(config+helper)
    source=(out/'BEALLIT.CPP').read_text()
    source,count=re.subn(r'(#include\s*"all.h")',r'\1\n#include "wide_compact.h"',source,count=1,flags=re.I)
    assert count==1
    replacements={
       'pk->alfa += pk->omega*dt;':'pk->alfa = compact_integrate(pk->alfa,pk->omega,dt,true);',
       'pk->r = pk->r + pk->v*dt;':'''pk->r.x=compact_integrate(pk->r.x,pk->v.x,dt,false);
        pk->r.y=compact_integrate(pk->r.y,pk->v.y,dt,false);''',
       'pmot->vezetor = pmot->vezetor + pmot->vezetov*dt;':'''pmot->vezetor.x=compact_integrate(pmot->vezetor.x,pmot->vezetov.x,dt,false);
    pmot->vezetor.y=compact_integrate(pmot->vezetor.y,pmot->vezetov.y,dt,false);'''}
    if a.step_units:
        replacements={old.replace('*dt',''):new for old,new in replacements.items()}
    for old,new in replacements.items():
        expected=1 if old.startswith('pmot') else 2
        if source.count(old)!=expected:raise ValueError('Unexpected integration site count')
        source=source.replace(old,new)
    (out/'BEALLIT.CPP').write_text(source)
    harness=(out/'wide_harness.cpp').read_text()
    harness=harness.replace('#include "all.h"','#include "all.h"\n#include "wide_compact.h"',1)
    anchor='wide_print_stats("simulation",wide_stats);'
    assert harness.count(anchor)==1
    harness=harness.replace(anchor,anchor+'compact_print_stats();')
    (out/'wide_harness.cpp').write_text(harness)
    metadata=json.loads((base/'build.json').read_text())
    command=[item.replace(str(base),str(out)) for item in metadata['command']]
    result=subprocess.run(command,capture_output=True,text=True)
    (out/'compile.txt').write_text(result.stdout+result.stderr)
    result.check_returncode()
    metadata.update({'command':command,'base':str(base),
        'change':'Compact%dQ%d state and%dQ%d/Q%d rate integration only; angles unwrapped'%(a.state_width,a.state_bits,a.rate_width,a.velocity_bits,a.omega_bits),
        'integration_rate_units':'step' if a.step_units else 'pc_with_compatibility_encoding',
        'source_sites':{'free_and_one_contact_body':4,'rider':1}})
    (out/'build.json').write_text(json.dumps(metadata,indent=2)+'\n')
    (out/'wide_integrate_variant.py').write_bytes(Path(__file__).read_bytes())
    print(out/'widecheck')


if __name__=='__main__':main()
