"""Derive idle/load engine cycles and native effect contours from elma.res.

No PCM is streamed by the cartridge. Two 16-byte CH3 waves, an original
wheel-speed/pitch lookup, and short CH2/CH4 controls are emitted. CH1 reinforces
the engine with a native pulse at the same period register. WAVs stay local.
"""
import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sys
import wave

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'console/snes/tools'))
from elmadata import Resource

MIX_RATE = 11025
VBLANK_HZ = 4194304 / 70224
STEP_TICKS = 4
LOOPS = {'harl.wav': (7526, 34648), 'harl2.wav': (14490, 18906)}
CROSSFADE = 100


def read_wave(resource, name):
    data = resource.read(name)
    with wave.open(io.BytesIO(data), 'rb') as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise ValueError(name + ': expected original mono 16-bit PCM')
        samples = np.frombuffer(wav.readframes(wav.getnframes()), '<i2').astype(float)
        metadata = {'wav_sha256': hashlib.sha256(data).hexdigest(),
                    'header_rate_hz': wav.getframerate(),
                    'mixer_rate_hz': MIX_RATE, 'samples': len(samples)}
    return samples, metadata


def engine_cycle(samples, start, end):
    # H_WAV.CPP wav::loopol: crossfade the last 100 samples into the first
    # 100, then shorten the loop by 100. The source loader's gain does not
    # affect normalized cycle selection.
    loop = samples[start:end].copy()
    ramp = np.arange(CROSSFADE) / CROSSFADE
    loop[:CROSSFADE] = loop[:CROSSFADE] * ramp + loop[-CROSSFADE:] * (1 - ramp)
    loop = loop[:-CROSSFADE]
    loop -= loop.mean()
    lags = np.arange(32, 257)
    correlations = np.array([np.corrcoef(loop[:-lag], loop[lag:])[0, 1] for lag in lags])
    period = int(lags[correlations.argmax()])

    # Locate complete cycles using the fundamental only. Read the waveform
    # itself from the original unfiltered samples, so its exhaust harmonics
    # survive; never average arbitrary phases or the two different engines.
    spectrum = np.fft.rfft(loop)
    frequencies = np.fft.rfftfreq(len(loop))
    spectrum[(frequencies < .65 / period) | (frequencies > 1.5 / period)] = 0
    fundamental = np.fft.irfft(spectrum, n=len(loop))
    crossings = np.where((fundamental[:-1] < 0) & (fundamental[1:] >= 0))[0]
    crossings = crossings - fundamental[crossings] / (
        fundamental[crossings + 1] - fundamental[crossings])
    candidates = []
    for left, right in zip(crossings[:-1], crossings[1:]):
        if left < CROSSFADE or not .75 * period <= right - left <= 1.3 * period:
            continue
        original = np.interp(np.linspace(left, right, 256, endpoint=False),
                             np.arange(len(loop)), loop)
        original -= original.mean()
        fft = np.fft.rfft(original)
        fft[16:] = 0  # Keep only harmonics representable by a 32-sample wave.
        coarse = np.fft.irfft(fft[:17], n=32) * (32 / 256)
        harmonics = np.abs(np.fft.rfft(coarse))[1:16]
        harmonics /= np.linalg.norm(harmonics)
        reconstructed = np.interp(np.arange(256) / 8, np.arange(33),
                                  np.r_[coarse, coarse[0]])
        fidelity = float(np.corrcoef(original, reconstructed)[0, 1])
        candidates.append((left, right, coarse, harmonics, fidelity, original))
    if not candidates:
        raise ValueError('No complete engine cycles in the original loop')
    # Select a real cycle closest to the loop's median harmonic profile,
    # rather than synthesizing an averaged cycle which never existed.
    median = np.median([candidate[3] for candidate in candidates], axis=0)
    median /= np.linalg.norm(median)
    selected = max(candidates, key=lambda candidate: float(candidate[3] @ median) * candidate[4])
    left, right, coarse, harmonics, fidelity, original = selected
    quantized = np.rint((coarse - coarse.min()) * 15 / np.ptp(coarse)).astype(np.uint8)
    reconstructed = np.interp(np.arange(256) / 8, np.arange(33),
                              np.r_[quantized, quantized[0]])
    quantized_fidelity = float(np.corrcoef(original, reconstructed)[0, 1])
    packed = bytes(int(quantized[i] << 4) | int(quantized[i + 1]) for i in range(0, 32, 2))
    return packed, {
        'original_loop_range_samples': [start, end],
        'crossfade_samples': CROSSFADE, 'loop_samples_after_crossfade': len(loop),
        'autocorrelation_lag_samples': period,
        'autocorrelation': round(float(correlations.max()), 6),
        'loop_fundamental_hz': round(MIX_RATE / period, 4),
        'candidate_cycles': len(candidates),
        'selected_source_cycle_samples': [round(start + left, 6), round(start + right, 6)],
        'selected_cycle_hz': round(MIX_RATE / (right - left), 4),
        'harmonic_profile_similarity': round(float(harmonics @ median), 6),
        'resampled_source_correlation': round(fidelity, 6),
        'quantized_source_correlation': round(quantized_fidelity, 6),
        'harmonic_energy_fractions': [round(float(value * value), 6) for value in harmonics[:8]],
        'wave_nibbles': quantized.tolist(), 'wave_sha256': hashlib.sha256(packed).hexdigest(),
    }


