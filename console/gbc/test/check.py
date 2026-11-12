"""Check actual ROM metadata, visible VRAM, controls, object colors and math.

No original game data is distributed with these tests; build with owned data.
"""
import argparse
import ctypes as C
import json
from pathlib import Path
import random
import re
import subprocess
import sys

import numpy as np
from PIL import Image
from pyboy import PyBoy

BASE = Path(__file__).resolve().parents[1]
BUILD = BASE/'build'
GEN = BUILD/'gen'
sys.path.insert(0,str(BASE/'tools'))
from assets import tile2bpp, render_level_data, OMITTED_PICTURES
import elmadata
import lgr as lgr_reader
import mapmodel


def symbols(name):
    return {k:int(v,16) for k,v in re.findall(r'DEF (_\w+) 0x([0-9a-fA-F]+)',
                                          (BUILD/(name+'.noi')).read_text())}


def u16(p, address):
    return p.memory[address] + 256*p.memory[address+1]


def c_array(path):
    block = re.search(r'\[\] = \{(.*?)\};',path.read_text(),re.S)[1]
    return bytes(map(int,re.findall(r'\d+',block)))


def rom_header(path):
    rom = path.read_bytes()
    assert rom[0x143] == 0xC0, 'must be CGB only'
    assert rom[0x147] == 0x19, 'MBC5 cartridge header'
    assert len(rom) == 32768 << rom[0x148], 'ROM bank count'
    assert rom[0x14d] == (-sum(rom[0x134:0x14d])-25)&255, 'header checksum'
    assert int.from_bytes(rom[0x14e:0x150],'big') == (sum(rom)-sum(rom[0x14e:0x150]))&65535


def source_conversion():
    meta=json.loads((GEN/'manifest.json').read_text())
    res=next(Path(p) for p in meta['source_sha256'] if Path(p).suffix.lower()=='.res')
    lgr_path=next(Path(p) for p in meta['source_sha256'] if Path(p).suffix.lower()=='.lgr')
    levels=elmadata.internal_levels(elmadata.Resource(res))
    exported=json.loads((GEN/'levels.json').read_text())
    assert len(levels)==len(exported)==meta['source_levels_preserved']
    for level,record in zip(levels,exported):
        assert record['polygons']==json.loads(json.dumps(level.polygons))
        assert record['objects']==json.loads(json.dumps(level.objects))
        assert record['pictures']==[vars(pic) for pic in level.pictures], 'original scenery metadata was lost'
        rendered=render_level_data(level)
        assert rendered is not level and rendered.polygons is level.polygons
        assert rendered.objects is level.objects
        assert all(pic.name not in OMITTED_PICTURES for pic in rendered.pictures)
        assert [vars(pic) for pic in rendered.pictures]==[vars(pic) for pic in level.pictures
            if pic.name not in {'tree1','tree2','tree3','tree4','tree5','flag','barrel'}]
    # Compare strip conversion against one whole original-PC raster operation.
    # This catches a sky origin accidentally restarting at every strip.
    pl=mapmodel.PcLevel(render_level_data(levels[0]),mapmodel.Textures(lgr_reader.Lgr(lgr_path)))
    ox,oy=meta['origin_m'];w,h=meta['size_px']
    x=round((ox-pl.origo[0])*48)
    y=round((oy-pl.origo[1])*48)-h*4
    indices,_=mapmodel.pc_picture(pl,x,y,w*4,h*4)
    expected=Image.fromarray(pl.tex.pal[indices].astype(np.uint8)).resize((w,h),Image.Resampling.BOX)
    assert np.array_equal(np.array(expected),np.array(Image.open(GEN/'scene-source.png'))), 'strip raster differs from original PC raster'
    return {'preserved_levels':len(levels),'whole_pc_raster_match':True,
            'scenery_filter_preserves_geometry_objects_and_source_pictures':True}


