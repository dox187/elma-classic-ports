"""Run production native physics and audio over a synthetic horizontal floor.

No contact/impact flags or motion states are injected after reset. A settled
bike accelerates under IN_GAS, and a second bike falls onto the same floor with
gas held. Native contact events must agree with the host physics trajectory;
CH2 creak must stay silent during flat acceleration and play on hard landing.
"""
import argparse
import ctypes
import json
from pathlib import Path
import re
import subprocess

import numpy as np

from pyboy import PyBoy

BASE = Path(__file__).resolve().parents[1]

WORLD = r'''
#include "physics_core.h"
#include "runtime.h"
#ifdef __SDCC
#pragma bank 8
#define FLOOR_FIXED NONBANKED
#else
#define FLOOR_FIXED
#endif
gbc_bike_t gbc_bike;
const seg_t *Seg_cur;
uint8_t Seg_left,Seg_subcell;
static seg_t floor_segment={-2048,0,8192,0,16384,0,8192,0,255,0,255};
volatile uint8_t fixture_alive,fixture_contact,fixture_impact;
volatile int32_t fixture_x,fixture_vx;
void seg_query(uint8_t cx,uint8_t cy,uint8_t subcell) FLOOR_FIXED {
 (void)cx;Seg_subcell=subcell;
 floor_segment.py=(int16_t)(16384L-((int32_t)cy<<12));
 Seg_cur=&floor_segment;Seg_left=cy>=3 && cy<=4;
}
const seg_t *seg_next(void) FLOOR_FIXED { if(!Seg_left)return 0;--Seg_left;return Seg_cur++; }
static void export_pose(gbc_pose_t *out,const circle_t *in) {
 out->x=in->rx>>2;out->y=in->ry>>2;
 out->angle=(uint16_t)(in->alfa>>RIDING_ANGLE_SHIFT);
}
void fixture_reset(uint8_t drop) PH_BANKED {
 ph_init(M_TO_F(16),M_TO_F(16.41)+(drop?M_TO_F(1.0):0));ph_turn();
 riding_audio_contact[0]=riding_audio_contact[1]=0;
 riding_audio_impact[0]=riding_audio_impact[1]=0;
 gbc_bike.alive=fixture_alive=1;gbc_bike.turned=Bike.turned;
}
void fixture_advance(uint8_t gas) PH_BANKED {
 fixture_alive=ph_step(gas?IN_GAS:0);
 gbc_bike.alive=fixture_alive;gbc_bike.turned=Bike.turned;
 export_pose(&gbc_bike.body,&Bike.body);
 export_pose(&gbc_bike.wheel[0],&Bike.wheel[0]);
 export_pose(&gbc_bike.wheel[1],&Bike.wheel[1]);
 fixture_contact=riding_audio_contact[0]|(riding_audio_contact[1]<<2);
 fixture_impact=riding_audio_impact[0]|(riding_audio_impact[1]<<1);
 fixture_x=Bike.body.rx;fixture_vx=Bike.body.vx;
}
'''


