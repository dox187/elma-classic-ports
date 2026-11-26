"""Check exact production screen-coordinate assembly in an isolated SM83 ROM."""
import hashlib,json,random,re,struct,subprocess
from pathlib import Path
from pyboy import PyBoy
BASE=Path(__file__).resolve().parents[1]
OUT=BASE/'build/screen-check'


def signed(x,bits=32):
    return (x+(1<<(bits-1)))%(1<<bits)-(1<<(bits-1))


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    assembly=(BASE/'src/video_screen_fast.s').read_bytes()
    (OUT/'screen.s').write_bytes(assembly)
    rng=random.Random(0x5c3ee)
    values=[-2147483648,-16777217,-16777216,-65536,-1,0,1,65535,65536,16777215,16777216,2147483647]
    # Every transition of floor(12*f/65536), including carries across a full metre.
    boundaries=[(whole<<16)+(pixel*65536+11)//12+offset
                for whole in (-32768,-257,-256,-1,0,1,255,256,32767)
                for pixel in range(13) for offset in (-1,0,1)]
    vectors=[]
    for n in range(1024):
        coordinates=[rng.choice(values) if n<256 else rng.randrange(-2**31,2**31) for _ in range(8)]
        origin=[rng.choice(values) if n<256 else rng.randrange(-2**31,2**31) for _ in range(2)]
        if n>=512:
            coordinates=[signed(origin[i&1]+rng.randrange(-16777217,16777218)) for i in range(8)]
        if 512<=n<512+len(boundaries):
            # Give every part and the camera body every boundary on both axes.
            coordinates=[signed(origin[i&1]+(-1 if i&1 else 1)*
                                boundaries[(n-512+31*i)%len(boundaries)]) for i in range(8)]
        camera=[rng.randrange(65536) for _ in range(2)]
        parts=[]
        # Source order: riderXY,headXY,wheel0XY,wheel1XY.
        for i,v in enumerate(coordinates):
            axis=i&1
            delta=signed(origin[axis]-v if axis else v-origin[axis])
            parts.append(signed(max(-3072,min(3072,delta*3//16384))-camera[axis],16))
        expected=b'\xa5'*4+struct.pack('<8h',parts[0],parts[1],parts[2],parts[3],parts[4],parts[6],parts[5],parts[7])
        vectors.append(struct.pack('<10i2H',*coordinates,*origin,*camera)+expected)
    banks=[]
    for k in range(4):
        bank=16+k;p=OUT/('data%d.c'%bank)
        blob=b''.join(vectors[k*256:(k+1)*256])
        p.write_text('#include <stdint.h>\n#pragma bank %d\nconst uint8_t cases%d[]={%s};\n'%(bank,bank,','.join(map(str,blob))))
        banks.append(p)
    (OUT/'near.c').write_text('''#include <gb/gb.h>
#pragma bank 5
void gbc_video_parts_screen(uint8_t *) __sdcccall(0);
void gbc_video_sprite_screen(uint8_t *) __sdcccall(0);
void gbc_video_body_world(uint8_t *) __sdcccall(0);
uint8_t output[24];
void fixture_screen(void) BANKED {gbc_video_parts_screen(output+2);}
void fixture_sprites(void) BANKED {gbc_video_sprite_screen(output+2);}
void fixture_body(void) BANKED {gbc_video_body_world(output+2);}
''')
    (OUT/'check.c').write_text('''#include <gb/gb.h>
#include <stdint.h>
#include <string.h>
extern const uint8_t cases16[],cases17[],cases18[],cases19[];
extern uint8_t output[24];
void fixture_screen(void) BANKED;
void fixture_sprites(void) BANKED;
void fixture_body(void) BANKED;
uint8_t gbc_bike[52],game_world[33];
uint16_t game_camera_x,game_camera_y;
uint8_t input[64];
volatile uint16_t completed,failures,bank_failures;
volatile uint8_t done;
void main(void){
 uint8_t bank,i;uint16_t n;int16_t x,y;const uint8_t *p;
 for(bank=16;bank<20;++bank){
  SWITCH_ROM(bank);p=bank==16?cases16:bank==17?cases17:bank==18?cases18:cases19;
  for(n=0;n<256;++n,p+=64){
   memcpy(input,p,64);
   memcpy(gbc_bike+30,input,8);memcpy(gbc_bike+40,input+8,8);
   memcpy(gbc_bike+10,input+16,8);memcpy(gbc_bike+20,input+24,8);
   memcpy(game_world+4,input+32,8);memcpy(&game_camera_x,input+40,2);memcpy(&game_camera_y,input+42,2);
   memset(output,0xa5,24);fixture_screen();
   if(memcmp(output+2,input+44,20))++failures;
   if(output[0]!=0xa5||output[1]!=0xa5||output[22]!=0xa5||output[23]!=0xa5)++failures;
   memset(output,0xa5,24);fixture_sprites();
   if(memcmp(output+10,input+52,12))++failures;
   for(i=0;i<24;++i)if((i<10||i>=22)&&output[i]!=0xa5)++failures;
   memcpy(gbc_bike,input,8);memcpy(&x,input+48,2);memcpy(&y,input+50,2);
   x+=game_camera_x;y+=game_camera_y;
   memset(output,0xa5,24);fixture_body();
   if(memcmp(output+2,&x,2)||memcmp(output+4,&y,2))++failures;
   for(i=0;i<24;++i)if((i<2||i>=6)&&output[i]!=0xa5)++failures;
   if(CURRENT_BANK!=bank)++bank_failures;
   ++completed;
  }
 }
 done=1;while(1)vsync();
}
''')
    command=[str(BASE/'.toolchain/gbdk/bin/lcc'),'-msm83:gb','-Wf--opt-code-size','-Wm-yC','-Wm-yt0x19','-Wm-yo32','-Wl-m','-Wl-j','-o',str(OUT/'check.gbc'),str(OUT/'check.c'),str(OUT/'near.c'),str(OUT/'screen.s'),*map(str,banks)]
    r=subprocess.run(command,capture_output=True,text=True);assert r.returncode==0,r.stdout+r.stderr
    symbols={k:int(v,16) for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',(OUT/'check.noi').read_text())}
    p=PyBoy(str(OUT/'check.gbc'),window='null',sound_emulated=False,cgb=True);p.set_emulation_speed(0)
    cycles=[];sprite_cycles=[];start=[];sprite_start=[]
    def enter(_):start.append(p._cycles())
    def enter_sprites(_):
        if not start:sprite_start.append(p._cycles())
    def leave(_):
        if start:cycles.append(p._cycles()-start.pop())
        else:sprite_cycles.append(p._cycles()-sprite_start.pop())
    address=symbols['_gbc_video_parts_screen'];p.hook_register(address>>16,address&65535,enter,None)
    sprite=symbols['_gbc_video_sprite_screen']
    p.hook_register(sprite>>16,sprite&65535,enter_sprites,None)
    end=symbols['_gbc_video_parts_screen_end']
    p.hook_register(end>>16,end&65535,leave,None)
    def word(name):
        a=symbols['_'+name];return p.memory[a]+256*p.memory[a+1]
    try:
        for _ in range(100):
            p.tick(100,False)
            if p.memory[symbols['_done']]:break
        report={'status':'passed','cases':word('completed'),'body_world_cases':word('completed'),'visible_sprite_cases':word('completed'),'failures':word('failures'),'bank_failures':word('bank_failures'),
                'cycles':{'min':min(cycles),'mean':sum(cycles)/len(cycles),'max':max(cycles)},
                'visible_sprite_cycles':{'min':min(sprite_cycles),'mean':sum(sprite_cycles)/len(sprite_cycles),'max':max(sprite_cycles)},
                'source_sha256':hashlib.sha256(assembly).hexdigest(),'source_still_current':(BASE/'src/video_screen_fast.s').read_bytes()==assembly}
        assert report['cases']==len(cycles)==len(sprite_cycles)==1024 and not report['failures'] and not report['bank_failures'] and report['source_still_current'],report
    finally:p.stop(save=False)
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
