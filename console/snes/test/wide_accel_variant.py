"""Fuse per-step force/mass and torque/inertia in isolated integer sources.

The spring+damper core is a C-compatible checked integer function with exact
rational coefficients and one rounding site. Force outputs are delta velocity;
torque outputs are delta omega. Contact torque uses inertia/mass consistently.
"""
import argparse
from decimal import Decimal, getcontext
import json
import re
from pathlib import Path
import shutil
import subprocess

from wide_unit_variant import replace

getcontext().prec=60


def literal(value):
    # Fixed decimal parser uses128-bit intermediates; eighteen places give
    # far more precision than Q40 and keep numerator*scale safely in range.
    text=format(value,'.18f').rstrip('0').rstrip('.')
    return 'wide_scalar::literal("'+text+'")'


CORE=r'''
#pragma once
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
// Mathematical coefficients: spring74529/2500000; damper273/500.
// All inputs/output are signed48; gumi is Q(GUMI_BITS), rates/output Q40.
// One final nearest-half-away rounding of the combined exact rational sum.
static inline int64_t wa_round(__int128 value,uint64_t divisor) {
 int negative=value<0;if(negative)value=-value;
 __int128 quotient=value/divisor,remainder=value%divisor;
 if(remainder>=divisor-remainder)++quotient;
 if(negative)quotient=-quotient;
 if(quotient<-((__int128)1<<47)||quotient>=((__int128)1<<47)){
  fprintf(stderr,"WIDE_ACCEL_OVERFLOW signed48\n");abort();
 }
 return (int64_t)quotient;
}
static inline int64_t wa_spring_damper(int64_t gumi,int64_t relative_rate,int active) {
 __int128 spring=active?(__int128)gumi*74529*((uint64_t)1<<(40-GUMI_BITS)):0;
 __int128 damper=(__int128)relative_rate*1365000;
 return wa_round(spring+damper,2500000);
}
'''
WRAPPER=r'''
#pragma once
#include "all.h"
#define GUMI_BITS @BITS@
#include "wide_accel_core.h"
static_assert(WIDE_BITS==40,"per-step fused reference requires Q40");
struct wa_stats_t {uint64_t calls=0,active_calls=0,max_gumi=0,max_relative_rate=0;};
inline wa_stats_t wa_stats;
inline wide_scalar wa_component(wide_scalar g,wide_scalar relative,int active) {
 int64_t graw=wide_checked(wide_round_div(g.raw,(__int128)1<<(40-GUMI_BITS)),"gumi conversion");
 if(graw<-(int64_t(1)<<47)||graw>=(int64_t(1)<<47))wide_fail("gumi signed48 range");
 if(relative.raw<-(int64_t(1)<<47)||relative.raw>=(int64_t(1)<<47))wide_fail("relative rate signed48 range");
 ++wa_stats.calls;
 wa_stats.active_calls+=active!=0;
 if(wide_magnitude(graw)>wa_stats.max_gumi)wa_stats.max_gumi=wide_magnitude(graw);
 if(wide_magnitude(relative.raw)>wa_stats.max_relative_rate)wa_stats.max_relative_rate=wide_magnitude(relative.raw);
 return wide_scalar::from_raw(wa_spring_damper(graw,relative.raw,active));
}
inline vekt2 wa_force(vekt2 g,vekt2 relative,int active) {
 return vekt2(wa_component(g.x,relative.x,active),wa_component(g.y,relative.y,active));
}
inline vekt2 wa_opposite_body(vekt2 wheel) {
 return vekt2(wide_scalar::from_raw(wa_round(-(__int128)wheel.x.raw,20)),
              wide_scalar::from_raw(wa_round(-(__int128)wheel.y.raw,20)));
}
inline void wa_print_stats(){fprintf(stderr,"WIDE_ACCEL_STATS {\"calls\":%llu,\"active_calls\":%llu,\"gumi_bits\":%d,\"max_gumi_raw\":%llu,\"max_relative_rate_raw\":%llu}\n",wa_stats.calls,wa_stats.active_calls,GUMI_BITS,wa_stats.max_gumi,wa_stats.max_relative_rate);}
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base',type=Path,default=Path('build/wide-unit-q40'))
    ap.add_argument('--out',type=Path,default=Path('build/wide-accel-q40'))
    ap.add_argument('--gumi-bits',type=int,choices=(32,40),default=40)
    ap.add_argument('--coefficient-bits',type=int,choices=(0,28,30,32),default=0,
                    help='0 uses exact rational coefficients; otherwise an independent coefficient grid')
    a=ap.parse_args()
    base,out=a.base.resolve(),a.out.resolve()
    metadata=json.loads((base/'build.json').read_text())
    rate_bits=metadata['bits']
    if not 32<=a.gumi_bits<=rate_bits<=48:raise ValueError('Invalid force fraction layout')
    if out.exists():raise ValueError('Use a fresh isolated output directory')
    shutil.copytree(base,out,ignore=shutil.ignore_patterns('fidelity','holdout','widecheck'))
    core=CORE
    core=core.replace('Q40','Q'+str(rate_bits)).replace('(40-GUMI_BITS)','('+str(rate_bits)+'-GUMI_BITS)')
    if a.coefficient_bits:
        scale=1<<a.coefficient_bits
        kw=int((Decimal('.0298116')*scale).to_integral_value(rounding='ROUND_HALF_UP'))
        sw=int((Decimal('.546')*scale).to_integral_value(rounding='ROUND_HALF_UP'))
        core=core.replace('gumi*74529','gumi*'+str(kw)).replace('relative_rate*1365000','relative_rate*'+str(sw))
        core=core.replace('wa_round(spring+damper,2500000)','wa_round(spring+damper,'+str(scale)+')')
        core+='\n// Stored coefficients: Q%d spring%d, damper%d; denominator2^%d.\n'%(a.coefficient_bits,kw,sw,a.coefficient_bits)
    (out/'wide_accel_core.h').write_text(core)
    wrapper=WRAPPER.replace('@BITS@',str(a.gumi_bits)).replace('WIDE_BITS==40','WIDE_BITS=='+str(rate_bits)).replace('requires Q40','requires Q'+str(rate_bits)).replace('(40-GUMI_BITS)','('+str(rate_bits)+'-GUMI_BITS)')
    (out/'wide_accel_helpers.h').write_text(wrapper)
    leptet=(out/'LEPTET.CPP').read_text()
    leptet='#include "wide_accel_helpers.h"\n'+leptet
    start=leptet.index('    wide_scalar Fsugar = 0;')
    end=leptet.index('    // Most jon surlodas szamitasa:',start)
    leptet=leptet[:start]+'''    int active = gumi.x < -wide_scalar::literal("0.0001") || gumi.x > wide_scalar::literal("0.0001") ||
                 gumi.y < -wide_scalar::literal("0.0001") || gumi.y > wide_scalar::literal("0.0001");
    *pMtest = active ? -(gumi*forgatas90fokkal(gumis))*'''+literal(Decimal('.298116')/Decimal('60.5'))+''' : wide_scalar(0);
