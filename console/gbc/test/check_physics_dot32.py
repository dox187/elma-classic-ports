#!/usr/bin/env python3
"""Check native signed32 dot products against unbounded Python arithmetic."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import subprocess
import time

from pyboy import PyBoy

BASE = Path(__file__).resolve().parents[1]


def vectors():
    rng = random.Random(960032)
    lo, hi = -(1 << 31), (1 << 31) - 1
    endpoints = (lo, lo + 1, -65537, -32769, -32768, -1, 0, 1,
                 32767, 32768, 65536, hi - 1, hi)
    weights = (-32768, -16384, -1, 0, 1, 16384, 32767)
    rows = [(a, b, c, d, s) for a in endpoints for b in endpoints
            for c, d in ((-32768, -32768), (-16384, 16384), (0, 0),
                         (1, -1), (32767, 32767)) for s in (1, 10, 14, 16)]
    # At -2^23, doubling the magnitude carries into the fourth product byte.
    # Opposed terms expose low bits that saturation of a single term can hide.
    for x in (-(1 << 23), -(1 << 23) + 1, (1 << 23) - 1):
        for y in (255, 256, 511, 512, 513, 767, 768):
            for sign in (-1, 1):
                rows.append((x, x + 1, sign*y, -sign*(y-1), 14))
                rows.append((x, 0, sign*y, 0, 14))
    for _ in range(4096):
        a, b = rng.randint(lo, hi), rng.randint(lo, hi)
        c, d = rng.randint(-32768, 32767), rng.choice(weights)
        rows.append((a, b, c, d, rng.randint(1, 16)))
        # Wide products cancel to a small result; early narrowing is invalid.
        b = max(lo, min(hi, a + rng.choice((-1, 0, 1))))
        rows.append((a, b, c, -c if c != -32768 else 32767,
                     rng.choice((10, 14))))
    return [(*r, max(lo, min(hi, (r[0]*r[2] + r[1]*r[3] +
                                  (1 << (r[4]-1))) >> r[4]))) for r in rows]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, default=BASE/'src')
    p.add_argument('--gen', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--lcc', type=Path, default=BASE/'.toolchain/gbdk/bin/lcc')
    a = p.parse_args()
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    rows = vectors()
    sources, loops = [], []
    header = '#include <stdint.h>\ntypedef struct {int32_t a,b;int16_t c,d;uint8_t s;int32_t want;} vec_t;\n'
    for bank, start in enumerate(range(0, len(rows), 512), 60):
        block = rows[start:start+512]
        header += f'extern const vec_t v{bank}[];\n'
        path = out/f'vectors{bank}.c'
        path.write_text(f'#pragma bank {bank}\n#include "vectors.h"\nconst vec_t v{bank}[]={{\n' +
            ',\n'.join('{'+','.join(str(x) + ('L' if i in (0, 1, 5) else '')
                                     for i, x in enumerate(r))+'}' for r in block)+'\n};\n')
        sources.append(path)
        loops.append(f'SWITCH_ROM({bank});for(i=0;i<{len(block)};++i){{'
                     f'check(&v{bank}[i]);if(CURRENT_BANK!={bank})++banks_bad;}}')
    (out/'vectors.h').write_text(header)
    driver = out/'driver.c'
    driver.write_text('''#include <gb/gb.h>
#include <gb/cgb.h>
#include "vectors.h"
int32_t riding_dotq32(int32_t,int32_t,int16_t,int16_t,uint8_t) __sdcccall(0);
volatile uint16_t checked,failures,banks_bad,first_failure;
volatile int32_t first_want,first_got;
volatile uint8_t done;
static void check(const vec_t *v){
 int32_t want=v->want,got=riding_dotq32(v->a,v->b,v->c,v->d,v->s);
 if(got!=want){if(!failures){first_failure=checked;first_want=want;first_got=got;}++failures;}
 ++checked;
}
void main(void){uint16_t i;cpu_fast();
''' + '\n'.join(loops) + '\ndone=1;while(1)vsync();}\n')
    implementation = [a.source/name for name in ('physics_math32_exact.s',
                      'physics_mul_fast.s', 'physics_mul16u8.s')]
    tables = sorted(a.gen.glob('physics_quarter_*.c')) + sorted(a.gen.glob('physics_scale_*.c'))
    assert len(tables) == 24, 'Expected 16 quarter-square and 8 scale table banks'
    rom = out/'dot32.gbc'
    command = [a.lcc.resolve(), '-msm83:gb', '-Wf--opt-code-size', '-Wm-yC',
               '-Wm-yt0x19', '-Wm-yoA', '-Wl-j', '-I'+str(out), '-o', rom,
               driver, *implementation, *sources, *tables]
    with (out/'build.log').open('w') as log:
        subprocess.run(list(map(str, command)), stdout=log, stderr=subprocess.STDOUT, check=True)
    symbols = {n: int(v, 16) for n, v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)', rom.with_suffix('.noi').read_text())}
    emu = PyBoy(str(rom), window='null', sound_emulated=False, cgb=True)
    emu.set_emulation_speed(0)
    def value(name, size=2, signed=False):
        address = symbols['_'+name]
        return int.from_bytes(bytes(emu.memory[address:address+size]), 'little', signed=signed)
    started = time.monotonic()
    try:
        while not value('done', 1) and time.monotonic()-started < 120:
            emu.tick(30, False)
        report = {n: value(n) for n in ('checked', 'failures', 'banks_bad', 'first_failure')}
        report.update(done=bool(value('done', 1)), expected=len(rows),
                      first_want=value('first_want', 4, True), first_got=value('first_got', 4, True),
                      source_sha256={str(f.resolve()): hashlib.sha256(f.read_bytes()).hexdigest()
                                     for f in [*implementation, Path(__file__)]})
        report['passed'] = report['done'] and report['checked']==len(rows) and not report['failures'] and not report['banks_bad']
        (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report, indent=2))
        assert report['passed'], 'Native dot product differs from the integer oracle'
    finally:
        emu.stop(save=False)


if __name__ == '__main__':
    main()
