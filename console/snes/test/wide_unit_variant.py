"""Build a true per-step-unit integer PC solver in private source copies.

Velocity/omega are stored as PC velocity*dt and PC omega*dt. Force/torque
are dt²-scaled, so beallit updates and position/angle integration are adds.
Original contact/search/turn/brake/jump branches remain in place. Only JSON
serialization converts speed units (step velocity*80); no solver conversion.
"""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import re
import shutil
import subprocess


DT=Decimal('0.00546')


def literal(value):
    return 'wide_scalar::literal("'+format(value,'f')+'")'


def replace(source,old,new,count=1):
    if source.count(old)!=count:
        raise ValueError('Unexpected hunk count: '+old+' ('+str(source.count(old))+')')
    return source.replace(old,new)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base',type=Path,default=Path('build/wide-optimized-guard-q36'))
    ap.add_argument('--out',type=Path,default=Path('build/wide-unit-q40'))
    ap.add_argument('--bits',type=int,default=40)
    a=ap.parse_args()
    base,out=a.base.resolve(),a.out.resolve()
    if out.exists():raise ValueError('Use a fresh isolated output directory')
    shutil.copytree(base,out,ignore=shutil.ignore_patterns('fidelity','holdout','widecheck'))
    pc=(out/'pcphys.cpp').read_text()
    coefficients={
        'Elszakadasisebhat':('0.01',Decimal('.01')*DT),
        'G':('10.0',Decimal(10)*DT*DT),
        'Drsugar':('10000.0',Decimal(10000)*DT*DT),
        'Drtang':('10000.0',Decimal(10000)*DT*DT),
        'Sr':('1000.0',Decimal(1000)*DT),
    }
    for name,(old,value) in coefficients.items():
        pc=replace(pc,name+' = wide_scalar::literal("'+old+'");',name+' = '+literal(value)+';')
    # Reject variable dt: all folded coefficients correspond to the matched80Hz step.
    anchor='int pc_step( int input, wide_scalar dt ) {'
    pc=replace(pc,anchor,anchor+'\n if(dt.raw!='+literal(DT)+'.raw)wide_fail("unit-folded dt mismatch");')
    (out/'pcphys.cpp').write_text(pc)
    leptet=(out/'LEPTET.CPP').read_text()
    for name,old,value in (
        ('Loket','12.0',Decimal(12)*DT),
        ('Omegavalt','3.0',Decimal(3)*DT),
        ('tulporgesomega','110.0',Decimal(110)*DT),
        ('gaznyomatek','600.0',Decimal(600)*DT*DT),
        ('fekero','1000.0',Decimal(1000)*DT*DT),
        ('surlodas','100.0',Decimal(100)*DT)):
        leptet=replace(leptet,name+' = wide_scalar::literal("'+old+'");',name+' = '+literal(value)+';')
    # Saved omega sentinel is a speed. Jump-time sentinels remain time units.
    for name in ('kezdoomega1','kezdoomega2'):
        leptet=leptet.replace('pmot->'+name+' = -wide_scalar::literal("1.0");',
                              'pmot->'+name+' = -'+literal(DT)+';')
    leptet=replace(leptet,'static wide_scalar Oszto = wide_scalar::literal("1.0")/wide_scalar::literal("1.0");',
                         'static wide_scalar Oszto = 1/'+literal(DT)+';')
    (out/'LEPTET.CPP').write_text(leptet)
    beallit=(out/'BEALLIT.CPP').read_text()
    beallit=replace(beallit,'Utodeshatar = wide_scalar::literal("1.5");',
                           'Utodeshatar = '+literal(Decimal('1.5')*DT)+';')
    beallit=replace(beallit,'ero = ero/wide_scalar::literal("0.8")*wide_scalar::literal("0.1");',
                           'ero = ero/'+literal(Decimal('.8')*DT)+'*wide_scalar::literal("0.1");')
    for op in ('>','<'):
        beallit=replace(beallit,'abs( pk->v ) '+op+' wide_scalar::literal("1.0")',
                               'abs( pk->v ) '+op+' '+literal(DT))
    for old,new,count in (
        ('pk->omega += beta*dt;','pk->omega += beta;',2),
        ('pk->alfa += pk->omega*dt;','pk->alfa += pk->omega;',2),
        ('pk->v = pk->v + a*dt;','pk->v = pk->v + a;',1),
        ('pk->r = pk->r + pk->v*dt;','pk->r = pk->r + pk->v;',2),
        ('pmot->vezetov = pmot->vezetov + a*dt;','pmot->vezetov = pmot->vezetov + a;',1),
        ('pmot->vezetor = pmot->vezetor + pmot->vezetov*dt;',
         'pmot->vezetor = pmot->vezetor + pmot->vezetov;',1)):
        beallit=replace(beallit,old,new,count)
    (out/'BEALLIT.CPP').write_text(beallit)
    harness=(out/'wide_harness.cpp').read_text()
    # Decode16.16 test coordinates directly, without a potentially overflowing
    # integer intermediate before the division by65536 at higher precision.
    for offset,axis in ((4,'x'),(8,'y')):
        old='wide_scalar(signed32(blob,p+%d))/65536'%offset
        new='wide_scalar::from_raw(wide_checked((__int128)signed32(blob,p+%d)*(int64_t(1)<<(WIDE_BITS-16)),"warp %s"))'%(offset,axis)
        if old in harness:harness=replace(harness,old,new)
        elif new not in harness:raise ValueError('Unknown warp decoder')
    harness=replace(harness,'const auto speed=wide_scalar::literal("0.4368");',
                           'const wide_scalar speed=80; // Output only: step units -> real units')
    (out/'wide_harness.cpp').write_text(harness)
    metadata=json.loads((base/'build.json').read_text())
    command=[item.replace(str(base),str(out)).replace('-DWIDE_BITS=36','-DWIDE_BITS='+str(a.bits))
             for item in metadata['command']]
    result=subprocess.run(command,capture_output=True,text=True)
    (out/'compile.txt').write_text(result.stdout+result.stderr)
    result.check_returncode()
    metadata.update({'bits':a.bits,'command':command,'base_build':str(base),
      'change':'True per-step velocity/omega and dt²-scaled force/torque; no per-step compatibility multiplication',
      'dt':str(DT),'scaled_coefficients':{name:str(value) for name,(_,value) in coefficients.items()},
      'preserved_rules':['geometry/collision search','speed high/low split at1PCunit','strict release velocity/force gate',
                         'brake angular differences and conditional wheel wrap','jump/volt/history chronology','sound event thresholds']})
    (out/'build.json').write_text(json.dumps(metadata,indent=2)+'\n')
    (out/'wide_unit_variant.py').write_bytes(Path(__file__).read_bytes())
    print(out/'widecheck')


if __name__=='__main__':main()