'''+leptet[end:]
    leptet=replace(leptet,'vekt2 Fdamper = korongrelv*Sr;',
                          'vekt2 Fdamper = korongrelv*'+literal(Decimal('.546'))+';')
    leptet=replace(leptet,'else Ftestnyom=kotomer*(*pMkerek/wide_distance_squared);',
                          'else Ftestnyom=kotomer*((*pMkerek*'+literal(Decimal('.032'))+')/wide_distance_squared);')
    leptet=replace(leptet,'*pFkerek = *pFkerek + Fdamper - Ftestnyom;',
                          '*pFkerek = wa_force(gumi,korongrelv,active) - Ftestnyom;')
    leptet=replace(leptet,'*pMtest += -(Fdamper*kotomer);',
                          '*pMtest += -(Fdamper*kotomer)*'+literal(Decimal(10)/Decimal('60.5'))+';')
    leptet=replace(leptet,'*pFtest = *pFtest - Fdamper + Ftestnyom;',
                          '*pFtest = wa_opposite_body(*pFkerek);')
    for name,value in [('gaznyomatek',Decimal('.01788696')/Decimal('.32')),
                       ('fekero',Decimal('.0298116')/Decimal('.32')),
                       ('surlodas',Decimal('.546')/Decimal('.32'))]:
        old={'gaznyomatek':'.01788696','fekero':'.0298116','surlodas':'.546'}[name]
        expression=re.compile(re.escape(name)+r' = wide_scalar::literal\("([^"]+)"\);')
        matches=expression.findall(leptet)
        assert len(matches)==1 and Decimal(matches[0])==Decimal(old)
        leptet=expression.sub(lambda _:name+' = '+literal(value)+';',leptet)
    (out/'LEPTET.CPP').write_text(leptet)
    beallit=(out/'BEALLIT.CPP').read_text()
    beallit=replace(beallit,'wide_scalar Mtm = M + hossz*n90*F;',
                           'wide_scalar Mtm = M*wide_constant_divide(pk->theta,pk->m) + hossz*n90*F;')
    beallit=replace(beallit,'wide_scalar beta = wide_constant_divide(M,pk->theta);','wide_scalar beta = M;')
    beallit=replace(beallit,'vekt2 a = F*(wide_constant_reciprocal(pk->m));','vekt2 a = F;')
    beallit=replace(beallit,'M += F*n90*pk->sugar;',
                           'M = M*wide_constant_divide(pk->theta,pk->m) + F*n90*pk->sugar;')
    beallit=replace(beallit,'wide_scalar thetaszelso = pk->theta+pk->m*hossz*hossz;',
                           'wide_scalar thetaszelso = wide_constant_divide(pk->theta,pk->m)+hossz*hossz;')
    beallit=replace(beallit,'vekt2 Frugo = rugoeroirany*(Drsugar*wide_scalar::literal("5.0"));',
                           'vekt2 Frugo = rugoeroirany*'+literal(Decimal('.0074529'))+';')
    beallit=replace(beallit,'vekt2 Fsurl = relv*Sr*wide_scalar::literal("3.0");',
                           'vekt2 Fsurl = relv*'+literal(Decimal('.0819'))+';')
    beallit=replace(beallit,'vekt2 a = F * (wide_constant_reciprocal(pmot->kor1.m));','vekt2 a = F;')
    (out/'BEALLIT.CPP').write_text(beallit)
    gravity=(out/'wide_gravity_helpers.h').read_text()
    gravity=replace(gravity,'auto result=direction*mass*G;','auto result=direction*G;')
    (out/'wide_gravity_helpers.h').write_text(gravity)
    harness=(out/'wide_harness.cpp').read_text()
    harness='#include "wide_accel_helpers.h"\n'+harness
    harness=replace(harness,'wide_print_stats("simulation",wide_stats);',
                           'wide_print_stats("simulation",wide_stats);wa_print_stats();')
    (out/'wide_harness.cpp').write_text(harness)
    command=[item.replace(str(base),str(out)) for item in metadata['command']]
    result=subprocess.run(command,capture_output=True,text=True)
    (out/'compile.txt').write_text(result.stdout+result.stderr)
    result.check_returncode()
    metadata.update({'command':command,'base_build':str(base),'gumi_bits':a.gumi_bits,'coefficient_bits':a.coefficient_bits,
                     'change':'Fused rational spring/damper; delta-V/delta-omega outputs with mass/inertia folded'})
    (out/'build.json').write_text(json.dumps(metadata,indent=2)+'\n')
    (out/'wide_accel_variant.py').write_bytes(Path(__file__).read_bytes())
    print(out/'widecheck')


if __name__=='__main__':main()
