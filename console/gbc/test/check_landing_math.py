#!/usr/bin/env python3
"""Compare native supported damping with its C reference on synthetic states.

Covers zero/one/two contacts, either wheel, signed exact axes, nonunit and
oblique normals, narrow/wide velocities, and wrapping body impulse sums.
Uses the production coefficient tables without regenerating shared assets.
"""
import argparse
import ctypes as C
import json
from pathlib import Path
import re
import subprocess

from pyboy import PyBoy
import compare_pc_physics as comparison

BASE = Path(__file__).resolve().parents[1]
COUNT = 768
VALUES = (0, 1, -1, 255, -256, 32767, -32768, 32768,
          -32769, 123456, -234567, 1048576, -1048576, 17, -19, 65535,
          2147483647, -2147483648, 1800000000, -1800000000,
          2147483600, -2147483600, 129, -129, 128, -128, 63, -63,
          4194304, -4194304, 1000000000, -1000000000)
NORMALS = ((0, 0), (0, 16384), (0, -16384), (16384, 0), (-16384, 0),
           (11585, 11585), (-11585, 11585), (11585, -11585),
           (8192, 8192), (16383, 1), (-8191, -14188), (1, -16383))


class Torque(C.Structure):
    _fields_ = [('relx', C.c_int32 * 2), ('rely', C.c_int32 * 2),
                ('kx', C.c_int16 * 2), ('ky', C.c_int16 * 2)]


def run(command, log):
    result = subprocess.run(list(map(str, command)), capture_output=True, text=True)
    log.write_text(result.stdout + result.stderr)
    if result.returncode:
        raise AssertionError(log.read_text())


