#!/usr/bin/env python3
"""Compare scheduled SM83 physics with the matching HOST implementation.

Builds a standalone ROM using the production collision packer and synthetic
flat/rotated surfaces. No original game assets are required. Every outer step
compares explicitly serialized fields, never the padded HOST structure bytes.
Run with the GBC virtualenv Python (PyBoy), --gen containing scheduled tables.
An optional --case-file replaces the built-in suite with a JSON list. Each case
requires name, level (0 flat, 1 -15 degrees, 2 +15 degrees, 3 air), height,
speed, keys and steps. Optional turned defaults to true; controls supplies
per-step key masks (then keys resumes), and turns lists outer-step indexes.
Optional seed maps whitelisted bike fields to raw integers at fixture_ready;
these are synthetic initial states, not controller-generated gameplay.
"""
import argparse
import ctypes as C
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import time

import compare_pc_physics as comparison

BASE = Path(__file__).resolve().parents[1]
CORE = comparison.GBC_SOURCES
NATIVE_EXTRA = ('physics_q24.c', 'physics_force.c', 'physics_math.s', 'physics_mul_fast.s',
                'physics_mul16u8.s', 'physics_math32_bounds.s', 'physics_math32_exact.s', 'physics_contact_loop.s',
                'physics_segment_scan.s', 'physics_normal_fast.s', 'physics_shift_fast.s',
                'physics_sqrt_fast.s', 'physics_div_fast.s', 'physics_sin_fast.s',
                'physics_spring_torque.s', 'physics_q24.s', 'physics_div20.s',
                'physics_export_fast.s','physics_rider_fast.s','physics_rider_response.s','physics_rider_coeff.s','physics_phase.s','physics_circle_scheduled.s',
                'physics_supports_fast.s','physics_ordered_pair.s','physics_free_fast.s','physics_roll_fast.s','physics_wheel_bridge.c',
                'physics_angle.c','physics_body_angle.s','physics_geometry.c','physics_pose_lookup.s','physics_head_pose.s','physics_brake_fast.s',
                'physics_suspension_scheduled.s','physics_step_scheduled.s','physics_level_bounds.s','physics_recip_fast.s','physics_contact_filter.s','physics_reaction_division.s')
TABLES = ('physics_quarter_*.c', 'physics_scale_*.c', 'physics_sine_*.c',
                'physics_q24_table_*.c', 'physics_rider_rows.c')

# Explicit offsets in packed SM83 bike_t, not padded ctypes offsets. Angles
# are deliberately excluded: changing them would invalidate cached sin/cos.
def seed_fields(wide):
    fields = {}
    stride = 24 if wide else 22
    for index, part in enumerate(('body', 'wheel0', 'wheel1')):
        for field, offset, fmt, ctype in (('vx', 8, 'i', C.c_int32),
                ('vy', 12, 'i', C.c_int32),
                ('omega', 20, 'i' if wide else 'h', C.c_int32 if wide else C.c_int16)):
            fields[f'{part}.{field}'] = (index*stride+offset, fmt, ctype)
    fields.update(rider_vx=(80 if wide else 74, 'i', C.c_int32),
                  rider_vy=(84 if wide else 78, 'i', C.c_int32))
    for index in range(2):
        fields[f'volt[{index}]'] = ((109 if wide else 103)+index, 'B', C.c_uint8)
        fields[f'volt_omega[{index}]'] = ((111+4*index) if wide else (105+2*index),
                         'i' if wide else 'h', C.c_int32 if wide else C.c_int16)
    return fields

SEED_FIELDS = seed_fields(True)


def integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label} must be an integer in [{low}, {high}]')


