"""Check inclusive Q16.16 bike bounds, including wrapping world coordinates."""
import json
from pathlib import Path
import random
import re
import subprocess

from pyboy import PyBoy

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / 'build/play-physics/bounds-check'


def signed(n):
    return (n + (1 << 31)) % (1 << 32) - (1 << 31)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cases = []
    deltas = (-196609, -196608, -196607, -131073, -131072, -65537, -65536,
              -1, 0, 1, 65535, 65536, 131071, 131072, 196607, 196608, 196609)
    for coordinate in range(6):
        for body in (0, -1, 1, 123456789, -987654321, 2147483647, -2147483648):
            for delta in deltas:
                part = signed(body + delta)
                cases.append((body, part, coordinate, int(-196608 <= delta <= 196608)))
    rng = random.Random(0xB0A1D5)
    for _ in range(512):
        body = rng.randrange(-(1 << 31), 1 << 31)
        delta = rng.choice((rng.randrange(-250000,250001), rng.randrange(-(1 << 31),1 << 31)))
        cases.append((body, signed(body+delta), rng.randrange(6),
                      int(-196608 <= delta <= 196608)))
    (OUT/'vectors.h').write_text('''#include <stdint.h>
typedef struct {int32_t body,part;uint8_t coordinate,expected;} bounds_vector_t;
extern const bounds_vector_t vectors[];
#define NCASES %d
''' % len(cases))
    (OUT/'vectors.c').write_text('#include "vectors.h"\n#pragma bank 15\n'
        'const bounds_vector_t vectors[]={\n'
        + ',\n'.join('{%dL,%dL,%d,%d}' % row for row in cases) + '\n};\n')
    (OUT/'check.c').write_text('''#include <gb/gb.h>
#include <gb/cgb.h>
#include <string.h>
#include "runtime.h"
#include "vectors.h"
uint8_t gbc_bike_bounded(void) __sdcccall(0);
gbc_bike_t gbc_bike;
typedef char checked_layout[sizeof(gbc_bike_t)==52?1:-1];
volatile uint16_t bounds_failures,reference_failures;
volatile uint8_t bounds_done;
static const uint8_t offsets[]={10,14,20,24,30,34};
static uint8_t reference(void) {
 uint8_t i;int32_t dx,dy;
 for(i=0;i<2;++i) {
  dx=gbc_bike.wheel[i].x-gbc_bike.body.x;
  dy=gbc_bike.wheel[i].y-gbc_bike.body.y;
  if((uint32_t)(dx+196608L)>393216UL || (uint32_t)(dy+196608L)>393216UL)return 0;
 }
 dx=gbc_bike.rider.x-gbc_bike.body.x;dy=gbc_bike.rider.y-gbc_bike.body.y;
 return (uint32_t)(dx+196608L)<=393216UL && (uint32_t)(dy+196608L)<=393216UL;
}
void main(void) {
 uint16_t i;uint8_t j;int32_t bx,by;
 cpu_fast();SWITCH_ROM(15);
 for(i=0;i<NCASES;++i) {
  memset(&gbc_bike,0xa5,sizeof(gbc_bike));
  bx=by=vectors[i].body;
  if(vectors[i].coordinate&1)bx^=0x3555aa33L;else by^=0x3555aa33L;
  gbc_bike.body.x=bx;gbc_bike.body.y=by;
  for(j=0;j<2;++j){gbc_bike.wheel[j].x=bx;gbc_bike.wheel[j].y=by;}
  gbc_bike.rider.x=bx;gbc_bike.rider.y=by;
  memcpy((uint8_t*)&gbc_bike+offsets[vectors[i].coordinate],&vectors[i].part,4);
  if(gbc_bike_bounded()!=vectors[i].expected)++bounds_failures;
  if(reference()!=vectors[i].expected)++reference_failures;
 }
 bounds_done=1;
 while(1)vsync();
}
''')
    subprocess.run([str(BASE/'.toolchain/gbdk/bin/lcc'), '-msm83:gb',
        '-Wf--opt-code-size', '-Wm-yC', '-Wm-yt0x19', '-Wm-yoA', '-Wl-m', '-Wl-j',
        '-I'+str(OUT), '-I'+str(BASE/'src'), '-o', str(OUT/'check.gbc'), str(OUT/'check.c'),
        str(OUT/'vectors.c'), str(BASE/'src/physics_bounds.s')],
        check=True, capture_output=True, text=True)
    symbols = {k:int(v,16) for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',
               (OUT/'check.noi').read_text())}
    p = PyBoy(str(OUT/'check.gbc'), window='null', sound_emulated=False, cgb=True)
    p.set_emulation_speed(0)
    timings, pending, returns = [], [], set()
    def returned(_):
        if pending:
            timings.append(p._cycles()-pending.pop())
    def entered(_):
        sp = p.register_file.SP
        ret = p.memory[sp]+256*p.memory[sp+1]
        if ret not in returns:
            returns.add(ret)
            p.hook_register(0,ret,returned,None)
        pending.append(p._cycles())
    p.hook_register(0,symbols['_gbc_bike_bounded'],entered,None)
    try:
        for _ in range(100):
            p.tick(100, False)
            if p.memory[symbols['_bounds_done']]:
                break
        assert p.memory[symbols['_bounds_done']], 'bounds test did not finish'
        def word(name):
            a = symbols[name]
            return p.memory[a]+256*p.memory[a+1]
        report = {'vectors':len(cases), 'failures':word('_bounds_failures'),
                  'original_c_failures':word('_reference_failures'),
                  'cycles_min':min(timings), 'cycles_max':max(timings),
                  'cycles_mean':sum(timings)/len(timings)}
        assert not report['failures'] and not report['original_c_failures'], report
    finally:
        p.stop(save=False)
    (OUT/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
