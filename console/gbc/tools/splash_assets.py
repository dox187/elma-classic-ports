"""Encode the owned intro.pcx as a complete CGB title screen in ROM bank 2."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'console/snes/tools'))
from gen_ui import Res
from assets import array,rgb555,tile2bpp
from pixel_font import FONT_PATH,font_rows,pair_tile


def encode_artwork(image):
    tiles=image.reshape(18,8,20,8,3).transpose(0,2,1,3,4).reshape(-1,64,3).astype(np.int32)
    means=tiles.mean(axis=1)
    centers=means[np.linspace(0,len(means)-1,7,dtype=int)].copy()
    for _ in range(12):
        labels=((means[:,None]-centers)**2).sum(axis=2).argmin(axis=1)
        for k in range(7):
            if np.any(labels==k):centers[k]=means[labels==k].mean(axis=0)
    palettes=[]
    for k in range(7):
        pixels=tiles[labels==k].reshape(-1,3)
        if not len(pixels):pixels=tiles[0]
        quant=Image.fromarray(pixels.astype(np.uint8).reshape(-1,1,3)).quantize(colors=4,method=Image.Quantize.MEDIANCUT)
        colors=quant.getpalette()[:12]
        colors+= [0]*(12-len(colors))
        palettes.append((np.array(colors,dtype=np.uint8).reshape(4,3)>>3)*8)
    palettes=np.array(palettes)
    encoded=[];attributes=[]
    for tile in tiles:
        distances=((tile[None,:,None]-palettes[:,None].astype(np.int32))**2).sum(axis=3)
        choice=int(distances.min(axis=2).sum(axis=1).argmin())
        attributes.append(choice)
        encoded.append(tile2bpp(distances[choice].argmin(axis=1).reshape(8,8)))
    return encoded,attributes,palettes


def generate(res_path,out):
    out.mkdir(parents=True,exist_ok=True)
    version=(Path(__file__).resolve().parents[1]/'VERSION').read_text().strip()
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+){1,2}',version):
        raise ValueError('VERSION must be a numeric release such as 0.3')
    label='V'+version
    if len(label)>20:raise ValueError('Version label is too wide for the title screen')
    source=Res(res_path).intro.convert('RGB')
    # Retain the complete 4:3 artwork, including its original footer; the
    # additional 24 scanlines provide a top margin and two native text rows.
    canvas=Image.new('RGB',(160,144))
    canvas.paste(source.resize((160,120),Image.Resampling.BOX),(0,8))
    encoded,attributes,palettes=encode_artwork(np.array(canvas))
    tiles=[bytes(tile)for tile in encoded]
    palettes=np.concatenate((palettes,np.array([[[0,0,0],[0,0,0],[248,248,224],[248,248,224]]])))
    rows=font_rows()
    def text(y,s):
        s+=' '*(len(s)%2)
        x=(20-len(s)//2)//2
        # The surrounding row is a solid black native tile as well.
        for tx in range(20):
            tiles[y*20+tx]=tile2bpp(np.zeros((8,8),dtype=np.uint8))
            attributes[y*20+tx]=7
        for i in range(0,len(s),2):
            tiles[y*20+x+i//2]=pair_tile(s[i],s[i+1],rows)
    text(16,label)
    text(17,'PRESS START')
    patterns=[];known={};tilemap=[];attrs=[]
    # Reserve at most 255 patterns in each VRAM bank, avoiding the API's
    # zero-count/256-tile special case. Only the selected BG bank is visible.
    for tile,attribute in zip(tiles,attributes):
        if tile not in known:known[tile]=len(patterns);patterns.append(tile)
        index=known[tile]
        tilemap.append(index%255)
        attrs.append(attribute|(8 if index>=255 else 0))
    if len(patterns)>510:raise ValueError('Splash exceeds CGB pattern budget')
    split=min(255,len(patterns));count1=len(patterns)-split
    data_bytes=len(patterns)*16+720+64
    if data_bytes>15500:raise ValueError('Splash leaves insufficient code space in bank 2')
    header=('#ifndef GBC_SPLASH_ASSETS_H\n#define GBC_SPLASH_ASSETS_H\n#include <stdint.h>\n'
            '#define SPLASH_TILE_COUNT0 %d\n#define SPLASH_TILE_COUNT1 %d\n'
            'extern const uint8_t splash_tiles0[],splash_tiles1[],splash_map[],splash_attributes[];\n'
            'extern const uint16_t splash_palettes[];\n#endif\n')%(split,count1)
    (out/'splash_assets.h').write_text(header)
    data='#include "splash_assets.h"\n#pragma bank 2\n'+array('splash_tiles0',b''.join(patterns[:split]))
    if count1:data+=array('splash_tiles1',b''.join(patterns[split:]))
    data+=array('splash_map',tilemap)+array('splash_attributes',attrs)+array('splash_palettes',rgb555(palettes),'uint16_t')
    (out/'splash_assets.c').write_text(data)
    # Decode the actual tile planes and CGB attributes for the preview.
    preview=np.zeros((144,160,3),dtype=np.uint8)
    for pos,(index,attribute)in enumerate(zip(tilemap,attrs)):
        tile=patterns[index+(255 if attribute&8 else 0)]
        pixels=np.array([[(tile[y*2]>>(7-x)&1)|((tile[y*2+1]>>(7-x)&1)<<1)for x in range(8)]for y in range(8)])
        y,x=divmod(pos,20);preview[y*8:y*8+8,x*8:x*8+8]=palettes[attribute&7][pixels]
    Image.fromarray(preview).save(out/'splash-preview.png')
    report={'version':version,'source':'intro.pcx','source_size':list(source.size),'artwork_rect':[0,8,160,120],
            'screen_size':[160,144],'patterns':len(patterns),'vram_bank_patterns':[split,count1],
            'asset_bytes':data_bytes,'bank':2,'font':'CG Pixel 3x5 Mono; native pixels, four-pixel advance',
            'font_sha256':hashlib.sha256(FONT_PATH.read_bytes()).hexdigest(),
            'source_res_sha256':hashlib.sha256(res_path.read_bytes()).hexdigest()}
    (out/'splash-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--res',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();print(json.dumps(generate(a.res,a.out)))


if __name__=='__main__':main()