def load_cases(path, settings):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'Duplicate JSON key: {key}')
            result[key] = value
        return result

    suite = json.loads(path.read_text(), object_pairs_hook=unique_object)
    if not isinstance(suite, list) or not 1 <= len(suite) <= 65535:
        raise ValueError('Case file must contain 1..65535 cases')
    required = {'name', 'level', 'height', 'speed', 'keys', 'steps'}
    optional = {'seed', 'controls', 'turns', 'turned'}
    names = set()
    for index, case in enumerate(suite):
        label = f'case[{index}]'
        if not isinstance(case, dict) or not required <= case.keys() or case.keys() - required - optional:
            raise ValueError(f'{label} requires {sorted(required)}; optional fields: {sorted(optional)}')
        name = case['name']
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError(f'{label}.name must be a nonempty, unique string')
        names.add(name)
        if 'turned' in case and type(case['turned']) is not bool:
            raise ValueError(f'{label}.turned must be a boolean')
        integer(case['level'], 0, 3, f'{label}.level')
        integer(case['keys'], 0, 15, f'{label}.keys')
        integer(case['steps'], 1, 65535, f'{label}.steps')
        for field, scale in (('height', 65536), ('speed', settings['velocity_scale'])):
            value = case[field]
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f'{label}.{field} must be finite numeric data')
            raw = math.floor(value * scale + .5) if field == 'height' else round(value * scale)
            integer(raw, -(1 << 31), (1 << 31) - 1, f'{label}.{field} scaled to int32')
        for field in ('controls', 'turns'):
            if field not in case:
                continue
            values = case[field]
            if not isinstance(values, list) or len(values) > case['steps']:
                raise ValueError(f'{label}.{field} must be a list no longer than steps')
            for value in values:
                integer(value, 0, 15 if field == 'controls' else case['steps'] - 1,
                        f'{label}.{field} entry')
            if field == 'turns' and len(set(values)) != len(values):
                raise ValueError(f'{label}.turns must contain unique step indexes')
        seed = case.get('seed', {})
        if not isinstance(seed, dict):
            raise ValueError(f'{label}.seed must be a field-to-integer object')
        for field, value in seed.items():
            if field not in SEED_FIELDS:
                raise ValueError(f'{label}.seed: unsupported field {field!r}; allowed: {sorted(SEED_FIELDS)}')
            _, _, ctype = SEED_FIELDS[field]
            bits = 8 * C.sizeof(ctype)
            signed = ctype(-1).value < 0
            integer(value, -(1 << (bits - 1)) if signed else 0,
                    (1 << (bits - int(signed))) - 1, f'{label}.seed.{field}')
    return suite


def seed_host(host, field, value):
    if '.' in field:
        part, member = field.split('.')
        target = host.b.body if part == 'body' else host.b.wheel[int(part[-1])]
        setattr(target, member, value)
    elif '[' in field:
        member, index = field[:-1].split('[')
        getattr(host.b, member)[int(index)] = value
    else:
        setattr(host.b, field, value)