def visible_vram(p,s):
    x,y = u16(p,s['_camera_x'])>>3, u16(p,s['_camera_y'])>>3
    patterns=c_array(GEN/'patterns.c')
    for ty in range(y,y+18):
        for tx in range(x,x+21):
            if tx>=64 or ty>=48:
                continue
            chunk=(ty//16)*2+tx//32+2
            blob=c_array(GEN/('world_%d.c'%chunk))
            local=(ty%16)*32+tx%32
            addr=0x9800+(ty%32)*32+tx%32
            tile,attr=p.memory[0,addr],p.memory[1,addr]
            assert (tile,attr)==(blob[local],blob[512+local]), (tx,ty,'map')
            pattern=tile+(256 if attr&8 else 0)
            actual=bytes(p.memory[1 if attr&8 else 0,0x8000+tile*16:0x8010+tile*16])
            assert actual==patterns[pattern*16:pattern*16+16], (tx,ty,'pattern')


def viewer():
    name='elma-gbc-viewer'
    rom_header(BUILD/(name+'.gbc'))
    p=PyBoy(str(BUILD/(name+'.gbc')),window='null',sound_emulated=False,cgb=True)
    p.set_emulation_speed(0)
    s=symbols(name)
    try:
        p.tick(180)
        assert p.memory[s['_viewer_ready']]==1
        visible_vram(p,s)
        p.screen.image.save(BUILD/'viewer-start.png')
        snapshots=[]
        # Cross both ROM chunks and the 32x32 BG map wrap, including diagonals.
        for keys,frames,label in [('right a',100,'apple'),('left a',110,'flower'),
                                   ('up a',90,'top'),('right down a',70,'diagonal'),
                                   ('down a',90,'bottom'),('left a',110,'left'),('start',1,'reset')]:
            for key in keys.split(): p.button_press(key)
            p.tick(frames)
            for key in keys.split(): p.button_release(key)
            p.tick(3)
            for _ in range(60):
                if p.memory[s['_viewer_ready']]: break
                p.tick(1)
            assert p.memory[s['_viewer_ready']]==1, 'camera reset did not finish'
            visible_vram(p,s)
            p.screen.image.save(BUILD/('viewer-'+label+'.png'))
            snapshots.append({'position':[u16(p,s['_camera_x']),u16(p,s['_camera_y'])], 'view':label})
        overruns=p.memory[s['_viewer_overruns']]
        assert overruns==0, 'viewer missed a display deadline: %d'%overruns
        p.button_press('b');p.tick(2);p.button_release('b');p.tick(2)
        assert p.memory[0xfe03]&0x20, 'B did not mirror the bike'
        p.button_press('b');p.tick(2);p.button_release('b');p.tick(2)
        assert not p.memory[0xfe03]&0x20
        p.button_press('select');p.tick(2);p.button_release('select');p.tick(2)
        assert all(p.memory[0xfe00+i*4]==0 for i in range(16)), 'Select did not hide the bike'
        p.button_press('select');p.tick(2);p.button_release('select');p.tick(2)
        assert any(p.memory[0xfe00+i*4]!=0 for i in range(16)), 'Select did not restore the bike'
        # Check protected palettes in the actual CGB object palette RAM.
        p.memory[0xff6a]=10  # palette 1, red color 1
        red=p.memory[0xff6b]
        p.memory[0xff6a]=11
        red|=p.memory[0xff6b]<<8
        p.memory[0xff6a]=18  # palette 2, white color 1
        white=p.memory[0xff6b]
        p.memory[0xff6a]=19
        white|=p.memory[0xff6b]<<8
        assert red==0x001f and white==0x7fff, (red,white)
        # Both visible object screenshots must actually contain their required color.
        for name,channel in [('apple','red'),('flower','white')]:
            manifest=json.loads((GEN/'manifest.json').read_text())
            obj=next(o for o in manifest['objects'] if o['kind']==(2 if name=='apple' else 1))
            cam=next(v['position'] for v in snapshots if v['view']==name)
            x,y=obj['x']-cam[0],obj['y']-cam[1]
            crop=Image.open(BUILD/('viewer-'+name+'.png')).convert('RGB').crop((max(0,x-8),max(0,y-8),min(160,x+8),min(136,y+8)))
            rgb=np.array(crop).astype(int)
            mask=((rgb[:,:,0]>200)&(rgb[:,:,1]<50)&(rgb[:,:,2]<50)) if channel=='red' else (rgb.min(axis=2)>240)
            assert mask.sum()>=4, 'missing visible '+channel+' object pixels'
        return {'overruns':overruns,'checked_views':snapshots,'apple_rgb555':red,'flower_rgb555':white}
    finally:
        p.stop(save=False)


class Axle(C.Structure):
    _fields_=[(name,C.c_int16) for name in ('rest_x','rest_y','dx','dy','relative_vx','relative_vy')]


class Output(C.Structure):
    _fields_=[('wheel_dvx',C.c_int16*2),('wheel_dvy',C.c_int16*2),
              ('body_dvx',C.c_int16),('body_dvy',C.c_int16),('body_domega',C.c_int16)]


def suspension():
    library=BUILD/('suspension.dylib' if sys.platform=='darwin' else 'suspension.so')
    subprocess.run(['cc','-shared','-fPIC','-std=c99','-I'+str(GEN),
                    str(BASE/'src/suspension.c'),'-o',str(library)],check=True)
    fn=C.CDLL(str(library)).suspension_impulses
    fn.argtypes=[C.POINTER(Axle),C.POINTER(Output)]
    original=json.loads((GEN/'physics-reference.json').read_text())
    rng=random.Random(182)
    maximum=0.
    for _ in range(2048):
        axes=(Axle*2)(*[Axle(rng.randint(-1600,1600),rng.randint(-1600,1600),
                             rng.randint(-100,100),rng.randint(-100,100),
                             rng.randint(-2048,2048),rng.randint(-2048,2048)) for i in range(2)])
        result=Output()
        fn(axes,C.byref(result))
        expected_w=[],[]
        bx=by=torque=0.
        for i,a in enumerate(axes):
            sx=a.dx*original['spring']*original['dt']/original['wheel_mass']
            sy=a.dy*original['spring']*original['dt']/original['wheel_mass']
            fx=a.relative_vx*original['damping']*original['dt']/original['wheel_mass']
            fy=a.relative_vy*original['damping']*original['dt']/original['wheel_mass']
            expected_w[0].append(sx+fx);expected_w[1].append(sy+fy)
            bx-=(sx+fx)*original['wheel_mass']/original['body_mass']
            by-=(sy+fy)*original['wheel_mass']/original['body_mass']
            torque-=((a.rest_x*sy-a.rest_y*sx)+(a.rest_x-a.dx)*fy-(a.rest_y-a.dy)*fx)/1024*original['wheel_mass']/original['inertia']
        actual=list(result.wheel_dvx)+list(result.wheel_dvy)+[result.body_dvx,result.body_dvy,result.body_domega]
        expected=expected_w[0]+expected_w[1]+[bx,by,torque]
        maximum=max(maximum,max(abs(a-b)/1024 for a,b in zip(actual,expected)))
    assert maximum<.005, maximum
    fixture=(Axle*2)(Axle(-870,-614,31,-17,341,-512),Axle(870,-614,-23,47,-172,239))
    result=Output();fn(fixture,C.byref(result))
    return maximum, bytes(result)


def probe(expected):
    name='physics-probe'
    rom_header(BUILD/(name+'.gbc'))
    s=symbols(name)
    p=PyBoy(str(BUILD/(name+'.gbc')),window='null',sound_emulated=False,cgb=True)
    p.set_emulation_speed(0)
    try:
        for _ in range(30):
            p.tick(100)
            if p.memory[s['_probe_done']]:break
        assert p.memory[s['_probe_done']]==1, 'probe timed out'
        assert p.memory[s['_probe_math_ok']]==1, 'SM83 signed multiplication vectors'
        address=s['_probe_result']
        assert bytes(p.memory[address:address+len(expected)])==expected, 'SM83 vs host kernel output'
        frames=u16(p,s['_probe_frames'])
        p.screen.image.save(BUILD/'physics-probe.png')
        return {'calls':1024,'display_frames':frames,'frames_per_call':frames/1024,
                'math_vectors':256,'host_kernel_bit_match':True,
                'full_physics':False,'hardware_tested':False}
    finally:
        p.stop(save=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gen',type=Path,default=GEN)
    GEN=parser.parse_args().gen.resolve()
    assert tile2bpp(np.tile(np.array([0,1,2,3,0,1,2,3]),(8,1)))==bytes([0x55,0x33])*8
    error,expected=suspension()
    report={'source_conversion':source_conversion(),'viewer':viewer(),'suspension_max_impulse_error':error,'probe':probe(expected)}
    (BUILD/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
