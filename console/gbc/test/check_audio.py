"""Bounded native GBC APU test: real PCM buffers, timing, banks and IRQs."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import wave

import numpy as np
from pyboy import PyBoy

BASE = Path(__file__).resolve().parents[1]
# Measured with live stationary poses: 5512 T steady / 6996 T transitions;
# inactive-bike baseline: 2488 T. The extra work is the bounded one-wheel
# motion probe, idle contour and independent creak scheduler. Leave roughly
# 300..600 T for IRQ alignment; reject the initial 11k/13k motion version.
CYCLE_BUDGET = {'live_steady': 6000, 'inactive_steady': 2800, 'update': 7600, 'transition': 7600}


def rms(data):
    samples = data[:, 0].astype(float)
    samples -= samples.mean()
    return float(np.sqrt(np.mean(samples * samples)))


def cgb_hpf_rms(data, sample_rate):
    # PyBoy's PCM buffer omits the analog output HPF. This Pan Docs CGB
    # capacitor model is a relative-level proxy, not a speaker simulation:
    # https://gbdev.io/pandocs/Audio_details.html#obscure-behavior
    samples = data[:, 0].astype(float)
    charge = .998943 ** (4194304 / sample_rate)
    capacitor = samples[0]
    energy = 0.0
    for sample in samples:
        output = sample - capacitor
        capacitor = sample - output * charge
        energy += output * output
    return math.sqrt(energy / len(samples))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=BASE / 'build/audio-check')
    parser.add_argument('--gen', type=Path, default=BASE / 'build/gen')
    parser.add_argument('--res', type=Path, help='generate isolated fixture assets from this elma.res')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    gen = args.gen.resolve()
    if args.res:
        gen = out / 'gen'
        gen.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.gen / 'riding_constants.h', gen / 'riding_constants.h')
        subprocess.run([sys.executable, str(BASE / 'tools/audio_assets.py'),
                        '--res', str(args.res.resolve()), '--out', str(gen)], check=True)
    manifest = json.loads((gen / 'audio-manifest.json').read_text())
    engine = manifest['engine']
    waves, expected_wave = {}, {}
    for mode, source in enumerate(('harl.wav', 'harl2.wav')):
        selected = engine['loops'][source]
        nibbles = np.array(selected['wave_nibbles'], dtype=np.uint8)
        waves[mode] = nibbles
        expected_wave[mode] = bytes(int(nibbles[i] << 4) | int(nibbles[i + 1]) for i in range(0, 32, 2))
        assert len(expected_wave[mode]) == 16 and len(set(nibbles)) >= 12
        assert hashlib.sha256(expected_wave[mode]).hexdigest() == selected['wave_sha256']
        assert selected['quantized_source_correlation'] > .98, 'wave lost its original cycle shape'
        assert selected['harmonic_energy_fractions'][0] > .6, 'cycle lost its low-frequency component'
        # Preserve the selected recorded cycle's duration, using the actual
        # PC mixer rate even though harl2.wav declares a different WAV rate.
        left, right = selected['selected_source_cycle_samples']
        base = engine['load_base_hz' if mode else 'idle_hz']
        assert abs(base-11025/(right-left)) < .001
    assert expected_wave[0] != expected_wave[1], 'gas still uses the idle timbre'
    constants = (gen / 'riding_constants.h').read_text()
    rate = float(re.search(r'#define PH_RATE ([\d.]+)', constants)[1])
    angle_units = int(re.search(r'#define RIDING_ANGLE_UNITS (\d+)', constants)[1])
    omega_units = angle_units * .4368 / (2 * math.pi * rate * 128)
    speeds = np.arange(65536)
    reference_hz = engine['load_base_hz'] * (2-np.exp(-np.minimum(speeds/omega_units*.025, 30)))
    periods = np.array(engine['curve']['periods'])
    actual_hz = 65536/(2048-periods[np.minimum(speeds >> 6, 511)])
    pitch_error = float(np.max(np.abs(actual_hz-reference_hz)))
    assert len(periods) == 512 and pitch_error < .65, ('original pitch-curve error', pitch_error)
    assert np.all(np.diff(actual_hz) >= 0) and actual_hz.max() < engine['load_base_hz']*2
    effect_names = {1: 'apple', 2: 'crash', 3: 'finish', 5: 'volt', 6: 'turn'}
    effect_lengths = {0: 3, **{effect: manifest['effects'][name]['duration_vblanks']
                              for effect, name in effect_names.items()}}
    (out / 'driver.c').write_text('''#include <gb/gb.h>
#include <gb/cgb.h>
#include "audio.h"
#include "runtime.h"
#include "physics_core.h"
gbc_bike_t gbc_bike;
bike_t Bike;
uint8_t riding_audio_contact[2]={1,1}, riding_audio_impact[2];
volatile uint8_t ready,hold,riding,gas,brake,fx=255,reset_request,half_rate;
volatile uint16_t speed,banks_bad,irq_count;
void service(void) BANKED;
void vblank(void) NONBANKED { ++irq_count; }
void main(void) NONBANKED {
 gbc_bike.alive=1;
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
    # Publish addresses only in the fixture, without altering production
    # code generation or adding probes to its timed update path.
    (out / 'observed_audio.c').write_text('''#include "audio.c"
const void * const audio_state_addresses[] = {
 &effect_active,&effect_start,&effect_note,&engine_mode,
 &creak_active,&creak_start,&creak_note,&idle_phase,&idle_pitch_index,&gbc_bike.alive
};
''')
    rom = out / 'check.gbc'
    subprocess.run([str(BASE / '.toolchain/gbdk/bin/lcc'), '-msm83:gb',
                    '-Wf--opt-code-size', '-Wm-yC', '-Wm-yt0x19', '-Wm-yoA',
                    '-Wl-m', '-Wl-j', '-I' + str(BASE / 'src'), '-I' + str(gen), '-o', str(rom),
                    str(out / 'driver.c'), str(out / 'caller.c'),
                    str(out / 'observed_audio.c')], check=True, capture_output=True, text=True)
    symbols = {k: int(v, 16) for k, v in re.findall(
        r'DEF (_\w+) 0x([0-9A-Fa-f]+)', rom.with_suffix('.noi').read_text())}
    rom_bytes = rom.read_bytes()
    location = symbols['_audio_state_addresses']
    offset = (location >> 16) * 0x4000 + (location & 65535) - 0x4000
    for index, name in enumerate(('effect_active', 'effect_start', 'effect_note', 'engine_mode',
                                 'creak_active', 'creak_start', 'creak_note', 'idle_phase', 'idle_pitch_index', 'bike_alive')):
        symbols['_' + name] = int.from_bytes(rom_bytes[offset + 2 * index:offset + 2 * index + 2], 'little')
    for name in ('audio_init', 'audio_update', 'audio_effect'):
        assert symbols['_' + name] >> 16 == 3, (name, 'wrong ROM bank')
    p = PyBoy(str(rom), window='null', sound_emulated=True, cgb=True,
              sound_sample_rate=48000)
    p.set_emulation_speed(0)
    samples = []
    cycles = []
    engine_cycles = []
    inactive_bike_cycles = []
    transition_cycles = []
    starts = []
    return_hooks = set()
    register_writes = {'wave_bytes': 0, 'triggers': 0, 'levels': 0,
                       'pulse_triggers': 0, 'pulse_envelopes': 0}
    period_low = {'wave': 0, 'pulse': 0}
    apu_periods = {'wave': None, 'pulse': None}
    loaded_wave = bytearray(16)
    hook_failures = []
    idle_phases, idle_levels, idle_pitch_indices = set(), set(), set()

    def returned(_):
        if starts and starts[-1][0] == p.register_file.SP - 2:
            _, started, engine_only, transition, alive = starts.pop()
            elapsed = p._cycles() - started
            if get('riding') and get('engine_mode') and apu_periods['wave'] != apu_periods['pulse']:
                hook_failures.append(('engine channels have different period registers', dict(apu_periods)))
            if get('riding') and not get('engine_mode'):
                phase, index = get('idle_phase'), get('idle_pitch_index')
                level = p.memory[0xFF12] >> 4
                expected_level = 2 if phase < 9 else 1 if phase < 17 or phase >= 19 else 0
                percent = 95 + index
                expected_period = 2048 - ((2048-engine['idle_period'])*100 + percent//2)//percent
                if level != expected_level or not 1 <= index <= 9:
                    hook_failures.append(('idle modulation outside contour', phase, index, level))
                if apu_periods != {'wave': engine['idle_period'], 'pulse': expected_period}:
                    hook_failures.append(('idle drift affected wrong channel', dict(apu_periods), expected_period))
                idle_phases.add(phase)
                idle_levels.add(level)
                idle_pitch_indices.add(index)
            cycles.append(elapsed)
            if transition:
                transition_cycles.append(elapsed)
            elif engine_only:
                (engine_cycles if alive else inactive_bike_cycles).append(elapsed)

    def entered(_):
        sp = p.register_file.SP
        pc = p.memory[sp] + 256 * p.memory[sp + 1]
        if pc >= 0x4000:
            hook_failures.append(('unexpected banked return', pc))
            return
        if pc not in return_hooks:
            p.hook_register(0, pc, returned, None)
            return_hooks.add(pc)
        starts.append((sp, p._cycles(), bool(get('riding') and not get('effect_active') and not get('creak_active')),
                       bool(get('riding') and get('engine_mode') != bool(get('gas'))),
                       bool(get('bike_alive'))))

    p.hook_register(3, symbols['_audio_update'] & 65535, entered, None)

    def apu_write(kind):
        if kind in ('wave_hl', 'wave_de'):
            address = p.register_file.HL if kind == 'wave_hl' else 256 * p.register_file.D + p.register_file.E
            if 0xFF30 <= address <= 0xFF3F:
                if p.memory[0xFF1A] & 0x80:
                    hook_failures.append('wave RAM written with DAC enabled')
                register_writes['wave_bytes'] += 1
                loaded_wave[address-0xFF30] = p.register_file.A
        elif kind in ('wave_low', 'pulse_low'):
            period_low[kind.split('_')[0]] = p.register_file.A
        elif kind in ('wave_high', 'pulse_high'):
            channel = kind.split('_')[0]
            register_writes['triggers' if channel == 'wave' else 'pulse_triggers'] += bool(p.register_file.A & 0x80)
            apu_periods[channel] = ((p.register_file.A & 7) << 8) | period_low[channel]
        elif kind == 'pulse_envelope':
            register_writes['pulse_envelopes'] += 1
        elif kind == 'sweep':
            if p.register_file.A:
                hook_failures.append('CH1 hardware sweep enabled')
        elif kind == 'level':
            register_writes['levels'] += 1

    # Decode only the two straight machine-code function ranges; hooks on
    # immediate bytes would corrupt instructions. Observe actual writes,
    # including an unexpected steady-state trigger or live wave RAM load.
    three_bytes = {0x01,0x08,0x11,0x21,0x31,0xC2,0xC3,0xC4,0xCA,0xCC,0xCD,
                   0xD2,0xD4,0xDA,0xDC,0xEA,0xFA}
    two_bytes = {0x06,0x0E,0x10,0x16,0x18,0x1E,0x20,0x26,0x28,0x2E,0x30,0x36,
                 0x38,0x3E,0xC6,0xCB,0xCE,0xD6,0xDE,0xE0,0xE6,0xE8,0xEE,
                 0xF0,0xF6,0xF8,0xFE}
    address = symbols['_audio_init'] & 65535
    end = symbols['_audio_effect'] & 65535
    while address < end:
        offset = 3 * 0x4000 + address - 0x4000
        opcode = rom_bytes[offset]
        kind = None
        if opcode == 0x77:
            kind = 'wave_hl'
        elif opcode == 0x12:
            kind = 'wave_de'
        elif opcode == 0xE0:
            kind = {0x10: 'sweep', 0x12: 'pulse_envelope',
                    0x13: 'pulse_low', 0x14: 'pulse_high',
                    0x1D: 'wave_low', 0x1E: 'wave_high', 0x1C: 'level'}.get(rom_bytes[offset + 1])
        if kind:
            p.hook_register(3, address, apu_write, kind)
        address += 3 if opcode in three_bytes else 2 if opcode in two_bytes else 1
    assert address == end, 'instruction decoder crossed function boundary'

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
            assert not hook_failures, hook_failures
            if capture:
                chunk = p.sound.ndarray.copy()
                if engine_min_level:
                    assert p.memory[0xFF26] & 5 == 5, 'an engine channel dropped out'
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
        mixed = frames(72, engine_min_level=minimum_level)
        # Isolate CH3 in this APU fixture to check the original cycle/pitch
        # independently of the new pulse's stronger higher harmonics.
        # Both generators keep running; production never changes routing.
        p.memory[0xFF25] = 0x44
        frames(2)
        wave = frames(72, engine_min_level=3)
        p.memory[0xFF25] = 0xFF
        frames(2)
        return mixed, wave

    def silent():
        # Ignore the transition frame and measure AC, not PyBoy's DC bias.
        frames(2)
        data = frames(3)
        assert not audible(data), ('not silent', np.ptp(data[:, 0].astype(np.int16)))

    def write_wav(name, data):
        with wave.open(str(out / name), 'wb') as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(p.sound.sample_rate)
            wav.writeframes((data.astype(np.int16) * 256).astype('<i2').tobytes())

    def waveform_correlation(data, period, mode, shift):
        # Match the real PCM against the intended shifted wave at its exact
        # hardware period, with only the unknown starting phase fitted.
        samples = data[:12000, 0].astype(float)
        phase = np.arange(len(samples)) * (65536 / (2048 - period)) * 32 / p.sound.sample_rate
        expected = waves[mode] >> shift
        return max(abs(float(np.corrcoef(samples, expected[(phase + shift).astype(int) % 32])[0, 1]))
                   for shift in np.arange(0, 32, .125))

    report = {}
    try:
        for _ in range(120):
            frames(1, False)
            if get('ready'):
                break
        assert get('ready'), 'driver did not boot'
        assert p.memory[0xFF24] == 0x55 and p.memory[0xFF25] == 0xFF
        assert p.memory[0xFF26] & 0x80
        assert bytes(p.memory[0xFF30:0xFF40]) == expected_wave[0], 'initial wave differs from idle cycle'
        assert register_writes['wave_bytes'] == 16, register_writes
        silent()
        put('riding', 1)
        put('half_rate', 1)
        idle, idle_wave = engine_segment()
        assert p.memory[0xFF12] >> 4 <= 2, 'idle exhaust exceeds quieter peak'
        assert get('engine_mode') == 0
        assert len(idle) >= p.sound.sample_rate, 'idle capture shorter than one second'
        put('gas', 1)
        low, low_wave = engine_segment()
        assert p.memory[0xFF12] == 0x60, 'loaded exhaust volume'
        steady_load = dict(register_writes)
        # CGB active wave RAM reads alias the byte being played. Inspect the
        # actual DAC-off writes, then independently verify emitted PCM below.
        assert get('engine_mode') == 1 and bytes(loaded_wave) == expected_wave[1]
        put('speed', 16000, 2)
        high, high_wave = engine_segment()
        put('brake', 1)
        brake, brake_wave = engine_segment()
        assert register_writes['pulse_triggers'] == steady_load['pulse_triggers'], 'loaded exhaust retriggered on speed/brake'
        assert register_writes['pulse_envelopes'] == steady_load['pulse_envelopes'], 'loaded envelope rewritten'
        put('gas', 0)
        put('brake', 0)
        coast, coast_wave = engine_segment()
        assert get('engine_mode') == 0 and bytes(loaded_wave) == expected_wave[0]
        put('brake', 1)
        brake_idle, brake_idle_wave = engine_segment()
        put('brake', 0)
        put('gas', 1)
        resumed, resumed_wave = engine_segment()
        assert register_writes['triggers'] == 4, ('engine retriggered without a mode change', register_writes)
        assert register_writes['levels'] == 5, ('unnecessary level writes', register_writes)
        assert register_writes['wave_bytes'] == 64, ('wave rewritten without a mode change', register_writes)
        assert register_writes['pulse_triggers'] > 4, 'idle volume envelope never changed'
        content_correlation = waveform_correlation(high_wave, int(periods[16000 >> 6]), 1, 0)
        assert content_correlation > .98, ('PCM does not reproduce the original cycle', content_correlation)
        idle_correlation = waveform_correlation(idle_wave, engine['idle_period'], 0, 1)
        assert idle_correlation > .98, ('idle PCM differs from its recorded cycle', idle_correlation)
        assert len(np.unique(high[:, 0])) >= 6, 'engine is still a two-level pulse'
        pitches = {name: fundamental(data) for name, data in
                   [('idle', idle_wave), ('gas_idle', low_wave), ('gas_fast', high_wave),
                    ('brake_fast', brake_wave), ('coast_fast', coast_wave),
                    ('brake_no_gas', brake_idle_wave), ('gas_resumed', resumed_wave)]}
        levels = {name: int(np.ptp(data[:, 0].astype(np.int16))) for name, data in
                  [('idle', idle), ('gas_idle', low), ('gas_fast', high),
                   ('brake_fast', brake), ('coast_fast', coast), ('brake_no_gas', brake_idle),
                   ('gas_resumed', resumed)]}
        assert abs(pitches['idle']-engine['idle_hz']) < 1, pitches
        assert abs(pitches['gas_idle']-engine['load_base_hz']) < 1, pitches
        assert abs(pitches['coast_fast'] - pitches['idle']) < 1, pitches
        assert abs(pitches['brake_no_gas'] - pitches['idle']) < 1, pitches
        assert 1.8 < pitches['gas_fast']/pitches['gas_idle'] < 2, pitches
        assert abs(pitches['gas_fast']-reference_hz[16000]) < 1, pitches
        assert abs(pitches['brake_fast']-pitches['gas_fast']) < 1, pitches
        assert abs(pitches['gas_resumed'] - pitches['gas_fast']) < 1, pitches
        assert 6 <= levels['idle'] < levels['gas_idle'] and 15 <= levels['gas_idle'] <= 23, levels
        # CH1's duty position survives retriggers, so relative phase and peak
        # sums may differ after a mode change. Check both layers separately.
        assert np.ptp(idle_wave[:, 0]) == np.ptp(coast_wave[:, 0]) == np.ptp(brake_idle_wave[:, 0]) == 7
        assert 15 <= levels['gas_fast'] <= 23 and 15 <= levels['gas_resumed'] <= 23, levels
        assert np.array_equal(high[:, 0], high[:, 1]), 'stereo routing differs'
        report['engine_hz'] = pitches
        report['engine_pcm_peak_to_peak'] = levels
        report['idle_seconds'] = round(len(idle) / p.sound.sample_rate, 3)
        report['engine_30hz_continuity_verified'] = True
        report['engine_wave_pcm_correlation'] = round(content_correlation, 6)
        report['idle_wave_pcm_correlation'] = round(idle_correlation, 6)
        report['original_pitch_curve_max_error_hz'] = pitch_error
        report['engine_wave_sha256'] = {name: details['wave_sha256'] for name, details in engine['loops'].items()}
        report['steady_engine_register_writes'] = dict(register_writes)
        write_wav('engine-example.wav', np.concatenate([idle, low, high, coast]))
        # Inspect native CH1 PCM: a 12.5% pulse exactly one octave above the
        # source cycle, with no sweep, clipping or automatic volume decay.
        p.memory[0xFF25] = 0x11
        frames(2)
        pulse = frames(72, engine_min_level=6)
        p.memory[0xFF25] = 0xFF
        frames(2)
        # A narrow pulse's second FFT harmonic can win by bin alignment.
        # Measure actual rising-edge spacing instead of its loudest bin.
        edges = np.flatnonzero((pulse[:-1, 0] == 0) & (pulse[1:, 0] > 0))
        pulse_hz = float(p.sound.sample_rate / np.mean(np.diff(edges)))
        pulse_duty = float(np.count_nonzero(pulse[:, 0]) / len(pulse))
        assert abs(pulse_hz-2*65536/(2048-int(periods[16000 >> 6]))) < 1, pulse_hz
        assert .12 < pulse_duty < .13 and set(np.unique(pulse[:, 0])) == {0, 6}, pulse_duty
        report['exhaust_pulse'] = {'hz': pulse_hz, 'duty_fraction': pulse_duty, 'volume': 6}
        # Observe low/mid/high speed bins and the entire argument boundary.
        # The reference uses original radians/model-second, not LUT indices.
        for speed in (0, 63, 64, 255, 1024, 4096, 8192, 16781, 32767, 32768, 65535):
            put('speed', speed, 2)
            data, wave_pcm = engine_segment()
            assert abs(fundamental(wave_pcm) - reference_hz[speed]) < 1.3, speed
            if speed == 16781:
                write_wav('engine-wheel-cap.wav', data)
        # Apple feedback shares the mixer with a running engine. Include
        # this costlier update path in the measured CPU budget and verify
        # that effect control writes leave CH3 phase and data untouched.
        triggers = register_writes['triggers']
        put('half_rate', 0)
        put('fx', 1)
        frames(2)
        assert p.memory[0xFF26] & 7 == 7, 'apple did not coexist with both engine channels'
        # Include the worst combination: a new effect control point and a
        # throttle-mode switch in the same update, in both directions.
        for mode in (0, 1) * 4:
            put('gas', mode)
            frames(1, engine_min_level=3)
        frames(effect_lengths[1] + 2, engine_min_level=3)
        assert register_writes['triggers'] == triggers + 8, 'apple restarted engine phase'
        put('riding', 0)
        frames(3)
        silent()
        assert not (p.memory[0xFF26] & 5), 'pause left an engine channel active'
        assert bytes(p.memory[0xFF30:0xFF40]) == expected_wave[1], 'loaded wave corrupted during playback'
        # Resume/restart and coast must retrigger a valid channel.
        put('reset_request', 1)
        frames(2)
        put('riding', 1)
        put('gas', 0)
        assert audible(frames(6))
        # Repeated throttle edges must change timbre once per edge, remain
        # audible, keep bank/IRQ state intact and never write active wave RAM.
        before = dict(register_writes)
        put('half_rate', 1)
        for mode in (1, 0) * 12:
            put('gas', mode)
            # A request written at the emulator frame boundary can arrive
            # after the 30 Hz caller has sampled it; allow its next return.
            frames(3, engine_min_level=3)
            assert get('engine_mode') == mode
            assert bytes(loaded_wave) == expected_wave[mode]
        assert register_writes['triggers']-before['triggers'] == 24
        assert register_writes['pulse_triggers']-before['pulse_triggers'] == 24
        assert register_writes['wave_bytes']-before['wave_bytes'] == 24*16
        put('riding', 0)
        frames(2)
        put('half_rate', 0)
        lengths = {}
        effect_pcm = {}
        noise_activity = {}
        for half_rate in (0, 1):
            put('half_rate', half_rate)
            for effect, duration in effect_lengths.items():
                put('fx', effect)
                capture = [frames(1)]
                stable_steps = {}
                assert p.memory[0xFF26] & (2 if effect < 2 else 8), ('wrong effect channel', effect)
                while get('effect_active'):
                    before_note = get('effect_note')
                    capture.append(frames(1))
                    # A full frame within one control point must actually
                    # contain noise. Whole-effect RMS alone used to miss
                    # completely silent, repeatedly reset slow-LFSR steps.
                    if effect >= 2 and get('effect_active') and get('effect_note') == before_note:
                        level = int(np.ptp(capture[-1][:, 0].astype(np.int16)))
                        stable_steps[before_note] = max(stable_steps.get(before_note, 0), level)
                    assert len(capture) < duration + 4, ('effect never stopped', effect)
                age = (get('sys_time', 2) - get('effect_start', 2)) & 65535
                assert duration <= age <= duration + half_rate, ('wrong effect duration', effect, age)
                data = np.concatenate(capture)
                assert audible(data), ('inaudible effect', effect, half_rate)
                if not half_rate:
                    write_wav('effect-%d.wav' % effect, data)
                    effect_pcm[effect] = data
                if effect >= 2:
                    name = effect_names[effect]
                    for index, step in enumerate(manifest['effects'][name]['windows']):
                        if step['volume'] >= 2 and duration - index * 4 >= 3:
                            assert stable_steps.get(index, 0) >= 1, ('silent noise control point',
                                                                     name, half_rate, index, stable_steps)
                    noise_activity['%s-%dhz' % (name, 30 if half_rate else 60)] = stable_steps
                silent()
                assert not (p.memory[0xFF26] & 0x0F), ('effect stuck', effect, half_rate)
                lengths['%d-%dhz' % (effect, 30 if half_rate else 60)] = age
        # Creak owns an independent CH2 scheduler while riding. Isolate its
        # native PCM to verify the whole contour at both service rates.
        creak_duration = manifest['effects']['creak']['duration_vblanks']
        for half_rate in (0, 1):
            put('half_rate', half_rate)
            put('riding', 1)
            frames(2)
            p.memory[0xFF25] = 0x22
            put('fx', 4)
            capture = [frames(1)]
            assert get('creak_active') and p.memory[0xFF26] & 2, 'creak did not start on CH2'
            while get('creak_active'):
                capture.append(frames(1))
                assert len(capture) < creak_duration + 4, 'creak never stopped'
            age = (get('sys_time', 2) - get('creak_start', 2)) & 65535
            assert creak_duration <= age <= creak_duration + half_rate, ('wrong creak duration', age)
            data = np.concatenate(capture)
            assert audible(data), ('inaudible creak', half_rate)
            assert not (p.memory[0xFF26] & 2), 'creak stuck on CH2'
            lengths['4-%dhz' % (30 if half_rate else 60)] = age
            if not half_rate:
                write_wav('effect-4.wav', data)
                effect_pcm[4] = data
            p.memory[0xFF25] = 0xFF
            put('riding', 0)
            silent()
        put('half_rate', 0)
        report['effect_durations_vblanks'] = lengths
        report['noise_step_pcm_peak_to_peak'] = noise_activity
        reference = effect_pcm[0]
        assert int(np.ptp(reference[:, 0].astype(np.int16))) == 8, 'menu beep level changed'
        assert rms(low) > rms(reference) and rms(low) > rms(idle), 'engine still underuses its output range'
        hpf_reference = cgb_hpf_rms(reference, p.sound.sample_rate)
        relative = {}
        for name, data in [('idle', idle), ('gas_idle', low), ('gas_fast', high),
                           ('menu', reference), ('apple', effect_pcm[1]),
                           ('crash', effect_pcm[2]), ('finish', effect_pcm[3]),
                           ('creak', effect_pcm[4]), ('volt', effect_pcm[5]), ('turn', effect_pcm[6])]:
            filtered = cgb_hpf_rms(data, p.sound.sample_rate)
            relative[name] = {'pcm_rms': round(rms(data), 4), 'cgb_hpf_proxy_rms': round(filtered, 4),
                              'cgb_hpf_proxy_db_vs_menu': round(20 * math.log10(filtered / hpf_reference), 2)}
        # Guard the corrected mix with one common gain. Never normalize
        # individual clips, which would hide the hardware volume regression.
        # CH1 load is 25% below 0.91, idle is stepped 0..2; CH3 stays intact.
        assert relative['gas_idle']['cgb_hpf_proxy_db_vs_menu'] > -11, relative
        assert relative['gas_fast']['cgb_hpf_proxy_db_vs_menu'] > -9, relative
        assert -19 < relative['idle']['cgb_hpf_proxy_db_vs_menu'] < relative['gas_idle']['cgb_hpf_proxy_db_vs_menu'], relative
        # The old crash measured about -17.7 dB over this whole capture;
        # require at least roughly 6 dB improvement, beyond gain alone.
        assert relative['crash']['cgb_hpf_proxy_db_vs_menu'] > -12, relative
        report['relative_volume'] = relative
        report['volume_model_note'] = 'CGB HPF proxy only; no speaker response or physical validation.'
        # A menu click cannot preempt the finish; an apple cannot replace crash.
        put('fx', 3)
        frames(2)
        put('fx', 0)
        frames(6)
        assert p.memory[0xFF26] & 8 and not (p.memory[0xFF26] & 2), 'menu interrupted finish'
        frames(effect_lengths[3])
        put('fx', 2)
        frames(2)
        put('fx', 1)
        frames(2)
        assert p.memory[0xFF26] & 8 and not (p.memory[0xFF26] & 2), 'apple interrupted crash'
        frames(effect_lengths[2])
        # Skip updates while an apple is playing. Age must catch up immediately.
        put('fx', 1)
        frames(2)
        put('hold', 1)
        frames(effect_lengths[1] + 2)
        silent()
        put('hold', 0)
        frames(2)
        silent()
        assert not (p.memory[0xFF26] & 0x0F)
        # A gap shorter than the whole finish must jump directly to its
        # current contour, including if the hardware watchdog has expired.
        put('fx', 3)
        frames(1)
        put('hold', 1)
        frames(20)
        silent()
        put('hold', 0)
        frames(1)
        age = (get('sys_time', 2) - get('effect_start', 2)) & 65535
        assert get('effect_note') == age >> 2, ('late effect did not skip expired steps', age)
        frames(effect_lengths[3])
        silent()
        # Engine hardware watchdog also expires without software or extra IRQs.
        put('riding', 1)
        put('gas', 1)
        frames(3)
        put('hold', 1)
        stopped_after = 0
        while p.memory[0xFF26] & 5:
            frames(1)
            stopped_after += 1
            assert stopped_after <= 16, 'engine watchdog exceeded 250 ms'
        assert 13 <= stopped_after <= 16, stopped_after
        silent()
        assert not (p.memory[0xFF26] & 5), 'an engine watchdog did not expire'
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
        frames(effect_lengths[1] + 2)
        silent()
        assert not (p.memory[0xFF26] & 0x0F), 'wrapped effect stuck'
        # Keep the no-motion baseline distinct from real riding, whose
        # bounded pose observation must also fit the gameplay CPU budget.
        put('bike_alive', 0)
        put('riding', 1)
        for gas in (0, 1):
            put('gas', gas)
            frames(74, engine_min_level=3)
        put('riding', 0)
        silent()
        assert get('banks_bad', 2) == 0, 'bank not restored'
        assert get('irq_count', 2) > 100, 'VBlank IRQs disabled'
        assert p.memory[0xFFFF] & 1 and not (p.memory[0xFF07] & 4), 'IRQ/timer changed'
        assert idle_phases == set(range(21)) and idle_levels == {0, 1, 2}, 'idle contour incomplete'
        assert len(idle_pitch_indices) > 1, 'idle pitch never varied'
        report['idle_modulation'] = {'phases_seen': sorted(idle_phases), 'volumes_seen': sorted(idle_levels),
                                     'pitch_indices_seen': sorted(idle_pitch_indices), 'wave_pitch_preserved': True}
        assert bytes(p.memory[0xFF30:0xFF40]) == expected_wave[1], 'effects corrupted wave RAM'
        report.update(bank_restore_failures=get('banks_bad', 2),
                      cycle_budget_t=CYCLE_BUDGET,
                      vblank_irqs=get('irq_count', 2), stereo_verified=True,
                      pause_resume_verified=True, skipped_updates_verified=True,
                      wrap_verified=True, watchdog_verified=True,
                      watchdog_stop_vblanks=stopped_after,
                      engine_only_cycles={'min': min(engine_cycles), 'max': max(engine_cycles),
                                          'mean': round(sum(engine_cycles) / len(engine_cycles), 1)},
                      inactive_bike_cycles={'min': min(inactive_bike_cycles), 'max': max(inactive_bike_cycles),
                                            'mean': round(sum(inactive_bike_cycles) / len(inactive_bike_cycles), 1)},
                      transition_cycles={'min': min(transition_cycles), 'max': max(transition_cycles),
                                         'mean': round(sum(transition_cycles) / len(transition_cycles), 1)},
                      update_cycles={'min': min(cycles), 'max': max(cycles),
                                     'mean': round(sum(cycles) / len(cycles), 1)})
        write_wav('preview.wav', np.concatenate(samples))
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
        assert cycles and max(cycles) <= CYCLE_BUDGET['update'], ('audio update budget', max(cycles))
        assert engine_cycles and max(engine_cycles) <= CYCLE_BUDGET['live_steady'], ('steady engine budget', max(engine_cycles))
        assert inactive_bike_cycles and max(inactive_bike_cycles) <= CYCLE_BUDGET['inactive_steady'], ('inactive bike budget', max(inactive_bike_cycles))
        assert transition_cycles and max(transition_cycles) <= CYCLE_BUDGET['transition'], ('throttle transition budget', max(transition_cycles))
    finally:
        p.stop(save=False)


if __name__ == '__main__':
    main()