def packed_host(host):
    b, p = host.b, host.p
    bike = b''.join(struct.pack('<iiiiIi' if host.wide_angular else '<iiiiIh', k.rx, k.ry, k.vx, k.vy, k.alfa, k.omega)
                    for k in (b.body, *b.wheel))
    bike += struct.pack('<iiiiiiBBBBBIIBBii' if host.wide_angular else '<iiiiiiBBBBBIIBBhh', b.rider_x, b.rider_y,
                        b.rider_vx, b.rider_vy, b.head_x, b.head_y, b.turned,
                        b.gravity, b.brake_was, b.steps, b.gfrac, *b.dbrake,
                        *b.volt, *b.volt_omega)
    public = b''.join(struct.pack('<iiH', k.x, k.y, k.angle)
                      for k in (p.body, *p.wheel, p.rider, p.head))
    public += struct.pack('<BB', p.alive, p.turned)
    assert len(bike) == (119 if host.wide_angular else 109) and len(public) == 52
    fields = {'Bike': bike, 'gbc_bike': public,
            'move_residual': struct.pack('<8i', *(C.c_int32 * 8).in_dll(host.f, 'move_residual')),
            'force_residual': struct.pack('<2q', *(C.c_int64 * 2).in_dll(host.f, 'force_residual')),
            'riding_subphase': struct.pack('<B', C.c_uint8.in_dll(host.f, 'riding_subphase').value),
            'riding_audio_contact': bytes((C.c_uint8 * 2).in_dll(host.f, 'riding_audio_contact')),
            'riding_audio_impact': bytes((C.c_uint8 * 2).in_dll(host.f, 'riding_audio_impact'))}
    try:
        residual = C.c_int32.in_dll(host.f, 'angular_residual')
    except ValueError:
        pass  # Historical HOST builds predate fractional body velocity.
    else:
        fields['angular_residual'] = struct.pack('<i', residual.value)
    try:
        contacts = (C.c_uint8 * 2).in_dll(host.f, 'riding_landing_contact')
    except ValueError:
        pass  # Earlier models did not carry wheel support into the next substep.
    else:
        fields['riding_landing_contact'] = bytes(contacts)
        for name in ('riding_landing_nx', 'riding_landing_ny'):
            fields[name] = struct.pack('<2h', *(C.c_int16 * 2).in_dll(host.f, name))
    return fields


def cases(steps):
    result = []
    for level, slope in enumerate((0, -15, 15)):
        for height in (1, 4, 8):
            for speed in (0, 4, 8):
                for label, keys in ((('coast', 0), ('gas', 1), ('brake', 2))
                                    if not slope else (('brake', 2),)):
                    result.append(dict(name=f'slope{slope}-h{height}-vx{speed}-{label}',
                                       level=level, height=height, speed=speed,
                                       keys=keys, steps=steps))
    result.append(dict(name='air-volts-turns', level=3, height=20, speed=4,
                       keys=0, steps=min(120, steps)))
    return result


def controls(case, index, legacy_air=True):
    if not legacy_air or case['level'] != 3 or 'controls' in case or 'turns' in case:
        sequence = case.get('controls', [])
        return (sequence[index] if index < len(sequence) else case['keys'],
                index in case.get('turns', []))
    # Accepted impulses are deliberately separated; turn is a separate API.
    keys = 1 if index < 20 else 2 if 60 <= index < 80 else 0
    if index in (3, 35, 91):
        keys |= 4
    if index in (20, 63):
        keys |= 8
    return keys, index in (12, 40, 80)


DRIVER = '''#include <gb/gb.h>
#include <gb/cgb.h>
#include "runtime.h"
#include "physics_core.h"
volatile uint16_t fixture_case,fixture_step,fixture_limit;
volatile uint8_t fixture_done,fixture_level,fixture_input,fixture_turn,fixture_turned;
volatile int32_t fixture_y,fixture_velocity;
void fixture_config(void){} void fixture_ready(void){}
void fixture_input_hook(void){} void fixture_before(void){} void fixture_after(void){}
void main(void){
 cpu_fast();
 for(fixture_case=0;fixture_case<CASE_COUNT;++fixture_case){
  fixture_config();physics_select_level(fixture_level);physics_reset(-55706L,fixture_y);
  if(fixture_turned)physics_turn();
  Bike.body.vx=Bike.wheel[0].vx=Bike.wheel[1].vx=Bike.rider_vx=fixture_velocity;
  fixture_ready();
  for(fixture_step=0;fixture_step<fixture_limit && gbc_bike.alive;++fixture_step){
   fixture_input_hook();fixture_before();
   if(fixture_turn)physics_turn();physics_step(fixture_input);
   fixture_after();vsync();
  }
 }
 fixture_done=1;while(1)vsync();
}
'''


def run(command, log):
    result = subprocess.run([str(x) for x in command], stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'Build failed ({result.returncode}); see {log.name}')


