"""Derive a fixed GBC engine wave and native effect contours from elma.res.

No PCM is streamed by the cartridge. Only one 16-byte CH3 wave, period
values, and short CH2/CH4 control tables are emitted. WAVs remain local.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
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
        peak = int(np.argmax(spectrum[1:]) + 1)
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
                   'method': 'RMS envelope and spectral centroid mapped to 15-bit noise' if noise else
                             'RMS envelope, dominant frequency and second-harmonic duty mapped to pulse',
                   'windows': [{key: round(value, 4) if isinstance(value, float) else value
                                for key, value in window.items()} for window in windows]}


def generate(res_path, out):
    out.mkdir(parents=True, exist_ok=True)
    resource = Resource(res_path)
    loops = {}
    waves = {}
    for name, (start, end) in LOOPS.items():
        samples, metadata = read_wave(resource, name)
        waves[name], details = engine_cycle(samples, start, end)
        loops[name] = metadata | details
    # A single idle-loop cycle keeps the lowest engine tone recognizable.
    # harl2 is analyzed and documented but is not mixed into an unrelated
    # phase, nor swapped into live wave RAM as the throttle changes.
    selected = 'harl.wav'
    packed = waves[selected]
    pitches = [round(2048 - 65536 / frequency) for frequency in range(64, 345, 8)]
    header = ['#ifndef GBC_AUDIO_ASSETS_H', '#define GBC_AUDIO_ASSETS_H',
              '/* Generated from local elma.res; no streamed PCM. */',
              'static const uint8_t engine_wave[16] = {',
              '    ' + ','.join('0x%02X' % value for value in packed) + '};',
              '/* CH3: 65536 / (2048-period), 64..344 Hz in 8 Hz steps. */',
              'static const uint16_t engine_pitch[36] = {',
              '    ' + ','.join(str(value) for value in pitches) + '};']
    effects = {}
    for label, name, noise, volume in [('apple', 'eves.wav', False, 10),
                                       ('crash', 'torik.wav', True, 12),
                                       ('finish', 'siker.wav', True, 10)]:
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
                         'desktop/F_SDL/SDL_SOUND.CPP: fixed 11025 Hz mixer'],
        'mixer_note': 'The original loader ignores WAV header rate; all samples use the 11025 Hz mixer.',
        'engine': {'selected_source': selected, 'wave_bytes': 16, 'samples': 32, 'bits': 4,
                   'selection': 'A real complete cycle nearest the idle loop median harmonic profile, '
                                'band-limited to 15 harmonics and quantized to 4 bits. '
                                'The loaded-engine loop is analyzed for comparison; no phase averaging.',
                   'wave_sha256': hashlib.sha256(packed).hexdigest(), 'loops': loops,
                   'pitch_formula': '65536 / (2048 - period)', 'periods': pitches,
                   'target_hz': list(range(64, 345, 8))},
        'effects': effects,
        'limitations': ['One periodic engine cycle cannot reproduce the original changing exhaust texture.',
                       'Native pulse/noise effect contours are approximations, not the original PCM.',
                       'No music is added. No listening or physical-hardware validation is implied.'],
    }
    (out / 'audio-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--res', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = generate(args.res, args.out)
    print(json.dumps({'engine_source': result['engine']['selected_source'],
                      'wave_bytes': result['engine']['wave_bytes'],
                      'effect_ticks': {name: effect['duration_vblanks'] for name, effect in result['effects'].items()}}))
