"""Check the idle envelope and pitch walk on the native SM83, including wrap."""
import argparse
import json
from pathlib import Path
import re
import subprocess

from pyboy import PyBoy

BASE = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gen', type=Path, default=BASE / 'build/gen-8m')
    parser.add_argument('--out', type=Path, default=BASE / 'build/audio-idle-check')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    period = int(re.search(r'#define AUDIO_IDLE_PERIOD (\d+)',
                          (args.gen / 'audio_assets.h').read_text())[1])
    (out / 'driver.c').write_text('''#include <gb/gb.h>
#include <gb/cgb.h>
volatile uint8_t done;
void idle_run(void) BANKED;
void main(void) {
 cpu_fast();disable_interrupts();idle_run();done=1;
 enable_interrupts();while(1)vsync();
}
''')
    (out / 'probe.c').write_text('''#pragma bank 3
#include <gb/gb.h>
#include <stdint.h>
#include "audio_idle.h"
volatile uint16_t cases,failures,positive_resets,negative_resets,walks;
volatile uint16_t measured_periods[11];
volatile uint8_t first_bad;
static const uint8_t expected[21]={
 2,2,2,2,2,2,2,2,2,1,1,1,1,1,1,1,1,0,0,1,1};
uint8_t idle_probe(uint16_t now) { return audio_idle_tick(now); }
static void check(uint8_t ok,uint8_t code) {
 ++cases;if(!ok){++failures;if(!first_bad)first_bad=code;}
}
void idle_run(void) BANKED {
 uint16_t now,cycle;
 uint8_t phase,volume,old_index,old_left,i,troughs;
 for(i=0;i<11;++i)measured_periods[i]=idle_periods[i];
 /* Each possible reset seed, including the zero-LFSR special case. */
 for(cycle=0;cycle<256;++cycle) {
  audio_idle_reset(cycle);
  check(idle_random && idle_pitch_index==5 && !idle_phase,1);
  check(idle_cycles_left==2 || idle_cycles_left==3,2);
  check(idle_probe(cycle)==2 && audio_idle_period()==AUDIO_IDLE_PERIOD,3);
 }
 /* Full-speed updates cross sys_time's 16-bit wrap. Repeated timestamps
  * must not advance the envelope or walk a second time. */
 now=65530U;audio_idle_reset(now);
 for(cycle=0;cycle<6;++cycle)for(phase=0;phase<21;++phase) {
  volume=idle_probe(now);
  check(volume==expected[phase] && idle_phase==phase,4);
  check(idle_probe(now)==volume,5);++now;
 }
 /* At normal 30 Hz service every cycle must still include its trough. */
 now=65530U;audio_idle_reset(now);troughs=0;
 for(i=0;i<42;i+=2) { if(!idle_probe(now))++troughs;now+=2; }
 check(troughs==2,6);
 /* Two calls per cycle avoid the deliberate long-gap restart. Verify
  * every 2/3-cycle step, both +/-5% reset boundaries, and bounded pitch. */
 now=0;audio_idle_reset(now);
 for(cycle=0;cycle<4096;++cycle) {
  old_index=idle_pitch_index;old_left=idle_cycles_left;
  now+=20;idle_probe(now);++now;idle_probe(now);
  check(!idle_phase && idle_pitch_index>=1 && idle_pitch_index<=9,7);
  if(old_left>1)check(idle_pitch_index==old_index &&
                      idle_cycles_left==old_left-1,8);
  else {
   ++walks;
   check(idle_cycles_left==2 || idle_cycles_left==3,9);
   if(old_index==9 && idle_pitch_index==5)++positive_resets;
   else if(old_index==1 && idle_pitch_index==5)++negative_resets;
   else check(idle_pitch_index==old_index+1 ||
              idle_pitch_index+1==old_index,10);
  }
 }
 check(positive_resets && negative_resets,11);
 /* Throttle/pause/restart integration calls reset; both partial cycles
  * and an already detuned state must resume at the base pitch and peak. */
 idle_pitch_index=9;idle_phase=18;audio_idle_reset(65535U);
 check(idle_probe(65535U)==2 && audio_idle_period()==AUDIO_IDLE_PERIOD,12);
 check(idle_probe(0)==2 && idle_phase==1,13);
 /* Long gaps restart in constant time, rather than catching up. */
 idle_pitch_index=1;check(idle_probe(21)==2 && !idle_phase &&
                         idle_pitch_index==5,14);
 idle_pitch_index=9;check(idle_probe(276)==2 && !idle_phase &&
                         idle_pitch_index==5,15);
 idle_pitch_index=1;check(idle_probe(240)==2 && !idle_phase &&
                         idle_pitch_index==5,16);
}
''')
    rom = out / 'check.gbc'
    subprocess.run([
        str(BASE / '.toolchain/gbdk/bin/lcc'), '-msm83:gb',
        '-Wf--opt-code-size', '-Wm-yC', '-Wm-yt0x19', '-Wm-yoA',
        '-Wl-m', '-Wl-j', '-I' + str(BASE / 'src'),
        '-DAUDIO_IDLE_PERIOD=' + str(period), '-o', str(rom),
        str(out / 'driver.c'), str(out / 'probe.c')], check=True,
        capture_output=True, text=True)
    symbols = {key: int(value, 16) for key, value in re.findall(
        r'DEF (_\w+) 0x([0-9A-Fa-f]+)', rom.with_suffix('.noi').read_text())}
    pyboy = PyBoy(str(rom), window='null', sound_emulated=False, cgb=True)
    pyboy.set_emulation_speed(0)
    starts, cycles, returns = [], [], set()

    def word(address):
        return pyboy.memory[address] + 256 * pyboy.memory[address + 1]

    def returned(_):
        if starts and starts[-1][0] == pyboy.register_file.SP - 2:
            _, start = starts.pop()
            cycles.append(pyboy._cycles() - start)

    def entered(_):
        sp = pyboy.register_file.SP
        if starts and starts[-1][0] == sp:
            return
        ret = word(sp)
        if ret not in returns:
            pyboy.hook_register(3, ret, returned, None)
            returns.add(ret)
        starts.append((sp, pyboy._cycles()))

    pyboy.hook_register(3, symbols['_idle_probe'] & 65535, entered, None)
    try:
        for _ in range(100):
            pyboy.tick(10, False)
            if pyboy.memory[symbols['_done']]:
                break
        report = {key: word(symbols['_' + key]) for key in
                  ('cases', 'failures', 'walks', 'positive_resets', 'negative_resets')}
        report['done'] = pyboy.memory[symbols['_done']]
        report['first_bad'] = pyboy.memory[symbols['_first_bad']]
        periods = [word(symbols['_measured_periods'] + 2 * i) for i in range(11)]
        ratios = [(2048 - period) / (2048 - value) for value in periods]
        report['pitch_periods'] = periods
        report['pitch_frequency_ratios'] = ratios
        report['fall_ms'] = 17 * 70224 / 4194304 * 1000
        report['rise_ms'] = 4 * 70224 / 4194304 * 1000
        report['helper_cycles'] = {'min': min(cycles), 'max': max(cycles),
                                   'calls': len(cycles)}
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
        assert report['done'] and not report['failures'], report
        assert report['positive_resets'] and report['negative_resets']
        assert all(abs(ratio - (95 + i) / 100) < .001
                   for i, ratio in enumerate(ratios)), ratios
        assert max(cycles) < 1500, report['helper_cycles']
    finally:
        pyboy.stop(save=False)


if __name__ == '__main__':
    main()
