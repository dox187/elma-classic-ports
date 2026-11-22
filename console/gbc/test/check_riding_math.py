"""Run the riding SM83 math against independent integer vectors in a real ROM."""
import json
import argparse
from pathlib import Path
import random
import re
import subprocess
import sys

from pyboy import PyBoy

BASE=Path(__file__).resolve().parents[1]
OUT=BASE/'build/play-physics/math-check'


def main(gen, serial_oracle=False):
    global OUT
    if serial_oracle:
        OUT=BASE/'build/play-physics/math-check-serial'
    OUT.mkdir(parents=True,exist_ok=True)
    rng=random.Random(0xC0B0)
    cases=[(x,m,e)for x in(-32768,-32767,-1024,-1,0,1,1024,32767)
           for m in(0,1,127,128,255)for e in range(1,17)]
    cases += [(rng.randrange(-32768,32768),rng.randrange(256),rng.randrange(1,17))for _ in range(1024)]
    records=[]
    for x,m,e in cases:
        expected=max(-32768,min(32767,(x*m+(1<<(e-1)))>>e))
        records.append('{%d,%d,%d,%d}'%(x,m,e,expected))
    pairs=[(a,b)for a in(-32768,-32767,-1,0,1,127,128,32767)for b in(-32768,-32767,-1,0,1,127,128,32767)]
    pairs += [(3,10923),(-3,10923),(2,16384),(-2,16384),(32767,2),(-32767,2)]
    pairs += [(rng.randrange(-32768,32768),rng.randrange(-32768,32768))for _ in range(1024)]
    # Exercise both operand orders of the unsigned8 narrow multiplier path.
    pairs += [(a,b)for a in(-32768,-32767,-1024,-255,-1,0,1,255,1024,32767)for b in(-255,-128,-1,0,1,128,255)]
    pairs += [(rng.randrange(-32768,32768),rng.randrange(-255,256))for _ in range(256)]
    pairs += [(rng.randrange(-255,256),rng.randrange(-32768,32768))for _ in range(128)]
    # Exact power-of-two and one-lookup square paths, in both operand orders.
    pairs += [(a,b)for x in(-32768,-32767,-1024,-1,0,1,1024,32767)for y in(-16384,16384)for a,b in((x,y),(y,x))]
    pairs += [(a,b)for x in[rng.randrange(-32768,32768)for _ in range(64)]for y in(-16384,16384)for a,b in((x,y),(y,x))]
    pairs += [(a,b)for x in[rng.randrange(-32768,32768)for _ in range(64)]for a,b in((x,x),(x,-x if x!=-32768 else x))]
    (OUT/'vectors.h').write_text('''#include <stdint.h>
typedef struct {int16_t x;uint8_t m,e;int16_t expected;} scale_vector_t;
typedef struct {int16_t a,b;int32_t expected;} mul_vector_t;
extern const scale_vector_t scales[];
extern const mul_vector_t products[];
typedef struct {int16_t a,b,q14,q10;} scaled_vector_t;
extern const scaled_vector_t scaled[];
typedef struct {int16_t a,b,c,d,expected;} dot_vector_t;
extern const dot_vector_t dots[];
#define NDOTS 512
#define NSCALES %d
#define NPRODUCTS %d
'''%(len(cases),len(pairs)))
    (OUT/'vectors.c').write_text('#include "vectors.h"\n#pragma bank 15\nconst scale_vector_t scales[]={\n'
        +',\n'.join(records)+'\n};\nconst mul_vector_t products[]={\n'
        +',\n'.join('{%d,%d,%dL}'%(a,b,a*b)for a,b in pairs)+'\n};\n')
    # Keep each vector table in a separate bank when both exceed 16KiB.
    (OUT/'vectors.c').write_text((OUT/'vectors.c').read_text().split('const mul_vector_t products[]')[0])
    (OUT/'products.c').write_text('#include "vectors.h"\n#pragma bank 16\nconst mul_vector_t products[]={\n'
        +',\n'.join('{%d,%d,%dL}'%(a,b,a*b)for a,b in pairs)+'\n};\n')
    sat=lambda x:max(-32768,min(32767,x))
    (OUT/'scaled.c').write_text('#include "vectors.h"\n#pragma bank 17\nconst scaled_vector_t scaled[]={\n'
        +',\n'.join('{%d,%d,%d,%d}'%(a,b,sat((a*b+8192)>>14),sat((a*b+512)>>10))for a,b in pairs)+'\n};\n')
    dots=[(rng.randrange(-32768,32768),rng.randrange(-32768,32768),rng.randrange(-16384,16385),rng.randrange(-16384,16385))for _ in range(512)]
    (OUT/'dots.c').write_text('#include "vectors.h"\n#pragma bank 18\nconst dot_vector_t dots[]={\n'
        +',\n'.join('{%d,%d,%d,%d,%d}'%(a,b,c,d,sat((a*c+b*d+8192)>>14))for a,b,c,d in dots)+'\n};\n')
    (OUT/'check.c').write_text('''#include <gb/gb.h>
#include <gb/cgb.h>
#include "physics_math.h"
#include "vectors.h"
volatile uint8_t math_done;
volatile uint16_t scale_failures,mul_failures,quotient_failures,dot_failures,bank_failures,sat_failures;
void main(void) {
 uint16_t i;
 cpu_fast();SWITCH_ROM(15);
 for(i=0;i<NSCALES;++i) {
  if(kmul(scales[i].x,scales[i].m,scales[i].e)!=scales[i].expected)++scale_failures;
  if(CURRENT_BANK!=15)++bank_failures;
 }
 SWITCH_ROM(16);
 for(i=0;i<NPRODUCTS;++i) {
  if(sat16(products[i].expected)!=(products[i].expected>32767L?32767:products[i].expected< -32768L? -32768:(int16_t)products[i].expected))++sat_failures;
  if(riding_mul16(products[i].a,products[i].b)!=products[i].expected)++mul_failures;
  if(CURRENT_BANK!=16)++bank_failures;
 }
 SWITCH_ROM(17);
 for(i=0;i<NPRODUCTS;++i) {
  if(mulq14(scaled[i].a,scaled[i].b)!=scaled[i].q14)++quotient_failures;
  if(mulq10(scaled[i].a,scaled[i].b)!=scaled[i].q10)++quotient_failures;
  if(CURRENT_BANK!=17)++bank_failures;
 }
 SWITCH_ROM(18);
 for(i=0;i<NDOTS;++i) {
  if(dotq14(dots[i].a,dots[i].b,dots[i].c,dots[i].d)!=dots[i].expected)++dot_failures;
  if(CURRENT_BANK!=18)++bank_failures;
 }
 math_done=1;
 while(1)vsync();
}
''')
    source=BASE/'src'
    quarter_sources=[gen/('physics_quarter_%d.c'%bank)for bank in range(20,36)]
    if not serial_oracle and any(not path.is_file()for path in quarter_sources):
        subprocess.run([sys.executable,str(BASE/'tools/mul_table.py'),'--out',str(gen)],check=True)
    scale_sources=[gen/('physics_scale_%d.c'%bank)for bank in range(36,44)]
    if any(not path.is_file() for path in scale_sources) or "physics_scale_planes_36" not in scale_sources[0].read_text():
        subprocess.run([sys.executable,str(BASE/'tools/scale_table.py'),'--out',str(gen)],check=True)
    implementation='physics_mul16.s' if serial_oracle else 'physics_mul_fast.s'
    cmd=[str(BASE/'.toolchain/gbdk/bin/lcc'),'-msm83:gb','-DPHYSICS_ASM','-Wf--opt-code-size',
         '-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-I'+str(source),'-I'+str(gen),'-I'+str(OUT),
         '-o',str(OUT/'check.gbc'),str(OUT/'check.c'),str(OUT/'vectors.c'),str(OUT/'products.c'),str(OUT/'scaled.c'),str(OUT/'dots.c'),
         str(source/'physics_math.c'),str(source/'physics_math.s'),str(source/'physics_kmul_fast.s'),str(source/implementation)] + list(map(str,scale_sources))
    if not serial_oracle:
        cmd += list(map(str,quarter_sources))
    subprocess.run(cmd,check=True,capture_output=True,text=True)
    sym={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',(OUT/'check.noi').read_text())}
    rom=(OUT/'check.gbc').read_bytes()
    for bank in range(36,44):
        assert sym['_physics_scale_planes_%d'%bank]==(bank<<16)|0x4000, ('scale bank layout',bank)
        first=(bank-36)*32
        expected=bytes(((m*x) >> shift) & 255 for m in range(first,first+32) for shift in (0,8) for x in range(256))
        assert rom[bank*16384:(bank+1)*16384]==expected, ('scale ROM bytes',bank)
    if not serial_oracle:
        for bank in range(20,36):
            assert sym['_physics_quarter_%d'%bank]==(bank<<16)|0x4000, ('table bank layout',bank)
            first=(bank-20)*4096
            expected=b''.join((n*n//4).to_bytes(4,'little')for n in range(first,first+4096))
            assert rom[bank*16384:(bank+1)*16384]==expected, ('table ROM bytes',bank)
    p=PyBoy(str(OUT/'check.gbc'),window='null',sound_emulated=False,cgb=True)
    p.set_emulation_speed(0)
    try:
        for _ in range(100):
            p.tick(100)
            if p.memory[sym['_math_done']]:break
        assert p.memory[sym['_math_done']],'math test did not finish'
        def word(name):
            a=sym[name];return p.memory[a]+256*p.memory[a+1]
        report={'scale_vectors':len(cases),'product_vectors':len(pairs),
                'saturate_vectors':len(pairs),'saturate_failures':word('_sat_failures'),'scale_failures':word('_scale_failures'),'product_failures':word('_mul_failures'),
                'quotient_failures':word('_quotient_failures'),'dot_failures':word('_dot_failures'),
                'quotient_vectors':2*len(pairs),'dot_vectors':len(dots),
                'bank_restore_failures':word('_bank_failures'),'multiplication_source':implementation,
                'quarter_table_rom_bytes_verified':0 if serial_oracle else 262144,
                'coefficient_multiplication_source':'physics_kmul_fast.s','coefficient_table_rom_bytes_verified':131072}
        assert report['saturate_failures']==report['scale_failures']==report['product_failures']==report['quotient_failures']==report['dot_failures']==report['bank_restore_failures']==0,report
    finally:p.stop(save=False)
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--serial-oracle',action='store_true',help='test the independent bit-serial multiplication instead')
    parser.add_argument('--gen', type=Path, default=BASE/'build/gen-8m', help='generated scheduled physics headers and tables')
    args = parser.parse_args()
    main(args.gen.resolve(), args.serial_oracle)
