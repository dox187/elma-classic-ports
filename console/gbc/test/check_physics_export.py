"""Check the production bank8 pose exporter against independent byte math."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import struct
import subprocess

from pyboy import PyBoy

BASE=Path(__file__).resolve().parents[1]


def signed(n):return (n+2**31)%2**32-2**31


def expected(raw,ox,oy,shift,alive):
    result=bytearray(52);result[50]=alive
    for source,target,axis,velocity in ((0,0,ox,None),(4,4,oy,None),(22,10,ox,None),
            (26,14,oy,None),(44,20,ox,None),(48,24,oy,None),(66,30,ox,74),
            (70,34,oy,78),(82,40,ox,None),(86,44,oy,None)):
        value=struct.unpack_from('<i',raw,source)[0]
        if velocity is not None and raw[93]&1:
            value=signed(value-4*struct.unpack_from('<i',raw,velocity)[0])
        struct.pack_into('<i',result,target,signed((value>>2)+axis))
    for source,target in ((16,8),(38,18),(60,28)):
        angle=struct.unpack_from('<I',raw,source)[0]>>shift
        struct.pack_into('<H',result,target,angle&65535)
    result[38:40]=result[48:50]=result[8:10];result[51]=raw[90]
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--gen',type=Path,default=BASE/'build/gen')
    p.add_argument('--out',type=Path,default=BASE/'build/export-check');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    rng=random.Random(0xE6B0);vectors=[]
    edges=(-2147483648,-2147483647,-262145,-262144,-65537,-65536,-5,-4,-3,-2,-1,0,1,2,3,4,5,65535,65536,2147483646,2147483647)
    for shift in (7,8):
        for n in range(512):
            raw=bytearray(rng.randbytes(109))
            if n<len(edges)*4:
                for off in (0,4,22,26,44,48,66,70,74,78,82,86):struct.pack_into('<i',raw,off,edges[(n+off)%len(edges)])
                raw[93]=n&1
            ox=rng.randrange(-2147483648,2147483648);oy=rng.randrange(-2147483648,2147483648);alive=rng.randrange(256)
            vectors.append(bytes(raw)+struct.pack('<iiBB',ox,oy,shift,alive)+expected(raw,ox,oy,shift,alive))
    per_bank=90;parts=[vectors[i:i+per_bank]for i in range(0,len(vectors),per_bank)]
    declarations=[];sources=[]
    for index,part in enumerate(parts):
        name='export_vectors%d'%index;declarations.append('extern const uint8_t %s[];'%name)
        path=a.out/(name+'.c');path.write_text('#include <stdint.h>\n#pragma bank %d\nconst uint8_t %s[]={\n'%(16+index,name)+','.join(map(str,b''.join(part)))+'\n};\n');sources.append(path)
    fixture='''#include <gb/gb.h>
#include <gb/cgb.h>
#include <stddef.h>
#include <string.h>
#include "physics_core.h"
#include "runtime.h"
typedef char layout[(sizeof(bike_t)==109 && sizeof(gbc_bike_t)==52 && offsetof(bike_t,steps)==93)?1:-1];
bike_t Bike;gbc_bike_t gbc_bike;
int32_t physics_level_origin_x,physics_level_origin_y;
uint8_t physics_export_angle_shift;
void physics_export_state_fast(void);
#pragma bank 8
void export_call(void) BANKED {physics_export_state_fast();}
'''
    (a.out/'fixture.c').write_text(fixture)
    main='''#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdint.h>
#include <string.h>
extern uint8_t Bike[],gbc_bike[];
extern int32_t physics_level_origin_x,physics_level_origin_y;
extern uint8_t physics_export_angle_shift;
void export_call(void) BANKED;
volatile uint8_t export_done;
volatile uint16_t export_failures,export_checked,export_bank_failures;
'''+ '\n'.join(declarations)+'\nconst uint8_t *const parts[]={'+','.join('export_vectors%d'%i for i in range(len(parts)))+'};\nconst uint8_t counts[]={'+','.join(str(len(x))for x in parts)+'''};
void main(void) {
 uint8_t bank,n,i;const uint8_t *v;
 cpu_fast();
 for(bank=0;bank<sizeof(counts);++bank) {
  SWITCH_ROM(16+bank);v=parts[bank];
  for(n=0;n<counts[bank];++n,v+=171) {
   memcpy(Bike,v,109);memcpy(&physics_level_origin_x,v+109,4);memcpy(&physics_level_origin_y,v+113,4);
   physics_export_angle_shift=v[117];memset(gbc_bike,0x69,52);gbc_bike[50]=v[118];
   export_call();
   if(CURRENT_BANK!=16+bank)++export_bank_failures;
   for(i=0;i<52;++i)if(gbc_bike[i]!=v[119+i])++export_failures;
   ++export_checked;
  }
 }
 export_done=1;while(1)vsync();
}
'''
    (a.out/'check.c').write_text(main)
    rom=a.out/'check.gbc'
    result=subprocess.run([str(BASE/'.toolchain/gbdk/bin/lcc'),'-msm83:gb','-Wf--opt-code-size','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-I'+str(BASE/'src'),'-I'+str(a.gen),'-o',str(rom),str(a.out/'check.c'),str(a.out/'fixture.c'),str(BASE/'src/physics_export_fast.s'),*map(str,sources)],capture_output=True,text=True)
    assert not result.returncode,result.stdout+result.stderr
    symbols={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',rom.with_suffix('.noi').read_text())}
    q=PyBoy(str(rom),window='null',sound_emulated=False,cgb=True);q.set_emulation_speed(0)
    def word(n):k=symbols['_'+n];return q.memory[k]+256*q.memory[k+1]
    cycles=[];started=[None];returns=set()
    def finish(_):
        if started[0] is not None:cycles.append(q._cycles()-started[0]);started[0]=None
    def begin(_):
        started[0]=q._cycles();sp=q.register_file.SP
        address=q.memory[sp]+256*q.memory[sp+1];bank=0 if address<0x4000 else 8
        if (bank,address)not in returns:q.hook_register(bank,address,finish,None);returns.add((bank,address))
    entry=symbols['_physics_export_state_fast'];q.hook_register(entry>>16,entry&65535,begin,None)
    try:
        for _ in range(100):
            q.tick(100,False)
            if q.memory[symbols['_export_done']]:break
        assert q.memory[symbols['_export_done']]
        report={'vectors':word('export_checked'),'failures':word('export_failures'),'bank_failures':word('export_bank_failures'),
                'cycles':{'min':min(cycles),'mean':sum(cycles)/len(cycles),'max':max(cycles)},
                'source_sha256':hashlib.sha256((BASE/'src/physics_export_fast.s').read_bytes()).hexdigest()}
        assert report['vectors']==len(vectors) and not report['failures'] and not report['bank_failures'],report
    finally:q.stop(save=False)
    (a.out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
