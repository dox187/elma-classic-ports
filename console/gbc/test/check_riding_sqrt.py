"""Exercise every square boundary and random bounded inputs on the SM83."""
import argparse
from io import BytesIO
import json
import math
from pathlib import Path
import random
import re
import subprocess

from pyboy import PyBoy

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / 'build/play-physics/sqrt-check'


def check_linked(rom, values):
    symbols = {name: int(addr, 16) for name, addr in re.findall(
        r'^DEF (\S+) 0x([0-9a-fA-F]+)', rom.with_suffix('.noi').read_text(), re.M)}
    image = bytearray(rom.read_bytes())
    def offset(name):
        addr = symbols[name]
        return (addr >> 16) * 16384 + (addr & 16383)
    large, upper, small, direct = map(offset, ('_riding_sqrt_large', '_riding_sqrt_upper',
                                               '_riding_sqrt_small', '_riding_sqrt_byte'))
    for n in range(1 << 20):
        if n < 256:
            root = image[direct+n]
        else:
            index, digit = divmod(n, 16 if n < 16384 else 256)
            base = small if n < 16384 else large
            pos = base + (index >> 8)*512 + (index & 255)
            root = image[pos] - (digit < image[pos+256])
            if n >= 16384:
                root += image[upper+(n >> 16)] << 8
        assert root == math.isqrt(n), (n, root)

    image[0x100:0x102] = bytes((0x18, 0xfe))
    emu = PyBoy(BytesIO(image), window='null', sound_emulated=False, cgb=True)
    emu.set_emulation_speed(0)
    entry = symbols['_riding_isqrt20']
    code, stack = 0xc900, 0xcff0
    cases = sorted(set(values + list(range(256)) + list(range(256, 16384, 16))
                       + list(range(16384, 1 << 20, 256))))
    try:
        emu.tick(240, False)
        emu.memory[code:code+6] = [0xf3, 0xcd, entry & 255, entry >> 8, 0x18, 0xfe]
        for i, n in enumerate(cases):
            bank = (8, 9, 15, 35, 175)[i % 5]
            emu.memory[symbols['__current_bank']] = bank
            emu.memory[0x2000] = bank
            emu.memory[0x3000] = 0
            args = n.to_bytes(4, 'little') + bytes((0xa3, 0xd7))
            emu.memory[stack:stack+6] = args
            reg = emu.register_file
            reg.SP, reg.PC = stack, code
            emu.tick(1, False)
            assert (reg.D << 8 | reg.E) == math.isqrt(n), (n, reg.D, reg.E)
            assert (reg.SP, reg.PC) == (stack, code+4)
            assert bytes(emu.memory[stack:stack+6]) == args
            assert emu.memory[symbols['__current_bank']] == bank
            assert bytes(emu.memory[0x4000:0x4020]) == image[bank*16384:bank*16384+32]
    finally:
        emu.stop(save=False)
    print(f'{1 << 20} exact table values and {len(cases)} linked square roots passed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, help='Verify the exact tables and reader of this cartridge')
    args = parser.parse_args()
    values = [0, (1 << 20)-1]
    for root in range(1024):
        values.extend(n for n in (root*root-1, root*root, root*root+1)
                      if 0 <= n < 1 << 20)
    rng = random.Random(0x5A27)
    values += [rng.randrange(1 << 20) for _ in range(1024)]
    if args.rom:
        return check_linked(args.rom, values)
    OUT.mkdir(parents=True, exist_ok=True)
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
