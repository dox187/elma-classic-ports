"""Build only the production splash; check its pixels, input edges and ROM bank."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import numpy as np
from PIL import Image
from pyboy import PyBoy

BASE=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--res',type=Path,required=True)
    p.add_argument('--out',type=Path,default=BASE/'build/splash-check')
    a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    gen=out/'gen'
    sources=[BASE/'src/splash.c',BASE/'src/splash.h',BASE/'tools/splash_assets.py']
    hashes={str(path):hashlib.sha256(path.read_bytes()).hexdigest()for path in sources}
    subprocess.run([sys.executable,str(BASE/'tools/splash_assets.py'),'--res',str(a.res),'--out',str(gen)],check=True,capture_output=True,text=True)
    (out/'driver.c').write_text('''#include <gb/gb.h>
#include "splash.h"
volatile uint8_t splash_phase,splash_bank_failures;
void main(void) {
    SWITCH_ROM(3);
    LCDC_REG|=LCDCF_BG9C00;
    SHOW_WIN;SHOW_SPRITES;move_bkg(71,39);
    splash_phase=1;splash_show();
    if(CURRENT_BANK!=3)++splash_bank_failures;
    splash_phase=2;splash_show();
    if(CURRENT_BANK!=3)++splash_bank_failures;
    splash_phase=3;
    while(1)vsync();
}
''')
    command=[str(BASE/'.toolchain/gbdk/bin/lcc'),'-msm83:gb','-Wf--opt-code-size','-Wm-yC','-Wm-yt0x19','-Wm-yo4','-Wl-m','-Wl-j','-I'+str(BASE/'src'),'-I'+str(gen),'-o',str(out/'check.gbc'),str(out/'driver.c'),str(BASE/'src/splash.c'),str(gen/'splash_assets.c')]
    result=subprocess.run(command,capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    assert not re.search(r'warning|error',result.stdout+result.stderr,re.I),result.stdout+result.stderr
    symbols={name:int(address,16)for name,address in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',(out/'check.noi').read_text())}
    names=['splash_show','splash_tiles0','splash_map','splash_attributes','splash_palettes']
    assert all(symbols['_'+name]>>16==2 for name in names)
    area=re.search(r'^_CODE_2\s+([0-9A-Fa-f]+)\s+([0-9A-Fa-f]+)',(out/'check.map').read_text(),re.M)
    assert area,'Bank 2 area missing from linker map'
    bank_bytes=int(area[2],16);assert bank_bytes<=16384,bank_bytes
    # Independently decode emitted C data rather than the host preview.
    data=(gen/'splash_assets.c').read_text()
    arrays={name:[int(value)for value in re.findall(r'\d+',body)]for name,body in re.findall(r'const uint(?:8|16)_t (\w+)\[\] = \{(.*?)\};',data,re.S)}
    expected=np.zeros((144,160,3),dtype=np.uint8)
    for pos,(tile,attribute)in enumerate(zip(arrays['splash_map'],arrays['splash_attributes'])):
        bank=1 if attribute&8 else 0
        blob=arrays['splash_tiles'+str(bank)][tile*16:tile*16+16]
        for y in range(8):
            for x in range(8):
                color=(blob[y*2]>>(7-x)&1)|((blob[y*2+1]>>(7-x)&1)<<1)
                rgb=arrays['splash_palettes'][(attribute&7)*4+color]
                expected[(pos//20)*8+y,(pos%20)*8+x]=[(rgb>>shift&31)*8 for shift in(0,5,10)]
    emulator=PyBoy(str(out/'check.gbc'),window='null',sound_emulated=False,cgb=True)
    emulator.set_emulation_speed(0)
    def value(name):return emulator.memory[symbols['_'+name]]
    try:
        emulator.button_press('start')
        for _ in range(180):
            emulator.tick(1,False)
            if value('splash_active'):break
        assert value('splash_active')and value('splash_phase')==1,'Splash never became ready'
        emulator.tick(3,True)
        screenshot=np.array(emulator.screen.image)[:,:,:3]
        Image.fromarray(screenshot).save(out/'splash-screen.png')
        assert np.array_equal(screenshot,expected),{'pixel_mismatches':int(np.any(screenshot!=expected,axis=2).sum()),'actual_colors':np.unique(screenshot.reshape(-1,3),axis=0).tolist()}
        assert emulator.memory[0xff40]&0xbb==0x91,'LCD, BG, tile addressing, sprites or window flags'
        assert emulator.memory[0xff42]==emulator.memory[0xff43]==0,'BG scroll was not reset'
        emulator.tick(60,False)
        assert value('splash_phase')==1 and value('splash_active'),'Held Start skipped splash'
        emulator.button_release('start');emulator.button_press('b');emulator.tick(5,False)
        assert value('splash_phase')==1,'B skipped splash'
        emulator.button_release('b');emulator.button_press('start')
        for _ in range(30):
            emulator.tick(1,False)
            if value('splash_phase')==2 and value('splash_active'):break
        assert value('splash_phase')==2 and value('splash_active'),('Fresh Start failed to return',value('splash_phase'),value('splash_active'))
        emulator.tick(20,False)
        assert value('splash_phase')==2,'Held Start skipped second splash'
        emulator.button_press('a');emulator.tick(5,False)
        assert value('splash_phase')==3 and not value('splash_active'),'Fresh A failed to return'
        assert not value('splash_bank_failures'),'Banked call failed to restore bank 3'
        assert hashes=={str(path):hashlib.sha256(path.read_bytes()).hexdigest()for path in sources}
        report={'status':'passed','bank':2,'bank_bytes':bank_bytes,'pixel_mismatches':0,
                'checks':['complete encoded framebuffer','LCD/window/sprite/scroll state','held Start','ignored B','fresh Start','fresh A','caller bank restoration'],
                'source_sha256':hashes,'assets':json.loads((gen/'splash-manifest.json').read_text())}
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    finally:emulator.stop(save=False)


if __name__=='__main__':main()
