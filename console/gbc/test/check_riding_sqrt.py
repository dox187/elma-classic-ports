"""Exercise every square boundary and random bounded inputs on the SM83."""
import json
import math
from pathlib import Path
import random
import re
import subprocess

from pyboy import PyBoy

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / 'build/play-physics/sqrt-check'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    values = [0, (1 << 20)-1]
    for root in range(1024):
        values.extend(n for n in (root*root-1, root*root, root*root+1)
                      if 0 <= n < 1 << 20)
    rng = random.Random(0x5A27)
    values += [rng.randrange(1 << 20) for _ in range(1024)]
    batches = [values[:2048], values[2048:]]
    (OUT/'vectors.h').write_text('''#include <stdint.h>
typedef struct {uint32_t n;uint16_t expected;} sqrt_vector_t;
extern const sqrt_vector_t cases15[],cases16[];
#define N15 %d
#define N16 %d
''' % tuple(map(len,batches)))
    for bank, batch in zip((15,16), batches):
        (OUT/('vectors%d.c'%bank)).write_text('#include "vectors.h"\n#pragma bank %d\n'%bank
            + 'const sqrt_vector_t cases%d[]={\n'%bank
            + ',\n'.join('{%dUL,%dU}'%(n,math.isqrt(n)) for n in batch)+'\n};\n')
    (OUT/'check.c').write_text('''#include <gb/gb.h>
#include <gb/cgb.h>
#include "vectors.h"
uint16_t riding_isqrt20(uint32_t n) __sdcccall(0);
volatile uint16_t sqrt_failures;
volatile uint8_t sqrt_done;
static void check(const sqrt_vector_t *v,uint16_t count) {
 uint16_t i;
 for(i=0;i<count;++i)
  if(riding_isqrt20(v[i].n)!=v[i].expected)++sqrt_failures;
}
void main(void) {
 cpu_fast();SWITCH_ROM(15);check(cases15,N15);
 SWITCH_ROM(16);check(cases16,N16);
 sqrt_done=1;
 while(1)vsync();
}
''')
    subprocess.run([str(BASE/'.toolchain/gbdk/bin/lcc'), '-msm83:gb',
        '-Wf--opt-code-size', '-Wm-yC', '-Wm-yt0x19', '-Wm-yoA', '-Wl-m', '-Wl-j',
        '-I'+str(OUT), '-o', str(OUT/'check.gbc'), str(OUT/'check.c'),
        str(OUT/'vectors15.c'), str(OUT/'vectors16.c'), str(BASE/'src/physics_sqrt_fast.s')],
        check=True, capture_output=True, text=True)
    symbols = {k:int(v,16) for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',
               (OUT/'check.noi').read_text())}
    p = PyBoy(str(OUT/'check.gbc'), window='null', sound_emulated=False, cgb=True)
    p.set_emulation_speed(0)
    try:
        for _ in range(100):
            p.tick(100, False)
            if p.memory[symbols['_sqrt_done']]:
                break
        assert p.memory[symbols['_sqrt_done']], 'sqrt test did not finish'
        a = symbols['_sqrt_failures']
        failures = p.memory[a] + 256*p.memory[a+1]
        report = {'vectors':len(values), 'failures':failures}
        assert not failures, report
    finally:
        p.stop(save=False)
    (OUT/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
