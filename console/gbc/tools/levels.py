"""Pack every original internal level for the streamed CGB renderer.

Patterns stay lossless after the documented four-color conversion. Map chunks
are raw planes so entering a new region never requires map decompression.
"""
import argparse
import hashlib
import json
import inspect
import math
from pathlib import Path
import struct
import shutil

import assets
import rolling_map_banks
import rider_map_tables

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
    # Named scenery pictures use a scalar source; grass edges use source
    # arrays. Keep their provenance through reduction for palette correction.
    decoration_source = -2
    for piece in pl.pieces():
        if np.isscalar(piece.src) and piece.src == mapmodel.S_PIC:
            piece.src = decoration_source
    texture = pl.tex.texture(pl.bg)
    sky_rows = mapmodel.sky_row_map(h*4, texture.shape[0])
    x = round((ox-pl.origo[0])*48)
    columns = ((x//2)+np.arange(w*4)) % texture.shape[1]
    image = np.empty((h,w,3), dtype=np.uint8)
    background = np.empty((h,w), dtype=bool)
    decorations = np.empty((h,w), dtype=bool)
    dominant = int(np.bincount(texture.ravel()).argmax())
    base = (pl.tex.pal[dominant].astype(np.uint8)>>3)*8
    source_colors = np.unique((pl.tex.pal[np.unique(texture)].astype(np.uint8)>>3)*8,axis=0)
    for top in range(0,h*4,128):
        rows = min(128,h*4-top)
        y = round((oy-pl.origo[1])*48)-top-rows
        _, distance, sources, colors = pl.render(x,x+w*4,y,y+rows)
        sr = sky_rows[h*4-top-rows:h*4-top][::-1]
        mask = distance == mapmodel.D_EG
        indices = np.where(mask,texture[sr][:,columns],colors)
        rgb = pl.tex.pal[indices].astype(np.uint32)
        green = ((sources == decoration_source) & (rgb[:,:,1] > rgb[:,:,0])
                 & (rgb[:,:,1] > rgb[:,:,2]))
        shape = rows//4,4,w,4
        sky_n = mask.reshape(shape).sum((1,3))
        sums = (rgb*mask[...,None]).reshape(*shape,3).sum((1,3))
        sky_rgb = sums/np.maximum(sky_n,1)[...,None]
        sums = (rgb*(~mask)[...,None]).reshape(*shape,3).sum((1,3))
        foreground_rgb = sums/np.maximum(16-sky_n,1)[...,None]
        use_sky = sky_n >= 8
        image[top//4:(top+rows)//4] = np.where(use_sky[...,None],sky_rgb,foreground_rgb).round().astype(np.uint8)
        background[top//4:(top+rows)//4] = use_sky
        decorations[top//4:(top+rows)//4] = green.reshape(shape).any((1,3)) & ~use_sky
    return image,background,ox,oy,base,source_colors,pl.bg == 'sky',decorations


def quantize(image, background, base, sky_colors, blue_sky, decorations):
    h,w,_ = image.shape
    flat = image.reshape(h//8,8,w//8,8,3).transpose(0,2,1,3,4).reshape(-1,64,3).astype(np.int32)
    masks = background.reshape(h//8,8,w//8,8).transpose(0,2,1,3).reshape(-1,64)
    scenery = decorations.reshape(h//8,8,w//8,8).transpose(0,2,1,3).reshape(-1,64)
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
    usage = np.zeros((7,4,3), dtype=np.int64)  # decoration, other, sky
    allowed = np.array([[(c==sky_colors).all(1).any() for c in pal] for pal in palettes])
    for tile,sky,decor in zip(flat,masks,scenery):
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
        usage[pi,:,0] += np.bincount(q.ravel()[decor], minlength=4)
        usage[pi,:,1] += np.bincount(q.ravel()[~decor], minlength=4)
        usage[pi,:,2] += np.bincount(q.ravel()[sky], minlength=4)
        encoded.append(tile2bpp(q));attrs.append(pi);preview.append(q)
    # One hardware green step for colors used mainly by named scenery. Fit
    # and index against the unmodified art so tile detail and sky stay exact;
    # bright grass colors and colors mainly used by terrain are left alone.
    green = ((palettes[:,:,1] > palettes[:,:,0]) & (palettes[:,:,1] > palettes[:,:,2])
             & (palettes[:,:,1] < 192) & (usage[:,:,0] > usage[:,:,1])
             & (usage[:,:,2] == 0) & ~allowed)
    palettes[:,:,1][green] += 8
    restored = palettes[np.asarray(attrs)[:,None,None],np.asarray(preview)]
    restored = restored.reshape(h//8,w//8,8,8,3).transpose(0,2,1,3,4).reshape(h,w,3)
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


# This pre-profile cache was generated by the same rendering functions. Its
# complete old fingerprint also binds the resource, LGR and physics metadata.
LEGACY_RENDER_FINGERPRINTS = {
    '1d600827c42379a44ad311059b0774b7678f5e549dcce71cf4be5e4ceeea7089':
        '575b7abb0c2db10cdf6c4f36ee43d49da832142a4c281ff11df5d88ba155ec7b',
}


def render_fingerprint(res, lgr):
    code = ''.join(inspect.getsource(fn) for fn in (scene, quantize, canonical))
    return hashlib.sha256(str(PPM).encode() + code.encode()
        + Path(assets.__file__).read_bytes() + Path(mapmodel.__file__).read_bytes()
        + res.read_bytes() + lgr.read_bytes()).hexdigest()


def rendered_cache(directory, render_key, source_hashes):
    path = directory / 'level_manifest.json'
    if not path.is_file():
        return None
    cached = json.loads(path.read_text())
    if sorted(cached.get('source_sha256', {}).values()) != sorted(source_hashes.values()):
        return None
    if cached.get('render_fingerprint') != render_key:
        if cached.get('render_fingerprint') or LEGACY_RENDER_FINGERPRINTS.get(cached.get('fingerprint')) != render_key:
            return None
    records = cached.get('levels', [])
    if len(records) != cached.get('count') or not records:
        return None
    if any(record['index'] != i or not (directory / 'levels' / ('%02d' % (i + 1)) / 'tiles.npz').is_file()
           for i, record in enumerate(records)):
        return None
    return cached


def main():
    p=argparse.ArgumentParser();p.add_argument('--res',type=Path,required=True);p.add_argument('--lgr',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--rom-mib',type=int,choices=(4,8),default=4)
    p.add_argument('--cache-gen',type=Path,help='reuse verified rendered tiles from another generated directory')
    p.add_argument('--compact-scenery', action='store_true',
                   help='release four whole banks in the original scheduled 8 MiB pack')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    assets.OUT=a.out
    physics=json.loads((a.out/'physics_bank_manifest.json').read_text())
    first=physics['next_free_bank'];packer=Packer(first)
    render_key=render_fingerprint(a.res,a.lgr)
    source_hashes={str(x.resolve()):hashlib.sha256(x.read_bytes()).hexdigest()for x in(a.res,a.lgr)}
    riding_constants=(a.out/'riding_constants.h').read_text()
    scheduled=a.rom_mib==8 and '#define RIDING_PC_SCHEDULE 1' in riding_constants
    compact_key = b''
    if a.compact_scenery:
        if not scheduled:
            p.error('--compact-scenery requires the scheduled 8 MiB profile')
        import scenery_compact
        compact_key = Path(scenery_compact.__file__).read_bytes()
    fingerprint=hashlib.sha256(Path(__file__).read_bytes()+render_key.encode()+compact_key
        + Path(rolling_map_banks.__file__).read_bytes()+Path(rider_map_tables.__file__).read_bytes()+riding_constants.encode()
        +(a.out/'physics_bank_manifest.json').read_bytes()).hexdigest()
    cache_dir=a.out
    cached=rendered_cache(cache_dir,render_key,source_hashes)
    desired_codec='zx0-planes32x16' if a.rom_mib==4 else 'raw3-plane32x16'
    if cached and cached.get('fingerprint')==fingerprint and cached.get('rom_mib')==a.rom_mib \
       and cached.get('map_codec') in ((desired_codec,rider_map_tables.CODEC,rolling_map_banks.CODEC) if scheduled else (desired_codec,)) and cached['first_bank']==first \
       and all((a.out/name).is_file()for name in ('level_catalogue.c','level_catalogue.h')) \
       and all((a.out/('level_bank_%d.c'%bank)).is_file()for bank in range(first,cached['last_bank']+1)
               if bank not in cached.get('released_banks', ())):
        print('All-level graphics unchanged: banks %d..%d'%(first,cached['last_bank']));return
    if cached is None and a.cache_gen:
        cache_dir=a.cache_gen
        cached=rendered_cache(cache_dir,render_key,source_hashes)
    levels=elmadata.internal_levels(elmadata.Resource(a.res));lgr=lgr_reader.Lgr(a.lgr)
    if cached and (len(levels)!=cached['count'] or any(level.name!=record['name']for level,record in zip(levels,cached['levels']))):
        raise ValueError('Rendered cache level catalogue differs from the resource')
    if cached:print('Repacking %d cached level renders from %s'%(len(levels),cache_dir),flush=True)
    for old in a.out.glob('level_bank_*.c'):old.unlink()
    directory=[];report=[];chunk_dedup={}
    for number,level in enumerate(levels):
        target=a.out/'levels'/('%02d'%(number+1));target.mkdir(parents=True,exist_ok=True)
        if cached:
            record=cached['levels'][number]
            w,h=record['size_px'];ox,oy=record['origin_m']
            blue_sky=record['blue_sky'];base=np.asarray(record['sky_base_rgb']);sky_colors=np.asarray(record['sky_colors_rgb'])
            source_dir=cache_dir/'levels'/('%02d'%(number+1))
            with np.load(source_dir/'tiles.npz') as tiles:
                grid=tiles['ids'];attribute=tiles['attrs'];pal=tiles['palettes'];patterns=tiles['patterns'].tobytes()
            if grid.shape!=(h//8,w//8) or attribute.shape!=grid.shape or pal.shape!=(7,4,3) \
               or len(patterns)!=record.get('source_pattern_count',record['pattern_count'])*16 \
               or grid.max()>=len(patterns)//16:
                raise ValueError('Invalid rendered tile cache for level %d'%(number+1))
            if source_dir.resolve()!=target.resolve():
                for name in ('tiles.npz','source.png','preview.png'):
                    if (source_dir/name).is_file():shutil.copy2(source_dir/name,target/name)
        else:
            image,mask,ox,oy,base,sky_colors,blue_sky,decor=scene(level,lgr)
            encoded,attrs,pal,preview=quantize(image,mask,base,sky_colors,blue_sky,decor)
            unique,ids,flips=canonical(encoded);attrs|=flips
            h,w,_=image.shape;grid=ids.reshape(h//8,w//8);attribute=attrs.reshape(h//8,w//8)
            patterns=b''.join(unique)
            Image.fromarray(image).save(target/'source.png');Image.fromarray(preview).save(target/'preview.png')
            np.savez_compressed(target/'tiles.npz',ids=grid,attrs=attribute,patterns=np.frombuffer(patterns,np.uint8),sky=mask,palettes=pal)
        pattern_count=len(patterns)//16
        assert pattern_count<32768,'Pattern lookup exceeds the uint16 index range'
        tw,th=w//8,h//8
        pattern_pointer=packer.allocate(patterns,16,True)
        chunks=[]
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
                         (w,h,ox*65536,oy*65536,pattern_count,*pattern_pointer,*chunk_pointer,*palette_pointer,*object_pointer,tw//32,th//16,len(objects)))
        record={'index':number,'name':level.name,'size_px':[w,h],'origin_m':[ox,oy],'pattern_count':pattern_count,
                'patterns':pattern_pointer,'chunks':chunks,'chunk_directory':chunk_pointer,'palette':palette_pointer,
                'objects_pointer':object_pointer,'objects':[list(o)for o in objects],
                'blue_sky':blue_sky,'sky_base_rgb':base.tolist(),'sky_colors_rgb':sky_colors.tolist()}
        report.append(record);print('%02d %-18s %dx%d %d patterns bank%d'%(number+1,level.name,w,h,pattern_count,packer.bank),flush=True)
    rider_bank = rider_map_tables.repack(packer, report, riding_constants) if scheduled else None
    rolling_banks = rolling_map_banks.repack(packer, report) if rider_bank is not None else None
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
    manifest={'fingerprint':fingerprint,'render_fingerprint':render_key,'rom_mib':a.rom_mib,'levels':report,'count':len(levels),'first_bank':first,'last_bank':packer.bank,
              'payload_bytes':sum(map(len,packer.banks)),'physical_bank_bytes':len(packer.banks)*16384,
              'map_codec':'raw3-plane32x16','pattern_codec':'raw-2bpp','palette_policy':'source sky colors; protected shared base blue; separate foreground coverage; one-step green lift for decoration-majority colors',
              'source_sha256':source_hashes}
    if rider_bank is not None:
        manifest.update(map_codec=rider_map_tables.CODEC, rider_product_first_bank=rider_bank,
                        rider_product_constants_sha256=hashlib.sha256(riding_constants.encode()).hexdigest())
    if rolling_banks:
        manifest.update(map_codec=rolling_map_banks.CODEC, rolling_map_banks=rolling_banks)
    (a.out/'level_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    if a.compact_scenery:
        scenery_compact.compact(a.out)
    else:
        print('All-level graphics banks %d..%d, %d payload bytes'%(first,packer.bank,manifest['payload_bytes']))


if __name__=='__main__':main()
