"""Pack every original internal level for the streamed CGB renderer.

Patterns stay lossless after the documented four-color conversion. Map chunks
are raw planes so entering a new region never requires map decompression.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

import assets

import numpy as np
from PIL import Image

from assets import (array, elmadata, lgr_reader, mapmodel, render_level_data,
                    palettes_for, rgb555, tile2bpp)

PPM = 12


class Packer:
    def __init__(self, first):
        self.first = first
        self.banks = [bytearray()]

    @property
    def bank(self):
        return self.first + len(self.banks) - 1

    def allocate(self, data, alignment=1, contiguous=False):
        pad = (-len(self.banks[-1])) % alignment
        if len(self.banks[-1])+pad == 16384:
            self.banks.append(bytearray())
            pad = 0
        self.banks[-1].extend(bytes(pad))
        if not contiguous and len(data)+len(self.banks[-1]) > 16384:
            self.banks.append(bytearray())
        result = self.bank, 0x4000+len(self.banks[-1])
        remaining = memoryview(data)
        while remaining:
            n = min(len(remaining), 16384-len(self.banks[-1]))
            self.banks[-1].extend(remaining[:n])
            remaining = remaining[n:]
            if remaining:
                self.banks.append(bytearray())
        assert self.bank < 512, 'All-level data exceeds the 8 MiB MBC5 limit'
        return result


def scene(level, lgr):
    """Reduce sky and foreground separately, without invented edge colors."""
    level = render_level_data(level)
    points = [p for _, poly in level.polygons for p in poly]
    ox = math.floor(min(x for x,y in points)-4)
    oy = math.ceil(max(y for x,y in points)+4)
    w = math.ceil((max(x for x,y in points)+4-ox)*PPM/256)*256
    h = math.ceil((oy-min(y for x,y in points)+4)*PPM/128)*128
    pl = mapmodel.PcLevel(level, mapmodel.Textures(lgr))
    texture = pl.tex.texture(pl.bg)
    sky_rows = mapmodel.sky_row_map(h*4, texture.shape[0])
    x = round((ox-pl.origo[0])*48)
    columns = ((x//2)+np.arange(w*4)) % texture.shape[1]
    image = np.empty((h,w,3), dtype=np.uint8)
    background = np.empty((h,w), dtype=bool)
    dominant = int(np.bincount(texture.ravel()).argmax())
    base = (pl.tex.pal[dominant].astype(np.uint8)>>3)*8
    source_colors = np.unique((pl.tex.pal[np.unique(texture)].astype(np.uint8)>>3)*8,axis=0)
    for top in range(0,h*4,128):
        rows = min(128,h*4-top)
        y = round((oy-pl.origo[1])*48)-top-rows
        _, distance, _, colors = pl.render(x,x+w*4,y,y+rows)
        sr = sky_rows[h*4-top-rows:h*4-top][::-1]
        mask = distance == mapmodel.D_EG
        indices = np.where(mask,texture[sr][:,columns],colors)
        rgb = pl.tex.pal[indices].astype(np.uint32)
        shape = rows//4,4,w,4
        sky_n = mask.reshape(shape).sum((1,3))
        sums = (rgb*mask[...,None]).reshape(*shape,3).sum((1,3))
        sky_rgb = sums/np.maximum(sky_n,1)[...,None]
        sums = (rgb*(~mask)[...,None]).reshape(*shape,3).sum((1,3))
        foreground_rgb = sums/np.maximum(16-sky_n,1)[...,None]
        use_sky = sky_n >= 8
        image[top//4:(top+rows)//4] = np.where(use_sky[...,None],sky_rgb,foreground_rgb).round().astype(np.uint8)
        background[top//4:(top+rows)//4] = use_sky
    return image,background,ox,oy,base,source_colors,pl.bg == 'sky'


def quantize(image, background, base, sky_colors, blue_sky):
    h,w,_ = image.shape
    flat = image.reshape(h//8,8,w//8,8,3).transpose(0,2,1,3,4).reshape(-1,64,3).astype(np.int32)
    masks = background.reshape(h//8,8,w//8,8).transpose(0,2,1,3).reshape(-1,64)
    means = flat.mean(1)
    centers = means[np.linspace(0,len(means)-1,7,dtype=int)].copy()
    for _ in range(12):
        labels = ((means[:,None]-centers)**2).sum(2).argmin(1)
        for k in range(7):
            if np.any(labels==k):centers[k]=means[labels==k].mean(0)
    palettes = []
    for k in range(7):
        pixels = flat[labels==k].reshape(-1,3)
        sky = masks[labels==k].ravel()
        if not len(pixels):pixels,sky=flat[0],masks[0]
        if not blue_sky:
            pal = palettes_for(pixels.reshape(-1,1,3),1,4)[0]
        elif sky.all():
            choices = Image.fromarray(pixels.astype(np.uint8).reshape(-1,1,3)).quantize(colors=3)
            extra = np.array(choices.getpalette()[:9]).reshape(3,3)
            nearest = ((extra[:,None]-sky_colors.astype(np.int32))**2).sum(2).argmin(1)
            pal = np.vstack((base,sky_colors[nearest]))
        elif not sky.any():
            pal = np.vstack((base,palettes_for(pixels.reshape(-1,1,3),1,3)[0]))
        else:
            ground = pixels[~sky]
            fg = palettes_for(ground.reshape(-1,1,3),1,2)[0]
            color = pixels[sky].mean(0)
            accent = sky_colors[((sky_colors.astype(np.int32)-color)**2).sum(1).argmin()]
            pal = np.vstack((base,accent,fg))
        palettes.append((pal.astype(np.uint8)>>3)*8)
    palettes = np.asarray(palettes)
    encoded,attrs,preview = [],[],[]
    allowed = np.array([[(c==sky_colors).all(1).any() for c in pal] for pal in palettes])
    for tile,sky in zip(flat,masks):
        distances = ((tile[None,:,None]-palettes[:,None].astype(np.int32))**2).sum(3)
        if blue_sky:
            # Sky pixels may only select actual source sky colors, never an
            # averaged brown/blue palette color fitted to a ground edge.
            distances = np.where(sky[None,:,None]&~allowed[:,None,:],2**28,distances)
            # The original base blue is exactly palette entry zero everywhere.
            exact = ((tile>>3)*8==base).all(1)&sky
            distances[:,exact,:]=2**28
            distances[:,exact,0]=0
        pi = int(distances.min(2).sum(1).argmin())
        q = distances[pi].argmin(1).astype(np.uint8).reshape(8,8)
        encoded.append(tile2bpp(q));attrs.append(pi);preview.append(palettes[pi][q])
    restored = np.asarray(preview).reshape(h//8,w//8,8,8,3).transpose(0,2,1,3,4).reshape(h,w,3)
    return encoded,np.array(attrs,dtype=np.uint8),palettes,restored


def canonical(encoded):
    reverse = bytes(int(f'{i:08b}'[::-1],2) for i in range(256))
    unique,ids,flips,index = [],[],[],{}
    for tile in encoded:
        vertical = b''.join(tile[i:i+2] for i in range(14,-1,-2))
        variants = tile,tile.translate(reverse),vertical,vertical.translate(reverse)
        v = min(range(4),key=lambda k:variants[k]);pattern=variants[v]
        if pattern not in index:index[pattern]=len(unique);unique.append(pattern)
        ids.append(index[pattern]);flips.append((0,32,64,96)[v])
    return unique,np.asarray(ids,dtype=np.uint16),np.asarray(flips,dtype=np.uint8)


def killer(lgr):
    pic = lgr['qkiller'].image
    frame = pic.crop((0,0,pic.height,pic.height))
    source=np.array(frame);alpha=(source!=source[0,0]).astype(np.uint8)*255
    rgba=frame.convert('RGBA');rgba.putalpha(Image.fromarray(alpha))
    size=max(1,round(pic.height/4));im=Image.new('RGBA',(16,16))
    im.paste(rgba.resize((size,size),Image.Resampling.BOX),((16-size)//2,(16-size)//2))
    a=np.array(im);pal=np.vstack(([0,0,0],palettes_for(a[a[:,:,3]>=128,:3].reshape(-1,1,3).astype(np.int32),1,3)[0]))
    q=(((a[:,:,None,:3].astype(np.int32)-pal[None,None,1:])**2).sum(3).argmin(2)+1).astype(np.uint8);q[a[:,:,3]<128]=0
    return b''.join(tile2bpp(q[y:y+8,x:x+8])for y in(0,8)for x in(0,8)),rgb555(pal)


def main():
    p=argparse.ArgumentParser();p.add_argument('--res',type=Path,required=True);p.add_argument('--lgr',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    assets.OUT=a.out
    physics=json.loads((a.out/'physics_bank_manifest.json').read_text())
    first=physics['next_free_bank'];packer=Packer(first)
    fingerprint=hashlib.sha256(Path(__file__).read_bytes()+Path(assets.__file__).read_bytes()
        +Path(mapmodel.__file__).read_bytes()+a.res.read_bytes()+a.lgr.read_bytes()
        +(a.out/'physics_bank_manifest.json').read_bytes()).hexdigest()
    previous=a.out/'level_manifest.json'
    if previous.is_file():
        cached=json.loads(previous.read_text())
        if cached.get('fingerprint')==fingerprint and all((a.out/name).is_file()for name in ('level_catalogue.c','level_catalogue.h')) \
           and all((a.out/('level_bank_%d.c'%bank)).is_file()for bank in range(first,cached['last_bank']+1)) \
           and all((a.out/'levels'/('%02d'%(index+1))/'tiles.npz').is_file()for index in range(cached['count'])):
            print('All-level graphics unchanged: banks%d..%d'%(first,cached['last_bank']));return
    levels=elmadata.internal_levels(elmadata.Resource(a.res));lgr=lgr_reader.Lgr(a.lgr)
    for old in a.out.glob('level_bank_*.c'):old.unlink()
    directory=[];report=[];chunk_dedup={}
    for number,level in enumerate(levels):
        image,mask,ox,oy,base,sky_colors,blue_sky=scene(level,lgr)
        encoded,attrs,pal,preview=quantize(image,mask,base,sky_colors,blue_sky)
        unique,ids,flips=canonical(encoded);attrs|=flips
        assert len(unique)<32768,'Pattern lookup needs more than64KiB scratch RAM'
        h,w,_=image.shape;tw,th=w//8,h//8
        pattern_pointer=packer.allocate(b''.join(unique),16,True)
        chunks=[]
        grid=ids.reshape(th,tw);attribute=attrs.reshape(th,tw)
        for cy in range(0,th,16):
            for cx in range(0,tw,32):
                values=grid[cy:cy+16,cx:cx+32].ravel()
                blob=bytes((values&255).astype(np.uint8))+bytes((values>>8).astype(np.uint8))+bytes(attribute[cy:cy+16,cx:cx+32].ravel())
                if blob not in chunk_dedup:chunk_dedup[blob]=packer.allocate(blob)
                chunks.append(chunk_dedup[blob])
        chunk_pointer=packer.allocate(b''.join(struct.pack('<HH',*c)for c in chunks),2)
        palette_pointer=packer.allocate(struct.pack('<28H',*rgb555(pal)),2)
        objects=[(round((x-ox)*12),round((oy-y)*12),kind,round(x*65536),round(y*65536),gravity)
                 for kind,x,y,gravity,_ in level.objects if kind in(1,2,3)]
        assert len(objects)<=64
        object_pointer=packer.allocate(b''.join(struct.pack('<HHBiiB',*obj)for obj in objects),2)
        directory.append('{%d,%d,%dL,%dL,%d,{%d,%d},{%d,%d},{%d,%d},{%d,%d},%d,%d,%d}'%
                         (w,h,ox*65536,oy*65536,len(unique),*pattern_pointer,*chunk_pointer,*palette_pointer,*object_pointer,tw//32,th//16,len(objects)))
        target=a.out/'levels'/('%02d'%(number+1));target.mkdir(parents=True,exist_ok=True)
        Image.fromarray(image).save(target/'source.png');Image.fromarray(preview).save(target/'preview.png')
        np.savez_compressed(target/'tiles.npz',ids=grid,attrs=attribute,patterns=np.frombuffer(b''.join(unique),np.uint8),sky=mask,palettes=pal)
        record={'index':number,'name':level.name,'size_px':[w,h],'origin_m':[ox,oy],'pattern_count':len(unique),
                'patterns':pattern_pointer,'chunks':chunks,'chunk_directory':chunk_pointer,'palette':palette_pointer,
                'objects_pointer':object_pointer,'objects':[list(o)for o in objects],
                'blue_sky':blue_sky,'sky_base_rgb':base.tolist(),'sky_colors_rgb':sky_colors.tolist()}
        report.append(record);print('%02d %-18s %dx%d %d patterns bank%d'%(number+1,level.name,w,h,len(unique),packer.bank),flush=True)
    header='''#ifndef GBC_LEVEL_CATALOGUE_H
#define GBC_LEVEL_CATALOGUE_H
#include <stdint.h>
#define LEVEL_COUNT %d
#define LEVEL_OBJECT_MAX 64
typedef struct {uint16_t bank,address;} world_far_t;
typedef struct {
 uint16_t width,height;int32_t origin_x,origin_y;uint16_t pattern_count;
 world_far_t patterns,chunks,palette,objects;
 uint8_t chunks_x,chunks_y,object_count;
} world_level_t;
extern const world_level_t world_levels[];
extern const char world_names[][20];
extern const uint8_t object_tiles[];
extern const uint16_t object_palette[];
extern const uint8_t killer_tiles[];
extern const uint16_t killer_palette[];
#endif
'''%len(levels)
    (a.out/'level_catalogue.h').write_text(header)
    kt,kp=killer(lgr)
    objects,object_palette=assets.object_data(lgr)
    (a.out/'level_catalogue.c').write_text('#include "level_catalogue.h"\n#pragma bank 14\nconst world_level_t world_levels[]={\n'+',\n'.join(directory)+'\n};\nconst char world_names[][20]={\n'+',\n'.join(json.dumps(l.name)for l in levels)+'\n};\n'+array('killer_tiles',kt)+array('killer_palette',kp,'uint16_t')+array('object_tiles',objects)+array('object_palette',object_palette,'uint16_t'))
    for i,data in enumerate(packer.banks):
        bank=first+i;(a.out/('level_bank_%d.c'%bank)).write_text('#include <stdint.h>\n#pragma bank %d\n'%bank+array('level_bank_%d'%bank,data))
    manifest={'fingerprint':fingerprint,'levels':report,'count':len(levels),'first_bank':first,'last_bank':packer.bank,
              'payload_bytes':sum(map(len,packer.banks)),'physical_bank_bytes':len(packer.banks)*16384,
              'map_codec':'raw3-plane32x16','palette_policy':'source sky colors; protected shared base blue; separate foreground coverage',
              'source_sha256':{str(x.resolve()):hashlib.sha256(x.read_bytes()).hexdigest()for x in(a.res,a.lgr)}}
    (a.out/'level_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('All-level graphics banks %d..%d, %d payload bytes'%(first,packer.bank,manifest['payload_bytes']))


if __name__=='__main__':main()
