#!/usr/bin/env python3
"""Audit high-speed GBC dynamics against original PC, without hiding clamps.

Initial states are synthetic fixtures, not controller-completed gameplay.
Observed HOST copies must match the untouched kernel in every packed state.
Detected physical limitations are report findings, not silently relaxed gates.
"""
import argparse
import ctypes as C
import json
import math
from pathlib import Path
import shutil

import compare_pc_physics as comparison
from check_scheduled_native import packed_host

BASE = comparison.BASE
LABELS = ('body_omega', 'free_wheel_omega', 'rolling_omega', 'brake_delta_omega',
          'brake_torque', 'spring_torque_input', 'volt_start_wrap',
          'volt_release_wrap', 'volt_residual_wrap', 'q24_result', 'wide_result')


def cases(settings):
    vs, ws = settings['velocity_scale'], settings['omega_scale']
    result = []
    def add(name, level=0, height=.395, speed=0, keys=0, steps=36,
            seed=None, controls=None, turned=True, category='high_speed'):
        result.append(dict(name=name, level=level, height=height, speed=speed,
                           keys=keys, steps=steps, seed=seed or {}, turned=turned,
                           controls=controls if controls is not None else [keys]*steps,
                           turns=[], category=category))
    for speed in (-80,-60,-57.12,-55,-44,-40,40,44,55,57.12,60,80):
        for facing,turned in (('forward',speed>0),('reverse',speed<0)):
            for label,keys in (('coast',0),('gas',1),('brake',2)):
                add(f'flat-{speed:g}-{facing}-{label}',speed=speed,keys=keys,
                    turned=turned)
    for level,slope in ((0,0),(1,-15),(2,15)):
        for speed in (-60,0,60):
            for label,keys in (('coast',0),('brake',2)):
                vy=round(-20*vs)
                add(f'impact-s{slope}-vx{speed}-{label}',level=level,height=4,
                    speed=speed,keys=keys,
                    seed={f'{part}.vy':vy for part in ('body','wheel0','wheel1')}|
                         {'rider_vy':vy})
    for turned,sign,wheel in ((False,1,'wheel1'),(True,-1,'wheel0')):
        for raw in (25240,25241,25242):
            for brake in (False,True):
                add(f'gas-boundary-{sign*raw}-brake{int(brake)}',level=3,height=20,
                    steps=12,keys=3 if brake else 1,turned=turned,
                    seed={wheel+'.omega':sign*raw},category='boundary')
    for sign in (-1,1):
        for raw in (16382,16383,16384):
            add(f'brake-delta-{sign*raw}',level=3,height=20,steps=12,keys=2,
                seed={'wheel0.omega':sign*raw,'wheel1.omega':sign*raw},category='boundary')
        for raw in (30013,30014,30015,32760):
            # Matching initial PC state, then a single outward volt impulse.
            key=4 if sign>0 else 8
            add(f'volt-{sign*raw}',level=3,height=20,steps=12,
                seed={'body.omega':sign*raw},controls=[key]+[0]*11,category='boundary')
        for omega in (100,120,140):
            raw=round(sign*omega*ws)
            add(f'body-spin-{sign*omega}',level=3,height=20,steps=12,
                seed={'body.omega':raw},category='boundary')
    return result


def fixture_levels():
    original=comparison.fixture_levels()
    levels=[]
    import copy
    for slope in (0,-15,15):
        level=copy.deepcopy(original[0]);a=math.radians(slope)
        solid,vertices=level.polygons[0]
        level.polygons[0]=solid,[(x*math.cos(a)-y*math.sin(a),
                                  x*math.sin(a)+y*math.cos(a)) for x,y in vertices]
        levels.append(level)
    levels.append(original[1])
    return levels


