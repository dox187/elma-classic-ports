#!/usr/bin/env python3
"""Check wide rolling/free wheel assembly against its native C reference.

Run with the GBC virtualenv Python and scheduled Q24 tables in --gen.
The deterministic 600 vectors run in both phases (1,200 cases, each testing
rolling and free motion). Full int32 extremes are synthetic ABI fixtures,
not gameplay. Shared arithmetic helpers are intentionally outside this parity
check's independent coverage. Each call starts with zero motion residuals.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import struct
import subprocess

from pyboy import PyBoy

BASE = Path(__file__).resolve().parents[1]
SEED = 96

REFERENCE = '''#pragma bank 9
#include "physics_core.h"
#include "physics_math32.h"
typedef struct {int16_t nx,ny,l,tx,ty;} contact_t;
static void move_ref(circle_t *k) {
 k->alfa+=phase_move(k->omega,7);
 k->rx+=phase_advance(k->vx,2,4);k->ry+=phase_advance(k->vy,2,5);
}
void roll_ref(circle_t *k,const contact_t *c,int32_t dx,int32_t dy,int32_t tq) __sdcccall(0) {
 int16_t x=-c->ny,y=c->nx;
 int32_t vn=riding_dotq32(k->vx,k->vy,x,y,14),dvn=riding_dotq32(dx,dy,x,y,14);
 int32_t t=tq+Q24_MUL(dvn,C_ROLL_T),sp=vn+Q24_MUL(t,C_ROLL_DV);
 k->omega=Q24_MUL(sp,C_ROLL_W);
 k->vx=riding_mulq32(sp,x,14);k->vy=riding_mulq32(sp,y,14);move_ref(k);
}
void free_ref(circle_t *k,int32_t dx,int32_t dy,int32_t tq) __sdcccall(0) {
 k->omega+=KMUL32(tq,C_FREE);k->vx+=dx;k->vy+=dy;move_ref(k);
}
'''

DRIVER = '''#include <gb/gb.h>
#include <gb/cgb.h>
#include <stddef.h>
#include <string.h>
#include "physics_core.h"
#include "physics_q24.h"
#include "vectors.h"
typedef char circle_abi[sizeof(circle_t)==24 && offsetof(circle_t,rx)==0 &&
 offsetof(circle_t,ry)==4 && offsetof(circle_t,vx)==8 && offsetof(circle_t,vy)==12 &&
 offsetof(circle_t,alfa)==16 && offsetof(circle_t,omega)==20 ? 1 : -1];
typedef char bike_abi[sizeof(bike_t)==119 && offsetof(bike_t,body)==0 &&
 offsetof(bike_t,wheel)==24 ? 1 : -1];
bike_t Bike;
uint8_t riding_subphase;
int32_t move_residual[8];
const uint8_t riding_move_index=Q24_MOVE,riding_angle_index=Q24_ANGLE;
typedef struct {int16_t nx,ny,l,tx,ty;} contact_t;
typedef char contact_abi[sizeof(contact_t)==10 && offsetof(contact_t,nx)==0 &&
 offsetof(contact_t,ny)==2 && offsetof(contact_t,l)==4 &&
 offsetof(contact_t,tx)==6 && offsetof(contact_t,ty)==8 ? 1 : -1];
void riding_roll32(circle_t*,const contact_t*,int32_t,int32_t,int32_t) __sdcccall(0);
void roll_ref(circle_t*,const contact_t*,int32_t,int32_t,int32_t) __sdcccall(0);
void riding_free32(circle_t*,int32_t,int32_t,int32_t) __sdcccall(0);
void free_ref(circle_t*,int32_t,int32_t,int32_t) __sdcccall(0);
volatile uint16_t roll_failures,free_failures,residual_failures,guards,banks_bad,count;
volatile uint8_t done;
uint8_t arena[32],expected[24],copy[46],residual[32];
void check(void) {
 uint8_t mode,i;
 int32_t dx=*(int32_t*)(copy+34),dy=*(int32_t*)(copy+38),tq=*(int32_t*)(copy+42);
 contact_t *c=(contact_t*)(copy+24);
 SWITCH_ROM(9);
 for(mode=0;mode<2;++mode) {
  memcpy(expected,copy,24);memset(move_residual,0,32);
  if(mode)free_ref((circle_t*)expected,dx,dy,tq);
  else roll_ref((circle_t*)expected,c,dx,dy,tq);
  if(CURRENT_BANK!=9)++banks_bad;
  memcpy(residual,move_residual,32);memset(move_residual,0,32);
  memset(arena,0xa5,32);memcpy(arena+4,copy,24);
  if(mode)riding_free32((circle_t*)(arena+4),dx,dy,tq);
  else riding_roll32((circle_t*)(arena+4),c,dx,dy,tq);
  if(CURRENT_BANK!=9)++banks_bad;
  if(memcmp(arena+4,expected,24)) {if(mode)++free_failures;else ++roll_failures;}
  if(memcmp(residual,move_residual,32))++residual_failures;
  for(i=0;i<32;++i)if((i<4||i>=28)&&arena[i]!=0xa5)++guards;
 }
 ++count;
}
void main(void) {
 uint16_t i;disable_interrupts();DISPLAY_OFF;cpu_fast();
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gen', type=Path, default=BASE / 'build/gen-v096-8m')
    parser.add_argument('--out', type=Path, default=BASE / 'build/wide-wheels-check',
                        help='New output directory (must not exist)')
    args = parser.parse_args()
    gen, out, src = args.gen.resolve(), args.out.resolve(), BASE / 'src'
    if out.exists():
        parser.error('--out must be a fresh directory')
    out.mkdir(parents=True)
    rng = random.Random(SEED)
    rows = []
    values = [-2**31, -2**31+1, -65537, -32769, -32768, -1, 0, 1,
              32767, 32768, 65535, 2**31-2, 2**31-1]
    for i in range(600):
        v = [rng.choice(values) if i < 300 else rng.randint(-2**31, 2**31-1)
             for _ in range(9)]
        nx, ny = rng.choice([(0, 16384), (16384, 0), (11585, 11585),
                             (-32768, 32767), (32767, -32768)])
        rows.append(struct.pack('<iiiiIihhhhhiii', *v[:4], v[4] & 0xffffffff,
                                v[5], nx, ny, 405, 0, 0, *v[6:]))
    header = '#include <stdint.h>\ntypedef struct {uint8_t data[46];} vec_t;\n'
    sources = []
    driver = DRIVER
    for bank, start in enumerate(range(0, len(rows), 100), 60):
        block = rows[start:start+100]
        header += f'extern const vec_t vecs{bank}[];\n'
        path = out / f'vecs{bank}.c'
        path.write_text(f'#pragma bank {bank}\n#include "vectors.h"\n'
                        f'const vec_t vecs{bank}[]={{\n' + ',\n'.join(
                            '{{' + ','.join(map(str, row)) + '}}' for row in block)
                        + '\n};\n')
        sources.append(path)
        driver += (f'for(i=0;i<{len(block)};++i){{SWITCH_ROM({bank});'
                   f'memcpy(copy,&vecs{bank}[i],46);'
                   'riding_subphase=0;check();riding_subphase=1;check();}\n')
    (out / 'vectors.h').write_text(header)
    (out / 'reference.c').write_text(REFERENCE)
    (out / 'driver.c').write_text(driver + 'done=1;while(1){}}\n')
    common = [src / name for name in (
        'physics_math32_exact.s', 'physics_mul_fast.s', 'physics_mul16u8.s',
        'physics_wheel_bridge.c', 'physics_roll_fast.s', 'physics_free_fast.s',
        'physics_circle_scheduled.s', 'physics_phase.s', 'physics_q24.s')]
    tables = [path for pattern in ('physics_quarter_*.c', 'physics_scale_*.c',
                                  'physics_q24_table_*.c') for path in sorted(gen.glob(pattern))]
    tables.append(gen / 'physics_q24_dispatch.c')
    inputs = [out / 'driver.c', out / 'reference.c', *common, *sources, *tables]
    rom = out / 'check.gbc'
    command = [BASE / '.toolchain/gbdk/bin/lcc', '-msm83:gb', '-Wf--opt-code-size',
               '-Wm-yC', '-Wm-yt0x19', '-Wm-yoA', '-Wl-m', '-Wl-j',
               '-I'+str(out), '-I'+str(gen), '-I'+str(src), '-o', rom, *inputs]
    result = subprocess.run(list(map(str, command)), capture_output=True, text=True)
    (out / 'compile.log').write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f'Build failed; see {out / "compile.log"}')
    # Hash fixture sources and production inputs, including generated constants.
    hashes = {}
    for prefix, paths in (('fixture', list(out.glob('*.c')) + list(out.glob('*.h'))),
                          ('source', common + list(src.glob('*.h'))),
                          ('generated', tables + list(gen.glob('*.h')))):
        for path in paths:
            hashes[f'{prefix}/{path.name}'] = hashlib.sha256(path.read_bytes()).hexdigest()
    hashes['test/check_wide_wheels.py'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    provenance = dict(seed=SEED, vectors_sha256=hashlib.sha256(b''.join(rows)).hexdigest(),
                      input_sha256=hashes, rom_sha256=hashlib.sha256(rom.read_bytes()).hexdigest())
    (out / 'build.json').write_text(json.dumps(provenance, indent=2) + '\n')
    symbols = {name: int(value, 16) for name, value in re.findall(
        r'DEF (_\w+) 0x([0-9A-Fa-f]+)', rom.with_suffix('.noi').read_text())}
    emulator = PyBoy(str(rom), window='null', sound_emulated=False, cgb=True)
    emulator.set_emulation_speed(0)
    failures = ('roll_failures', 'free_failures', 'residual_failures', 'guards', 'banks_bad')
    try:
        for _ in range(300):
            emulator.tick(100, False)
            if emulator.memory[symbols['_done']]:
                break
        report = {name: int.from_bytes(bytes(emulator.memory[symbols['_'+name]:
                  symbols['_'+name]+2]), 'little') for name in (*failures, 'count')}
        report.update(done=emulator.memory[symbols['_done']], expected_cases=2*len(rows),
                      wheel_calls=4*len(rows), vectors_sha256=provenance['vectors_sha256'])
    finally:
        emulator.stop(save=False)
    report['passed'] = bool(report['done'] and report['count'] == 2*len(rows)
                            and not any(report[name] for name in failures))
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
