"""GBC main menu and level list: native text and original menu artwork."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'console/snes/tools'))
from gen_ui import Res,helmet_frames
from elmadata import internal_levels
from assets import array,rgb555,tile2bpp
from pixel_font import FONT_PATH,font_rows,pair_tile,write_header


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--res',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    res=Res(a.res);rows=font_rows();write_header(a.out,rows)
    names=[level.name for level in internal_levels(res.res)]
    version=(Path(__file__).resolve().parents[1]/'VERSION').read_text().strip()
    version_text='VERSION '+version
    if not version or len(version_text)>12:raise ValueError('VERSION does not fit the menu heading')
    if not 1<=len(names)<=54:raise ValueError('Unsupported level catalogue size')
    if any(len(name)>18 for name in names):raise ValueError('Level name does not fit an 18-column menu row')
    labels=('ELASTO MANIA LEVEL A/START PLAY B RESUME L/R PAGE UP/DOWN SELECT '
            'SELECTED LEVEL RESTART LEVEL SELECT CONTROLS BACK '
            'A THROTTLE B BRAKE LEFT/RIGHT ROTATE UP TURN SELECT MENU START RESTART ')
    needed=set((''.join(names)+labels+version_text+'0123456789:()/-').upper())-{' '}
    missing=needed-{chr(code) for code in range(32,96)}
    if missing:raise ValueError('Pixel font lacks required glyphs: '+repr(missing))
    pal=np.array(res.pal,dtype=np.uint8).reshape(-1,3)
    text_palette=np.array([[0,32,0],[0,32,0],[248,248,224],[248,248,224]])
    # A quarter-size copy of the original repeated menu texture. Pad through
    # periodic sampling so the source's 400x114 border does not become a seam.
    source=res.pcx('szoveg1.pcx')
    big=Image.new('P',(416,128));big.putpalette(res.pal)
    for y in (0,114):
        for x in (0,400):big.paste(source,(x,y))
    rgb=big.convert('RGB').resize((104,32),Image.Resampling.BOX)
    quant=rgb.quantize(colors=4,method=Image.Quantize.MEDIANCUT)
    background_palette=np.array(quant.getpalette()[:12],dtype=np.uint8).reshape(4,3)
    indices=np.array(quant);patterns=[];known={};texture_map=[]
    for y in range(0,32,8):
        for x in range(0,104,8):
            data=tile2bpp(indices[y:y+8,x:x+8])
            if data not in known:known[data]=len(patterns);patterns.append(data)
            texture_map.append(64+known[data])
    if len(patterns)>176:raise ValueError('Menu background pattern budget exceeded')
    background_map=bytes(texture_map[(y%4)*13+x%13] for y in range(18) for x in range(20))
    # Use the original menu's resting helmet frame, including its corrected top.
    frame=helmet_frames(res)[25]
    rgba=np.zeros(frame.shape+(4,),dtype=np.uint8);opaque=frame>=0
    rgba[opaque,:3]=pal[frame[opaque]];rgba[opaque,3]=255
    cursor=np.array(Image.fromarray(rgba).resize((8,8),Image.Resampling.BOX))
    colors=cursor[cursor[:,:,3]>=128,:3]
    q=Image.fromarray(colors.reshape(-1,1,3)).quantize(colors=3,method=Image.Quantize.MEDIANCUT)
    cursor_palette=np.vstack(([0,32,0],np.array(q.getpalette()[:9],dtype=np.uint8).reshape(3,3)))
    ci=((cursor[:,:,None,:3].astype(int)-cursor_palette[None,None,1:].astype(int))**2).sum(axis=3).argmin(axis=2)+1
    ci[cursor[:,:,3]<96]=0
    header=('#ifndef GBC_MENU_ASSETS_H\n#define GBC_MENU_ASSETS_H\n#include <stdint.h>\n'
            '#define MENU_LEVEL_COUNT %d\n#define MENU_BG_PATTERN_COUNT %d\n'
            '#define MENU_VERSION_TEXT %s\n'
            'extern const uint8_t menu_background[],menu_background_map[],menu_cursor[];\n'
            'extern const uint16_t menu_palettes[];\n#endif\n')%(len(names),len(patterns),json.dumps(version_text))
    (a.out/'menu_assets.h').write_text(header)
    (a.out/'menu_assets.c').write_text('#include "menu_assets.h"\n#pragma bank 7\n'
        +array('menu_background',b''.join(patterns))
        +array('menu_background_map',background_map)+array('menu_cursor',tile2bpp(ci))
        +array('menu_palettes',rgb555(np.array([text_palette,background_palette,cursor_palette])),'uint16_t'))
    # Host preview uses the encoded glyphs and real source names for QA.
    def decode(blob):
        return np.array([[(blob[y*2]>>(7-x)&1)|((blob[y*2+1]>>(7-x)&1)<<1) for x in range(8)]for y in range(8)])
    def background():
        result=Image.new('RGB',(160,144))
        for y in range(18):
            for x in range(20):
                tile=background_map[y*20+x]-64
                result.paste(Image.fromarray(background_palette[decode(patterns[tile])]),(x*8,y*8))
        return result
    def text(x,y,s,width):
        s=s.upper()[:width].ljust(width)
        for i in range(0,len(s),2):
            preview.paste(Image.fromarray(text_palette[decode(pair_tile(s[i],s[i+1],rows))].astype(np.uint8)),(x*8,y*8));x+=1
    def cursor(x,y):
        preview.paste(Image.fromarray(cursor_palette[ci].astype(np.uint8)),(x*8,y*8))
    for paused in (False,True):
        preview=background()
        text(7,0,'ELASTO MANIA',12);text(7,2,version_text,12)
        text(5,4,'SELECTED LEVEL 01/%02d'%len(names),20);text(5,5,names[0],20)
        options=('RESUME','RESTART','LEVEL SELECT','CONTROLS') if paused else ('PLAY','LEVEL SELECT','CONTROLS')
        for i,label in enumerate(options):text(7,7+i*2,label,20)
        cursor(5,7)
        text(0,15,'A/START SELECT',20)
        if paused:text(0,16,'B RESUME',20)
        text(0,17,'UP/DOWN SELECT',20)
        preview.save(a.out/('menu-paused-preview.png' if paused else 'menu-preview.png'))
    preview=background()
    text(7,0,'ELASTO MANIA',12);text(7,2,'LEVEL 01/%02d'%len(names),12)
    for i,name in enumerate(names[:9]):text(2,4+i,name,18)
    cursor(0,4)
    text(0,15,'A/START PLAY',20);text(0,16,'B BACK    L/R PAGE',20);text(0,17,'UP/DOWN SELECT',20)
    preview.save(a.out/'menu-levels-preview.png')
    preview=background()
    text(7,0,'ELASTO MANIA',12);text(8,2,'CONTROLS',8)
    for i,label in enumerate(('A          THROTTLE','B          BRAKE','LEFT/RIGHT ROTATE',
                              'UP         TURN','SELECT     MENU','START      RESTART')):
        text(2,5+i*2,label,36)
    text(0,17,'B BACK',20)
    preview.save(a.out/'menu-controls-preview.png')
    report={'version':version,'screens':['main','levels','controls'],'level_count':len(names),'max_name_columns':max(map(len,names)),'font':'CG Pixel 3x5 Mono,4-pixel advance',
            'background':'original szoveg1.pcx quarter-size repeat','cursor':'original sisak.pcx frame25',
            'font_bytes':320,'font_sha256':hashlib.sha256(FONT_PATH.read_bytes()).hexdigest(),
            'background_patterns':len(patterns),'background_bytes':sum(map(len,patterns)),
            'bank':7,'source_res_sha256':hashlib.sha256(a.res.read_bytes()).hexdigest()}
    (a.out/'menu-manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