def instrument(source,destination):
    shutil.copytree(source,destination)
    wide='Bike.body.omega += dwb;' in (source/'physics_core.c').read_text()
    def edit(name,replacements):
        p=destination/name;s=p.read_text()
        for before,after in replacements:
            if s.count(before)!=1:raise ValueError(f'Instrumentation anchor changed: {name}: {before}')
            s=s.replace(before,after,1)
        p.write_text('#include "speed_audit.h"\n'+s)
    header=['#include <stdint.h>', 'int16_t sat16(int32_t);',
            'void audit_range(int64_t,int64_t,int64_t,uint8_t);',
            'int16_t audit_narrow(int32_t,uint8_t);',
            'int32_t audit_wide(int64_t,uint8_t);']
    for i,label in enumerate(LABELS):
        helper='audit_wide' if wide else 'audit_narrow'
        header.append(f'#define audit_{label}(v) {helper}((v),{i})')
    (destination/'speed_audit.h').write_text('\n'.join(header)+'\n')
    spring_term = ('spring_input' if 'KMUL32(spring_input,C_SPRING_T)' in
                   (source/'physics_core.c').read_text() else 'riding_sra8(ts)>>2')
    core_replacements=[
        ('int32_t dw = Bike.wheel[k].omega-Bike.body.omega;',
         'int32_t dw = audit_brake_delta_omega((int64_t)Bike.wheel[k].omega-Bike.body.omega);'),
        ('tq[k] = -spring-(riding_landing_contact[k]?KMUL32(dw,C_BRAKE_GW):KMUL32(dw,C_BRAKE_W));',
         'tq[k] = audit_brake_torque(-(int64_t)spring-(riding_landing_contact[k]?KMUL32(dw,C_BRAKE_GW):KMUL32(dw,C_BRAKE_W)));'),
        (f'KMUL32({spring_term},C_SPRING_T)',
         f'KMUL32(audit_spring_torque_input({spring_term}),C_SPRING_T)'),
        ('Bike.body.omega += dwb;',
         'Bike.body.omega = audit_body_omega((int64_t)Bike.body.omega+dwb);')
    ] if wide else [
        ('static int16_t clamp_w( int32_t w ) {',
         'static int16_t clamp_w( int32_t w ) {\n audit_range(w,-16383,16383,3);'),
        ('tq[k] = sat16(', 'tq[k] = audit_brake_torque('),
        ('KMUL(sat16(riding_sra8(ts)>>2),C_SPRING_T)',
         'KMUL(audit_spring_torque_input(riding_sra8(ts)>>2),C_SPRING_T)'),
        ('Bike.body.omega = sat16( (int32_t)Bike.body.omega+dwb );',
         'Bike.body.omega = audit_body_omega( (int32_t)Bike.body.omega+dwb );')]
    if 'static int32_t clamp_damping(int64_t value) {' in (source/'physics_core.c').read_text():
        core_replacements.append(('static int32_t clamp_damping(int64_t value) {',
            'static int32_t clamp_damping(int64_t value) {\n audit_range(value,INT32_MIN,INT32_MAX,10);'))
    edit('physics_core.c',core_replacements)
    arithmetic_type='int64_t' if wide else 'int32_t'
    p=destination/'physics_core.c';s=p.read_text()
    prefix,volts=s.split('\t// Volts:',1)
    releases,starts=volts.split('\tif( input & IN_VOLT_RIGHT )',1)
    for section,label in (('release','volt_release_wrap'),('start','volt_start_wrap')):
        part=releases if section=='release' else starts
        for op,sign in (('+=','+'),('-=','-')):
            before=f'Bike.body.omega {op} LOKET;'
            assert part.count(before)==1
            part=part.replace(before,f'Bike.body.omega = audit_{label}(({arithmetic_type})Bike.body.omega {sign} LOKET);')
        if section=='release':releases=part
        else:starts=part
    # Legacy volt assignments narrow without saturation; wide assignments
    # retain int32 values. The observers preserve both paths' conversions.
    s=prefix+'\t// Volts:'+releases+'\tif( input & IN_VOLT_RIGHT )'+starts
    for op,sign in (('+=','+'),('-=','-')):
        before=f'Bike.body.omega {op} OMEGAVALT;';assert s.count(before)==1
        s=s.replace(before,f'Bike.body.omega = audit_volt_residual_wrap(({arithmetic_type})Bike.body.omega {sign} OMEGAVALT);')
    p.write_text(s)
    contact_replacements=[
        ('k->omega += KMUL32(tq,C_FREE);',
         'k->omega = audit_free_wheel_omega((int64_t)k->omega+KMUL32(tq,C_FREE));'),
        ('k->omega=Q24_MUL(sp,C_ROLL_W);',
         'k->omega=audit_rolling_omega(Q24_MUL(sp,C_ROLL_W));')
    ] if wide else [
        ('k->omega = sat16((int32_t)k->omega+KMUL(tq,C_FREE));',
         'k->omega = audit_free_wheel_omega((int32_t)k->omega+KMUL(tq,C_FREE));'),
        ('k->omega=sat16(Q24_MUL(sp,C_ROLL_W));',
         'k->omega=audit_rolling_omega(Q24_MUL(sp,C_ROLL_W));')]
    edit('physics_contacts.c',contact_replacements)
    edit('physics_math32.c',[
        ('static int32_t clamp32(int64_t x) {',
         'static int32_t clamp32(int64_t x) {\n audit_range(x,INT32_MIN,INT32_MAX,10);')])
    edit('physics_q24.c',[
        ('q24_saturated=rounded>INT32_MAX || rounded<INT32_MIN;',
         'audit_range(rounded,INT32_MIN,INT32_MAX,9);\n q24_saturated=rounded>INT32_MAX || rounded<INT32_MIN;')])
    with (destination/'physics_q24.c').open('a') as f:
        f.write('''
#ifndef __SDCC
static uint32_t audit_calls[11],audit_hits[11];
static int64_t audit_lo[11],audit_hi[11];
void audit_reset(void){for(uint8_t i=0;i<11;++i){audit_calls[i]=audit_hits[i]=0;audit_lo[i]=INT64_MAX;audit_hi[i]=INT64_MIN;}}
void audit_range(int64_t x,int64_t lo,int64_t hi,uint8_t tag){
 ++audit_calls[tag];if(x<lo || x>hi)++audit_hits[tag];
 if(x<audit_lo[tag])audit_lo[tag]=x;if(x>audit_hi[tag])audit_hi[tag]=x;
}
int16_t audit_narrow(int32_t x,uint8_t tag){
 audit_range(x,-32768,32767,tag);
 return tag>=6 && tag<=8 ? (int16_t)x : sat16(x);
}
int32_t audit_wide(int64_t x,uint8_t tag){
 audit_range(x,INT32_MIN,INT32_MAX,tag);
 return (int32_t)x;
}
uint32_t audit_count(uint8_t tag){return audit_hits[tag];}
uint32_t audit_call_count(uint8_t tag){return audit_calls[tag];}
int64_t audit_min(uint8_t tag){return audit_lo[tag];}
int64_t audit_max(uint8_t tag){return audit_hi[tag];}
#endif
''')


