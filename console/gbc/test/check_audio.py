"""Bounded native GBC APU test: real PCM buffers, timing, banks and IRQs."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import wave

import numpy as np
from pyboy import PyBoy

BASE = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=BASE / 'build/audio-check')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / 'driver.c').write_text('''#include <gb/gb.h>
#include <gb/cgb.h>
#include "audio.h"
volatile uint8_t ready,hold,riding,gas,brake,fx=255,reset_request,half_rate;
volatile uint16_t speed,banks_bad,irq_count;
void service(void) BANKED;
void vblank(void) NONBANKED { ++irq_count; }
void main(void) NONBANKED {
 cpu_fast();add_VBL(vblank);SWITCH_ROM(9);audio_init();
 if(CURRENT_BANK!=9)++banks_bad;
 ready=1;
 while(1) {
  vsync();
  if(reset_request) { audio_init();reset_request=0;if(CURRENT_BANK!=9)++banks_bad; }
  if(!hold)service();
  if(CURRENT_BANK!=9)++banks_bad;
 }
}
''')
    (out / 'caller.c').write_text('''#pragma bank 5
#include <gb/gb.h>
#include "audio.h"
extern volatile uint8_t riding,gas,brake,fx,half_rate;
extern volatile uint16_t speed,banks_bad;
void service(void) BANKED {
 if(fx!=255) { audio_effect(fx);fx=255; }
 if(!half_rate || !(sys_time&1))audio_update(riding,gas,brake,speed);
 if(CURRENT_BANK!=5)++banks_bad;
}
''')
    rom = out / 'check.gbc'
    subprocess.run([str(BASE / '.toolchain/gbdk/bin/lcc'), '-msm83:gb',
                    '-Wf--opt-code-size', '-Wm-yC', '-Wm-yt0x19', '-Wm-yoA',
                    '-Wl-m', '-Wl-j', '-I' + str(BASE / 'src'), '-o', str(rom),
                    str(out / 'driver.c'), str(out / 'caller.c'),
                    str(BASE / 'src/audio.c')], check=True, capture_output=True, text=True)
    symbols = {k: int(v, 16) for k, v in re.findall(
        r'DEF (_\w+) 0x([0-9A-Fa-f]+)', rom.with_suffix('.noi').read_text())}
    for name in ('audio_init', 'audio_update', 'audio_effect'):
        assert symbols['_' + name] >> 16 == 3, (name, 'wrong ROM bank')
    p = PyBoy(str(rom), window='null', sound_emulated=True, cgb=True,
              sound_sample_rate=48000)
    p.set_emulation_speed(0)
    samples = []
    cycles = []
    starts = []
    return_hooks = set()

    def returned(_):
        if starts and starts[-1][0] == p.register_file.SP - 2:
            cycles.append(p._cycles() - starts.pop()[1])

    def entered(_):
        sp = p.register_file.SP
        pc = p.memory[sp] + 256 * p.memory[sp + 1]
        assert pc < 0x4000, ('unexpected banked return', pc)
        if pc not in return_hooks:
            p.hook_register(0, pc, returned, None)
            return_hooks.add(pc)
        starts.append((sp, p._cycles()))

    p.hook_register(3, symbols['_audio_update'] & 65535, entered, None)

    def get(name, width=1):
        address = symbols['_' + name]
        return int.from_bytes(bytes(p.memory[address:address + width]), 'little')

    def put(name, value, width=1):
        address = symbols['_' + name]
        p.memory[address:address + width] = list(value.to_bytes(width, 'little'))

    def frames(count, capture=True, engine_min_level=0):
        chunks = []
        for _ in range(count):
            p.tick(1, False)
            if capture:
                chunk = p.sound.ndarray.copy()
                if engine_min_level:
                    assert p.memory[0xFF26] & 1, 'engine channel dropped out'
                    level = int(np.ptp(chunk[:, 0].astype(np.int16)))
                    assert level >= engine_min_level, ('engine PCM dropped out between updates', level)
                chunks.append(chunk)
                samples.append(chunk)
        return np.concatenate(chunks) if chunks else np.zeros((0, 2), dtype=np.int8)

    def audible(data):
        return int(np.ptp(data[:, 0].astype(np.int16))) > 2

    def fundamental(data):
        a = data[:, 0].astype(float)
        a -= a.mean()
        fft = np.abs(np.fft.rfft(a * np.hanning(len(a))))
        return round(float(np.fft.rfftfreq(len(a), 1 / p.sound.sample_rate)[fft.argmax()]), 2)

    def engine_segment(minimum_level=3):
        # Discard transition frames, then require over one second of audible
        # PCM on every VBlank while software services the engine at 30 Hz.
        frames(2)
        return frames(72, engine_min_level=minimum_level)

    def silent():
        # Ignore the transition frame and measure AC, not PyBoy's DC bias.
        frames(2)
        data = frames(3)
        assert not audible(data), ('not silent', np.ptp(data[:, 0].astype(np.int16)))

    report = {}
    try:
        for _ in range(120):
            frames(1, False)
            if get('ready'):
                break
        assert get('ready'), 'driver did not boot'
        assert p.memory[0xFF24] == 0x55 and p.memory[0xFF25] == 0xBB
        assert p.memory[0xFF26] & 0x80
        silent()
        put('riding', 1)
        put('half_rate', 1)
        idle = engine_segment()
        assert len(idle) >= p.sound.sample_rate, 'idle capture shorter than one second'
        put('gas', 1)
        low = engine_segment()
        put('speed', 16000, 2)
        high = engine_segment()
        put('brake', 1)
        brake = engine_segment(2)
        put('gas', 0)
        put('brake', 0)
        coast = engine_segment()
        put('brake', 1)
        brake_idle = engine_segment()
        put('brake', 0)
        put('gas', 1)
        resumed = engine_segment()
        pitches = {name: fundamental(data) for name, data in
                   [('idle', idle), ('gas_idle', low), ('gas_fast', high),
                    ('brake_fast', brake), ('coast_fast', coast),
                    ('brake_no_gas', brake_idle), ('gas_resumed', resumed)]}
        levels = {name: int(np.ptp(data[:, 0].astype(np.int16))) for name, data in
                  [('idle', idle), ('gas_idle', low), ('gas_fast', high),
                   ('brake_fast', brake), ('coast_fast', coast), ('brake_no_gas', brake_idle),
                   ('gas_resumed', resumed)]}
        assert 85 <= pitches['idle'] <= 91, pitches
        assert pitches['idle'] < pitches['gas_idle'], pitches
        assert abs(pitches['coast_fast'] - pitches['idle']) < 1, pitches
        assert abs(pitches['brake_no_gas'] - pitches['idle']) < 1, pitches
        assert pitches['gas_fast'] > pitches['gas_idle'] * 2, pitches
        assert pitches['brake_fast'] < pitches['gas_fast'], pitches
        assert abs(pitches['gas_resumed'] - pitches['gas_fast']) < 1, pitches
        assert 2 < levels['idle'] < levels['gas_idle'], levels
        assert levels['idle'] == levels['coast_fast'] == levels['brake_no_gas'], levels
        assert levels['gas_fast'] == levels['gas_resumed'] > levels['idle'], levels
        assert np.array_equal(high[:, 0], high[:, 1]), 'stereo routing differs'
        report['engine_hz'] = pitches
        report['engine_pcm_peak_to_peak'] = levels
        report['idle_seconds'] = round(len(idle) / p.sound.sample_rate, 3)
        report['engine_30hz_continuity_verified'] = True
        put('riding', 0)
        frames(3)
        silent()
        assert not (p.memory[0xFF26] & 1), 'pause left engine active'
        # Resume/restart and coast must retrigger a valid channel.
        put('reset_request', 1)
        frames(2)
        put('riding', 1)
        put('gas', 0)
        assert audible(frames(6))
        put('riding', 0)
        frames(2)
        put('half_rate', 0)
        lengths = {}
        for half_rate in (0, 1):
            put('half_rate', half_rate)
            for effect, duration in [(0, 3), (1, 11), (2, 14), (3, 48)]:
                put('fx', effect)
                assert audible(frames(2)), ('inaudible effect', effect, half_rate)
                frames(duration + 2)
                silent()
                assert not (p.memory[0xFF26] & 0x0B), ('effect stuck', effect, half_rate)
                lengths[str(effect)] = duration
        put('half_rate', 0)
        report['effect_durations_vblanks'] = lengths
        # A menu click cannot preempt the finish; an apple cannot replace crash.
        put('fx', 3)
        frames(2)
        put('fx', 0)
        frames(6)
        assert p.memory[0xFF26] & 2, 'menu interrupted finish'
        frames(48)
        put('fx', 2)
        frames(2)
        put('fx', 1)
        frames(2)
        assert p.memory[0xFF26] & 8 and not (p.memory[0xFF26] & 2), 'apple interrupted crash'
        frames(16)
        # Skip updates while an apple is playing. Age must catch up immediately.
        put('fx', 1)
        frames(2)
        put('hold', 1)
        frames(30)
        silent()
        put('hold', 0)
        frames(2)
        silent()
        assert not (p.memory[0xFF26] & 0x0B)
        # Engine hardware watchdog also expires without software or extra IRQs.
        put('riding', 1)
        put('gas', 1)
        frames(3)
        put('hold', 1)
        frames(30)
        silent()
        assert not (p.memory[0xFF26] & 1), 'engine watchdog did not expire'
        put('hold', 0)
        assert audible(frames(5)), 'expired watchdog did not restart'
        # sys_time wrap must not extend an effect beyond its specified duration.
        put('riding', 0)
        put('hold', 1)
        address = symbols['_sys_time']
        p.memory[address:address + 2] = [252, 255]
        put('fx', 1)
        put('hold', 0)
        assert audible(frames(2))
        frames(13)
        silent()
        assert not (p.memory[0xFF26] & 0x0B), 'wrapped effect stuck'
        assert get('banks_bad', 2) == 0, 'bank not restored'
        assert get('irq_count', 2) > 100, 'VBlank IRQs disabled'
        assert p.memory[0xFFFF] & 1 and not (p.memory[0xFF07] & 4), 'IRQ/timer changed'
        assert cycles and max(cycles) < 20000, ('audio update budget', max(cycles))
        report.update(bank_restore_failures=get('banks_bad', 2),
                      vblank_irqs=get('irq_count', 2), stereo_verified=True,
                      pause_resume_verified=True, skipped_updates_verified=True,
                      wrap_verified=True, watchdog_verified=True,
                      update_cycles={'min': min(cycles), 'max': max(cycles),
                                     'mean': round(sum(cycles) / len(cycles), 1)})
        pcm = np.concatenate(samples).astype(np.int16) * 256
        with wave.open(str(out / 'preview.wav'), 'wb') as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(p.sound.sample_rate)
            wav.writeframes(pcm.astype('<i2').tobytes())
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
    finally:
        p.stop(save=False)


if __name__ == '__main__':
    main()
