"""GBC level menu: original menu.abc, szoveg1.pcx and sisak.pcx artwork."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'console/snes/tools'))
from gen_ui import Res,parse_abc,helmet_frames
from elmadata import internal_levels
from assets import array,rgb555,tile2bpp


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--res',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    res=Res(a.res);letters=parse_abc(res.res.read('menu.abc'))
    names=[level.name for level in internal_levels(res.res)]
    if not 1<=len(names)<=54:raise ValueError('Unsupported level catalogue size')
    if any(len(name)>18 for name in names):raise ValueError('Level name does not fit an 18-column menu row')
    needed=set(''.join(names).upper()+'ELASTO MANIA LEVEL A/START PLAY B RESUME L/R PAGE UP/DOWN SELECT0123456789:()/-')-{' '}
    missing=needed-{chr(code) for code in letters}
    if missing:raise ValueError('Original menu.abc lacks required glyphs: '+repr(missing))
    pal=np.array(res.pal,dtype=np.uint8).reshape(-1,3)
    all_colors=np.concatenate([pal[rows[mask]] for code,(yo,rows,mask) in letters.items() if 32<=code<=95])
    order=all_colors[np.argsort(all_colors.astype(int).sum(axis=1))]
    text_palette=np.vstack(([0,32,0],*[order[min(len(order)-1,int(len(order)*q))] for q in (.95,.6,.2)]))
    font=bytearray()
    for code in range(32,96):
        rgba=np.zeros((32,32,4),dtype=np.uint8)
        if code in letters:
            yo,rows,mask=letters[code];h,w=rows.shape
            top=min(0,yo);height=max(32,yo+h)-top;width=max(32,w)
            rgba=np.zeros((height,width,4),dtype=np.uint8)
            x=(width-w)//2;y=yo-top
            rgba[y:y+h,x:x+w,:3]=pal[rows]
            rgba[y:y+h,x:x+w,3]=mask.astype(np.uint8)*255
        im=np.array(Image.fromarray(rgba).resize((8,8),Image.Resampling.BOX))
        mixed=im[:,:,:3].astype(float)*im[:,:,3,None]/255+text_palette[0]*(1-im[:,:,3,None]/255)
        indices=((mixed[:,:,None]-text_palette[None,None])**2).sum(axis=3).argmin(axis=2)
        indices[im[:,:,3]<48]=0
        font.extend(tile2bpp(indices))
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
            'extern const uint8_t menu_font[],menu_background[],menu_background_map[],menu_cursor[];\n'
            'extern const uint16_t menu_palettes[];\n#endif\n')%(len(names),len(patterns))
    (a.out/'menu_assets.h').write_text(header)
    (a.out/'menu_assets.c').write_text('#include "menu_assets.h"\n#pragma bank 7\n'
        +array('menu_font',font)+array('menu_background',b''.join(patterns))
        +array('menu_background_map',background_map)+array('menu_cursor',tile2bpp(ci))
        +array('menu_palettes',rgb555(np.array([text_palette,background_palette,cursor_palette])),'uint16_t'))
    # Host preview uses the encoded glyphs and real source names for QA.
    def decode(blob):
        return np.array([[(blob[y*2]>>(7-x)&1)|((blob[y*2+1]>>(7-x)&1)<<1) for x in range(8)]for y in range(8)])
    preview=Image.new('RGB',(160,144))
    for y in range(18):
        for x in range(20):
            tile=background_map[y*20+x]-64
            preview.paste(Image.fromarray(background_palette[decode(patterns[tile])]),(x*8,y*8))
    def text(x,y,s):
        for c in s.upper():
            code=ord(c)-32;preview.paste(Image.fromarray(text_palette[decode(font[code*16:code*16+16])].astype(np.uint8)),(x*8,y*8));x+=1
    text(4,0,'ELASTO MANIA');text(4,2,'LEVEL 01/%02d'%len(names))
    for i,name in enumerate(names[:9]):text(0,4+i,'  '+name.ljust(18))
    preview.paste(Image.fromarray(cursor_palette[ci].astype(np.uint8)),(0,32))
    text(0,15,'A/START PLAY');text(0,16,'L/R PAGE');text(0,17,'UP/DOWN SELECT')
    preview.save(a.out/'menu-preview.png')
    report={'level_count':len(names),'max_name_columns':max(map(len,names)),'font':'original menu.abc,8x8 cells',
            'background':'original szoveg1.pcx quarter-size repeat','cursor':'original sisak.pcx frame25',
            'font_bytes':len(font),'background_patterns':len(patterns),'background_bytes':sum(map(len,patterns)),
            'bank':7,'source_res_sha256':hashlib.sha256(a.res.read_bytes()).hexdigest()}
    (a.out/'menu-manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
