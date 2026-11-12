"""Check bulk cache-reference retirement against a C model on the SM83."""
import hashlib,json,re,subprocess
from pathlib import Path
from pyboy import PyBoy
BASE=Path(__file__).resolve().parents[1]
OUT=BASE/'build/retire-check'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    source=(BASE/'src/world_retire_fast.s').read_bytes();(OUT/'retire.s').write_bytes(source)
    (OUT/'check.c').write_text('''#include <gb/gb.h>
#include <stdint.h>
#include <string.h>
void world_refs_retire(uint16_t *,const uint16_t *,uint8_t,uint8_t *) __sdcccall(0);
uint16_t refs[446],expected[446],retired[40];
uint8_t bits[58],expected_bits[58];
volatile uint16_t failures,completed,bank_failures;
volatile uint8_t done;
uint16_t seed=4723;
static uint16_t random16(void){seed=seed*25173U+13849U;return seed;}
void main(void){
 uint16_t n,i,slot;uint8_t count;
 for(n=0;n<1024;++n){
  for(i=0;i<446;++i)refs[i]=random16()&7;
  if(n&1)for(i=1;i<445;++i)refs[i]=i&1?1:0;
  memcpy(expected,refs,sizeof(refs));
  for(i=0;i<58;++i)bits[i]=(uint8_t)random16();
  memcpy(expected_bits,bits,sizeof(bits));
  count=n%41;
  for(i=0;i<count;++i)retired[i]=n<444?n:(random16()%444);
  for(i=0;i<count;++i){slot=retired[i]+1;if(expected[slot]&&!--expected[slot])expected_bits[1+(slot-1)/8]|=1U<<((slot-1)&7);}
  world_refs_retire(refs+1,retired,count,bits+1);
  if(memcmp(expected,refs,sizeof(refs))||memcmp(expected_bits,bits,sizeof(bits)))++failures;
  if(CURRENT_BANK!=1)++bank_failures;
  ++completed;
 }
 done=1;while(1)vsync();
}
''')
    command=[str(BASE/'.toolchain/gbdk/bin/lcc'),'-msm83:gb','-Wf--opt-code-size','-Wm-yC','-Wl-m','-Wl-j','-o',str(OUT/'check.gbc'),str(OUT/'check.c'),str(OUT/'retire.s')]
    r=subprocess.run(command,capture_output=True,text=True);assert r.returncode==0,r.stdout+r.stderr
    symbols={k:int(v,16) for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',(OUT/'check.noi').read_text())}
    p=PyBoy(str(OUT/'check.gbc'),window='null',sound_emulated=False,cgb=True);p.set_emulation_speed(0)
    def word(name):
        a=symbols['_'+name];return p.memory[a]+256*p.memory[a+1]
    try:
        for _ in range(100):
            p.tick(100,False)
            if p.memory[symbols['_done']]:break
        report={'status':'passed','cases':word('completed'),'failures':word('failures'),'bank_failures':word('bank_failures'),
                'source_sha256':hashlib.sha256(source).hexdigest(),'source_still_current':(BASE/'src/world_retire_fast.s').read_bytes()==source}
        assert report['cases']==1024 and not report['failures'] and not report['bank_failures'] and report['source_still_current'],report
    finally:p.stop(save=False)
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
