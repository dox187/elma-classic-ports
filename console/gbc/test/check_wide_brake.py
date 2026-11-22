#!/usr/bin/env python3
"""Check wide brake torques against 1,500 independent Python oracle cases.

Run with the GBC virtualenv Python and scheduled Q24 tables in --gen.
Synthetic packed bike states exercise int32 wrapping, signed angle shifts,
Q24 rounding/saturation, both phases, and zero/nonzero wheel contacts.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import struct
import subprocess
import sys

from pyboy import PyBoy

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'tools'))
import brake_dispatch

SEED = 96

DRIVER = '''#include <gb/gb.h>
#include <gb/cgb.h>
#include <stddef.h>
#include <string.h>
#include "physics_core.h"
#include "vectors.h"
typedef char circle_abi[sizeof(circle_t)==24 && offsetof(circle_t,alfa)==16 &&
 offsetof(circle_t,omega)==20 ? 1 : -1];
typedef char bike_abi[sizeof(bike_t)==119 && offsetof(bike_t,body)==0 &&
 offsetof(bike_t,wheel)==24 && offsetof(bike_t,dbrake)==101 &&
 sizeof(((bike_t*)0)->dbrake[0])==4 ? 1 : -1];
typedef char row_abi[sizeof(row_t)==135 && offsetof(row_t,contacts)==119 &&
 offsetof(row_t,phase)==121 && offsetof(row_t,expected)==122 &&
 offsetof(row_t,fraction)==130 && offsetof(row_t,saturated)==134 ? 1 : -1];
bike_t Bike;
uint8_t riding_landing_contact[2],riding_subphase;
row_t row;uint8_t arena[16];
volatile uint8_t done;
extern int32_t q24_fraction;extern uint8_t q24_saturated;
volatile uint16_t failures,guards,state_bad,banks_bad,q24_bad,count;
volatile int32_t first_actual,first_expected;volatile uint16_t first_case;
void riding_brake32(int32_t*) __sdcccall(0);
void riding_brake_fields(int32_t*,int32_t*);
void check(void) {
 uint8_t k,left=4,right=8;
 memcpy(&Bike,row.bike,sizeof(Bike));
 memcpy(riding_landing_contact,row.contacts,2);riding_subphase=row.phase;
 memset(arena,0xa5,16);SWITCH_ROM(8);
 if(count & 2) {
  left=9;right=2;
  riding_brake_fields((int32_t*)(arena+left),(int32_t*)(arena+right));
 } else riding_brake32((int32_t*)(arena+left));
 if(q24_fraction!=row.fraction || q24_saturated!=row.saturated)++q24_bad;
 if(CURRENT_BANK!=8)++banks_bad;
 for(k=0;k<2;k++)if((*(int32_t*)(arena+(k?right:left)))!=row.expected[k]) {
  if(!failures) {
   first_actual=(*(int32_t*)(arena+(k?right:left)));first_expected=row.expected[k];first_case=count;
  }
  failures++;
 }
 for(k=0;k<16;k++)if((k<left||k>=left+4)&&(k<right||k>=right+4)&&arena[k]!=0xa5)guards++;
 if(memcmp(&Bike,row.bike,sizeof(Bike)))state_bad++;
 count++;
}
void main(void) {
 uint16_t i;disable_interrupts();DISPLAY_OFF;cpu_fast();
'''

def s32(value):
    return (value + 2**31) % 2**32 - 2**31


def q24(value, coefficient):
    return max(-2**31, min(2**31-1, (value*coefficient + 2**23) >> 24))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gen', type=Path, default=BASE / 'build/gen-v096-8m')
    parser.add_argument('--out', type=Path, default=BASE / 'build/wide-brake-check',
                        help='New output directory (must not exist)')
    args = parser.parse_args()
    gen, out, src = args.gen.resolve(), args.out.resolve(), BASE / 'src'
    if out.exists():
        parser.error('--out must be a fresh directory')
    constants = {name: list(map(int, values.split(','))) for name, values in re.findall(
        r'q24_(C_BRAKE_\w+)\[2\]=\{([^}]+)\}', (gen / 'riding_constants.h').read_text())}
    required = ('C_BRAKE_A', 'C_BRAKE_W', 'C_BRAKE_GW')
    if any(name not in constants or len(constants[name]) != 2 for name in required):
        parser.error('--gen must provide both phases of the scheduled brake Q24 constants')
    out.mkdir(parents=True)
    rng = random.Random(SEED)
    rows = []
    values = [-2**31, -2**31+1, -1000000, -65537, -65536, -32769, -32768,
              -16384, -1, 0, 1, 16384, 32767, 32768, 65535, 65536, 1000000, 2**31-1]
    for i in range(1500):
        state = bytearray(rng.randbytes(119))
        phase, contacts = i % 2, bytes([i % 3, (i // 3) % 3])
        omega = values[i % len(values)] if i < 324 else rng.randint(-2**31, 2**31-1)
        alfa = rng.getrandbits(32)
        struct.pack_into('<Ii', state, 16, alfa, omega)
        expected = []
        for k in range(2):
            angle, brake = rng.getrandbits(32), rng.getrandbits(32)
            speed = (values[(i // len(values) + k) % len(values)] if i < 324
                     else rng.randint(-2**31, 2**31-1))
            struct.pack_into('<Ii', state, 40+24*k, angle, speed)
            struct.pack_into('<I', state, 101+4*k, brake)
            # Subtractions wrap before the signed angle shift / Q24 products.
            da, dw = s32(angle-alfa-brake) >> 8, s32(speed-omega)
            damping = 'C_BRAKE_GW' if contacts[k] else 'C_BRAKE_W'
            expected.append(s32(-q24(da, constants['C_BRAKE_A'][phase])
                                - q24(dw, constants[damping][phase])))
        # Q24 leaves the last wheel's damping residual and saturation flag live.
        raw = dw * constants[damping][phase]
        rounded = (raw + 2**23) >> 24
        saturated = rounded != q24(dw, constants[damping][phase])
        fraction = 0 if saturated else raw - (rounded << 24)
        rows.append(bytes(state) + contacts + bytes([phase])
                    + struct.pack('<iiiB', *expected, fraction, saturated))
    header = ('#include <stdint.h>\n'
              'typedef struct {uint8_t bike[119],contacts[2],phase;int32_t expected[2],fraction;uint8_t saturated;} row_t;\n')
    sources = []
    driver = DRIVER
    for bank, start in enumerate(range(0, len(rows), 80), 10):
        block = rows[start:start+80]
        header += f'extern const uint8_t rows{bank}[{len(block)}][135];\n'
        path = out / f'vec{bank}.c'
        path.write_text(f'#pragma bank {bank}\n#include "vectors.h"\n'
                        f'const uint8_t rows{bank}[{len(block)}][135]={{\n'
                        + ',\n'.join('{' + ','.join(map(str, row)) + '}' for row in block)
                        + '\n};\n')
        sources.append(path)
        driver += (f'for(i=0;i<{len(block)};i++){{SWITCH_ROM({bank});'
                   f'memcpy(&row,rows{bank}[i],sizeof(row));check();}}\n')
    (out / 'vectors.h').write_text(header)
    (out / 'driver.c').write_text(driver + 'done=1;while(1){}}\n')
    brake_source = src / 'physics_brake_fast.s'
    brake = brake_dispatch.generate(gen, brake_source, out / 'physics_brake_game.s')
    common = [brake, src / 'physics_q24.s']
    tables = [gen / 'physics_q24_dispatch.c', *sorted(gen.glob('physics_q24_table_*.c'))]
    inputs = [out / 'driver.c', *common, *tables, *sources]
    rom = out / 'check.gbc'
    command = [BASE / '.toolchain/gbdk/bin/lcc', '-msm83:gb', '-Wf--opt-code-size',
               '-Wm-yC', '-Wm-yt0x19', '-Wm-yoA', '-Wl-m', '-Wl-j',
               '-I'+str(out), '-I'+str(gen), '-I'+str(src), '-o', rom, *inputs]
    result = subprocess.run(list(map(str, command)), capture_output=True, text=True)
    (out / 'compile.log').write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f'Build failed; see {out / "compile.log"}')
    hashes = {}
    for prefix, paths in (('fixture', list(out.glob('*.c')) + list(out.glob('*.h'))),
                          ('source', common + [brake_source, Path(brake_dispatch.__file__)] + list(src.glob('*.h'))),
                          ('generated', tables + list(gen.glob('*.h')))):
        for path in paths:
            hashes[f'{prefix}/{path.name}'] = hashlib.sha256(path.read_bytes()).hexdigest()
    hashes['test/check_wide_brake.py'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    provenance = dict(seed=SEED, constants=constants,
                      vectors_sha256=hashlib.sha256(b''.join(rows)).hexdigest(),
                      input_sha256=hashes, rom_sha256=hashlib.sha256(rom.read_bytes()).hexdigest())
    (out / 'build.json').write_text(json.dumps(provenance, indent=2) + '\n')
    symbols = {name: int(value, 16) for name, value in re.findall(
        r'DEF (_\w+) 0x([0-9A-Fa-f]+)', rom.with_suffix('.noi').read_text())}
    emulator = PyBoy(str(rom), window='null', sound_emulated=False, cgb=True)
    emulator.set_emulation_speed(0)

    def number(name, size=2, signed=False):
        address = symbols['_'+name]
        return int.from_bytes(bytes(emulator.memory[address:address+size]), 'little', signed=signed)

    failures = ('failures', 'guards', 'state_bad', 'banks_bad', 'q24_bad')
    try:
        for _ in range(200):
            emulator.tick(50, False)
            if number('done', 1):
                break
        report = {name: number(name) for name in (*failures, 'count', 'first_case')}
        report.update(done=number('done', 1), first_actual=number('first_actual', 4, True),
                      first_expected=number('first_expected', 4, True), expected_cases=len(rows),
                      vectors_sha256=provenance['vectors_sha256'])
    finally:
        emulator.stop(save=False)
    report['passed'] = bool(report['done'] and report['count'] == len(rows)
                            and not any(report[name] for name in failures))
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