def prepare(args, suite=None):
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    source, gen = out / 'source/gbc/src', out / 'gen'
    if source.exists() or gen.exists():
        raise ValueError('Use a fresh output directory; source snapshots are immutable')
    shutil.copytree(args.source, source)
    # The shared integer approximation tables are included relative to gbc/src.
    shared = args.source.resolve().parent.parent / 'nes/src'
    if not shared.is_dir():
        shared = BASE.parent / 'nes/src'
    shared_snapshot = out / 'source/nes/src'
    shared_snapshot.mkdir(parents=True)
    for name in ('recip.inc', 'rsqrt.inc'):
        shutil.copy2(shared / name, shared_snapshot / name)
    gen.mkdir()
    generated_inputs = set(args.gen.glob('*.h'))
    for pattern in (*TABLES, 'physics_q24_dispatch.c'):
        generated_inputs.update(args.gen.glob(pattern))
    for path in generated_inputs:
        shutil.copy2(path, gen / path.name)
    spec = importlib.util.spec_from_file_location('scheduled_geometry', BASE / 'tools/physics_level.py')
    geometry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(geometry)
    levels = []
    for slope in (0, -15, 15):
        level = comparison.fixture_levels()[0]
        solid, vertices = level.polygons[0]
        a = math.radians(slope)
        level.polygons[0] = solid, [(x * math.cos(a) - y * math.sin(a),
                                    x * math.sin(a) + y * math.cos(a)) for x, y in vertices]
        levels.append(level)
    levels.append(comparison.fixture_levels()[1])
    packer = geometry.BankPacker(geometry.FIRST_BANK)
    pairs = [geometry.pack_level(level, i, packer) for i, level in enumerate(levels)]
    geometry.write_outputs(gen, packer, *zip(*pairs))
    if args.host_source:
        host_source = out / 'host-source/gbc/src'
        shutil.copytree(args.host_source, host_source)
        shutil.copytree(shared_snapshot, out / 'host-source/nes/src')
    else:
        host_source = source
    library = comparison.build_host(out, gen, host_source, 'matching-host')
    settings = comparison.constants(gen / 'riding_constants.h')
    if not settings['pc_schedule'] or not 29 < settings['rate'] < 31:
        raise ValueError('This test requires the approximately 30 Hz outer scheduled profile')
    names = json.loads(args.native_sources.read_text()) if args.native_sources else [*CORE, *NATIVE_EXTRA]
    native_sources = [source / name for name in names]
    generated = [gen / 'physics_level_data.c', *sorted(gen.glob('physics_bank_*.c'))]
    for pattern in TABLES:
        generated.extend(sorted(gen.glob(pattern)))
    if (gen / 'physics_q24_dispatch.c').exists():
        generated.append(gen / 'physics_q24_dispatch.c')
    driver = out / 'driver.c'
    driver.write_text(f'#define CASE_COUNT {len(cases(args.steps) if suite is None else suite)}\n' + DRIVER)
    sources = [driver, *native_sources, *generated]
    flags = [args.lcc.resolve(), '-msm83:gb', '-Wf--opt-code-size',
             '-Wf--max-allocs-per-node', '-Wf100000', '-Wm-yC', '-Wm-yt0x19',
             '-Wm-yoA', '-Wl-m', '-Wl-j', '-I' + str(source), '-I' + str(gen)]
    rom = out / 'scheduled-native.gbc'
    with (out / 'compile.log').open('w') as log:
        objects = []
        for index, path in enumerate(sources):
            obj = out / f'{index:03}-{path.stem}.o'
            run([*flags, '-c', '-o', obj, path], log)
            objects.append(obj)
        run([*flags, '-o', rom, *objects], log)
    inputs = set(sources + list(source.glob('*.h')) + list(gen.glob('*.h')))
    inputs.update(host_source / name for name in CORE)
    inputs.update(host_source.glob('*.h'))
    inputs.update(shared_snapshot.glob('*.inc'))
    if (host_source / 'physics_q24.c').exists():
        inputs.add(host_source / 'physics_q24.c')
    inputs.add(BASE / 'tools/physics_level.py')
    inputs.add(Path(__file__).resolve())
    if getattr(args, 'case_file', None):
        inputs.add(args.case_file.resolve())
    hashes = {str(p): comparison.sha256(p) for p in sorted(inputs)}
    digest = hashlib.sha256(json.dumps([(str(Path(p).relative_to(out)) if Path(p).is_relative_to(out)
                                        else p, h) for p, h in hashes.items()], sort_keys=True).encode()).hexdigest()
    metadata = dict(input_sha256=hashes, source_sha256=digest,
                    rom_sha256=comparison.sha256(rom), host_sha256=comparison.sha256(library),
                    native_sources=[str(p) for p in sources], settings=settings)
    (out / 'build.json').write_text(json.dumps(metadata, indent=2) + '\n')
    return out, rom, library, settings, metadata