def case(index):
    t = Torque()
    t.relx[:] = (VALUES[index * 3 % 32], VALUES[(index * 5 + 1) % 32])
    t.rely[:] = (VALUES[(index * 7 + 2) % 32], VALUES[(index * 11 + 3) % 32])
    t.kx[:] = (111, -222)
    t.ky[:] = (-333, 444)
    n = (NORMALS[index % 12], NORMALS[(index * 7 + 3) % 12])
    contacts = (index // 16 % 3, index // 48 % 3)
    return t, n, contacts, C.c_int32(VALUES[(index + 5) % 32]), C.c_int32(VALUES[(index + 9) % 32])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gen', type=Path, default=BASE / 'build/gen-8m')
    parser.add_argument('--out', type=Path, default=BASE / 'build/landing-math-check')
    args = parser.parse_args()
    gen, out, src = args.gen.resolve(), args.out.resolve(), BASE / 'src'
    out.mkdir(parents=True, exist_ok=True)
    if '#define RIDING_EXPONENTIAL_DAMPER 1' not in (gen/'riding_constants.h').read_text():
        parser.error('this helper fixture requires the exponential profile')
    wrapper = out / 'reference.c'
    wrapper.write_text('#include "physics_core.c"\n'
                       'void fixture_reference(riding_torque32_t *t,int32_t *x,int32_t *y) '
                       '{landing_response(t,x,y);}\n')
    physics = [src/name for name in comparison.GBC_SOURCES if name != 'physics_core.c']
    data = [gen/'physics_level_data.c', *sorted(gen.glob('physics_bank_*.c'))]
    library = out/'reference.dylib'
    run(['cc', '-shared', '-fPIC', '-O0', '-fwrapv', '-Wno-unknown-pragmas',
         '-I'+str(src), '-I'+str(gen), wrapper, *physics, *data, '-o', library],
        out/'host-compile.log')
    host = C.CDLL(str(library))
    host.fixture_reference.argtypes = [C.POINTER(Torque), C.POINTER(C.c_int32), C.POINTER(C.c_int32)]
    nx = (C.c_int16*2).in_dll(host, 'riding_landing_nx')
    ny = (C.c_int16*2).in_dll(host, 'riding_landing_ny')
    contact = (C.c_uint8*2).in_dll(host, 'riding_landing_contact')
    expected = []
    for index in range(COUNT):
        t, normal, contacts, sx, sy = case(index)
        nx[:] = [n[0] for n in normal]
        ny[:] = [n[1] for n in normal]
        contact[:] = contacts
        host.fixture_reference(C.byref(t), C.byref(sx), C.byref(sy))
        expected.append(bytes(t)+bytes(sx)+bytes(sy))
    (out/'driver.c').write_text('''#include <gb/gb.h>
#include <gb/cgb.h>
#include "physics_math32.h"
void fixture_run(void) BANKED;
extern int16_t riding_landing_nx[2],riding_landing_ny[2];
extern uint8_t riding_landing_contact[2];
riding_torque32_t fixture_t;
int32_t fixture_sx,fixture_sy;
volatile uint16_t fixture_index;
volatile uint8_t fixture_done;
void fixture_before(void) {}
void fixture_mark(void) {}
const int32_t values[]={'''+','.join(str(v)+'L' for v in VALUES)+'''};
const int16_t normals[][2]={'''+','.join('{%d,%d}' % n for n in NORMALS)+'''};
void main(void){uint16_t i;uint8_t j;cpu_fast();
 for(i=0;i<'''+str(COUNT)+''';++i){
  fixture_index=i;
  fixture_t.relx[0]=values[i*3%32];fixture_t.relx[1]=values[(i*5+1)%32];
  fixture_t.rely[0]=values[(i*7+2)%32];fixture_t.rely[1]=values[(i*11+3)%32];
  fixture_t.kx[0]=111;fixture_t.kx[1]=-222;fixture_t.ky[0]=-333;fixture_t.ky[1]=444;
  for(j=0;j<2;++j){
   riding_landing_nx[j]=normals[j?(i*7+3)%12:i%12][0];
   riding_landing_ny[j]=normals[j?(i*7+3)%12:i%12][1];
  }
  riding_landing_contact[0]=i/16%3;riding_landing_contact[1]=i/48%3;
  fixture_sx=values[(i+5)%32];fixture_sy=values[(i+9)%32];
  fixture_before();fixture_run();fixture_mark();vsync();
 }
 fixture_done=1;while(1)vsync();}
''')
    (out/'native.c').write_text('''#pragma bank 8
#include <gb/gb.h>
#include "physics_math32.h"
extern riding_torque32_t fixture_t;
extern int32_t fixture_sx,fixture_sy;
void riding_landing_response32(riding_torque32_t*,int32_t*,int32_t*) __sdcccall(0);
void fixture_run(void) BANKED {riding_landing_response32(&fixture_t,&fixture_sx,&fixture_sy);}
''')
    assembly = [p for p in sorted(src.glob('physics_*.s')) if p.name != 'physics_mul16.s']
    tables = sum((sorted(gen.glob(pattern)) for pattern in
                  ('physics_quarter_*.c', 'physics_scale_*.c', 'physics_sine_*.c',
                   'physics_coefficient_*.c')), [])
    rom = out/'native.gbc'
    run([BASE/'.toolchain/gbdk/bin/lcc', '-msm83:gb', '-Wf--opt-code-size',
         '-Wf--max-allocs-per-node', '-Wf100000', '-DRIDING_COEFFICIENT_LOOKUP',
         '-Wm-yC', '-Wm-yt0x19', '-Wm-yoA', '-Wl-m', '-Wl-j',
         '-I'+str(src), '-I'+str(gen), '-o', rom, out/'driver.c', out/'native.c',
         *physics, src/'physics_core.c', *assembly, *data, *tables,
         gen/'physics_coefficient_calls.s'], out/'native-compile.log')
    symbols = {name: int(value,16) for name,value in re.findall(
        r'DEF (_\w+) 0x([0-9A-Fa-f]+)', rom.with_suffix('.noi').read_text())}
    emu = PyBoy(str(rom), window='null', sound_emulated=False, cgb=True)
    emu.set_emulation_speed(0)
    observed, failures, timings = set(), [], []
    started = [None]
    def before(_):
        started[0] = emu._cycles()
    def mark(_):
        address = symbols['_fixture_index']
        index = emu.memory[address] + 256*emu.memory[address+1]
        if index in observed:
            return
        observed.add(index)
        actual = b''.join(bytes(emu.memory[symbols[name]:symbols[name]+size])
                          for name,size in (('_fixture_t',24),('_fixture_sx',4),('_fixture_sy',4)))
        if actual != expected[index]:
            failures.append({'index':index, 'actual':actual.hex(), 'expected':expected[index].hex()})
        timings.append(emu._cycles()-started[0])
    emu.hook_register(0,symbols['_fixture_before'],before,None)
    emu.hook_register(0,symbols['_fixture_mark'],mark,None)
    try:
        for _ in range(100):
            emu.tick(50,False)
            if emu.memory[symbols['_fixture_done']]:
                break
        done = bool(emu.memory[symbols['_fixture_done']])
    finally:
        emu.stop(save=False)
    report = {'cases':COUNT,'observed':len(observed),'done':done,'failures':failures,
              'compared_bytes_per_case':32, 'math':'Production HOST C helper versus SM83 assembly',
              'cycles_including_banked_wrapper':{'min':min(timings),'mean':sum(timings)/len(timings),'max':max(timings)},
              'rom_sha256':comparison.sha256(rom), 'constants_sha256':comparison.sha256(gen/'riding_constants.h')}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    assert done and len(observed)==COUNT and not failures, 'landing math mismatch; see report.json'


if __name__ == '__main__':
    main()