def noise_periods():
    # Match the source spectral centroid to 15-bit noise held at each legal
    # LFSR clock. This is a coarse colour approximation, not sample playback.
    frequencies = np.linspace(0, 24000, 4097)
    result = []
    for shift in range(14):
        for divider in range(8):
            clock = 262144 / ((divider or .5) * 2 ** shift)
            # Retriggering clears the 15-bit LFSR. Its first output needs
            # 15 clocks: slower rates can stay silent for the entire
            # four-VBlank step. Require startup within one VBlank, leaving
            # the rest of the step for audible noise and its envelope.
            if clock < 15 * VBLANK_HZ:
                continue
            power = np.sinc(frequencies / clock) ** 2
            centroid = float((frequencies * power).sum() / power.sum())
            result.append((shift << 4 | divider, centroid))
    return result


def effect_contour(samples, noise, max_volume):
    duration = int(np.ceil(len(samples) * VBLANK_HZ / MIX_RATE))
    if not 1 <= duration <= 255:
        raise ValueError('Effect exceeds the native control table duration')
    windows = []
    for tick in range(0, duration, STEP_TICKS):
        left = round(tick * MIX_RATE / VBLANK_HZ)
        right = min(len(samples), round((tick + STEP_TICKS) * MIX_RATE / VBLANK_HZ))
        part = samples[left:right].copy()
        part -= part.mean()
        spectrum = np.abs(np.fft.rfft(part * np.hanning(len(part)))) ** 2
        frequencies = np.fft.rfftfreq(len(part), 1 / MIX_RATE)
        # CH2 cannot represent fundamentals below 64 Hz. Select the strongest
        # representable source component instead of clamping sub-bass rumble.
        first = 1 if noise else int(np.searchsorted(frequencies, 64))
        peak = int(np.argmax(spectrum[first:]) + first)
        centroid = float((spectrum * frequencies).sum() / max(1, spectrum.sum()))
        windows.append({'rms': float(np.sqrt(np.mean(part * part))),
                        'peak_hz': float(frequencies[peak]), 'centroid_hz': centroid,
                        'second_harmonic_ratio': float(spectrum[min(2 * peak, len(spectrum) - 1)] /
                                                       max(1, spectrum[peak]))})
    maximum = max(window['rms'] for window in windows)
    volumes = [int(round(window['rms'] * max_volume / maximum)) for window in windows]
    noise_choices = noise_periods() if noise else []
    steps = []
    for index, window in enumerate(windows):
        volume = volumes[index]
        next_volume = volumes[index + 1] if index + 1 < len(volumes) else 0
        difference = next_volume - volume
        envelope = 0
        if volume:
            # The hardware envelope fills the space between software updates.
            pace = int(np.clip(round(64 * STEP_TICKS / VBLANK_HZ / abs(difference)), 1, 7)) if difference else 0
            envelope = volume << 4 | (8 if difference > 0 else 0) | pace
        if noise:
            period = min(noise_choices, key=lambda choice: abs(np.log(choice[1] / window['centroid_hz'])))[0]
            duty = 0
        else:
            period = int(np.clip(round(2048 - 131072 / window['peak_hz']), 0, 2047))
            duty = 0x40 if window['second_harmonic_ratio'] > .08 else 0x80
        steps.append((period, envelope, duty))
        window.update(volume=volume, period=period, envelope=envelope, duty=duty)
    return steps, {'duration_vblanks': duration, 'step_vblanks': STEP_TICKS,
                   'channel': 4 if noise else 2,
                   **({'noise_startup_max_vblanks': 1} if noise else {}),
                   'method': 'RMS envelope and spectral centroid mapped to 15-bit noise' if noise else
                             'RMS envelope, strongest representable source frequency (>=64 Hz) and second-harmonic duty mapped to pulse',
                   'windows': [{key: round(value, 4) if isinstance(value, float) else value
                                for key, value in window.items()} for window in windows]}


