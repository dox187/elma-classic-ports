"""Incremental native-ROM build; cache independent objects, never game assets."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

import bike_frames16
import body_transfers
import bowling_planes
import bumpy_terrain
import brake_dispatch
import corner_bank
import corner_cells
import gravity_strips
import hang_terrain
import head_clearance
import head_refinement
import head_lane_tables
import mul_table
import normal_atlas
import normal_length
import pair_patches
import pose_products
import pixel_font
import phase_tables
import projection_tables
import rolling_tables
import rolling_map_banks
import rider_map_tables
import scenery_pins
import seat_tables
import sqrt_tables
import stopped_pair
import wheel_direct_tiles
import wheel_terrain

BASE=Path(__file__).resolve().parents[1]


def scheduled_profile(gen):
    return bool(re.search(r'^#define RIDING_PC_SCHEDULE 1$',
                         (gen/'riding_constants.h').read_text(),re.M))


def validate_linked_layout(symbol_path,rom_mib):
    """Include library/startup areas when checking the physical ROM windows."""
    symbols={name:int(value,16) for name,value in
             re.findall(r'^DEF (\S+) 0x([0-9A-Fa-f]+)$',symbol_path.read_text(),re.M)}
    if 'screen_fraction_page' in symbols and symbols.get('fraction_pixels') != 0x054000:
        raise ValueError('Screen projection needs its fraction table at the start of bank 5')
    if 's__HRAM' in symbols:
        start = symbols['s__HRAM']
        if start < 0xff80 or start + symbols['l__HRAM'] > 0xffff:
            raise ValueError('Linked HRAM overlaps I/O registers or interrupt enable')
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
    if 'body_angle_pages' in symbols:
        pages = [f'_riding_angle_digit{i}' for i in range(4)]
        pages += [f'_riding_angle_frac{i}' for i in range(3)]
        for name in (*pages, '_riding_oms_product', '_riding_angle_carry'):
            address = symbols[name]
            if address >> 16 != 3 or address & 255:
                raise ValueError(f'{name} requires an aligned lookup page in bank 3')
    if '_torque_C_SPRING_T_0' in symbols:
        for name in ('C_SPRING_T', 'C_FRIC_T'):
            for phase in (0, 1):
                address = symbols[f'_torque_{name}_{phase}']
                if address >> 16 != 1 or address & 255:
                    raise ValueError('Angular torque digit tables require aligned pages in bank 1')
    if '_riding_reaction_coefficient' in symbols:
        bank = rolling_tables.REACTION_WORD_BANK
        start = (bank << 16) + 0x4000
        if (symbols['_riding_reaction_coefficient'] >= 0x4000 or
                symbols.get(f'_level_bank_{bank}') != start or
                symbols.get('_riding_reaction_words') != start or
                symbols.get('_riding_reaction_words_end') != start + 14 * 256):
            raise ValueError('Reaction reader requires fixed ROM and two aligned signed16 tables')
    if '_hang_wheel_select' in symbols:
        if (symbols.get('_physics_bank_87') != 0x574000 or
                symbols['_hang_wheel_select'] >> 16 != hang_terrain.BANK):
            raise ValueError('Hang Tight reader must follow the packed terrain in bank 87')
        if '_hang_query' in symbols and (symbols['_hang_query'] >> 16 != 7 or
                symbols['_riding_sparse_bind'] + 1 + symbols['hang_stub_bytes'] > symbols['_riding_sparse_lookup']):
            raise ValueError('Hang Tight wheel dispatch or query is misplaced')
    if '_bumpy_query' in symbols:
        bank = symbols['bumpy_bank']
        if (symbols['bumpy_tiles'] != (bank << 16)+0x4000+bumpy_terrain.TABLE_OFFSET or
                symbols['bumpy_tiles_end'] - symbols['bumpy_tiles'] != 512 or
                symbols['_bumpy_query'] >> 16 != bank or symbols['_bumpy_wheel_select'] >> 16 != 87 or
                symbols['_riding_sparse_bind']+symbols['bumpy_stub_bytes'] > symbols['_riding_sparse_lookup']):
            raise ValueError('Bumpy Journey wheel dispatch overlaps its rolling directory or WRAM reader')
    if '_bowling_wheel_select' in symbols:
        if (symbols['_physics_bank_86'] != 0x564000 or symbols['_bowling_wheel_select'] >> 16 != 86 or
                symbols['_bowling_terrain_end'] > 0x568000):
            raise ValueError('Bowling reader must follow packed terrain in bank 86')
        if 'bowling_stub_bytes' in symbols and (
                symbols['_riding_sparse_bind']+1+symbols['bowling_stub_bytes'] > symbols['_riding_sparse_lookup']):
            raise ValueError('Bowling dispatch overlaps the sparse terrain reader')
    if '_riding_corner_lookup' in symbols:
        if symbols['_riding_corner_lookup'] >= 0x4000:
            raise ValueError('Corner bank switch must execute in fixed ROM')
        dispatch = symbols['step_solve_wheels']
        init = symbols['s__INITIALIZED']
        if not init <= dispatch <= init + symbols['l__INITIALIZED'] - 12:
            raise ValueError('Wheel dispatch must be initialized by the CRT')
        if not all(symbols['s__DATA'] <= symbols[name] < symbols['s__DATA'] + symbols['l__DATA']
                   for name in ('_riding_sparse_lookup', '_riding_sparse_bind')):
            raise ValueError('Corner bank reader must execute in WRAM')
        for bank in corner_bank.RANGES:
            start = symbols.get(f'_riding_corner_data_{bank}')
            if start is not None:
                size = symbols[f'_riding_corner_end_{bank}'] - start
                if bank in corner_cells.REGIONS and size != symbols[f'corner_size_{bank}']:
                    raise ValueError(f'Incorrect size for the dense corner data in bank {bank}')
                has_reader = bank in corner_cells.REGIONS or bank == corner_cells.corner_pairs.PAIR_BANK
                corner_bank.validate_layout(symbols, bank, size, with_code=has_reader)
    if '_world_scenery_pins' in symbols:
        scenery_pins.validate_layout(symbols)
    if 'pose_bank_18' in symbols:
        pose_products.validate_layout(symbols)
    if '_riding_scale_directory' in symbols and (symbols.get('_riding_projection_hash'), symbols['_riding_scale_directory'], symbols.get('_riding_scale_pages')) != (0x200, 0x600, 0x700):
        raise ValueError('Fixed projection hash, scale banks and scale pages must start on pages 2, 6 and 7')
    if symbols.get('_bike_render_draw', 0) >> 16 == 13:
        for name in ('_riding_heads', '_riding_wheels'):
            address = symbols.get(name, 0)
            if address >> 16 != 13 or address & 15:
                raise ValueError(f'{name} must be GDMA-aligned in sprite bank 13')
    if '_bike_body_upload' in symbols:
        for i in range(3):
            if symbols.get(f'_riding_body_{i}') != ((10+i) << 16) + 0x4000:
                raise ValueError('Body DMA source frames require page-aligned whole banks 10..12')
    if '_riding_sqrt_large' in symbols:
        for name, bank in (('_riding_sqrt_large', 15), ('_riding_sqrt_upper', 15),
                           ('_riding_sqrt_small', 35), ('_riding_sqrt_byte', 35)):
            address = symbols[name]
            if address >> 16 != bank or address & 255:
                raise ValueError(f'Unaligned or misplaced square-root lookup page {name}')
    if '_riding_div20_rows' in symbols and symbols['_riding_div20_rows'] != 0x234000:
        raise ValueError('Force division rows must be page-aligned at bank 35 address 0x4000')
    if '_riding_rider_rows' in symbols and symbols['_riding_rider_rows'] != 0x24000:
        raise ValueError('Rider spring and damper rows must start at bank 2 address 0x4000')
    if '_riding_small_squares' in symbols:
        for label, address in (('_riding_small_squares', 0x4000), ('_riding_endpoint_square_rows', 0x4100),
                               ('_riding_square_rows', 0x4500), ('_riding_contact_high', 0x6500),
                               ('_riding_merge_limit', 0x7d00)):
            if symbols.get(label) != 28 * 65536 + address:
                raise ValueError(f'{label} must be at bank 28 address {address:#06x}')
    if 'brake_angle_rows' in symbols:
        if symbols.get('_physics_bank_93') != 0x5d4000:
            raise ValueError('Brake lookup relocated packed terrain in bank 93')
        for name in ('brake_angle_rows','brake_damp_byte','brake_damp_low','brake_damp_high'):
            address = symbols.get(name, 0)
            if address >> 16 != 93 or address & 255:
                raise ValueError(f'{name} requires a page boundary in bank 93')
    if '_riding_head_cell_mask' in symbols:
        for bank in (506,507):
            if symbols.get(f'_physics_head_bank_{bank}') != (bank << 16) + 0x4000:
                raise ValueError(f'Head-clearance directory requires bank {bank} at 0x4000')
        if symbols['_riding_head_cell_mask'] >> 16 != 4 or symbols['_riding_head_read_map'] >= 0x4000:
            raise ValueError('Head-clearance reader requires caller bank 4 and fixed-ROM bank switching')
    if '_head_strip_filtered' in symbols:
        head_lane_tables.validate_layout(symbols)
    if '_riding_head_quarters' in symbols:
        head_refinement.validate_layout(symbols)
    if '_riding_phase_words' in symbols:
        if (symbols['_riding_phase_words'], symbols['_riding_phase_direct']) != (0x204000, 0x214000):
            raise ValueError('Movement product pages must begin at 0x4000 in banks 32 and 33')
    if '_riding_normal_ring' in symbols:
        normal_atlas.validate_layout(symbols)
        if 'direct_data_start' in symbols:
            if symbols['direct_template_size'] >= symbols['_riding_sparse_lookup'] - symbols['_riding_sparse_bind']:
                raise ValueError('Direct wheel trampoline exceeds the inactive binder')
            bank = wheel_direct_tiles.BANK
            if not (symbols[f'_riding_radial_space_{bank}'] <= symbols['direct_data_start'] <
                    symbols['direct_data_end'] <= symbols[f'_riding_radial_space_end_{bank}']):
                raise ValueError('Direct wheel reader exceeds the reserved radial bank')
    if '_riding_wheel_lookup' in symbols:
        wheel_terrain.validate_layout(symbols)
    if '_riding_projection_bank_477' in symbols:
        projection_tables.validate_layout(symbols)
    if 'rom_slope_find' in symbols:
        rolling_map_banks.validate_layout(symbols)
    if 'roll_first_0' in symbols:
        for phase, bank in enumerate(rolling_tables.BANKS):
            for label in ('first', 'short', 'second'):
                address = symbols[f'roll_{label}_{phase}']
                if address >> 16 != bank or address & 255:
                    raise ValueError(f'Unaligned rolling scalar table in bank {bank}')
    if 'ground_rows_29' in symbols:
        rolling_tables.validate_shallow_layout(symbols)
    if 'near_rows_positive_134' in symbols:
        start = symbols['near_rows_positive_134']
        if start >> 16 != 13 or start & 255 or symbols.get('near_upper_digits') != start + 6 * 512:
            raise ValueError('Near-horizontal rolling products require six aligned rows in bank 13')
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


def mismatched_map_banks(rom, sources):
    """Check each linked map and tile bank against the packer's exact bytes."""
    mismatches = []
    packed = {f'scenery_pins_{scenery_pins.BANK}.s': scenery_pins.BANK,
              f'reaction_words_{rolling_tables.REACTION_WORD_BANK}.s': rolling_tables.REACTION_WORD_BANK}
    for source in sources:
        corner = re.fullmatch(r'corner_bank_(\d+)\.s', source.name)
        if corner:
            if not corner_bank.matches_rom(rom, source, int(corner[1])):
                mismatches.append(source)
            continue
        if source.name == f'head_lanes_bank_{head_lane_tables.BANK}.s':
            data = bytearray()
            for line in source.read_text().splitlines():
                if line.startswith(' .db '):
                    data.extend(map(int, line[5:].split(',')))
            offset = head_lane_tables.BANK * 16384
            if not data or rom[offset:offset + len(data)] != data:
                mismatches.append(source)
            continue
        match = re.fullmatch(r'level_bank_(\d+)\.c', source.name)
        helper = re.fullmatch(r'rolling_(directory|products)_(\d+)\.s', source.name)
        if source.name in packed:
            data = bytes(int(value) for line in source.read_text().splitlines()
                         if line.startswith(' .db ') for value in line[5:].split(','))
            start = packed[source.name]*16384
            if rom[start:start+len(data)] != data:
                mismatches.append(source)
            continue
        if match or helper:
            bank = int(match[1] if match else helper[2])
            skip = 0 if match else (512 if helper[1]=='directory' else 2048)
            offset = bank * 16384 + skip
            data = source if match else source.with_name(f'level_bank_{bank}.c')
            values = data.read_text().split('{', 1)[1].split('}', 1)[0].strip()
            payload = bytearray(map(int, values.rstrip(',').split(',')))[skip:]
            if helper and helper[1] == 'directory' and 'bumpy_tiles::' in source.read_text():
                tile_lines = source.read_text().split('bumpy_tiles::\n')[1].split('bumpy_tiles_end::')[0]
                tiles = bytes(int(n) for line in tile_lines.splitlines() for n in line[5:].split(','))
                if len(tiles) != 512:
                    raise ValueError('Truncated wheel strip directory')
                start = bumpy_terrain.TABLE_OFFSET - skip
                payload[start:start+len(tiles)] = tiles
            if rom[offset:offset + len(payload)] != payload:
                mismatches.append(source)
    return mismatches