def verify(out, rom, library, settings, metadata, steps, timeout, suite=None):
    from pyboy import PyBoy
    import re
    symbols = {name: int(value, 16) for name, value in
               re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)', rom.with_suffix('.noi').read_text())}
    host = comparison.Gbc(library, settings)
    layout = packed_host(host)
    if ('angular_residual' in layout) != ('_angular_residual' in symbols):
        raise ValueError('HOST and native body angular residual layouts differ')
    legacy_air = suite is None
    suite = cases(steps) if suite is None else suite
    emulator = PyBoy(str(rom), window='null', sound_emulated=False, cgb=True)
    emulator.set_emulation_speed(0)
    state = dict(case=0, step=0, start=0, initialized=0, states=0,
                 ready_case=-1, duplicate_hooks=0)
    failures, costs = [], []
    results = [{**case, 'compared_steps': 0, 'death_step': None, 'costs': []} for case in suite]
    for case, result in zip(suite, results):
        if case.get('seed'):
            result['fixture_kind'] = 'seeded synthetic fixture; not controller gameplay'
            result['seed_stage'] = 'fixture_ready before first comparison'

    def read(name, size):
        address = symbols['_' + name]
        return bytes(emulator.memory[address:address + size])

    def write(name, fmt, value):
        data = struct.pack(fmt, value)
        address = symbols['_' + name]
        emulator.memory[address:address + len(data)] = data

    def compare(stage):
        state['states'] += 1
        for name, expected in packed_host(host).items():
            actual = read(name, len(expected))
            if actual != expected:
                failures.append(dict(case=suite[state['case']]['name'], step=state['step'],
                                     stage=stage, field=name, native=actual.hex(), host=expected.hex()))

    def configure(_):
        state['case'] = struct.unpack('<H', read('fixture_case', 2))[0]
        case = suite[state['case']]
        write('fixture_level', '<B', case['level'])
        write('fixture_turned', '<B', case.get('turned', True))
        write('fixture_y', '<i', math.floor(case['height'] * 65536 + .5))
        write('fixture_velocity', '<i', round(case['speed'] * settings['velocity_scale']))
        write('fixture_limit', '<H', case['steps'])
        host.reset(case['level'], case.get('turned', True), (-.85, case['height']))
        velocity = round(case['speed'] * settings['velocity_scale'])
        for part in (host.b.body, *host.b.wheel):
            part.vx = velocity
        host.b.rider_vx = velocity
        state['step'] = -1

    def ready(_):
        if state['ready_case']==state['case']:
            state['duplicate_hooks']+=1
            return
        state['ready_case']=state['case']
        for field, value in suite[state['case']].get('seed', {}).items():
            offset, fmt, _ = seed_fields(host.wide_angular)[field]
            seed_host(host, field, value)
            data = struct.pack('<' + fmt, value)
            address = symbols['_Bike'] + offset
            emulator.memory[address:address + len(data)] = data
        state['initialized'] += 1
        compare('reset')

    def input_hook(_):
        state['step'] = struct.unpack('<H', read('fixture_step', 2))[0]
        keys, turn = controls(suite[state['case']], state['step'], legacy_air)
        write('fixture_input', '<B', keys)
        write('fixture_turn', '<B', turn)

    def before(_):
        state['start'] = emulator._cycles()

    def after(_):
        result = results[state['case']]
        # An interrupt can return to a hooked RET before it executes. PyBoy
        # then reports the address twice, although the game step ran once.
        if result['compared_steps']==state['step']+1:
            state['duplicate_hooks']+=1
            return
        assert result['compared_steps']==state['step'], 'Missing native outer-step hook'
        cost = emulator._cycles() - state['start']
        costs.append(cost)
        result['costs'].append(cost)
        result['compared_steps'] += 1
        keys, turn = controls(suite[state['case']], state['step'], legacy_air)
        if turn:
            host.f.physics_turn()
        host.f.physics_step(keys)
        compare('outer-step')
        if not host.p.alive:
            result['death_step'] = state['step']

    for name, callback in [('fixture_config', configure), ('fixture_ready', ready),
                           ('fixture_input_hook', input_hook), ('fixture_before', before),
                           ('fixture_after', after)]:
        emulator.hook_register(0, symbols['_' + name], callback, None)
    start = last_update = time.monotonic()
    complete = False
    try:
        while not failures and time.monotonic() - start < timeout:
            emulator.tick(30, False)
            complete = bool(read('fixture_done', 1)[0])
            if complete:
                break
            if time.monotonic() - last_update > 30:
                print(f"Compared {len(costs)} outer steps; {suite[state['case']]['name']}", flush=True)
                last_update = time.monotonic()
    finally:
        emulator.stop(save=False)
    for result in results:
        samples = result.pop('costs')
        result['mean_tcycles'] = sum(samples) / len(samples) if samples else None
        result['max_tcycles'] = max(samples) if samples else None
    report = dict(schema='scheduled-native-v1', complete=complete,
                  passed=complete and not failures and state['initialized'] == len(suite),
                  cases_initialized=state['initialized'], compared_states=state['states'],
                  outer_steps=len(costs), differences=failures[:20], difference_count=len(failures),
                  mean_tcycles=sum(costs) / len(costs) if costs else None,
                  max_tcycles=max(costs) if costs else None, elapsed_s=time.monotonic() - start,
                  packed_bytes_per_state=sum(map(len, layout.values())), cases=results, provenance=metadata,
                  duplicate_interrupt_hooks=state['duplicate_hooks'],
                  verification_sha256=comparison.sha256(Path(__file__)),
                  cost_note='SM83 T-cycles including turn when requested; excludes vsync and reset')
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('cases', 'provenance')}, indent=2))
    return report['passed']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=BASE / 'src')
    parser.add_argument('--host-source', type=Path)
    parser.add_argument('--gen', type=Path, required=True)
    parser.add_argument('--native-sources', type=Path, help='JSON array of source-relative filenames')
    parser.add_argument('--case-file', type=Path,
                        help='JSON case list replacing the default suite; optional raw seed, controls, turns')
    parser.add_argument('--out', type=Path, default=BASE / 'build/scheduled-native-validation')
    parser.add_argument('--lcc', type=Path, default=BASE / '.toolchain/gbdk/bin/lcc')
    parser.add_argument('--steps', type=int, default=240)
    parser.add_argument('--timeout', type=float, default=1800)
    args = parser.parse_args()
    if not 1 <= args.steps <= 65535:
        parser.error('--steps must fit a nonzero uint16')
    try:
        suite = load_cases(args.case_file, comparison.constants(args.gen / 'riding_constants.h')) if args.case_file else None
    except (OSError, ValueError, OverflowError) as error:
        parser.error(str(error))
    return 0 if verify(*prepare(args, suite), args.steps, args.timeout, suite) else 1


if __name__ == '__main__':
    raise SystemExit(main())
