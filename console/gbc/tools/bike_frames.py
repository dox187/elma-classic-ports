"""Build rotated, three-pose rider art from the original LGR bike parts.

The GBC draws the two physical wheels and the rider's head independently.
The frame/limbs use 32 angles and three rider-compression poses; this is a
graphics approximation only and never changes the physical bike positions.
"""
import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'console/snes/tools'))
import bikemodel
from lgr import Lgr
from assets import array, palettes_for, rgb555, tile2bpp

PPM = 12
ANGLES = 32
COMPRESSIONS = (-.15,0.,.15)


def rgba(pics,parts,size):
    indices=bikemodel.render_pc(pics,parts,-size/2/PPM,size/2/PPM,size*4,size*4)
    opaque=indices>=0
    pixels=np.zeros((size*4,size*4,4),dtype=np.uint8)
    pixels[opaque,:3]=pics.pal[indices[opaque]]
    pixels[opaque,3]=255
    return np.array(Image.fromarray(pixels).resize((size,size),Image.Resampling.BOX))


def palette(images):
    colors=np.concatenate([a[a[:,:,3]>=128,:3] for a in images])
    pal=palettes_for(colors.reshape(-1,1,3).astype(np.int32),1,3)[0]
    return np.vstack(([0,0,0],pal)).astype(np.uint8)


def head_palette(pics,images):
    """Reserve the three opaque colors for the LGR face, helmet and outline.

    Generic fitting to the tiny averaged frames loses the few skin pixels and
    makes the helmet an indistinct grey blob. Select representative colors from
    the original full-resolution picture instead; never redraw its outline.
    """
    indices,transparent=pics['q1head']
    colors=pics.pal[indices[indices!=transparent]].astype(np.int32)
    skin=(colors[:,0]>colors[:,1]+12)&(colors[:,0]>colors[:,2]+12)
    if not skin.any() or skin.all():return palette(images)
    brightness=colors.mean(axis=1)
    face=colors[skin&(brightness>=np.median(brightness[skin]))]
    helmet=colors[~skin]
    light=helmet.mean(axis=1)
    outline=helmet[light<=np.percentile(light,25)]
    helmet=helmet[light>=np.median(light)]
    pal=np.vstack(([0,0,0],np.median(face,axis=0),np.median(helmet,axis=0),np.median(outline,axis=0)))
    return (pal.astype(np.uint8)>>3)<<3


def encode(image,pal):
    delta=image[:,:,None,:3].astype(np.int32)-pal[None,None,1:,:].astype(np.int32)
    indices=((delta*delta).sum(axis=3).argmin(axis=2)+1).astype(np.uint8)
    indices[image[:,:,3]<128]=0
    h,w=indices.shape
    tiles=[]
    mask=0
    for y in range(0,h,8):
        for x in range(0,w,8):
            tile=indices[y:y+8,x:x+8]
            if tile.any():mask|=1<<len(tiles)
            tiles.append(tile2bpp(tile))
    return b''.join(tiles),mask


def source_state(theta,turned,compression):
    wheel0=bikemodel.rotate(bikemodel.v(-.85,-.6),theta)
    wheel1=bikemodel.rotate(bikemodel.v(.85,-.6),theta)
    rider=bikemodel.rotate(bikemodel.v(0,.44+compression),theta)
    return bikemodel.State(body=(0,0),body_a=theta,wheel0=wheel0,wheel1=wheel1,
                           rider=rider,turned=turned)