def engine_pitches(constants, base_hz):
    """Convert the native omega units before applying the PC mixer curve."""
    data = constants.read_text()
    def value(name):
        match = re.search(r'^#define '+name+r'\s+([\d.]+)', data, re.M)
        if not match:
            raise ValueError('Missing physics constant: '+name)
        return float(match[1])
    rate, angle_units = value('PH_RATE'), value('RIDING_ANGLE_UNITS')
    # Scheduled integration keeps angular units independent of frame length.
    unit_time = (value('PH_ANGULAR_UNIT_TIME') if 'PH_ANGULAR_UNIT_TIME' in data
                 else .4368 / rate)
    omega_scale = angle_units / (2 * math.pi) * unit_time / 128
    # At most 64 native omega units per bin. Center interior bins; preserve
    # exactly zero wheel speed. Values above the audio lookup range clamp.
    speed = np.arange(512) * 64 + 32
    speed[0] = 0
    multiplier = 2 - np.exp(-np.minimum(speed / omega_scale * .025, 30))
    target = base_hz * multiplier
    periods = np.rint(2048 - 65536 / target).astype(int)
    # The caller saturates abs(int32 wheel.omega) to 32768 before narrowing.
    # The uint16 mixer API also saturates larger inputs to that lookup limit.
    all_speed = np.minimum(np.arange(65536), 32768)
    exact = base_hz * (2 - np.exp(-np.minimum(all_speed / omega_scale * .025, 30)))
    actual = 65536 / (2048 - periods[np.minimum(all_speed >> 6, 511)])
    return periods.tolist(), {
        'original_curve': '2 - exp(-min(abs(omega) * 0.025, 30))',
        'physics_constants_sha256': hashlib.sha256(constants.read_bytes()).hexdigest(),
        'physics_hz': int(value('PH_HZ')), 'physics_rate_hz': rate,
        'pc_schedule': bool(re.search(r'^#define RIDING_PC_SCHEDULE 1$', data, re.M)),
        'angle_units_per_turn': int(angle_units), 'omega_units_per_rad_model_second': omega_scale,
        'lookup_shift': 6, 'lookup_entries': 512, 'lookup_speed_units': speed.tolist(),
        'target_hz': target.tolist(), 'periods': periods.tolist(),
        'max_error_hz_over_uint16': float(np.max(np.abs(actual - exact))),
        'wheel_cap_units': int(value('WHEEL_MAXW')),
        'wheel_cap_multiplier': float(2 - math.exp(-value('WHEEL_MAXW') / omega_scale * .025)),
    }


