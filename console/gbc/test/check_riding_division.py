"""Check the narrow-quotient rider divider on the actual SM83 CPU."""
import json
from pathlib import Path
import random
import re
import subprocess

from pyboy import PyBoy

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / 'build/play-physics/division-check'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cases = []
    for d in (1, 2, 255, 256, 491, 1024, 32768, 65535):
        for q in (0, 1, 255, 256, 32767, 65535):
            for r in (0, d - 1):
                cases.append((d*q+r, d, q))
    rng = random.Random(0xD1B1DE)
    for _ in range(1024):
        d = rng.randrange(1, 65536)
        n = rng.randrange(d << 16)
        cases.append((n, d, n//d))
    (OUT/'vectors.h').write_text('''#include <stdint.h>
typedef struct {uint32_t n;uint16_t d,q;} division_vector_t;
extern const division_vector_t vectors[];
#define NCASES %d
''' % len(cases))
    (OUT/'vectors.c').write_text('#include "vectors.h"\n#pragma bank 15\n'
        'const division_vector_t vectors[]={\n'
        + ',\n'.join('{%dUL,%dU,%dU}' % row for row in cases) + '\n};\n')
    (OUT/'check.c').write_text('''#include <gb/gb.h>
#include <gb/cgb.h>
#include "vectors.h"
uint16_t riding_div_u32_u16(uint32_t n,uint16_t d) __sdcccall(0);
volatile uint16_t division_failures;
volatile uint8_t division_done;
void main(void) {
 uint16_t i;cpu_fast();SWITCH_ROM(15);
 for(i=0;i<NCASES;++i)
  if(riding_div_u32_u16(vectors[i].n,vectors[i].d)!=vectors[i].q)
   ++division_failures;
 division_done=1;
 while(1)vsync();
}
''')
    subprocess.run([str(BASE/'.toolchain/gbdk/bin/lcc'), '-msm83:gb',
        '-Wf--opt-code-size', '-Wm-yC', '-Wm-yt0x19', '-Wm-yoA', '-Wl-m', '-Wl-j',
        '-I'+str(OUT), '-o', str(OUT/'check.gbc'), str(OUT/'check.c'),
        str(OUT/'vectors.c'), str(BASE/'src/physics_div_fast.s')],
        check=True, capture_output=True, text=True)
    symbols = {k:int(v,16) for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',
               (OUT/'check.noi').read_text())}
    p = PyBoy(str(OUT/'check.gbc'), window='null', sound_emulated=False, cgb=True)
    p.set_emulation_speed(0)
    try:
        for _ in range(100):
            p.tick(100, False)
            if p.memory[symbols['_division_done']]:
                break
        assert p.memory[symbols['_division_done']], 'division test did not finish'
        a = symbols['_division_failures']
        failures = p.memory[a] + 256*p.memory[a+1]
        report = {'vectors':len(cases), 'failures':failures}
        assert not failures, report
    finally:
        p.stop(save=False)
    (OUT/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
