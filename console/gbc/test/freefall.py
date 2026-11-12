"""Drive the actual Freefall course without input and check high-speed descent.

Menu buttons select the original course. The test never changes guest memory.
It checks the 32-bit velocity range, tall-course camera, streamed source tiles
and moving head publications through normal gameplay and eventual death.
"""
import argparse
import json
from pathlib import Path
import struct

from all_levels import HeadVerifier,menu_check
from play import Driver,RIDING,DEAD,BASE


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom',type=Path,default=BASE/'build/elma-gbc.gbc')
    parser.add_argument('--gen',type=Path,default=BASE/'build/gen')
    parser.add_argument('--out',type=Path,default=BASE/'build/playtest/freefall')
    parser.add_argument('--max-overruns',type=int,default=0)
    args=parser.parse_args();d=Driver(args.rom,args.out,args.gen);head=HeadVerifier(d)
    samples=[];original_entry=Driver._physics_entry

    def physics_entry(driver):
        original_entry(driver)
        if driver.phase=='freefall':
            try:
                address=d.symbols['_Bike']
                samples.extend(struct.unpack('<ii',bytes(d.p.memory[address+8:address+16])))
            except BaseException as error:d.observer_errors.append(error)

    address=d.symbols['_physics_step'];d.p.hook_deregister(address>>16,address&65535)
    d.p.hook_register(address>>16,address&65535,physics_entry,d)
    report={'status':'running','rom_sha256':d.rom_sha256,'real_rom':str(args.rom.resolve())}
    try:
        d.ready();names=[record['name']for record in d.level_manifest['levels']]
        assert names[43].lower()=='freefall','original course order changed'
        for _ in range(4):d.pulse('right')
        for _ in range(7):d.pulse('down')
        menu_check(d,43,names);d.pulse('start');d.ready();assert d.level_index()==43
        base=d.word('game_steps');max_camera=0;max_head_y=-999.;last_bucket=-1
        d.phase='freefall'
        for _ in range(1000):
            if d.byte('game_state')!=RIDING:break
            bike=d.step();camera=d.word('game_camera_y');record=d.level_source(43)['record']
            head_y=(record['origin_m'][1]-bike['head']['y'])*12-camera
            max_camera=max(max_camera,camera);max_head_y=max(max_head_y,head_y)
            if d.byte('game_state')==RIDING:
                assert head_y<140,'live rider fell below the tracked viewport'
            steps=(d.word('game_steps')-base)&65535;bucket=steps//100
            if bucket!=last_bucket:d.snapshot('fall-%04d'%steps);last_bucket=bucket
        assert d.byte('game_state')==DEAD,'no-input fall did not end in a normal head collision'
        assert samples and max(abs(value)for value in samples)>32767,'descent did not exercise 32-bit velocity'
        assert max_camera>1536,'descent did not exercise the tall-course camera range'
        max_raw=max(abs(value)for value in samples)
        velocity_unit=65536*.4368/(59.727500569606/d.frame_interval)
        overruns=d.word('game_overruns')
        report.update({'status':'passed','functional_checks_passed':True,
            'controller':'menu selection and no-input fall; no guest-memory writes',
            'level':43,'final_state':d.byte('game_state'),
            'physics_steps':(d.word('game_steps')-base)&65535,
            'max_raw_velocity_units':max_raw,'max_speed_component_m_per_model_second':max_raw/velocity_unit,
            'max_camera_y':max_camera,'max_head_screen_y':max_head_y,
            'display_overruns':overruns,'performance_requirement_met':overruns==0,
            'deadline_budget_relaxed_for_diagnostics':args.max_overruns!=0,
            'head_publication_checks':dict(head.counts),**d.timing(),'hardware_tested':False})
        assert overruns<=args.max_overruns,'display deadline misses:%d'%overruns
        d.snapshot('fall-final')
    except BaseException as error:
        d.snapshot('failure');report.update({'status':'failed','error':str(error),
            'game_state':d.byte('game_state'),'display_overruns':d.word('game_overruns'),
            'head_publication_checks':dict(head.counts),**d.timing()});raise
    finally:
        (args.out/'run.json').write_text(json.dumps(report,indent=2)+'\n');d.close()
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