def seed(host,case):
    host.reset(case['level'],case['turned'],(-.85,case['height']))
    velocity=round(case['speed']*host.settings['velocity_scale'])
    for circle in (host.b.body,*host.b.wheel):circle.vx=velocity
    host.b.rider_vx=velocity
    for path,value in case['seed'].items():
        if '.' in path:
            part,field=path.split('.')
            target=host.b.body if part=='body' else host.b.wheel[int(part[-1])]
        else:target,field=host.b,path
        setattr(target,field,value)


class AuditedGbc(comparison.Gbc):
    """Distinguish the production stretch guard from death in the core."""
    def __init__(self,*args):
        super().__init__(*args)
        native_step=self.f.physics_step
        def observe_step(keys):
            native_step(keys)
            self.core_alive=bool(self.p.alive)
        self.f.physics_step=observe_step

    def reset(self,*args,**kwargs):
        super().reset(*args,**kwargs)
        self.core_alive=True
        self.death_cause=None

    def step(self,keys):
        super().step(keys)
        if self.dead and self.death_cause is None:
            self.death_cause='physics_core' if not self.core_alive else 'runtime_stretch_guard'


def spin_regression(host, pc, gen, suite, steps=120):
    """Follow the four original false deaths through recovery or PC termination."""
    results = {}
    for case in suite:
        if case['name'] not in ('body-spin--140', 'body-spin--120', 'body-spin-120', 'body-spin-140'):
            continue
        seed(host, case)
        pc.reset(gen / f"fixture{case['level']}.txt", host.seed_values(), case['turned'])
        peak = {'pc': 0., 'gbc': 0.}
        terminal = {'pc': None, 'gbc': None}
        early_error = live_error = 0.
        for step in range(1, steps + 1):
            if terminal['pc'] is None:
                pc.step(0, host.settings['dt'])
            if terminal['gbc'] is None:
                host.step(0)
            states = {'pc': pc.snapshot(), 'gbc': host.snapshot()}
            for model, state in states.items():
                if state['dead']:
                    if terminal[model] is None:
                        terminal[model] = step
                    continue
                pos = state['position']
                separation = max(abs(pos[k][axis] - pos['body'][axis])
                                 for k in ('wheel0', 'wheel1') for axis in (0, 1))
                peak[model] = max(peak[model], separation)
            if not any(terminal.values()):
                error = max(math.dist(states['pc']['position'][k], states['gbc']['position'][k])
                            for k in states['pc']['position'])
                live_error = max(live_error, error)
                if step <= case['steps']:
                    early_error = max(early_error, error)
            if all(terminal.values()):
                break
        results[case['name']] = {
            'death_step': terminal, 'gbc_death_cause': host.death_cause,
            'peak_live_wheel_axis_m': peak,
            'max_position_error_first_12_steps_m': early_error,
            'max_position_error_common_live_m': live_error,
            'passed': terminal['pc'] == terminal['gbc'] and
                      (terminal['pc'] is None or terminal['pc'] > case['steps']) and min(peak.values()) > 3,
        }
    return {'steps': steps, 'cases': results,
            'passed': len(results) == 4 and all(r['passed'] for r in results.values())}


