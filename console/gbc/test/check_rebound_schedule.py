#!/usr/bin/env python3
"""Measure landing fidelity without changing the original PC frame schedule.

Includes frame-sampled and actual PC-substep peaks, per-wheel contact windows,
30 Hz contact-time quantization diagnostics, and an immutable Git baseline.
A custom --driver Python module may define make_candidate(out, constants,
source, name), returning (Gbc-compatible object, fixture_gen_directory).
The comparison.fixture_levels function already describes the requested slope.
"""
import argparse
import ctypes as C
import importlib.util
import json
import math
from pathlib import Path
import sys

import compare_pc_physics as comparison
import check_landing_response as landing


class ObservedPc(comparison.Pc):
    def __init__(self, library):
        super().__init__(library)
        self.f.compare_pc_record_substeps.argtypes = [C.c_int]
        self.f.compare_pc_substep.argtypes = [C.c_int, C.POINTER(C.c_double),
            C.POINTER(C.c_int), C.POINTER(C.c_double), C.POINTER(C.c_int), C.POINTER(C.c_int)]
        self.f.compare_pc_record_substeps(1)

    def substeps(self):
        result = []
        for index in range(self.f.compare_pc_substep_count()):
            values, flags = (C.c_double*24)(), (C.c_int*5)()
            modes, observations, time = (C.c_int*2)(), (C.c_int*2)(), C.c_double()
            self.f.compare_pc_substep(index, values, flags, C.byref(time), modes, observations)
            result.append({'t_game':time.value, 't_wall':time.value/.4368,
                'position':{part:list(values[i*6:i*6+2]) for i,part in enumerate(('body','wheel0','wheel1'))},
                'dead':bool(flags[0]), 'finished':bool(flags[1]),
                'wheel_contacts':dict(zip(landing.WHEELS,modes))})
        return result


