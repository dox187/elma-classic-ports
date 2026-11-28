"""Check native suspension creaks over the scheduled synthetic floor."""
import argparse
import json
from pathlib import Path
import re
import tempfile

import numpy as np
from pyboy import PyBoy

from check_scheduled_native import BASE, comparison, packed_host, prepare

DRIVER = r'''
#include <gb/gb.h>
#include <gb/cgb.h>
#include "audio.h"
#include "runtime.h"
#include "physics_core.h"

static const int32_t height[]={FIXTURE_HEIGHTS};
volatile uint8_t fixture_case,fixture_step,fixture_done;
void fixture_mark(void) {}
void main(void) {
 cpu_fast();
 for(fixture_case=0;fixture_case<CASE_COUNT;++fixture_case) {
  physics_select_level(0);
  physics_reset(-55706L,height[fixture_case]);
  physics_turn();
  audio_init();
  NR51_REG=0x22;
  audio_update(1,0,0,0);
  for(fixture_step=0;fixture_step<(fixture_case?60:180);++fixture_step) {
   uint8_t gas=fixture_case || fixture_step>=120;
   physics_step(gas?IN_GAS:0);
   audio_update(1,gas,0,0);
   fixture_mark();
   vsync();vsync();
  }
 }
 fixture_done=1;
 while(1)vsync();
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gen', type=Path, default=BASE/'build/gen-8m')
    parser.add_argument('--out', type=Path, default=BASE/'build/impact-audio-check')
    args = parser.parse_args()
    report_dir = args.out
    report_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fixture-', dir=report_dir) as scratch:
        args.out = Path(scratch)
        args.source = BASE/'src'
        args.lcc = BASE/'.toolchain/gbdk/bin/lcc'
        args.host_source = args.native_sources = None
        try:
            report = check(args)
        except RuntimeError:
            log = args.out/'compile.log'
            if log.exists():
                (report_dir/'compile.log').write_text(log.read_text())
            raise
    (report_dir/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


def check(args):
    heights = (.41, 1.41, 2.41)
    inputs = [[0]*120+[1]*60, [1]*60, [1]*60]
    driver = '#define FIXTURE_HEIGHTS ' + ','.join(f'{round(height*65536)}L' for height in heights)
    _, rom, library, settings, _ = prepare(
        args, heights, driver_code=driver+'\n'+DRIVER, extra_sources=('audio.c',))
    host = comparison.Gbc(library, settings)
    expected = []
    for case, (height, keys) in enumerate(zip(heights, inputs)):
        host.reset(0, True, (-.85, height))
        trajectory = []
        for step, gas in enumerate(keys):
            host.f.physics_step(gas)
            assert host.p.alive, 'flat-floor fixture crashed'
            trajectory.append(packed_host(host))
            if case == 0 and step == 120:
                flat_start_x = host.b.body.rx
        if case == 0:
            flat_distance = abs(host.b.body.rx-flat_start_x)/262144
            assert flat_distance > 1, 'gas did not move the bike by one meter'
        expected.append(trajectory)

    contact, impact = 'riding_audio_contact', 'riding_audio_impact'
    assert any(any(row[contact]) for row in expected[1]), 'mild drop missed the floor'
    assert not any(any(row[impact]) for rows in expected[:2] for row in rows)
    landings = [step for step, row in enumerate(expected[2]) if any(row[impact])]
    assert landings, 'hard drop never produced an impact'

    symbols = {key: int(value, 16) for key, value in re.findall(
        r'DEF (_\w+) 0x([0-9A-Fa-f]+)', rom.with_suffix('.noi').read_text())}
    emu = PyBoy(str(rom), window='null', sound_emulated=True, sound_sample_rate=48000, cgb=True)
    emu.set_emulation_speed(0)
    seen = [set() for _ in inputs]
    pcm_peak = [0]*len(inputs)

    def read(name, width=1):
        address = symbols['_'+name]
        return bytes(emu.memory[address:address+width])

    def mark(_):
        case, step = read('fixture_case')[0], read('fixture_step')[0]
        if step in seen[case]:
            return
        seen[case].add(step)
        for name, value in expected[case][step].items():
            actual = read(name, len(value))
            assert actual == value, ('native/host state differs', case, step, name, actual.hex(), value.hex())
        channel2 = bool(emu.memory[0xff26]&2)
        if case < 2:
            assert not channel2, ('creak during gentle motion', case, step)
        if case == 2 and step in landings:
            assert channel2, ('hard landing inaudible with gas', step)

    emu.hook_register(0, symbols['_fixture_mark'], mark, None)
    try:
        for _ in range(3000):
            emu.tick(1, False)
            case = read('fixture_case')[0]
            if case < len(inputs) and (case or read('fixture_step')[0] >= 120):
                pcm_peak[case] = max(pcm_peak[case], int(np.ptp(emu.sound.ndarray[:, 1].astype(np.int16))))
            if read('fixture_done')[0]:
                break
        assert read('fixture_done')[0], 'native fixture did not finish'
        assert list(map(len, seen)) == list(map(len, inputs))
        assert pcm_peak[:2] == [0, 0], ('gentle motion leaked CH2 PCM', pcm_peak)
        assert pcm_peak[2] >= 6, ('hard drop produced no audible CH2 PCM', pcm_peak)
        return dict(status='passed', native_host_steps=list(map(len, inputs)),
                    flat_distance_m=flat_distance,
                    mild_drop_m=1, hard_drop_m=2, hard_drop_impact_steps=landings,
                    isolated_ch2_pcm_peak_to_peak=pcm_peak,
                    impact_audio_with_gas=True, hardware_tested=False)
    finally:
        emu.stop(save=False)


if __name__ == '__main__':
    main()