def gas_cutoff_regression(report):
    """Catch the missing last drive impulse against the actual PC integrator."""
    results={}
    for name,row in report['cases'].items():
        if not name.startswith('gas-boundary-') or not name.endswith('brake0'):
            continue
        wheel='wheel0' if row['configuration']['turned'] else 'wheel1'
        pc=row['maximum_abs_omega']['pc'][wheel]
        gbc=row['maximum_abs_omega']['gbc'][wheel]
        error=100*abs(gbc-pc)/pc
        results[name]={'pc_peak_rad_s':pc,'gbc_peak_rad_s':gbc,
                       'relative_error_percent':error,'passed':error<=.1}
    return {'bound_percent':.1,'cases':results,
            'passed':len(results)==6 and all(r['passed'] for r in results.values())}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gen',type=Path,default=BASE/'build/gen-8m')
    p.add_argument('--source',type=Path,default=BASE/'src')
    p.add_argument('--out',type=Path,default=BASE/'build/v094-speed-limits')
    p.add_argument('--require-gas-cutoff',action='store_true',
                   help='Fail unless the six original-PC drive-cutoff cases meet 0.1%%')
    p.add_argument('--require-spin-survival',action='store_true',
                   help='Fail unless the four extreme spins match PC survival for 120 steps or until death')
    a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    source=out/'source/gbc/src';observed_source=out/'observed/gbc/src'
    if source.exists():raise ValueError('Use a fresh output directory for immutable evidence')
    shutil.copytree(a.source,source);instrument(source,observed_source)
    for tree in ('source','observed'):
        dest=out/tree/'nes/src';dest.mkdir(parents=True)
        for name in ('recip.inc','rsqrt.inc'):shutil.copy2(BASE.parent/'nes/src'/name,dest/name)
    settings=comparison.constants(a.gen/'riding_constants.h');suite=cases(settings)
    (out/'cases.json').write_text(json.dumps([{k:v for k,v in case.items() if k!='category'}
                                            for case in suite],indent=2)+'\n')
    levels=fixture_levels();original=comparison.fixture_levels
    comparison.fixture_levels=lambda:levels
    try:
        lib,gen,_=comparison.build_fixtures(out,a.gen/'riding_constants.h',source,'control',contacts=True)
        observed_lib=comparison.build_host(out,gen,observed_source,'observed',contacts=True)
    finally:comparison.fixture_levels=original
    host=AuditedGbc(lib,settings);observed=AuditedGbc(observed_lib,settings)
    assert host.wide_angular==observed.wide_angular, 'Observer changed angular ABI'
    angular_bits=32 if host.wide_angular else 16
    angular_bounds=[-(2**(angular_bits-1)),2**(angular_bits-1)-1]
    brake_bounds=angular_bounds if host.wide_angular else [-16383,16383]
    pc=comparison.Pc(comparison.build_pc(out,contacts=True))
    for name in ('audit_count','audit_call_count','audit_min','audit_max'):
        fn=getattr(observed.f,name);fn.argtypes=[C.c_uint8]
        fn.restype=C.c_int64 if name in ('audit_min','audit_max') else C.c_uint32
    report={'schema':'speed-limit-audit-v1','version':(BASE/'VERSION').read_text().strip(),
            'settings':settings,'scope':'Synthetic initial states, original PC equations compiled with native double; not a controller-completed route or a Windows x87 run',
            'fixture_note':'Flat cases start with zero wheel omega and no contact history, then establish contact. Forward/reverse facing tests both throttle directions.',
            'termination_note':'GBC uses the source snapshot runtime guard; exported native cases verify raw core states only.',
            'runtime_axis_bounds_m':{'wheel':host.wheel_bound,'rider':host.rider_bound},
            'verification_sha256':comparison.sha256(Path(__file__)),
            'constants_sha256':comparison.sha256(a.gen/'riding_constants.h'),
            'observational_identity_states':0,'cases':{},'limits':{
                'linear32_m_per_model_s':[( -2**31)/settings['velocity_scale'],(2**31-1)/settings['velocity_scale']],
                f'angular{angular_bits}_rad_per_model_s':[x/settings['omega_scale'] for x in angular_bounds],
                'brake_relative_omega_rad_per_model_s':[x/settings['omega_scale'] for x in brake_bounds]},
            'instrumentation':{'angular_bits':angular_bits,
                'raw_bounds':{label:([-2**31,2**31-1] if i>=9 else
                                     brake_bounds if i==3 else angular_bounds)
                              for i,label in enumerate(LABELS)},
                'note':'Legacy label names are retained; wide angular paths observe int32 range without adding saturation.'},
            'libraries':{str(x):comparison.sha256(x) for x in (lib,observed_lib,pc.library)}}
    for case in suite:
        seed(host,case);seed(observed,case);observed.f.audit_reset()
        initial=host.seed_values()
        pc.reset(gen/f"fixture{case['level']}.txt",initial,case['turned'])
        traces={'pc':[pc.snapshot()],'gbc':[host.snapshot()]};first_hits={}
        for step in range(case['steps']):
            assert packed_host(host)==packed_host(observed),f"observer changed {case['name']} step {step}"
            report['observational_identity_states']+=1
            keys=case['controls'][step]
            if not traces['pc'][-1]['dead']:pc.step(keys,settings['dt']);traces['pc'].append(pc.snapshot())
            if not host.dead:
                host.step(keys);observed.step(keys);traces['gbc'].append(host.snapshot())
                for i,label in enumerate(LABELS):
                    if observed.f.audit_count(i) and label not in first_hits:first_hits[label]=step+1
            if host.dead and traces['pc'][-1]['dead']:break
        assert packed_host(host)==packed_host(observed),case['name']
        report['observational_identity_states']+=1
        stats={label:{'calls':observed.f.audit_call_count(i),'clipped_or_wrapped':observed.f.audit_count(i),
                      'minimum_input':observed.f.audit_min(i),'maximum_input':observed.f.audit_max(i),
                      'first_outer_step':first_hits.get(label)} for i,label in enumerate(LABELS)}
        row={'initial_state':initial,'configuration':case,'limits':stats,
             'errors':comparison.describe_errors(traces['pc'],traces['gbc']),
             'pc_dead':traces['pc'][-1]['dead'],'gbc_dead':traces['gbc'][-1]['dead'],
             'gbc_death_cause':host.death_cause,
             'maximum_abs_omega':{model:{part:max(abs(s['angular_velocity'][part]) for s in trace)
                                       for part in ('body','wheel0','wheel1')} for model,trace in traces.items()}}
        report['cases'][case['name']]=row
        (out/(case['name']+'.json')).write_text(json.dumps({'summary':row,'traces':traces},indent=2)+'\n')
    report['cases_with_limits']=[name for name,row in report['cases'].items()
        if any(s['clipped_or_wrapped'] for s in row['limits'].values())]
    report['survival_differences']=[name for name,row in report['cases'].items() if row['pc_dead']!=row['gbc_dead']]
    report['gas_cutoff_regression']=gas_cutoff_regression(report)
    report['spin_survival_regression']=spin_regression(host,pc,gen,suite)
    report['status']='audit_complete'
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'report':str(out/'report.json'),'cases':len(suite),
                      'cases_with_limits':len(report['cases_with_limits']),
                      'survival_differences':len(report['survival_differences']),
                      'gas_cutoff_passed':report['gas_cutoff_regression']['passed'],
                      'spin_survival_passed':report['spin_survival_regression']['passed'],
                      'observational_identity_states':report['observational_identity_states']}))
    if a.require_gas_cutoff and not report['gas_cutoff_regression']['passed']:
        raise SystemExit('Original-PC gas cutoff regression failed')
    if a.require_spin_survival and not report['spin_survival_regression']['passed']:
        raise SystemExit('Original-PC spin survival regression failed')


if __name__=='__main__':main()