def validate_profile(gen, requested_rom_mib=None, sources=()):
    """Reject mixed codecs, stale table banks and out-of-range bank layouts."""
    levels=json.loads((gen/'level_manifest.json').read_text())
    physics=json.loads((gen/'physics_bank_manifest.json').read_text())
    if physics.get('segment_format') != 'length14-internal-endpoints-v1':
        raise ValueError('Collision data lacks artificial endpoint flags; regenerate physics levels')
    scheduled=scheduled_profile(gen)
    coefficient_manifest='physics_q24_manifest.json' if scheduled else 'physics-coefficient-manifest.json'
    coefficients=json.loads((gen/coefficient_manifest).read_text())
    codecs={'zx0-planes32x16':(4,'zx0-512'), 'raw3-plane32x16':(8,'raw-2bpp'),
            rider_map_tables.CODEC:(8,'raw-2bpp'), rolling_map_banks.CODEC:(8,'raw-2bpp')}
    if levels.get('map_codec') not in codecs:
        raise ValueError('Unknown level graphics codec: '+str(levels.get('map_codec')))
    rom_mib,pattern_codec=codecs[levels['map_codec']]
    if requested_rom_mib is not None and requested_rom_mib!=rom_mib:
        raise ValueError('%d MiB profile requires %s graphics; %s contains %s'%
                         (requested_rom_mib,'compressed'if requested_rom_mib==4 else'raw',gen,levels['map_codec']))
    if levels.get('rom_mib',rom_mib)!=rom_mib or levels.get('pattern_codec',pattern_codec)!=pattern_codec:
        raise ValueError('Level manifest has inconsistent ROM size or pattern codec')
    if levels['map_codec'] in (rider_map_tables.CODEC,rolling_map_banks.CODEC):
        constants=(gen/'riding_constants.h').read_bytes()
        if not scheduled or levels.get('rider_product_constants_sha256')!=hashlib.sha256(constants).hexdigest():
            raise ValueError('Direct rider scenery requires matching scheduled constants')
        rider_map_tables.validate(gen, levels, constants.decode())
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
        if coefficients.get('geometry_format') != 'planar-pose-ranked-angle-pages-v2':
            raise ValueError('Regenerate scheduled pose and angle tables with math_q24_coefficients.py')
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
    if scheduled:
        head = json.loads((gen/'physics_head_manifest.json').read_text())
        if (head['first_bank'], head['last_bank']) != (506,507):
            raise ValueError('Scheduled head clearance reserves banks 506..507')
        inputs = hashlib.sha256((gen/'physics_bank_manifest.json').read_bytes())
        for bank in physics['banks']:
            inputs.update((gen/f'physics_bank_{bank}.c').read_bytes())
        if inputs.hexdigest() != head['collision_sha256']:
            raise ValueError('Head clearance differs from the packed collision geometry')
        for name, digest in head['output_sha256'].items():
            if hashlib.sha256((gen/name).read_bytes()).hexdigest() != digest:
                raise ValueError(f'Head-clearance source changed during build: {name}')
        intervals['physics_head_bank_'] = (head['first_bank'], head['last_bank'])
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
    scheduled=scheduled_profile(a.gen)
    if scheduled:
        head_clearance.write_if_changed(a.gen/'clock_font.h', pixel_font.clock_header(pixel_font.font_rows()))
        head_clearance.generate(a.gen)
    rom_mib=validate_profile(a.gen,a.rom_mib)
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
    names=['play.c','splash.c','audio.c','save.c','world.c','world_dma.c','world_memory.s','world_retire_fast.s','world_alloc_fast.s','world_acquire_fast.s','world_upload_raw.s','menu.c','result.c','bike_render16.c','bike_render16_init.c','physics.c','physics_core.c',
           'physics_contacts.c','physics_collision.c','physics_sweep.c','video_screen_fast.s','video_strip_pair.s','objects_touch_fast.s','objects_draw_fast.s','objects_bounds_fast.s','objects_visible_fast.s']
    sources=[BASE/'src'/name for name in names]
    sources.append(BASE/'src'/('world_lookup_raw.s' if rom_mib==8 else 'world_lookup_linked.s'))
    graphics = json.loads((a.gen/'level_manifest.json').read_text())
    signed_bg = scheduled and rom_mib==8 and graphics['map_codec']==rolling_map_banks.CODEC
    # Full slow-pivot sign interval requires 8/17 < alpha < 8/15 for
    # every contact length in 384..415, where alpha=4*length*C/(64*2^24).
    pivot_bound = False
    if signed_bg:
        constants = (a.gen/'riding_constants.h').read_text()
        full_old = int(re.search(r'q24_C_OLD\[2\]=\{(-?\d+),', constants).group(1))
        pivot_bound = 328966 <= full_old <= 344977
    pivot_flags = 'RIDING_PAIR_BOUND = 1\n' if pivot_bound else ''

    if rom_mib==8:
        sources[sources.index(BASE/'src/video_strip_pair.s')] = BASE/'src/world_map_planes.s'
        # Only world.c and its near acquisition kernel call these SRAM helpers.
        # Keep the ROM-mapping readers fixed while the raw cart streams scenery.
        for name in ('world_memory', 'world_alloc_fast', 'world_lookup_raw'):
            source = BASE/'src'/(name+'.s')
            raw = a.gen/(name+'_game.s')
            prefix = 'WORLD_RAW_STREAM_BANK6 = 1\n'
            if name=='world_memory' and graphics['map_codec']==rolling_map_banks.CODEC:
                prefix += 'WORLD_PACKED_HIGH = 1\n'
            if signed_bg and name=='world_memory':
                prefix += 'WORLD_SIGNED_BG = 1\n'
            head_clearance.write_if_changed(raw, prefix+source.read_text())
            sources[sources.index(source)] = raw
    if rom_mib==4:
        sources=[path for path in sources if path.name!='world_upload_raw.s']
        sources.extend((BASE/'src/world_decompress.c', BASE/'src/world_zx0.s'))
    if a.sweep_source:
        sources=[a.sweep_source.resolve() if path.name=='physics_sweep.c' else path for path in sources]
    if a.collision_source:
        sources=[a.collision_source.resolve() if path.name=='physics_collision.c' else path for path in sources]
    seat_lookup = scheduled and rom_mib == 8 and seat_tables.generate(a.gen)
    if seat_lookup:
        sources.append(BASE/'src/physics_seat_lookup.c')
    if scheduled:
        sources += [BASE/'src'/name for name in ('physics_q24.c','physics_force.c','physics_q24.s',
            'physics_mul_scheduled.s','physics_mul16u8.s','physics_math32_exact.s',
            'physics_math.s','physics_contact_loop.s','physics_segment_scan.s',
            'physics_normal_fast.s','physics_shift_fast.s','physics_sqrt_scheduled.s',
            'physics_div_fast.s','physics_sin_fast.s',
            'physics_div20_scheduled.s','physics_export_fast.s','physics_bounds.s',
            'physics_rider_fast.s','physics_rider_response.s','physics_phase.s','physics_circle_scheduled.s',
            'physics_supports_fast.s','physics_ordered_pair.s','physics_free_fast.s','physics_roll_fast.s','physics_wheel_bridge.c',
            'physics_angle.c','physics_body_angle.s','physics_geometry.c','physics_pose_lookup.s','physics_head_pose.s','physics_brake_fast.s',
            'physics_suspension_scheduled.s','physics_step_scheduled.s','physics_level_bounds.s','physics_recip_fast.s','physics_contact_filter.s','physics_reaction_division.s')]
        sources.insert(0, a.gen/'physics_rider_rows.c')
        rider_game = a.gen/'physics_rider_coeff_game.s'
        rider_source = BASE/'src/physics_rider_coeff.s'
        rider_prefix = 'RIDING_ALIGNED_RIDER_ROWS = 1\n'
        if graphics['map_codec'] in (rider_map_tables.CODEC,rolling_map_banks.CODEC):
            rider_prefix += f"RIDING_DIRECT_RIDER_BANK = {graphics['rider_product_first_bank']}\n"
        head_clearance.write_if_changed(rider_game, rider_prefix+rider_source.read_text())
        sources.extend((rider_game, a.gen/'physics_q24_dispatch.c'))
        sources.extend((BASE/'src/head_clearance.s', a.gen/'physics_head_map.c'))
        suspension = BASE/'src/physics_suspension_scheduled.s'
        sources[sources.index(suspension)] = rolling_tables.generate_reaction(
            a.gen, suspension, BASE.parent/'nes/src/recip.inc')
        # The product bank-selector table must begin on a page boundary.
        mul = BASE/'src/physics_mul_scheduled.s'
        sources.remove(mul)
        sources.insert(0, mul)
        scale = BASE/'src/physics_mul16u8.s'
        scale_game = a.gen/'physics_mul16u8_game.s'
        head_clearance.write_if_changed(scale_game, 'RIDING_SCALE_DIRECTORY = 1\n'+scale.read_text())
        sources[sources.index(scale)] = scale_game
        div = BASE/'src/physics_div20_scheduled.s'
        sources.insert(sources.index(div)+1, sqrt_tables.generate(a.gen))
        bounds_source = BASE/'src/physics_bounds.s'
        bounds_game = a.gen/'physics_bounds_game.s'
        head_clearance.write_if_changed(bounds_game, 'RIDING_BANKED_BOUNDS = 1\n'+bounds_source.read_text())
        sources[sources.index(bounds_source)] = bounds_game
        phase_source = BASE/'src/physics_phase.s'
        phase = phase_tables.generate(a.gen, phase_source)
        sources[sources.index(phase_source)] = phase
        circle_source = BASE/'src/physics_circle_scheduled.s'
        sources[sources.index(circle_source)] = phase_tables.circle_source(a.gen, circle_source, phase)
        sources.remove(BASE/'src/physics_angle.c')
        sources.insert(0, phase_tables.body_angle_pages(a.gen))
        angle_source = BASE/'src/physics_body_angle.s'
        sources[sources.index(angle_source)] = phase_tables.body_angle(a.gen, angle_source)
        free_source = BASE/'src/physics_free_fast.s'
        sources[sources.index(free_source)] = rolling_tables.generate_free(a.gen, free_source)
        sources.append(stopped_pair.generate(a.gen, BASE/'src/stopped_pair_lookup.s'))
        brake_source = BASE/'src/physics_brake_fast.s'
        brake_game = brake_dispatch.generate(a.gen, brake_source)
        sources.remove(brake_source)
        roll_source = BASE/'src/physics_roll_fast.s'
        sources[sources.index(roll_source)] = rolling_tables.generate(a.gen, roll_source)
        # Both scalar banks start with low-byte-indexed quotient pages.
        sources.insert(0, a.gen/'physics_roll_scalar.s')
        pair_source = BASE/'src/physics_ordered_pair.s'
        pair_game = a.gen/'physics_ordered_pair_game.s'
        head_clearance.write_if_changed(pair_game, 'RIDING_LEAF_REGION = 1\n'+pivot_flags+pair_source.read_text())
        sources[sources.index(pair_source)] = pair_game
        math_source = BASE/'src/physics_math32_exact.s'
        sources[sources.index(math_source)] = projection_tables.generate(math_source, a.gen/'physics_projection_game.s')
        length_bands = 'normal_length_bands::' in (a.gen/'physics_projection_game.s').read_text()
        for name in ('physics_contact_loop', 'physics_normal_fast'):
            source = BASE/'src'/(name+'.s')
            game_source = a.gen/(name+'_game.s')
            text = 'RIDING_NORMAL_ATLAS = 1\n'+source.read_text()
            if name == 'physics_contact_loop':
                text = ('RIDING_LEAF_REGION = 1\n' + text + '\n' + (BASE/'src/corner_pair.inc').read_text()
                        + '\n' + (BASE/'src/wheel_candidates.inc').read_text())
            if name == 'physics_normal_fast':
                text += '\n'+(BASE/'src/physics_normal_atlas.s').read_text()
                if length_bands:
                    text = 'RIDING_NORMAL_LENGTH_BANDS = 1\n'+text
                if signed_bg:
                    text = 'RIDING_NORMAL_SRAM = 1\n'+text
            head_clearance.write_if_changed(game_source,text)
            sources[sources.index(source)] = game_source
        rider_source = BASE/'src/physics_rider_response.s'
        rider_game = a.gen/'physics_rider_response_game.s'
        head_clearance.write_if_changed(rider_game, 'RIDING_PAIRED_ROTATION = 1\nRIDING_PROJECTION_TABLES = 1\n'+rider_source.read_text()+
                                        '\n'+(BASE/'src/physics_rider_rotation.s').read_text())
        sources[sources.index(rider_source)] = rider_game
        geometry_math = BASE/'src/physics_math.s'
        geometry_game = a.gen/'physics_math_game.s'
        head_clearance.write_if_changed(geometry_game, 'RIDING_GEOMETRY_PRODUCTS = 1\n'+geometry_math.read_text())
        sources[sources.index(geometry_math)] = geometry_game
    else:
        sources.extend((BASE/'src/physics_math.c', BASE/'src/physics_math32.c'))
        sources += sorted(x for x in (BASE/'src').glob('physics_*.s')if x.name not in ('physics_mul16.s','physics_mul_scheduled.s','physics_div20_scheduled.s','physics_leaf_region.s','physics_rider_rotation.s','physics_roll_shallow.s','physics_sqrt_scheduled.s') and not x.name.startswith('physics_q24'))
    if scheduled:
        sources.insert(0, mul_table.scheduled_squares(a.gen))
        sources.insert(0, projection_tables.hash_source(a.gen))
    else:
        sources += sorted(a.gen.glob('physics_quarter_*.c'))
    for pattern in ('physics_scale_*.c','physics_sine_*.c',
                    'physics_q24_table_*.c' if scheduled else 'physics_coefficient_*.c',
                    'physics_bank_*.c','physics_head_bank_*.c','level_bank_*.c','riding16_body_*.c'):
        sources+=sorted(a.gen.glob(pattern))
    if not scheduled:sources.append(a.gen/'physics_coefficient_calls.s')
    sources += [a.gen/name for name in ('level_catalogue.c','menu_assets.c','splash_assets.c','physics_level_data.c','riding16_parts.c','riding_meta.c')]
    if scheduled:
        sources[sources.index(a.gen/'riding_meta.c')] = bike_frames16.paired_metadata(a.gen)
        # Native graphics pointers require their original bank base. Place
        # each linked terrain row after the graphics payload in its bank.
        wheel_rows = wheel_terrain.generate(a.gen)
        projection = a.gen/'physics_projection_game.s'
        radial_slabs = {int(bank):'' for bank in re.findall(r'^_riding_radial_space_(\d+)::',
                                                            projection.read_text(),re.M)} if signed_bg else {}
        sources += [BASE/'src/physics_leaf_region.c', BASE/'src/wheel_terrain.s',
                    BASE/'src/physics_leaf_region.s', wheel_rows, head_refinement.generate(a.gen),
                    normal_atlas.generate(a.gen, BASE.parent/'nes/src/rsqrt.inc', wheel_rows,
                                          extend_rows=signed_bg, slabs=radial_slabs)]
        sources.append(brake_game)
    if scheduled:
        # Append the divider after the aligned bank-35 numeric tables.
        div_source = BASE/'src/physics_div_fast.s'
        div_game = a.gen/'physics_div_game.s'
        head_clearance.write_if_changed(div_game, 'RIDING_BANKED_DIVISION = 1\n'+div_source.read_text())
        sources.remove(div_source)
        sources.append(div_game)
        touch = BASE/'src/objects_touch_fast.s'
        touch_game = a.gen/'objects_touch_game.s'
        head_clearance.write_if_changed(touch_game, 'RIDING_OBJECT_CIRCLES = 1\n'+touch.read_text())
        sources[sources.index(touch)] = touch_game
        sources.insert(sources.index(a.gen/'head_quarters.s'), mul_table.object_circles(a.gen))
    profile_sources = list(sources)
    validate_profile(a.gen,rom_mib,profile_sources)
    # Validate the complete packed source first, then remove only verified
    # padding. The shortened object keeps its original place in link order.
    if scheduled and rom_mib == 8:
        sources.insert(0, phase_tables.torque_words(a.gen))
        suspension = a.gen/'physics_suspension_game.s'
        paired = a.gen/'physics_suspension_torque_game.s'
        prefix = 'RIDING_TORQUE_WORDS = 1\n'
        if signed_bg:
            prefix += 'RIDING_REACTION_PAIR = 1\n'
            sources.insert(sources.index(a.gen/'head_quarters.s'), BASE/'src/physics_reaction_pair.s')
        if graphics['map_codec'] == rolling_map_banks.CODEC:
            bank = rolling_tables.REACTION_WORD_BANK
            original = a.gen/f'level_bank_{bank}.c'
            sources[sources.index(original)] = rolling_tables.reaction_word_table(a.gen, original)
            prefix += f'RIDING_REACTION_WORDS = 1\nreaction_word_bank = {bank}\n'
        head_clearance.write_if_changed(paired, prefix+suspension.read_text()
                                        +'\n'+(BASE/'src/torque_words.inc').read_text())
        sources[sources.index(suspension)] = paired
        packed = pose_products.generate(a.gen, BASE/'src')
        for bank in (16, 17, 18, 19):
            sources.remove(a.gen/f'physics_sine_{bank}.c')
        sources.append(packed)
        sources[sources.index(BASE/'src/physics_geometry.c')] = a.gen/'pose_geometry_packed.c'
        for original, replacement in (('physics_pose_lookup.s', 'pose_lookup_packed.s'),
                                      ('physics_sin_fast.s', 'pose_sine_packed.s')):
            sources[sources.index(BASE/'src'/original)] = BASE/'src'/replacement
        head = BASE/'src/physics_head_pose.s'
        game = a.gen/'physics_head_pose_game.s'
        head_clearance.write_if_changed(game, 'RIDING_BIASED_HEAD = 1\n'+head.read_text())
        sources[sources.index(head)] = game
    if scheduled and 'brake_tables = 1\n' in brake_game.read_text():
        terrain = a.gen/'physics_bank_93.c'
        sources[sources.index(terrain)] = brake_dispatch.terrain_object(a.gen, brake_dispatch.terrain_prefix(a.gen))
    if scheduled:
        # Head frames must start on a GDMA boundary before bank 13 code.
        sprites = a.gen/'riding16_parts.c'
        sources.remove(sprites)
        sources.insert(sources.index(BASE/'src/bike_render16.c'), sprites)
        sources.insert(sources.index(sprites) + 1, BASE/'src/roll_near_rows.s')
    if scheduled and graphics['map_codec']==rolling_map_banks.CODEC:
        sources = rolling_map_banks.bank_sources(sources, graphics, a.gen, BASE/'src')
    head_lanes = scheduled and rom_mib == 8 and graphics['map_codec'] == rolling_map_banks.CODEC
    immediate_drive = False
    if head_lanes:
        compact, transfers = body_transfers.generate(a.gen, BASE/'src/bike_body_upload.inc')
        sources[sources.index(a.gen/'riding16_parts.c')] = compact
        sources.insert(sources.index(a.gen/'head_quarters.s'), transfers)
        levels, terrain_banks, _ = head_clearance.packed_inputs(a.gen)
        hang = hang_terrain.generate(a.gen, BASE/'src/hang_terrain.inc', levels, terrain_banks)
        sources[sources.index(a.gen/'physics_bank_87.c')] = hang
        bowling = bowling_planes.generate(a.gen, BASE/'src/bowling_planes.inc', levels, terrain_banks)
        sources[sources.index(a.gen/'physics_bank_86.c')] = bowling
        for bank, path in gravity_strips.generate(a.gen, BASE/'src/gravity_strip.inc', levels, terrain_banks).items():
            sources[sources.index(a.gen/f'physics_bank_{bank}.c')] = path
        patch_source = pair_patches.generate(a.gen, BASE/'src/pair_patches.inc', levels, terrain_banks)
        sources.insert(sources.index(a.gen/'head_quarters.s'), patch_source)
        tables, directory = corner_cells.generate(a.gen, BASE/'src/corner_cell_reader.inc')
        step = BASE/'src/physics_step_scheduled.s'
        step_game = a.gen/'physics_step_corners.s'
        header = (a.gen/'riding_constants.h').read_text()
        drive = dict(re.findall(r'^#define (WHEEL_MAXW|GAS_TQ) (\d+)$', header, re.M))
        prefix = 'RIDING_CORNER_CELLS = 1\n'
        immediate_drive = len(drive) == 2 and 0 < int(drive['WHEEL_MAXW']) < 32768 and int(drive['GAS_TQ']) < 32768
        if immediate_drive:
            prefix += f"STEP_DRIVE_LIMIT = {drive['WHEEL_MAXW']}\nSTEP_DRIVE_TORQUE = {drive['GAS_TQ']}\n"
        head_clearance.write_if_changed(step_game, prefix+step.read_text())
        sources[sources.index(step)] = step_game
        lookup = a.gen/'corner_lookup_game.s'
        direct_prefix = ''
        if wheel_direct_tiles.BANK in radial_slabs:
            runtime, data = wheel_direct_tiles.generate(BASE/'src/direct_wheel.inc', levels, terrain_banks)
            radial_slabs[wheel_direct_tiles.BANK] += '\n' + data
            head_clearance.write_if_changed(a.gen/'direct_wheel_runtime.s', runtime)
            direct_prefix = 'RIDING_DIRECT_TILES = 1\n'
        head_clearance.write_if_changed(lookup, direct_prefix + (BASE/'src/corner_lookup.s').read_text() + directory)
        sources.append(lookup)
        sources.insert(sources.index(a.gen/'head_quarters.s'), BASE/'src/haircut_gate.s')
        bounds = BASE/'src/physics_level_bounds.s'
        bounds_game = a.gen/'physics_level_bounds_sram.s'
        bounds_flags = 'RIDING_NORMAL_SRAM = 1\n'+pivot_flags
        if signed_bg:
            bounds_flags += 'RIDING_REACTION_PAIR = 1\nRIDING_WHEEL_ROW_RAM = 1\n'
            wheel = BASE/'src/wheel_terrain.s'
            cached_wheel = a.gen/'wheel_terrain_sram.s'
            head_clearance.write_if_changed(cached_wheel, 'RIDING_WHEEL_ROW_RAM = 1\n'+wheel.read_text())
            sources[sources.index(wheel)] = cached_wheel
            sources.insert(sources.index(a.gen/'head_quarters.s'), BASE/'src/wheel_course_rows.c')
        head_clearance.write_if_changed(bounds_game, bounds_flags+bounds.read_text())
        sources[sources.index(bounds)] = bounds_game
        sources.insert(sources.index(a.gen/'head_quarters.s'), BASE/'src/normal_sram.s')
        lane_code, lane_table = head_lane_tables.generate(a.gen, BASE/'src/head_lanes.s')
        sources[sources.index(a.gen/'level_bank_469.c')] = lane_table
        sources.insert(sources.index(a.gen/'head_quarters.s'), lane_code)
    cache=BASE/'build/objects';cache.mkdir(parents=True,exist_ok=True)
    tool_key=[]
    for name in ('lcc','sdcc','sdasgb','sdldgb'):
        path=a.sdk/'bin'/name
        if path.exists():
            stat=path.stat();tool_key.append((str(path),stat.st_size,stat.st_mtime_ns))
    configuration=json.dumps([compile_flags,tool_key]).encode()
    if signed_bg:
        bank = a.gen/f'level_bank_{scenery_pins.BANK}.c'
        sources[sources.index(bank)] = scenery_pins.generate(a.gen,bank)
        for name in ('world_upload_raw','objects_draw_fast'):
            source = BASE/'src'/(name+'.s')
            signed = a.gen/('signed_'+name+'.s')
            head_clearance.write_if_changed(signed,'WORLD_SIGNED_BG = 1\n'+source.read_text())
            sources[sources.index(source)] = signed
        unused = {'world_acquire_fast.s','world_retire_fast.s','world_alloc_fast_game.s','world_lookup_raw_game.s'}
        sources = [path for path in sources if path.name not in unused]
    if head_lanes:
        for bank, table in tables.items():
            original = a.gen/f'level_bank_{bank}.c'
            if bank == rolling_tables.REACTION_WORD_BANK:
                original = a.gen/f'reaction_words_{bank}.s'
                corner_bank.after_numeric_prefix(table, original, bank, '_riding_reaction_words_end')
            elif bank == scenery_pins.BANK and signed_bg:
                original = a.gen/f'scenery_pins_{bank}.s'
                corner_bank.after_numeric_prefix(table, original, bank, '_world_scenery_pins_end')
            sources[sources.index(original)] = table

    if scheduled and not length_bands:
        lengths, inner_lengths = normal_length.generate(
            a.gen, BASE/'src/normal_length.inc', BASE.parent/'nes/src/rsqrt.inc')
        # The inner radial lookup follows the page-aligned braking data in bank 93.
        sources.insert(sources.index(a.gen/'head_quarters.s'), lengths)
        sources.append(inner_lengths)
    if scheduled:
        deep = BASE/'src/normal_deep.s'
        packed_deep = projection_tables.deep_fractions(a.gen, deep)
        if packed_deep == deep:
            sources.append(deep)
        else:
            index = sources.index(a.gen/'physics_projection_game.s')
            sources.insert(index+1, packed_deep)
        if radial_slabs:
            index = sources.index(projection)
            sources[index] = normal_atlas.fill_projection_space(a.gen,projection,radial_slabs)
        sources.extend((BASE/'src/physics_pair_impulse.s',
                        BASE/'src/terrain_region.s', a.gen/'wheel_candidate_planes.s'))
    if head_lanes:
        sources.insert(sources.index(a.gen/'head_quarters.s'), BASE/'src/head_near.c')
        sources.insert(sources.index(a.gen/'head_quarters.s'), BASE/'src/bumpy_setup.s')
        sources.insert(sources.index(a.gen/'head_quarters.s'), BASE/'src/physics_impact_bound.s')

    if pivot_bound:
        sources.append(BASE/'src/physics_pivot_bound.s')

    def coefficient_lookup(path):
        return not scheduled and ((path.parent==BASE/'src' and path.suffix=='.c' and path.name.startswith('physics')) or any(candidate is not None and path==candidate.resolve()for candidate in(a.sweep_source,a.collision_source)))
    sweep_path=a.sweep_source.resolve() if a.sweep_source else BASE/'src/physics_sweep.c'
    colored = signed_bg and '_world_scenery_slots::' in (a.gen/'physics_projection_game.s').read_text()
    if colored:
        sources.append(BASE/'src/world_scenery_slots.c')
    def apply_scenery_flags(path,flags):
        if colored and path.name=='world.c':
            flags = flags+['-DWORLD_SCENERY_SLOTS']
        if signed_bg and path.name in ('world.c','world_dma.c','play.c','result.c','bike_render16.c',
                                       'bike_render16_init.c','riding16_meta.c'):
            return flags+['-DWORLD_SIGNED_BG']
        return flags
    if scheduled:
        screen = BASE/'src/video_screen_fast.s'
        page = a.gen/'video_screen_game.s'
        head_clearance.write_if_changed(page, 'SCREEN_FRACTION_PAGE = 1\n' + screen.read_text())
        sources.remove(screen)
        sources.insert(0, page)
    def source_flags(path):
        if scheduled and path == BASE/'src/physics_core.c':
            flags = ['-DRIDING_PAIRED_ROTATION'] + (['-DRIDING_SEAT_LOOKUP'] if seat_lookup else [])
            return flags + (['-DRIDING_IMMEDIATE_DRIVE'] if immediate_drive else [])
        if scheduled and path == BASE/'src/play.c': return ['-DRIDING_BANKED_DRAW']
        if scheduled and path == BASE/'src/bike_render16.c': return ['-DRIDING_BANKED_DRAW','-DRIDING_PAIRED_MASKS'] + (['-DRIDING_BODY_TRANSFERS'] if head_lanes else [])
        if scheduled and path == BASE/'src/bike_render16_init.c': return ['-DRIDING_PAIRED_MASKS'] + (['-DRIDING_BODY_TRANSFERS'] if head_lanes else [])
        if scheduled and path == BASE/'src/physics_q24.c': return ['-DRIDING_SCHEDULED_CART']
        if scheduled and path==BASE/'src/physics_contacts.c':return ['-DRIDING_WHEEL_TERRAIN','-DRIDING_NORMAL_ATLAS','-DRIDING_STOPPED_PAIR'] + (['-DRIDING_CORNER_CELLS'] if head_lanes else []) + (['-DRIDING_PAIR_BOUND'] if pivot_bound else [])
        if scheduled and path==sweep_path:
            return ['-DRIDING_HEAD_TERRAIN'] + (['-DRIDING_HEAD_LANES'] if head_lanes else [])
        return ['-DRIDING_COEFFICIENT_LOOKUP'] if coefficient_lookup(path) else []
    def source_key(path):
        extra=b''.join(b' '+flag.encode() for flag in apply_scenery_flags(path,source_flags(path)))
        return hashlib.sha256(configuration+extra+dependencies(path,a.gen)).hexdigest()
    if head_lanes and wheel_direct_tiles.BANK in radial_slabs:
        # The lookup pages in low ROM must stay at the start of their banks.
        sources.append(a.gen/'direct_wheel_runtime.s')
    objects=[];keys=[];pending=[]
    for path in sources:
        key=source_key(path)
        obj=cache/(path.stem+'-'+key[:24]+'.o');objects.append(obj);keys.append(key)
        if not obj.is_file():pending.append((path,obj,key))
    def compile_one(item):
        path,obj,key=item
        extra=apply_scenery_flags(path,source_flags(path))
        # lcc can leave a partial ASxxxx object after an interrupted write.
        # Only a completed compilation may publish an object into the cache.
        with tempfile.TemporaryDirectory(dir=cache) as staging:
            candidate = Path(staging)/obj.name
            result=subprocess.run([str(compiler),*compile_flags,*extra,'-c','-o',str(candidate),str(path)],capture_output=True,text=True)
            if result.returncode:
                raise RuntimeError(str(path)+'\n'+result.stdout+result.stderr)
            if source_key(path)!=key:
                raise RuntimeError('Source changed while compiling: '+str(path)+'; rerun the build after edits finish')
            candidate.replace(obj)
        if result.stdout.strip() or result.stderr.strip():print(result.stdout+result.stderr,flush=True)
    print('Objects: %d cached, %d compiling'%(len(objects)-len(pending),len(pending)),flush=True)
    with ThreadPoolExecutor(max_workers=max(1,a.jobs))as pool:
        for _ in pool.map(compile_one,pending):pass
    for path,key in zip(sources,keys):
        if source_key(path)!=key:
            raise RuntimeError('Source changed during the build: '+str(path)+'; rerun after edits finish')
    validate_profile(a.gen,rom_mib,profile_sources)
    manifest_path=a.out.with_suffix('.build.json')
    build_key=hashlib.sha256(json.dumps([keys,link_flags,tool_key]).encode()).hexdigest()
    if manifest_path.is_file() and a.out.is_file() and a.out.with_suffix('.noi').is_file():
        previous=json.loads(manifest_path.read_text())
        if (previous.get('build_key')==build_key and previous.get('rom_sha256')==hashlib.sha256(a.out.read_bytes()).hexdigest()
                and not mismatched_map_banks(a.out.read_bytes(), sources)):
            layout=validate_linked_layout(a.out.with_suffix('.noi'),rom_mib)
            if previous.get('linked_layout')!=layout:
                previous['linked_layout']=layout
                manifest_path.write_text(json.dumps(previous,indent=2)+'\n')
            a.out.with_suffix('.ihx').unlink(missing_ok=True)
            print('ROM unchanged: '+str(a.out));return
    def link():
        subprocess.run([str(compiler),*link_flags,'-o',str(a.out),*map(str,objects)],check=True)
        return a.out.read_bytes()

    rom = link()
    bad = mismatched_map_banks(rom, sources)
    if bad:
        # Repair interrupted objects from caches created by older builds.
        for path in bad:
            i = sources.index(path)
            compile_one((path, objects[i], keys[i]))
        rom = link()
        bad = mismatched_map_banks(rom, sources)
        if bad:
            raise ValueError('Linked graphics differ from packed bytes in '+', '.join(p.name for p in bad))
    layout=validate_linked_layout(a.out.with_suffix('.noi'),rom_mib)
    if len(rom)!=rom_mib*1024*1024 or rom[0x147:0x14a]!=bytes((0x1B,{4:7,8:8}[rom_mib],3)):
        raise ValueError('Linked ROM does not match the selected MBC5+RAM+BATTERY / 32 KiB RAM profile')
    if rom_mib==8 and rom[508*16384:]!=bytes([255])*(4*16384):
        raise ValueError('The 8 MiB cartridge profile must leave the last 64 KiB unused')
    report={'rom_mib':rom_mib,'cartridge_type':0x1B,'ram_kib':32,'generated_dir':str(a.gen),'build_key':build_key,'rom_sha256':hashlib.sha256(rom).hexdigest(),
            'sources':[str(x)for x in sources],'objects':[str(x)for x in objects],'linked_layout':layout}
    manifest_path.write_text(json.dumps(report,indent=2)+'\n')
    a.out.with_suffix('.ihx').unlink(missing_ok=True)
    print('Built '+str(a.out)+' '+report['rom_sha256'])


if __name__=='__main__':main()