def scanline_max(mask,state):
    """Hardware counts an entire 8-pixel OAM row, including transparent pixels."""
    spans=[]
    for row in range(4):
        for col in range(4):
            if mask&(1<<(row*4+col)):spans.append((48+row*8,8))
    for wheel in state.wheel:
        y=64-round(wheel[1]*PPM)
        spans.extend([(y-8,8)]*2+[(y,8)]*2)
    spans.append((64-round(state.head[1]*PPM)-4,8))
    return max(sum(y0<=y<y0+height for y0,height in spans)for y in range(128))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--lgr',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    out=args.out
    out.mkdir(parents=True,exist_ok=True)
    pics=bikemodel.Pictures(Lgr(args.lgr))
    bodies=[]
    heads=[]
    wheels=[]
    for turned in (False,True):
        for compression in COMPRESSIONS:
            for angle in range(ANGLES):
                theta=angle*2*math.pi/ANGLES
                state=source_state(theta,turned,compression)
                parts=[p for p in bikemodel.kibike(state) if p.kind not in ('wheel','head')]
                bodies.append(rgba(pics,parts,32))
        for angle in range(ANGLES):
            theta=angle*2*math.pi/ANGLES
            for phase in range(4):
                # Keep the physical subpixel phase when rounding OAM to pixels.
                center=bikemodel.v((phase&1)*.5/PPM,-(phase>>1)*.5/PPM)
                part=bikemodel.kidobozkerek('q1head',center,bikemodel.HEAD_R,
                                          theta,turned,kind='head')
                heads.append(rgba(pics,[part],8))
    for angle in range(8):
        part=bikemodel.kidobozkerek('q1wheel',bikemodel.v(0,0),bikemodel.WHEEL_R,
                                  angle*math.pi/4)
        wheels.append(rgba(pics,[part],16))
    body_pal,head_pal,wheel_pal=palette(bodies),head_palette(pics,heads),palette(wheels)
    body_blob=bytearray()
    body_masks=[]
    # Worst-case bike-only occupancy, before culling at screen boundaries.
    max_line=0
    max_bike_line=0
    for index,im in enumerate(bodies):
        data,mask=encode(im,body_pal)
        body_blob.extend(data)
        body_masks.append(mask)
        max_line=max(max_line,max(sum(bool(mask & (1<<(r*4+c))) for c in range(4))
                                  for r in range(4)))
        state=source_state((index%32)*math.pi/16,index>=96,COMPRESSIONS[(index//32)%3])
        max_bike_line=max(max_bike_line,scanline_max(mask,state))
    assert len(body_blob)==3*16384
    for bank in range(3):
        name='riding_body_%d'%bank
        (out/(name+'.c')).write_text('#include <stdint.h>\n#pragma bank %d\n'%(10+bank)
                                    +array(name,body_blob[bank*16384:(bank+1)*16384]))
    head_blob=b''.join(encode(im,head_pal)[0] for im in heads)
    wheel_blob=b''.join(encode(im,wheel_pal)[0] for im in wheels)
    (out/'riding_parts.c').write_text('#include <stdint.h>\n#pragma bank 13\n'
        +array('riding_heads',head_blob)+array('riding_wheels',wheel_blob))
    (out/'riding_assets.h').write_text('''#ifndef GBC_RIDING_ASSETS_H
#define GBC_RIDING_ASSETS_H
#include <stdint.h>
extern const uint8_t riding_body_0[],riding_body_1[],riding_body_2[];
extern const uint8_t riding_heads[],riding_wheels[];
extern const uint8_t *const riding_bodies[];
extern const uint16_t riding_masks[],riding_body_palette[],riding_head_palette[],riding_wheel_palette[];
extern const int8_t riding_up_x[],riding_up_y[];
#endif
''')
    ux=[round(-math.sin(i*2*math.pi/32)*127)for i in range(32)]
    uy=[round(-math.cos(i*2*math.pi/32)*127)for i in range(32)]
    (out/'riding_meta.c').write_text('#include "riding_assets.h"\n'
        +'const uint8_t *const riding_bodies[]={riding_body_0,riding_body_1,riding_body_2};\n'
        +array('riding_masks',body_masks,'uint16_t')
        +array('riding_body_palette',rgb555(body_pal),'uint16_t')
        +array('riding_head_palette',rgb555(head_pal),'uint16_t')
        +array('riding_wheel_palette',rgb555(wheel_pal),'uint16_t')
        +array('riding_up_x',ux,'int8_t')+array('riding_up_y',uy,'int8_t'))
    # Contact sheet preserves alpha over a neutral background for inspection.
    sheet=Image.new('RGB',(8*96,4*96),(100,150,190))
    for i in range(32):
        im=Image.fromarray(bodies[32+i]).resize((96,96),Image.Resampling.NEAREST)
        sheet.paste(im,(i%8*96,i//8*96),im)
    sheet.save(out/'riding-angles.png')
    # Decoded native tiles expose exactly the palette and alpha sent to VRAM.
    sheet=Image.new('RGB',(8*64,8*64),(100,150,190))
    for index in range(64):
        image=heads[index*4]
        delta=image[:,:,None,:3].astype(np.int32)-head_pal[None,None,1:,:].astype(np.int32)
        indices=((delta*delta).sum(axis=3).argmin(axis=2)+1).astype(np.uint8)
        indices[image[:,:,3]<128]=0
        decoded=Image.fromarray(head_pal[indices]).convert('RGBA')
        decoded.putalpha(Image.fromarray((indices!=0).astype(np.uint8)*255))
        decoded=decoded.resize((64,64),Image.Resampling.NEAREST)
        sheet.paste(decoded,(index%8*64,index//8*64),decoded)
    sheet.save(out/'riding-heads.png')
    report={'source':'original LGR parts through PC bikemodel','angles':32,
            'facing_states':2,'rider_compression_m':list(COMPRESSIONS),
            'body_frame_bytes':256,'body_upload':'only on angle/pose/facing change',
            'head_frame_bytes':16,'wheel_frame_bytes':64,
            'head_subpixel_phases':4,'head_palette':'original face/helmet/outline representatives',
            'head_vram_tiles':[216,245],'head_oam_entry':24,
            'max_body_sprites_per_scanline':max_line,'bike_oam':25,
            'max_nominal_bike_sprites_per_scanline':max_bike_line,
            'max_with_one_object_per_scanline':max_bike_line+2,
            'sprite_vram_bank':1,'sprite_vram_range':[192,216],
            'atlas_rom_banks':[10,11,12,13]}
    (out/'riding-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Original riding art:',len(bodies),'body frames;',len(heads),'heads;',len(wheels),'wheel phases')


if __name__=='__main__':main()