def compile_run(command, log):
    result = subprocess.run(list(map(str, command)), capture_output=True, text=True)
    log.write_text(result.stdout + result.stderr)
    assert result.returncode == 0, log.read_text()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gen', type=Path, default=BASE/'build/gen-8m')
    parser.add_argument('--out', type=Path, default=BASE/'build/impact-audio-check')
    args = parser.parse_args()
    gen, out = args.gen.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    src = BASE/'src'
    (out/'world.c').write_text(WORLD)
    physics = [src/name for name in ('physics_core.c', 'physics_contacts.c',
                'physics_sweep.c', 'physics_math.c', 'physics_math32.c')]
    compile_run(['cc', '-shared', '-fPIC', '-O0', '-fwrapv', '-Wno-unknown-pragmas',
                 '-I'+str(src), '-I'+str(gen), out/'world.c', *physics,
                 '-o', out/'host.dylib'], out/'host-compile.log')
    host = ctypes.CDLL(str(out/'host.dylib'))
    host.fixture_reset.argtypes = host.fixture_advance.argtypes = [ctypes.c_uint8]
    fields = ('alive', 'contact', 'impact', 'x', 'vx')
    values = {name: (ctypes.c_int32 if name in ('x', 'vx') else ctypes.c_uint8)
              .in_dll(host, 'fixture_'+name) for name in fields}
    # Let the springs settle before applying throttle. The drop starts in air
    # and uses gas throughout, so a global throttle mute cannot pass.
    inputs = [[0]*120+[1]*60, [1]*60]
    expected = []
    for case, keys in enumerate(inputs):
        host.fixture_reset(case)
        trajectory = []
        for gas in keys:
            host.fixture_advance(gas)
            trajectory.append({name: value.value for name, value in values.items()})
        expected.append(trajectory)
    (out/'host-trajectory.json').write_text(json.dumps(expected, indent=2)+'\n')
    assert all(row['alive'] for rows in expected for row in rows), 'flat-floor fixture crashed'
    assert not any(row['impact'] for row in expected[0][120:]), 'flat acceleration produced an impact'
    assert abs(expected[0][-1]['x']-expected[0][120]['x']) > 262144, 'gas did not move the bike by one meter'
    assert any(row['impact'] for row in expected[1]), 'drop never produced a physical impact'
    (out/'observed_audio.c').write_text('#include "audio.c"\n'
        'const void * const observed[]={&creak_active,&creak_start};\n')
    (out/'driver.c').write_text(r'''
#include <gb/gb.h>
#include <gb/cgb.h>
#include "audio.h"
#include "physics_core.h"
void fixture_reset(uint8_t) BANKED;
void fixture_advance(uint8_t) BANKED;
volatile uint8_t fixture_case,fixture_done,fixture_gas;
volatile uint16_t fixture_step;
void fixture_mark(void) { }
void main(void) {
 cpu_fast();
 for(fixture_case=0;fixture_case<2;++fixture_case) {
  fixture_reset(fixture_case);audio_init();NR51_REG=0x22;audio_update(1,0,0,0);
  for(fixture_step=0;fixture_step<(fixture_case?60:180);++fixture_step) {
   fixture_gas=fixture_case || fixture_step>=120;
   fixture_advance(fixture_gas);
   audio_update(1,fixture_gas,0,0);fixture_mark();
   vsync();vsync();
  }
 }
 fixture_done=1;while(1)vsync();
}
''')
    assembly = [path for path in sorted(src.glob('physics_*.s'))
                if path.name not in ('physics_mul16.s', 'physics_export_fast.s')]
    tables = sum((sorted(gen.glob(pattern)) for pattern in
                 ('physics_quarter_*.c', 'physics_scale_*.c', 'physics_sine_*.c',
                  'physics_coefficient_*.c')), [])
    rom = out/'check.gbc'
    compile_run([BASE/'.toolchain/gbdk/bin/lcc', '-msm83:gb', '-Wf--opt-code-size',
                 '-Wf--max-allocs-per-node', '-Wf100000', '-DRIDING_COEFFICIENT_LOOKUP',
                 '-Wm-yC', '-Wm-yt0x19', '-Wm-yoA', '-Wl-m', '-Wl-j',
                 '-I'+str(src), '-I'+str(gen), '-o', rom, out/'driver.c',
                 out/'world.c', out/'observed_audio.c', *physics, *assembly, *tables,
                 gen/'physics_coefficient_calls.s'], out/'native-compile.log')
    symbols = {key: int(value, 16) for key, value in re.findall(
        r'DEF (_\w+) 0x([0-9A-Fa-f]+)', rom.with_suffix('.noi').read_text())}
    data = rom.read_bytes()
    observed = symbols['_observed']
    offset = (observed>>16)*16384+(observed&65535)-16384
    for i, name in enumerate(('creak_active', 'creak_start')):
        symbols['_'+name] = int.from_bytes(data[offset+2*i:offset+2*i+2], 'little')
    emu = PyBoy(str(rom), window='null', sound_emulated=True, sound_sample_rate=48000, cgb=True)
    emu.set_emulation_speed(0)
    rows = [dict(), dict()]
    pcm_peak = [0, 0]
    def read(name, width=1, signed=False):
        address = symbols['_'+name]
        return int.from_bytes(bytes(emu.memory[address:address+width]), 'little', signed=signed)
    def mark(_):
        case, step = read('fixture_case'), read('fixture_step', 2)
        if case >= 2 or step >= len(inputs[case]) or step in rows[case]:
            return
        row = {name: read('fixture_'+name, 4 if name in ('x', 'vx') else 1,
                          name in ('x', 'vx')) for name in fields}
        assert row == expected[case][step], ('native/host contact trajectory differs', case, step, row, expected[case][step])
        row.update(creak=read('creak_active'), onset=read('creak_start', 2),
                   gas=read('fixture_gas'), channel2=bool(emu.memory[0xff26]&2))
        rows[case][step] = row
    emu.hook_register(0, symbols['_fixture_mark'], mark, None)
    try:
        for _ in range(3000):
            emu.tick(1, False)
            case, step = read('fixture_case'), read('fixture_step', 2)
            if case < 2 and (case or step >= 120):
                pcm_peak[case] = max(pcm_peak[case], int(np.ptp(emu.sound.ndarray[:, 0].astype(np.int16))))
            if read('fixture_done'):
                break
        assert read('fixture_done'), 'native fixture did not finish'
        assert [len(row) for row in rows] == list(map(len, inputs))
        flat = [rows[0][step] for step in range(120, 180)]
        assert not any(row['creak'] or row['channel2'] for row in flat), 'creak during flat acceleration'
        landings = [step for step, row in rows[1].items() if row['impact']]
        assert landings, 'native drop produced no impact'
        for step in landings:
            row = rows[1][step]
            assert row['gas'] and row['creak'] and row['channel2'], ('landing inaudible with gas', step, row)
        assert pcm_peak[0] == 0, ('flat acceleration leaked CH2 PCM', pcm_peak)
        assert pcm_peak[1] >= 6, ('drop produced no audible CH2 PCM', pcm_peak)
        report = dict(status='passed', native_host_steps=list(map(len, inputs)),
                      flat_acceleration_steps=len(flat), flat_acceleration_creaks=0,
                      isolated_ch2_pcm_peak_to_peak=pcm_peak,
                      flat_distance_m=abs(flat[-1]['x']-flat[0]['x'])/262144,
                      drop_impact_steps=landings, impact_audio_with_gas=True,
                      production_physics=True, synthetic_horizontal_floor=True,
                      hardware_tested=False)
        (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report, indent=2))
    finally:
        emu.stop(save=False)


if __name__ == '__main__':
    main()