def generate(res_path, out, constants=None):
    out.mkdir(parents=True, exist_ok=True)
    resource = Resource(res_path)
    loops = {}
    waves = {}
    for name, (start, end) in LOOPS.items():
        samples, metadata = read_wave(resource, name)
        waves[name], details = engine_cycle(samples, start, end)
        loops[name] = metadata | details
    # Preserve the playback rate of each selected real cycle. The loops are
    # nonstationary; these rates are representative cycle pitches, not a claim
    # that either complete recording has a single exact fundamental.
    idle_hz = loops['harl.wav']['selected_cycle_hz']
    load_hz = loops['harl2.wav']['selected_cycle_hz']
    idle_period = round(2048 - 65536 / idle_hz)
    pitches, curve = engine_pitches(constants or out / 'riding_constants.h', load_hz)
    header = ['#ifndef GBC_AUDIO_ASSETS_H', '#define GBC_AUDIO_ASSETS_H',
              '/* Generated from local elma.res; no streamed PCM. */',
              '#if PH_HZ != %d || RIDING_ANGLE_UNITS != %dL' %
              (curve['physics_hz'], curve['angle_units_per_turn']),
              '#error Regenerate audio assets for this physics profile', '#endif',
              '#if defined(RIDING_PC_SCHEDULE) != %d' % curve['pc_schedule'],
              '#error Regenerate audio assets for this physics integration schedule', '#endif',
              '#define AUDIO_IDLE_PERIOD %d' % idle_period,
              'static const uint8_t engine_wave[2][16] = {',
              '    {' + ','.join('0x%02X' % value for value in waves['harl.wav']) + '},',
              '    {' + ','.join('0x%02X' % value for value in waves['harl2.wav']) + '}};',
              '/* speed>>6, saturated to 511; original 1..2 playback multiplier. */',
              'static const uint16_t engine_pitch[512] = {',
              '    ' + ','.join(str(value) for value in pitches) + '};']
    effects = {}
    for label, name, noise, volume in [('apple', 'eves.wav', False, 10),
                                       ('crash', 'torik.wav', True, 15),
                                       ('finish', 'siker.wav', True, 15),
                                       ('creak', 'dorzsol.wav', False, 8),
                                       ('volt', 'ugras.wav', True, 12),
                                       ('turn', 'fordul.wav', True, 10)]:
        samples, metadata = read_wave(resource, name)
        steps, details = effect_contour(samples, noise, volume)
        effects[label] = {'source': name} | metadata | details
        header += ['#define AUDIO_%s_TICKS %d' % (label.upper(), details['duration_vblanks']),
                   'static const effect_step_t %s_steps[] = {' % label,
                   '    ' + ','.join('{%d,0x%02X,0x%02X}' % step for step in steps) + '};']
    header += ['#endif', '']
    (out / 'audio_assets.h').write_text('\n'.join(header))
    manifest = {
        'source_res_sha256': hashlib.sha256(res_path.read_bytes()).hexdigest(),
        'source_logic': ['src/H_WAV.CPP: wav::wav and wav::loopol',
                         'desktop/F_SDL/SDL_HHIGH.CPP: I1..I5, Mix and starthanghigh',
                         'src/LEJATSZO.CPP: driven-wheel frequency 2-exp(-abs(omega)*0.025), WAV_UGRAS1/2 and WAV_FORDULAS',
                         'src/LEPTET.CPP: surlodasverseny positive compression displacement and velocity',
                         'console/gbc/src/physics_core.h: PH_WS angular-velocity units',
                         'desktop/F_SDL/SDL_SOUND.CPP: fixed 11025 Hz mixer'],
        'mixer_note': 'The original loader ignores WAV header rate; all samples use the 11025 Hz mixer.',
        'engine': {'idle_source': 'harl.wav', 'load_source': 'harl2.wav',
                   'wave_bytes': 32, 'samples_per_wave': 32, 'bits': 4,
                   'selection': 'A real complete cycle nearest each source loop median harmonic profile, '
                                'band-limited to 15 harmonics and quantized to 4 bits. '
                                'The two source cycles are kept separate and played at their source rates.',
                   'loops': loops, 'pitch_formula': '65536 / (2048 - period)',
                   'idle_hz': idle_hz, 'idle_period': idle_period, 'load_base_hz': load_hz,
                   'curve': curve,
                   'pulse_layer': {'channel': 1, 'duty_percent': 12.5,
                                   'idle_volume': [0, 2], 'load_volume': 6,
                                   'frequency_ratio_to_wave': 2,
                                   'method': 'Native exhaust reinforcement; unchanged CH3 source cycles, '
                                             'idle CH1 envelope breathes over 21 VBlanks and pitch walks by 1% every 2-3 cycles, '
                                             'resetting at +/-5%; CH3 retains its source period.'},
                   'wave_switch': 'Only at throttle-mode changes, with CH3 DAC off; no active wave RAM writes.'},
        'effects': effects,
        'suspension_trigger': 'New supported wheel contact with incoming terrain-normal speed above 6 model m/s; '
                              'contact and impact are observed before collision response, not inferred from spring travel; '
                              'one audio observation per physics step; mute when both wheels leave ground.',
        'limitations': ['Representative periodic engine cycles cannot reproduce the complete changing recordings or their start/rev transition.',
                       'The CH1 exhaust pulse improves speaker audibility but adds a synthesized timbre to the original-derived CH3 cycles.',
                       'Native pulse/noise effect contours are approximations, not the original PCM.',
                       'No music is added. No listening or physical-hardware validation is implied.'],
    }
    (out / 'audio-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--res', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--constants', type=Path, help='physics units (default: OUT/riding_constants.h)')
    args = parser.parse_args()
    result = generate(args.res, args.out, args.constants)
    print(json.dumps({'engine_sources': [result['engine']['idle_source'], result['engine']['load_source']],
                      'wave_bytes': result['engine']['wave_bytes'],
                      'idle_hz': result['engine']['idle_hz'], 'load_base_hz': result['engine']['load_base_hz'],
                      'max_pitch_error_hz': result['engine']['curve']['max_error_hz_over_uint16'],
                      'effect_ticks': {name: effect['duration_vblanks'] for name, effect in result['effects'].items()}}))
