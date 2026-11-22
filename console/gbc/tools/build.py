"""Incremental native-ROM build; cache independent objects, never game assets."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess

BASE=Path(__file__).resolve().parents[1]


def scheduled_profile(gen):
    return bool(re.search(r'^#define RIDING_PC_SCHEDULE 1$',
                         (gen/'riding_constants.h').read_text(),re.M))


def validate_linked_layout(symbol_path,rom_mib):
    """Include library/startup areas when checking the physical ROM windows."""
    symbols={name:int(value,16) for name,value in
             re.findall(r'^DEF (\S+) 0x([0-9A-Fa-f]+)$',symbol_path.read_text(),re.M)}
    fixed_end=0
    for area in ('_CODE','_HOME','_INITIALIZER','_GSINIT','_GSFINAL'):
        if 's_'+area not in symbols or 'l_'+area not in symbols:
            raise ValueError('Missing linked ROM area: '+area)
        start,size=symbols['s_'+area],symbols['l_'+area]
        if start+size>0x4000:
            raise ValueError(f'ROM0 overflow: {area} ends at 0x{start+size:04x}, beyond 0x4000')
        fixed_end=max(fixed_end,start+size)
    for name,start in symbols.items():
        match=re.fullmatch(r's__CODE_(\d+)',name)
        if not match:continue
        bank=int(match[1]);size=symbols.get('l'+name[1:])
        if size is None:raise ValueError('Missing linked ROM area size: '+name)
        if not size:continue
        address=start&65535
        if bank==0:
            if start+size>0x4000:raise ValueError('ROM0 overflow in _CODE_0')
            fixed_end=max(fixed_end,start+size)
        elif bank>=rom_mib*64 or start>>16!=bank or address<0x4000 or address+size>0x8000:
            raise ValueError(f'ROM bank {bank} exceeds its linked address window')
    return {'rom0_end':fixed_end,'rom0_free_bytes':0x4000-fixed_end}


def dependencies(path,gen,seen=None):
    seen=set() if seen is None else seen
    path=path.resolve()
    if path in seen:return b''
    seen.add(path)
    data=path.read_bytes();result=str(path).encode()+b'\0'+data
    for name in re.findall(rb'^\s*#\s*include\s*"([^"]+)"',data,re.M):
        for directory in (path.parent,gen,BASE/'src'):
            candidate=directory/name.decode()
            if candidate.is_file():
                result+=dependencies(candidate,gen,seen);break
    return result


def validate_profile(gen, requested_rom_mib=None, sources=()):
    """Reject mixed codecs, stale table banks and out-of-range bank layouts."""
    levels=json.loads((gen/'level_manifest.json').read_text())
    physics=json.loads((gen/'physics_bank_manifest.json').read_text())
    if physics.get('segment_format') != 'length14-internal-endpoints-v1':
        raise ValueError('Collision data lacks artificial endpoint flags; regenerate physics levels')
    scheduled=scheduled_profile(gen)
    coefficient_manifest='physics_q24_manifest.json' if scheduled else 'physics-coefficient-manifest.json'
    coefficients=json.loads((gen/coefficient_manifest).read_text())
    codecs={'zx0-planes32x16':(4,'zx0-512'), 'raw3-plane32x16':(8,'raw-2bpp')}
    if levels.get('map_codec') not in codecs:
        raise ValueError('Unknown level graphics codec: '+str(levels.get('map_codec')))
    rom_mib,pattern_codec=codecs[levels['map_codec']]
    if requested_rom_mib is not None and requested_rom_mib!=rom_mib:
        raise ValueError('%d MiB profile requires %s graphics; %s contains %s'%
                         (requested_rom_mib,'compressed'if requested_rom_mib==4 else'raw',gen,levels['map_codec']))
    if levels.get('rom_mib',rom_mib)!=rom_mib or levels.get('pattern_codec',pattern_codec)!=pattern_codec:
        raise ValueError('Level manifest has inconsistent ROM size or pattern codec')
    header=(gen/'level_catalogue.h').read_text()
    for name,value in (('WORLD_GRAPHICS_ZX0',1),('WORLD_PATTERN_BLOCK_BYTES',512),('WORLD_MAP_PLANE_BYTES',512),('WORLD_ZX0_COST_PREFIX',1)):
        definitions=re.findall(r'^[ \t]*#[ \t]*define[ \t]+'+name+r'\b([^\n]*)$',header,re.M)
        expected=[str(value)] if rom_mib==4 else []
        if [definition.strip()for definition in definitions]!=expected:
            raise ValueError('Level catalogue header and manifest disagree about '+name)
    if rom_mib==4 and (not levels.get('compression_key') or levels.get('pattern_block_bytes')!=512
                      or levels.get('map_plane_bytes')!=512 or levels.get('pattern_codec')!=pattern_codec
                      or levels.get('decode_cost_prefix_bytes')!=1):
        raise ValueError('Compressed graphics are missing their 512-byte block metadata')
    if rom_mib==8 and any(key in levels for key in ('compression_key','pattern_block_bytes','map_plane_bytes','decode_cost_prefix_bytes','decoder_sha256')):
        raise ValueError('Raw graphics retain stale compression metadata')
    if rom_mib==4:
        from zx0_cost import validate_decoder
        if levels.get('decoder_sha256')!=validate_decoder(BASE/'src/world_zx0.s'):
            raise ValueError('Compressed decode costs do not match the native decoder')
        def pointer(value,length=1):
            return (isinstance(value,(list,tuple)) and len(value)==2
                    and all(type(part)is int for part in value)
                    and levels['first_bank']<=value[0]<=levels['last_bank']
                    and 0x4000<=value[1] and value[1]+length<=0x8000)
        if len(levels['levels'])!=levels['count']:
            raise ValueError('Compressed level count differs from its catalogue')
        for record in levels['levels']:
            blocks=record.get('pattern_blocks',[]);chunks=record.get('chunks',[])
            width,height=record['size_px']
            if (width%256 or height%128 or len(blocks)!=(record['pattern_count']+31)//32
                    or not blocks or not all(pointer(block)for block in blocks)
                    or not pointer(record.get('patterns'),len(blocks)*4)):
                raise ValueError('Invalid compressed pattern directory for level %d'%(record['index']+1))
            if (len(chunks)!=(width//256)*(height//128) or not chunks
                    or not all(isinstance(chunk,(list,tuple)) and len(chunk)==3
                               and all(pointer(plane)for plane in chunk)for chunk in chunks)
                    or not pointer(record.get('chunk_directory'),len(chunks)*12)):
                raise ValueError('Invalid three-plane map directory for level %d'%(record['index']+1))
    bank_count=rom_mib*64
    coefficient_first=481 if scheduled else {4:252,8:477}[rom_mib]
    coefficient_last=coefficients['last_bank'] if scheduled else coefficient_first+3
    if scheduled and (rom_mib!=8 or not coefficient_first<=coefficient_last<508):
        raise ValueError('Scheduled Q24 physics requires the 8 MiB profile, below bank 508')
    if scheduled and coefficients.get('kind')!='q24-table-v3':
        raise ValueError('Unsupported scheduled coefficient table format')
    if (coefficients['first_bank'],coefficients['last_bank'])!=(coefficient_first,coefficient_last):
        raise ValueError('%d MiB profile reserves coefficient banks %d..%d'%
                         (rom_mib,coefficient_first,coefficient_last))
    if coefficients['constants_sha256']!=hashlib.sha256((gen/'riding_constants.h').read_bytes()).hexdigest():
        raise ValueError('Coefficient tables do not match the generated riding constants')
    if scheduled:
        rider_rows = gen / 'physics_rider_rows.c'
        if not rider_rows.is_file() or hashlib.sha256(rider_rows.read_bytes()).hexdigest() != coefficients.get('rider_rows_sha256'):
            raise ValueError('Regenerate the signed rider coefficient tables for these physics constants')
        for name in ('physics_pose_rows.h', 'physics_angle_rows.h'):
            path = gen / name
            if not path.is_file() or coefficients.get('geometry_sha256', {}).get(name) != hashlib.sha256(path.read_bytes()).hexdigest():
                raise ValueError(f'Missing or stale {name}. Regenerate scheduled physics coefficient tables.')
    if not scheduled:
        calls=(gen/'physics_coefficient_calls.s').read_text()
        if '_riding_coeff32_C_LANDING_EXTRA::' not in calls:
            raise ValueError('Missing supported damping coefficient; regenerate riding constants and coefficient tables')
        if '_riding_landing_fric_residue::' not in calls:
            raise ValueError('Missing landing residue table; regenerate the coefficient tables')
        for name,value in (('lo',coefficient_first&255),('hi',coefficient_first>>8)):
            if not re.search(r'^_riding_coefficient_bank_'+name+r'\s*=\s*'+str(value)+r'\s*$',calls,re.M):
                raise ValueError('Coefficient bank selection differs from its tables; regenerate the coefficients')
    intervals={
        'physics_bank_':(physics['first_bank'],physics['next_free_bank']-1),
        'level_bank_':(levels['first_bank'],levels['last_bank']),
        ('physics_q24_table_' if scheduled else 'physics_coefficient_'):
            (coefficients['first_bank'],coefficients['last_bank']),
    }
    previous_end=-1
    for prefix,(first,last) in intervals.items():
        if not 0<first<=last<bank_count or first<=previous_end:
            raise ValueError('Overlapping or out-of-range ROM bank reservation: %s%d..%d'%(prefix,first,last))
        previous_end=last
        expected={gen/('%s%d.c'%(prefix,bank))for bank in range(first,last+1)}
        actual=set(gen.glob(prefix+'*.c'))
        if expected!=actual:
            raise ValueError('Missing or stale generated bank files for '+prefix)
        for path in expected:
            bank=int(path.stem.rsplit('_',1)[1])
            match=re.search(r'^#pragma bank (\d+)\s*$',path.read_text(),re.M)
            if not match or int(match[1])!=bank:
                raise ValueError('Generated source bank differs from its filename: '+str(path))
    for path in sources:
        for match in re.finditer(r'^\s*#pragma bank (\d+)\s*$',path.read_text(),re.M):
            bank=int(match[1])
            if not 0<=bank<bank_count:
                raise ValueError('Source exceeds the selected ROM size: '+str(path))
            if rom_mib==8 and bank>=508:
                raise ValueError('The 8 MiB cartridge profile leaves banks 508..511 unused: '+str(path))
            for prefix,(first,last) in intervals.items():
                if first<=bank<=last and path!=gen/('%s%d.c'%(prefix,bank)):
                    raise ValueError('Source overlaps reserved ROM bank %d: %s'%(bank,path))
    return rom_mib


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sdk',type=Path,default=BASE/'.toolchain/gbdk')
    p.add_argument('--gen',type=Path,help='generated directory (default: build/gen-8m; build/gen with --rom-mib 4)')
    p.add_argument('--out',type=Path,help='output ROM (default: build/elma-gbc-vVERSION-4m.gbc or -8m.gbc)')
    p.add_argument('--jobs',type=int,default=4)
    p.add_argument('--rom-mib',type=int,choices=(4,8),help='validate the profile; otherwise infer it from the graphics manifest')
    p.add_argument('--sweep-source',type=Path,help='isolated exact head-collision candidate')
    p.add_argument('--collision-source',type=Path,help='isolated exact collision-cache candidate')
    a=p.parse_args();a.sdk=a.sdk.resolve()
    a.gen=(a.gen or BASE/('build/gen' if a.rom_mib==4 else 'build/gen-8m')).resolve()
    rom_mib=validate_profile(a.gen,a.rom_mib)
    scheduled=scheduled_profile(a.gen)
    if not scheduled:
        raise ValueError('Current riding sources require scheduled physics; regenerate assets with --hz 30 --damper scheduled')
    version=(BASE/'VERSION').read_text().strip()
    if not re.fullmatch(r'\d+(?:\.\d+)+',version):raise ValueError('Invalid VERSION for the ROM filename')
    a.out=(a.out or BASE/'build'/('elma-gbc-v%s-%dm.gbc'%(version,rom_mib))).resolve()
    a.out.parent.mkdir(parents=True,exist_ok=True)
    compiler=a.sdk/'bin/lcc'
    compile_flags=['-msm83:gb','-Wf--opt-code-size','-Wf--max-allocs-per-node','-Wf100000',
                   '-I'+str(a.gen),'-I'+str(BASE/'src')]
    link_flags=['-msm83:gb','-Wm-yC','-Wm-yt0x1B','-Wm-ya4','-Wm-yo%d'%(rom_mib*64),'-Wm-ynELMA-GBC','-Wl-m','-Wl-j']
    names=['play.c','splash.c','audio.c','save.c','world.c','world_dma.c','world_zx0.s','world_memory.s','world_retire_fast.s','world_alloc_fast.s','world_acquire_fast.s','world_upload_raw.s','menu.c','result.c','bike_render16.c','physics.c','physics_core.c',
           'physics_contacts.c','physics_collision.c','physics_sweep.c','physics_math.c','physics_math32.c','mul16.s','video.s','video_screen_fast.s','video_strip_pair.s','object16.s','objects_touch_fast.s','objects_draw_fast.s','objects_bounds_fast.s','objects_visible_fast.s']
    sources=[BASE/'src'/name for name in names]
    sources.append(BASE/'src'/('world_lookup_raw.s' if rom_mib==8 else 'world_lookup_linked.s'))
    if rom_mib==4:
        sources=[path for path in sources if path.name!='world_upload_raw.s']
    if a.sweep_source:
        sources=[a.sweep_source.resolve() if path.name=='physics_sweep.c' else path for path in sources]
    if a.collision_source:
        sources=[a.collision_source.resolve() if path.name=='physics_collision.c' else path for path in sources]
    if scheduled:
        sources += [BASE/'src'/name for name in ('physics_q24.c','physics_force.c','physics_q24.s',
            'physics_mul_fast.s','physics_mul16u8.s','physics_math32_bounds.s','physics_math32_exact.s',
            'physics_math.s','physics_contact_loop.s','physics_segment_scan.s',
            'physics_normal_fast.s','physics_shift_fast.s','physics_sqrt_fast.s',
            'physics_div_fast.s','physics_sin_fast.s','physics_spring_torque.s',
            'physics_div20.s','physics_export_fast.s','physics_bounds.s',
            'physics_rider_fast.s','physics_rider_response.s','physics_phase.s','physics_circle_scheduled.s',
            'physics_supports_fast.s','physics_free_fast.s','physics_roll_fast.s','physics_wheel_bridge.c',
            'physics_angle.c','physics_body_angle.s','physics_geometry.c','physics_pose_lookup.s','physics_head_pose.s','physics_brake_fast.s',
            'physics_suspension_scheduled.s','physics_step_scheduled.s','physics_level_bounds.s','physics_recip_fast.s','physics_contact_filter.s','physics_reaction_division.s')]
        sources.extend((BASE/'src/physics_rider_coeff.s', a.gen/'physics_rider_rows.c', a.gen/'physics_q24_dispatch.c'))
    else:
        sources += sorted(x for x in (BASE/'src').glob('physics_*.s')if x.name!='physics_mul16.s' and not x.name.startswith('physics_q24'))
    for pattern in ('physics_quarter_*.c','physics_scale_*.c','physics_sine_*.c',
                    'physics_q24_table_*.c' if scheduled else 'physics_coefficient_*.c',
                    'physics_bank_*.c','level_bank_*.c','riding16_body_*.c'):
        sources+=sorted(a.gen.glob(pattern))
    if not scheduled:sources.append(a.gen/'physics_coefficient_calls.s')
    sources += [a.gen/name for name in ('level_catalogue.c','menu_assets.c','splash_assets.c','physics_level_data.c','riding16_parts.c','riding_meta.c')]
    validate_profile(a.gen,rom_mib,sources)
    cache=BASE/'build/objects';cache.mkdir(parents=True,exist_ok=True)
    tool_key=[]
    for name in ('lcc','sdcc','sdasgb','sdldgb'):
        path=a.sdk/'bin'/name
        if path.exists():
            stat=path.stat();tool_key.append((str(path),stat.st_size,stat.st_mtime_ns))
    configuration=json.dumps([compile_flags,tool_key]).encode()
    def coefficient_lookup(path):
        return not scheduled and ((path.parent==BASE/'src' and path.suffix=='.c' and path.name.startswith('physics')) or any(candidate is not None and path==candidate.resolve()for candidate in(a.sweep_source,a.collision_source)))
    def source_key(path):
        extra=b' -DRIDING_COEFFICIENT_LOOKUP' if coefficient_lookup(path) else b''
        return hashlib.sha256(configuration+extra+dependencies(path,a.gen)).hexdigest()
    objects=[];keys=[];pending=[]
    for path in sources:
        key=source_key(path)
        obj=cache/(path.stem+'-'+key[:24]+'.o');objects.append(obj);keys.append(key)
        if not obj.is_file():pending.append((path,obj,key))
    def compile_one(item):
        path,obj,key=item
        extra=['-DRIDING_COEFFICIENT_LOOKUP'] if coefficient_lookup(path) else []
        result=subprocess.run([str(compiler),*compile_flags,*extra,'-c','-o',str(obj),str(path)],capture_output=True,text=True)
        if result.returncode:
            obj.unlink(missing_ok=True)
            raise RuntimeError(str(path)+'\n'+result.stdout+result.stderr)
        if source_key(path)!=key:
            obj.unlink(missing_ok=True)
            raise RuntimeError('Source changed while compiling: '+str(path)+'; rerun the build after edits finish')
        if result.stdout.strip() or result.stderr.strip():print(result.stdout+result.stderr,flush=True)
    print('Objects: %d cached, %d compiling'%(len(objects)-len(pending),len(pending)),flush=True)
    with ThreadPoolExecutor(max_workers=max(1,a.jobs))as pool:
        for _ in pool.map(compile_one,pending):pass
    for path,key in zip(sources,keys):
        if source_key(path)!=key:
            raise RuntimeError('Source changed during the build: '+str(path)+'; rerun after edits finish')
    validate_profile(a.gen,rom_mib,sources)
    manifest_path=a.out.with_suffix('.build.json')
    build_key=hashlib.sha256(json.dumps([keys,link_flags,tool_key]).encode()).hexdigest()
    if manifest_path.is_file() and a.out.is_file() and a.out.with_suffix('.noi').is_file():
        previous=json.loads(manifest_path.read_text())
        if previous.get('build_key')==build_key and previous.get('rom_sha256')==hashlib.sha256(a.out.read_bytes()).hexdigest():
            layout=validate_linked_layout(a.out.with_suffix('.noi'),rom_mib)
            if previous.get('linked_layout')!=layout:
                previous['linked_layout']=layout
                manifest_path.write_text(json.dumps(previous,indent=2)+'\n')
            print('ROM unchanged: '+str(a.out));return
    subprocess.run([str(compiler),*link_flags,'-o',str(a.out),*map(str,objects)],check=True)
    layout=validate_linked_layout(a.out.with_suffix('.noi'),rom_mib)
    rom=a.out.read_bytes()
    if len(rom)!=rom_mib*1024*1024 or rom[0x147:0x14a]!=bytes((0x1B,{4:7,8:8}[rom_mib],3)):
        raise ValueError('Linked ROM does not match the selected MBC5+RAM+BATTERY / 32 KiB RAM profile')
    if rom_mib==8 and rom[508*16384:]!=bytes([255])*(4*16384):
        raise ValueError('The 8 MiB cartridge profile must leave the last 64 KiB unused')
    report={'rom_mib':rom_mib,'cartridge_type':0x1B,'ram_kib':32,'generated_dir':str(a.gen),'build_key':build_key,'rom_sha256':hashlib.sha256(rom).hexdigest(),
            'sources':[str(x)for x in sources],'objects':[str(x)for x in objects],'linked_layout':layout}
    manifest_path.write_text(json.dumps(report,indent=2)+'\n')
    print('Built '+str(a.out)+' '+report['rom_sha256'])


if __name__=='__main__':main()