def compare_case(pc, control, host, path, height, speed, keys, steps, slope):
    host.reset(0,True,(-.85,height))
    velocity=round(speed*host.settings['velocity_scale'])
    for part in (host.b.body,*host.b.wheel): part.vx=velocity
    host.b.rider_vx=velocity
    seed=host.seed_values()
    pc.reset(path,seed,True);control.reset(path,seed,True)
    traces={'pc':[pc.snapshot()],'candidate':[host.snapshot()],'pc_substeps':[pc.snapshot()]}
    candidate_observer=getattr(host,'substeps',None)
    if candidate_observer:traces['candidate_substeps']=[host.snapshot()]
    observed_intervals=[]; last=0.
    schedule_checks=0
    for _ in range(steps):
        if not traces['pc'][-1]['dead']:
            frame_start=pc.t
            pc.step(keys,host.settings['dt']); control.step(keys,host.settings['dt'])
            assert pc.state_bytes()==control.state_bytes(), 'Substep/contact observer changes original PC state'
            traces['pc'].append(pc.snapshot())
            for row in pc.substeps():
                expected=min(.0055,frame_start+host.settings['dt']-last)
                assert abs(row['t_game']-last-expected)<1e-12, 'PC substep schedule changed'
                schedule_checks+=1
                observed_intervals.append(row['t_game']-last);last=row['t_game']
                traces['pc_substeps'].append(row)
        if not traces['candidate'][-1]['dead']:
            host.step(keys);traces['candidate'].append(host.snapshot())
            if candidate_observer:traces['candidate_substeps'].extend(candidate_observer())
        if traces['pc'][-1]['dead'] and traces['candidate'][-1]['dead']:break
    events={'pc':pc.contact_events(),'candidate':host.contact_events}
    metrics={'pc':landing.measure(traces['pc'],events['pc'],slope),
             'pc_substeps':landing.measure(traces['pc_substeps'],events['pc'],slope),
             'candidate':landing.measure(traces['candidate'],events['candidate'],slope)}
    if candidate_observer:
        metrics['candidate_substeps']=landing.measure(traces['candidate_substeps'],events['candidate'],slope)
    diagnostics={}
    period=host.settings['dt']/.4368
    for wheel in landing.WHEELS:
        frame=metrics['pc'][wheel]; fine=metrics['pc_substeps'][wheel]; candidate=metrics['candidate'][wheel]
        peak=frame.get('first_flight_peak_bottom_m'); subpeak=fine.get('first_flight_peak_bottom_m')
        got=candidate.get('first_flight_peak_bottom_m'); duration=frame.get('first_airtime_wall_s')
        nearest=round(duration/period)*period if duration else None
        candidate_fine=metrics.get('candidate_substeps',{}).get(wheel,{}).get('first_flight_peak_bottom_m')
        candidate_airtime=candidate.get('first_airtime_wall_s')
        diagnostics[wheel]={
            'candidate_airtime_error_percent':None if duration in (None,0) or candidate_airtime is None else 100*abs(candidate_airtime-duration)/duration,
            'candidate_substep_peak_m':candidate_fine,
            'candidate_substep_peak_error_percent':None if subpeak in (None,0) or candidate_fine is None else 100*abs(candidate_fine-subpeak)/abs(subpeak),
            'pc_frame_peak_m':peak,'pc_substep_peak_m':subpeak,'candidate_peak_m':got,
            'pc_sampling_peak_difference_m':None if peak is None or subpeak is None else subpeak-peak,
            'candidate_frame_peak_error_percent':None if peak in (None,0) or got is None else 100*abs(got-peak)/abs(peak),
            'candidate_pc_substep_peak_error_percent':None if subpeak in (None,0) or got is None else 100*abs(got-subpeak)/abs(subpeak),
            'if_contacts_only_at_frame_boundaries':{
                'period_wall_s':period,'nearest_representable_airtime_wall_s':nearest,
                'unavoidable_airtime_error_percent':None if nearest is None else 100*abs(nearest-duration)/duration,
                'note':'Diagnostic lower bound for frame-boundary contact timestamps only, not an allowance for trajectory error.'}}
    return {'initial_state':seed,'traces':traces,'contact_events':events,'metrics':metrics,
            'trajectory_errors':comparison.describe_errors(traces['pc'],traces['candidate']),
            'diagnostics':diagnostics,'pc_step_intervals_game_s':observed_intervals,
            'observer_identity_samples':len(traces['pc'])-1,'pc_schedule_checks':schedule_checks}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gen',type=Path,default=comparison.BASE/'build/gen-8m')
    p.add_argument('--source',type=Path,default=comparison.BASE/'src')
    p.add_argument('--out',type=Path,default=comparison.BASE/'build/rebound-schedule')
    p.add_argument('--baseline-ref',default='b2c314b')
    p.add_argument('--driver',type=Path)
    p.add_argument('--steps',type=int,default=240)
    p.add_argument('--max-rebound-error-percent',type=float)
    p.add_argument('--max-airtime-error-percent',type=float)
    p.add_argument('--slopes',default='0,-15,15')
    args=p.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    if args.steps<=0:p.error('--steps must be positive')
    slopes=[float(x) for x in args.slopes.split(',')]
    if any(abs(x)>45 for x in slopes):p.error('slopes must be in [-45,45]')
    if args.max_rebound_error_percent is not None and args.max_rebound_error_percent<0:p.error('negative error bound')
    if args.max_airtime_error_percent is not None and args.max_airtime_error_percent<0:p.error('negative airtime error bound')
    settings=comparison.constants(args.gen/'riding_constants.h')
    baseline_library=comparison.freeze_baseline(out/'frozen-baseline',args.baseline_ref,args.gen,contacts=True)
    frozen=baseline_library.parent
    baseline_source=frozen/'baseline-source/console/gbc/src'
    baseline_constants=frozen/'baseline-gen/riding_constants.h'
    pc=ObservedPc(comparison.build_pc(out,contacts=True))
    control=comparison.Pc(comparison.build_contact_control(pc.library))
    driver=None
    if args.driver:
        spec=importlib.util.spec_from_file_location('rebound_candidate_driver',args.driver.resolve())
        driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
    original=comparison.fixture_levels
    report={'schema':'rebound-schedule-v1','baseline_ref':args.baseline_ref,'cases':{},'failures':[],
            'math':'Original PC native double, actual capped .0055+remainder frame schedule; not Windows x87',
            'settings':settings,'driver':str(args.driver) if args.driver else None,
            'requested_source':str(args.source.resolve()),
            'libraries':{'pc':{'path':str(pc.library),'sha256':comparison.sha256(pc.library)}},
            'baseline_metadata':str(frozen/'baseline-revision.json'),'max_rebound_error_percent':args.max_rebound_error_percent,
            'max_airtime_error_percent':args.max_airtime_error_percent,
            'metric_note':'Candidate vs same-time frame peaks; actual PC substep peaks reported separately. No invented continuous-time peak.',
            'observer_identity':'All PC internal numeric state/object activations compared each frame against observer-disabled build.'}
    for slope in slopes:
        def fixtures():
            levels=original();angle=math.radians(slope);surface=levels[0].polygons[0]
            levels[0].polygons[0]=(surface[0],[(x*math.cos(angle)-y*math.sin(angle),x*math.sin(angle)+y*math.cos(angle)) for x,y in surface[1]])
            return levels
        comparison.fixture_levels=fixtures
        folder=out/f'slope-{slope:g}';folder.mkdir(exist_ok=True)
        base_lib,base_gen,_=comparison.build_fixtures(folder,baseline_constants,baseline_source,'baseline',contacts=True)
        baseline=comparison.Gbc(base_lib,comparison.constants(baseline_constants))
        if driver:
            candidate,gen=driver.make_candidate(folder,args.gen/'riding_constants.h',args.source,'candidate')
        else:
            lib,gen,_=comparison.build_fixtures(folder,args.gen/'riding_constants.h',args.source,'candidate',contacts=True)
            candidate=comparison.Gbc(lib,settings)
        report['libraries'][f'slope{slope:g}']={
            'candidate':{'path':str(candidate.library),'sha256':comparison.sha256(candidate.library)},
            'baseline':{'path':str(baseline.library),'sha256':comparison.sha256(baseline.library)},
            'candidate_constants_sha256':comparison.sha256(gen/'riding_constants.h')}
        for height in (1,4,8):
            for speed in (0,4,8):
                for title,keys in ([('coast',0),('gas',1),('brake',2)] if slope==0 else [('brake',2)]):
                    name=f'slope{slope:g}-h{height}-vx{speed}-{title}';case={}
                    for label,host,path in [('candidate',candidate,gen/'fixture0.txt'),('baseline',baseline,base_gen/'fixture0.txt')]:
                        run=compare_case(pc,control,host,path,height,speed,keys,args.steps,slope)
                        landing.write_json(folder/f'{name}-{label}.json',run)
                        case[label]=run['metrics']['candidate']
                        case.setdefault('trajectory_errors',{})[label]=run['trajectory_errors']
                        if label=='candidate':
                            case['pc']=run['metrics']['pc'];case['pc_substeps']=run['metrics']['pc_substeps'];case['diagnostics']=run['diagnostics']
                        else:
                            case['baseline_pc']=run['metrics']['pc']
                    if case['candidate']['dead'] != case['pc']['dead']:
                        report['failures'].append(f'{name}: survival/death differs from original PC')
                    if slope==0 and keys==0 and height in (4,8) and args.max_rebound_error_percent is not None:
                        for wheel in landing.WHEELS:
                            error=case['diagnostics'][wheel]['candidate_frame_peak_error_percent']
                            if error is None or error>args.max_rebound_error_percent:
                                report['failures'].append(f'{name}/{wheel}: rebound error {error}%, bound {args.max_rebound_error_percent}%')
                    if slope==0 and keys==0 and height in (4,8) and args.max_airtime_error_percent is not None:
                        for wheel in landing.WHEELS:
                            error=case['diagnostics'][wheel]['candidate_airtime_error_percent']
                            if error is None or error>args.max_airtime_error_percent:
                                report['failures'].append(f'{name}/{wheel}: airtime error {error}%, bound {args.max_airtime_error_percent}%')
                    case['survival_matches_pc']=case['candidate']['dead']==case['pc']['dead']
                    report['cases'][name]=case
        landing.write_json(out/'report.json',report)
    comparison.fixture_levels=original
    print(json.dumps({'report':str(out/'report.json'),'cases':len(report['cases']),'failures':report['failures']}))
    if report['failures']:raise AssertionError('Rebound validation failed; full evidence saved')


if __name__=='__main__':main()
