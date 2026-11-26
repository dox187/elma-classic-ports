"""Select every original course through the actual ROM menu and verify its data.

All state changes come from buttons. Source payload, spawn, object/gravity
metadata, dynamic VRAM cache and displayed background colors are checked
independently; this does not claim that all54 courses were completed.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

import numpy as np
from PIL import Image

from play import bg_tile_address,Driver,RIDING,DEAD,FINISHED,PAUSED,MENU

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE.parents[1]/'console/snes/tools'))
import elmadata


def tile_pixels(data):
    return np.array([[(data[y*2]>>(7-x)&1)|((data[y*2+1]>>(7-x)&1)<<1)
                      for x in range(8)]for y in range(8)],dtype=np.uint8)


def original_object_pixels(data):
    result=[]
    for base in (0,64):
        tiles=[tile_pixels(data[base+i*16:base+(i+1)*16])for i in range(4)]
        result.append(np.block([[tiles[0],tiles[1]],[tiles[2],tiles[3]]]))
    return result


def object_graphics_check(d):
    height=d.rom_constant('game_sprite_height',8)
    offset=128 if d.rom_constant('world_lookup_format',0)==3 else 0
    for index,base in enumerate((248-offset,252-offset)):
        raw=bytes(d.p.memory[1,0x8000+base*16:0x8040+base*16])
        tiles=[tile_pixels(raw[i*16:(i+1)*16])for i in range(4)]
        image=(np.block([[tiles[0],tiles[2]],[tiles[1],tiles[3]]]) if height==16
               else np.block([[tiles[0],tiles[1]],[tiles[2],tiles[3]]]))
        assert np.array_equal(image,d.original_object_pixels[index]),'sprite backend changed original apple/flower pixels'
    address=d.symbols['_killer_tiles'];expected=d.rom_far((address>>16,address&65535),64)
    start=0x8fc0-offset*16
    raw=bytes(d.p.memory[0,start:start+64]);tiles=[tile_pixels(raw[i*16:(i+1)*16])for i in range(4)]
    actual=(np.block([[tiles[0],tiles[2]],[tiles[1],tiles[3]]])if height==16
            else np.block([[tiles[0],tiles[1]],[tiles[2],tiles[3]]]))
    tiles=[tile_pixels(expected[i*16:(i+1)*16])for i in range(4)]
    assert np.array_equal(actual,np.block([[tiles[0],tiles[1]],[tiles[2],tiles[3]]])),'killer sprite pixels changed or background cache overwrote them'


class HeadVerifier:
    """Observe actual head publications without changing registers or memory."""
    def __init__(self,d):
        self.d=d;self.stack=[];self.returns=set();self.counts=Counter()
        self.height=d.rom_constant('game_sprite_height',8)
        self.index=d.rom_constant('game_head_oam_index',24)
        self.frame_bytes=self.height*2
        self.tiles=(216,218)if self.height==16 else(216,245)
        if d.rom_constant('world_lookup_format',0)==3:
            self.tiles=tuple(tile-128 for tile in self.tiles)
        address=d.symbols['_riding_heads'];bank,offset=address>>16,address&65535
        self.frames=[d.rom_far((bank,offset+i*self.frame_bytes),self.frame_bytes)for i in range(256)]
        for name in ('bike_render_prepare','bike_render_draw'):
            address=d.symbols['_'+name]
            d.p.hook_register(address>>16,address&65535,self.observe(self.enter),name)

    def observe(self,callback):
        def checked(context):
            try:callback(context)
            except BaseException as error:self.d.observer_errors.append(error)
        return checked

    def hardware(self):
        d=self.d
        if not d.byte('game_ready') or d.byte('game_state')in(MENU,PAUSED) or d.p.memory[0xff40]&0x82!=0x82:return None
        assert bool(d.p.memory[0xff40]&4)==(self.height==16),'hardware sprite size differs from active renderer'
        address=0xfe00+self.index*4
        oam=bytes(d.p.memory[address:address+4])
        if not oam[0] or not oam[1]:return None
        assert oam[2]in self.tiles and oam[3]==12,'head must occupy one dedicated palette4 sprite'
        start=0x8000+oam[2]*16
        pattern=bytes(d.p.memory[1,start:start+self.frame_bytes])
        assert pattern in self.frames,'hardware head references a corrupt/partial pattern'
        return oam,pattern

    def expected(self):
        d=self.d;a=d.symbols['_gbc_bike'];raw=bytes(d.p.memory[a:a+52])
        angle=(struct.unpack_from('<H',raw,8)[0]+1024)>>11&31
        x,y=struct.unpack_from('<ii',raw,40)
        phase=((x*12&65535)>>15)|(((-y*12&65535)>>15)<<1)
        frame=(((32 if raw[51] else 0)+angle)<<2)|phase
        world=d.symbols['_game_world'];ox,oy=struct.unpack('<ii',bytes(d.p.memory[world+4:world+12]))
        sx=(x-ox)*12//65536-d.word('game_camera_x')-4
        sy=(oy-y)*12//65536-d.word('game_camera_y')-4
        position=(0,0) if sx< -7 or sx>=160 or sy<1-self.height or sy>=136 else (sy+16,sx+8)
        return self.frames[frame],position

    def enter(self,name):
        d=self.d;sp=d.p.register_file.SP
        address=d.p.memory[sp]|d.p.memory[sp+1]<<8
        bank=0 if address<0x4000 else d.p.memory[d.symbols['__current_bank']]
        key=(bank,address)
        if key not in self.returns:
            d.p.hook_register(bank,address,self.observe(self.returned),key);self.returns.add(key)
        self.stack.append((key,sp,name,self.hardware(),self.expected()if name=='bike_render_draw'else None))

    def returned(self,key):
        d=self.d
        if not self.stack or self.stack[-1][0]!=key or d.p.register_file.SP!=self.stack[-1][1]+2:return
        _,_,name,before,expected=self.stack.pop();self.counts[name]+=1
        after=self.hardware()
        if name=='bike_render_prepare' and before and after and before[0]==after[0]:
            assert before[1]==after[1],'head texture changed while hardware still displayed the old pose'
            self.counts['old_hardware_patterns_preserved']+=1
            shadow=d.symbols['_shadow_OAM']+self.index*4
            if d.p.memory[shadow+2]!=after[0][2]:self.counts['double_buffer_publications']+=1
        if name=='bike_render_draw' and d.byte('game_ready') and d.byte('game_state')not in(MENU,PAUSED):
            shadow=d.symbols['_shadow_OAM']+self.index*4;oam=bytes(d.p.memory[shadow:shadow+4])
            assert (oam[0],oam[1])==expected[1],('head shadow pose differs',oam,expected[1])
            start=0x8000+oam[2]*16
            assert bytes(d.p.memory[1,start:start+self.frame_bytes])==expected[0],'head pattern/half-pixel phase does not match its published pose'
            self.counts['source_pose_phase_matches']+=1


_font_pixels={}


def font_pixels(text):
    # Read the source bitmap independently of the converter's generated header.
    if not _font_pixels:
        source=BASE/'fonts/CG-pixel-3x5-mono.bdf'
        for block in source.read_text().split('STARTCHAR ')[1:]:
            lines=block.splitlines()
            code=int(next(line.split()[1]for line in lines if line.startswith('ENCODING ')))
            if not 32<=code<=95:continue
            w,h,x,y=map(int,next(line for line in lines if line.startswith('BBX ')).split()[1:])
            bitmap=np.zeros((8,4),dtype=np.uint8);start=lines.index('BITMAP')+1
            for row,raw in enumerate(lines[start:start+h]):
                bits=bin(int(raw,16))[2:].zfill(len(raw)*4)
                for col in range(w):bitmap[6-h-y+row,x+col]=int(bits[col])
            _font_pixels[chr(code)]=bitmap
    return np.concatenate([_font_pixels[c]for c in text.upper()],axis=1)


def ui_pixels(d,x,y,characters,window=False):
    lcd=d.p.memory[0xff40]
    if not window:assert lcd&16,'menu must use unsigned tile addresses'
    base=(0x9c00 if lcd&64 else 0x9800)if window else(0x9c00 if lcd&8 else 0x9800)
    result=[]
    for col in range((characters+1)//2):
        address=base+y*32+x+col
        tile,attr=d.p.memory[0,address],d.p.memory[1,address]
        start=bg_tile_address(tile,lcd)
        raw=bytes(d.p.memory[1 if attr&8 else 0,start:start+16])
        pixels=tile_pixels(raw)
        if attr&32:pixels=pixels[:,::-1]
        if attr&64:pixels=pixels[::-1]
        assert set(np.unique(pixels))<={1,3},'UI contains blended font pixels'
        result.append((pixels==3).astype(np.uint8))
    return np.concatenate(result,axis=1)[:,:characters*4]


def menu_check(d,selected,names):
    assert d.byte('game_state') in (MENU,PAUSED),'level menu is not active'
    assert not d.p.memory[0xff40]&0x22,'menu must hide sprites and window'
    if '_menu_screen'in d.symbols:assert d.byte('menu_screen')==1,'expected the course list'
    heading='LEVEL %02d/54 '%(selected+1)
    assert np.array_equal(ui_pixels(d,7,2,12),font_pixels(heading)),('menu heading',selected)
    first=(selected//9)*9
    for row in range(9):
        address=0x9800+(4+row)*32
        expected=names[first+row].upper().ljust(18)
        assert np.array_equal(ui_pixels(d,2,4+row,18),font_pixels(expected)),('menu name',first+row,expected)
        assert d.p.memory[0,address]==(240 if first+row==selected else 241),'menu cursor'
    return 9


def world_check(d,index,record,physics):
    assert d.level_index()==index,'menu selected a different course'
    assert d.byte('physics_level_index')==index,'rendered and physical courses differ'
    for name,expected in zip(('start_x','start_y'),physics['start_q16']):
        address=d.symbols['_physics_level_'+name]
        assert int.from_bytes(bytes(d.p.memory[address:address+4]),'little',signed=True)==expected,'wrong physical spawn descriptor'
    address=d.symbols['_game_world'];raw=bytes(d.p.memory[address:address+33])
    width,height,ox,oy,count=struct.unpack_from('<HHiiH',raw)
    assert [width,height]==record['size_px']
    assert [ox,oy]==[n*65536 for n in record['origin_m']]
    assert count==record['pattern_count']
    for n,name in enumerate(('patterns','chunk_directory','palette','objects_pointer')):
        assert list(struct.unpack_from('<HH',raw,14+n*4))==record[name],('far pointer',index,name)
    assert list(raw[30:])==[width//256,height//128,len(record['objects'])]
    address=d.symbols['_game_objects']
    objects=[list(struct.unpack_from('<HHBiiB',bytes(d.p.memory[address+i*14:address+(i+1)*14])))for i in range(len(record['objects']))]
    assert objects==record['objects'],'runtime lost or changed original object/gravity metadata'
    active_address=d.symbols['_game_object_active']
    active=list(d.p.memory[active_address:active_address+len(objects)])
    assert all(n in(0,1)for n in active)
    assert d.byte('game_apples_left')==sum(o[2]==2 and flag for o,flag in zip(objects,active))
    bike=d.bike();sx,sy=(n/65536 for n in physics['start_q16'])
    assert abs(bike['wheel0']['x']-sx)<.6 and abs(bike['wheel0']['y']-sy)<.6,('spawn',index,bike['wheel0'],[sx,sy])
    d.physical_bounds(bike);d.visible_vram(force=True);object_graphics_check(d)
    return {'objects':len(objects),'apples':sum(o[2]==2 for o in objects),'killers':sum(o[2]==3 for o in objects),'gravity_objects':sum(bool(o[5])for o in objects),'start_state':d.byte('game_state')}


def palette_check(d,source):
    # Read the completed frame and its per-scanline scroll registers. Mask the
    # union of neighboring actual OAM states so sprite cycling is not mistaken
    # for a wrong background palette. No guest registers are written.
    oam=[]
    for _ in range(3):
        oam.append(bytes(d.p.memory[0xfe00:0xfea0]));d.tick()
    oam.append(bytes(d.p.memory[0xfe00:0xfea0]))
    pixels=np.asarray(d.p.screen.image.convert('RGB'))
    expected=np.empty_like(pixels[:136]);mask=np.ones((136,160),dtype=bool)
    preview=np.asarray(Image.open(d.gen/'levels'/('%02d'%(d.level_index()+1))/'preview.png').convert('RGB'))
    cx,cy=d.word('game_camera_x'),d.word('game_camera_y')
    for y,(sx,sy,_,_)in enumerate(d.p.screen.tilemap_position_list[:136]):
        x=(cx&~255)+sx;top=(cy&~255)+sy
        if x-cx>128:x-=256
        elif cx-x>128:x+=256
        if top-cy>128:top-=256
        elif cy-top>128:top+=256
        if x<0 or top+y<0 or x+160>preview.shape[1] or top+y>=preview.shape[0]:
            mask[y]=False;expected[y]=0
        else:expected[y]=preview[top+y,x:x+160]
    for state in oam:
        height=16 if d.p.memory[0xff40]&4 else 8
        for i in range(40):
            y,x,_,_=state[i*4:i*4+4]
            if not y or not x:continue
            x-=8;y-=16
            mask[max(0,y-10):min(136,y+height+10),max(0,x-10):min(160,x+18)]=False
    count=int(mask.sum());matches=int((np.all(pixels[:136]==expected,axis=2)&mask).sum())
    assert count>100,'insufficient unobstructed background pixels'
    ratio=matches/count
    assert ratio>=.995,('displayed background palette/pixels differ from generated preview',d.level_index(),ratio,count)
    record=source['record'];sky=source['sky']
    if record['blue_sky']:
        allowed={tuple(c)for c in record['sky_colors_rgb']}
        assert all(tuple(c)in allowed for c in np.unique(preview[sky],axis=0)),'sky uses colors absent from original sky texture'
    return {'unobstructed_pixels':count,'exact_matches':matches,'match_fraction':ratio,'source_sky_policy_verified':bool(record['blue_sky'])}


def hud_count_check(d,record):
    if d.byte('game_state')!=RIDING:return None
    if d.rom_constant('game_hud_font_advance',8)==4:
        actual=ui_pixels(d,0,0,4,window=True)
        matches=[n for n in range(100)if np.array_equal(actual,font_pixels('A:%02d'%n))]
        assert len(matches)==1,'HUD apple count must be readable in native3x5 pixels'
        count=matches[0]
        initial=sum(o[2]==2 for o in record['objects'])
        assert count in(initial,d.byte('game_apples_left')),'HUD lost a two-digit apple count'
        return count
    font=220 if d.rom_constant('game_sprite_height',8)==16 else 217
    base=0x9c00 if d.p.memory[0xff40]&64 else 0x9800
    assert d.p.memory[0,base]==font+13 and d.p.memory[0,base+1]==font+11,'riding HUD prefix'
    tens,units=d.p.memory[0,base+2],d.p.memory[0,base+3]
    assert tens==font or font+1<=tens<=font+10,'apple tens must use a digit or blank'
    assert font+1<=units<=font+10,'apple units must use a digit'
    count=(0 if tens==font else tens-font-1)*10+units-font-1
    initial=sum(o[2]==2 for o in record['objects'])
    assert count in(initial,d.byte('game_apples_left')),'HUD lost a two-digit apple count'
    return count


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom',type=Path,default=BASE/'build/elma-gbc.gbc')
    parser.add_argument('--gen',type=Path,default=BASE/'build/gen')
    parser.add_argument('--out',type=Path,default=BASE/'build/playtest/all-levels')
    parser.add_argument('--max-overruns',type=int,default=0)
    parser.add_argument('--idle-updates',type=int,default=0,
                        help='additional no-input controller updates per course, until death/finish')
    args=parser.parse_args();d=Driver(args.rom,args.out,args.gen);head=HeadVerifier(d)
    assert args.idle_updates>=0
    manifest=d.level_manifest;assert manifest and manifest['count']==54
    physics=json.loads((args.gen/'physics_bank_manifest.json').read_text())['levels']
    for path,digest in manifest['source_sha256'].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,'original build resource changed'
    resource=next(Path(path)for path in manifest['source_sha256']if Path(path).suffix.lower()=='.res')
    lgr_path=next(Path(path)for path in manifest['source_sha256']if Path(path).suffix.lower()=='.lgr')
    sys.path.insert(0,str(BASE/'tools'));import assets
    assets.OUT=args.out/'source-objects';assets.OUT.mkdir(exist_ok=True)
    object_data,object_palette=assets.object_data(assets.lgr_reader.Lgr(lgr_path))
    d.original_object_pixels=original_object_pixels(object_data)
    address=d.symbols['_object_palette']
    assert d.rom_far((address>>16,address&65535),16)==struct.pack('<8H',*object_palette),'protected red apple/white flower palettes changed'
    originals=elmadata.internal_levels(elmadata.Resource(resource))
    assert len(originals)==54
    for original,record,body in zip(originals,manifest['levels'],physics):
        assert original.name==record['name']==body['name'],'original level order/name was changed'
        points=[p for _,poly in original.polygons for p in poly];xs,ys=zip(*points)
        ox,oy=math.floor(min(xs)-4),math.ceil(max(ys)+4)
        width=math.ceil((max(xs)+4-ox)*12/256)*256
        height=math.ceil((oy-min(ys)+4)*12/128)*128
        assert record['origin_m']==[ox,oy] and record['size_px']==[width,height],'course silently changed original12PPM scale/extents'
        expected=[[round((x-ox)*12),round((oy-y)*12),kind,round(x*65536),round(y*65536),gravity]
                  for kind,x,y,gravity,_ in original.objects if kind in(1,2,3)]
        assert record['objects']==expected,'original apple/flower/killer/gravity data was lost'
        assert body['start_q16']==[round(v*65536)for v in original.start()]
        assert body['original_edges']==sum(len(poly)for grass,poly in original.polygons if not grass)
    names=[r['name']for r in manifest['levels']];results=[];menu_rows=0
    report={'status':'running','rom_sha256':d.rom_sha256,'hardware_tested':False}
    try:
        d.ready();assert d.byte('game_state')==MENU;d.level_menu();menu_rows+=menu_check(d,0,names)
        d.snapshot('menu-first');d.pulse('up');menu_rows+=menu_check(d,53,names);d.snapshot('menu-last')
        d.pulse('down');menu_rows+=menu_check(d,0,names)
        for index,record in enumerate(manifest['levels']):
            if index:
                d.level_menu();assert d.byte('game_state')in(MENU,PAUSED)
                d.pulse('down');menu_rows+=menu_check(d,index,names)
            d.phase='all-levels';d.pulse('a');d.ready()
            source=d.level_source(index);details=world_check(d,index,record,physics[index])
            details.update({'index':index,'name':record['name'],'palette':palette_check(d,source),
                            'hud_apple_count':hud_count_check(d,record),'overruns':d.word('game_overruns')})
            if index==0:
                d.advance_physics(30);d.level_menu();assert d.byte('game_state')==PAUSED
                frozen=(d.time_frames(),d.bike(),d.word('game_steps'))
                d.tick(20);assert frozen==(d.time_frames(),d.bike(),d.word('game_steps'))
                d.pulse('down');menu_rows+=menu_check(d,1,names)
                d.pulse('b')
                if '_menu_screen'in d.symbols:d.pulse('b')
                assert d.byte('game_state')==RIDING and d.level_index()==0
                assert d.time_frames()>=frozen[0],'menu resume reset the race timer'
                d.visible_vram(force=True);palette_check(d,source)
            idle_steps=d.word('game_steps')
            for _ in range(args.idle_updates):
                if d.byte('game_state')!=RIDING:break
                d.step()
            details.update({'additional_idle_physics_steps':(d.word('game_steps')-idle_steps)&65535,
                            'overruns':d.word('game_overruns')})
            d.snapshot('level-%02d'%(index+1));results.append(details)
            print('%02d %-18s state%d objects%d cache%d'% (index+1,record['name'],d.byte('game_state'),details['objects'],d.word('world_cache_failures')),flush=True)
        d.level_menu();d.pulse('down');menu_rows+=menu_check(d,0,names)
        d.pulse('up');menu_rows+=menu_check(d,53,names)
        d.pulse('left');menu_rows+=menu_check(d,44,names)
        d.pulse('right');menu_rows+=menu_check(d,53,names)
        overruns=d.word('game_overruns')
        report={'status':'passed','rom_sha256':d.rom_sha256,'real_rom':str(args.rom.resolve()),
            'levels_started':len(results),'menu_name_rows_checked':menu_rows,'all_levels_completed':False,
            'idle_controller_updates_per_level':args.idle_updates,
            'functional_checks_passed':True,'display_overruns':overruns,'performance_requirement_met':overruns==0,
            'deadline_budget_relaxed_for_diagnostics':args.max_overruns!=0,'levels':results,**d.timing(),'hardware_tested':False}
        report['head_publication_checks']=dict(head.counts)
        assert head.counts['double_buffer_publications']>0,'test did not exercise a visible head pattern publication'
        assert overruns<=args.max_overruns,'display deadline misses:%d'%overruns
    except BaseException as error:
        d.snapshot('failure');report.update({'status':'failed','error':str(error),'levels_started':len(results),'levels':results,
            'active_level':d.level_index(),'game_state':d.byte('game_state'),'head_publication_checks':dict(head.counts),
            'display_overruns':d.word('game_overruns'),**d.timing()});raise
    finally:
        (args.out/'run.json').write_text(json.dumps(report,indent=2)+'\n');d.close()
    print(json.dumps({k:v for k,v in report.items()if k not in('levels','viewport_tile_positions')},indent=2))


if __name__=='__main__':main()
