"""Store exact paired rolling products in losslessly compacted MBC5 scenery banks."""
from collections import defaultdict
import re
import struct

import bumpy_terrain
from head_clearance import write_if_changed
from projection_tables import planes, byte_lines

CODEC = 'raw-packed-high32x16'
# The scheduled catalog and extended controller routes supplied these tangents.
# The dot-product reader checks every key byte and falls back on a width miss.
TANGENTS = (
    (-16379, -396), (-14282, 8029), (-16078, 3152), (-16379, -412),
    (-16379, 402), (-16368, -725), (-15279, 5914), (-16370, -677),
    (-16362, 856), (-16381, -301), (-15747, -4523), (-16378, 457),
    (-16095, -3066), (-15580, -5069), (-16120, -2927), (-14037, -8449),
    (-10611, -12484), (-10948, 12195), (-10689, 12417), (-15702, 4677),
    (-13123, 9809), (-15788, 4377), (-14955, -6692), (-9638, 13249),
    (-14140, -8277), (-15821, 4256), (-16379, 394), (-6840, 14888),
    (-15504, 5297), (-9636, 13251), (-15259, -5967), (-14141, -8275),
    (-15940, -3788), (-3013, 16105), (-15270, -5937), (-10914, 12198),
    (-15589, 5042), (-10682, 12416), (-15758, 4487), (-15843, 4174),
    (-10907, 12236), (-2401, 16207), (-4419, 15777), (-16364, -819),
    (-11181, 11975), (-12167, 10973), (737, 16367), (-16384, -24),
    (-15586, 5052), (-16378, 432), (-14337, -7931), (-15654, 4835),
    (-15455, 5440), (-13549, 9212), (-15100, 6358), (-13007, 9963),
    (-16384, 30), (-16356, 956), (-14454, 7715), (-101, 16384),
    (-11872, -11292), (-11011, 12136), (-15965, 3680), (-9217, -13546),
    (-16015, 3455), (-10649, 12458), (-26, 16384), (-14863, 6893),
    (-10706, 12397), (-12731, -10313), (-10988, 12155), (1046, -16351),
    (-10666, 12437), (-16362, 769), (-6794, 14909), (-10730, 12377),
    (-14315, 7970), (-10746, 12356), (-14115, 8318), (-10763, 12335),
    (-16383, -159), (-16, -16384), (-15854, -4135), (-10642, 12456),
    (-13138, -9789), (-16371, -683), (-16376, -512), (-1553, 16310),
    (-10424, 12638), (-10884, 12255), (-10787, 12316), (-10827, 12276),
    (-11493, 11654), (-16356, -724), (-13782, 8860), (-11408, 11771),
    (-10971, 12176), (-16351, 1130), (-11448, 11730), (70, -16384),
    (-9147, 13593), (-10770, 12337), (-15429, 5513), (-16366, -807),
    (-10440, 12617), (-12538, 10529), (-11575, 11596), (-11310, 11833),
    (-280, 16382), (-10448, 12618), (-16356, -764), (-15914, -3899),
    (-13272, -9606), (-11270, 11873), (-11332, 11815), (-11489, 11690),
    (-10465, 12598), (-10505, 12558), (-16362, 810), (-16366, -847),
    (-11149, 11994), (-12558, 10505), (-10561, 12537), (16053, 3276),
    (-11229, 11914), (1613, -16304), (-11859, 11305), (-11345, 11829),
    (-10602, 12496), (-11189, 11954), (-15266, 5948), (-16366, -928),
    (-11028, 12115), (-16351, 969), (-16366, 846), (-16341, -966),
    (-10569, 12498), (-11091, 12056), (-16351, 928), (-16366, -887),
    (-16362, 729), (-16326, 1169), (86, 16384), (-15833, 4219),
    (-9429, 13401), (-16381, 362), (-16336, 1091), (-16362, 850),
    (-16326, -1170), (-15923, -3870), (-11051, 12096), (-11068, 12075),
    (-11109, 12034), (-10529, 12538), (-16341, 966), (-16351, 1049),
    (-16351, 860), (-16326, -1210), (-16341, -1047), (-16356, -925),
    (-16366, 645), (-16326, 1249), (-16326, 1209), (-16371, 521),
    (-15923, 3870), (-15072, -6425), (-10626, 12477), (-11172, 11975),
    (-16311, 1413), (-16381, 201), (-15746, 4522), (-16366, 362),
)


def reserved_prefixes(manifest):
    if manifest['map_codec'] != CODEC:
        return {}
    banks = manifest['rolling_map_banks']
    if (len(banks) != 1 + len(TANGENTS)//4 or len(set(banks)) != len(banks) or
            any(type(b) != int or not manifest['first_bank'] <= b <= min(255,manifest['last_bank'])
                for b in banks)):
        raise ValueError('Invalid rolling projection bank allocation')
    first = manifest['rider_product_first_bank']
    if any(first <= b < first+8 for b in banks):
        raise ValueError('Rolling projection banks overlap rider products')
    return {bank:(4096 if i==0 else 12288) for i,bank in enumerate(banks)}


def product_payloads(banks):
    if not 0 < len(TANGENTS) < 512 or len(set(TANGENTS)) != len(TANGENTS) or len(TANGENTS) % 4:
        raise ValueError('Four distinct tangents are required per bank')
    directory = bytearray(4096)
    buffers = {b:bytearray(12288) for b in banks[1:]}
    for i,(x,y) in enumerate(TANGENTS):
        if abs(x)+abs(y) > 32767:
            raise ValueError('Rolling tangent exceeds signed24 dot bound')
        mixed = (x^y)&255
        h = ((((mixed<<3)|(mixed>>5))^(x>>8))&255) | ((((y>>8)^mixed)&1)<<8)
        while directory[512+h]:
            h = (h+1)&511
        bank,slot = banks[1+i//4],i%4
        for j,value in enumerate((bank,x&255,(x>>8)&255,y&255,(y>>8)&255,slot)):
            directory[512*(j+1)+h] = value
        for axis,k in enumerate((x,y)):
            at = (8+10*slot+5*axis)*256
            buffers[bank][at:at+1280] = b''.join(planes(k))
    return {banks[0]:directory, **buffers}


def repack(packer, records):
    """Allocate only inside map chunks already emitted by the direct-rider packer."""
    extents = defaultdict(list)
    encoded = {}
    chunks = {tuple(c) for r in records for c in r['chunks']}
    for tag,address in sorted(chunks, key=lambda c:(c[0]&511,c[1])):
        bank = tag & 511
        start = address-0x4000
        size = 1024 if tag&0x8000 else 1536
        ranges = extents[bank]
        if ranges and ranges[-1][1] == start:
            ranges[-1][1] += size
        else:
            if ranges and ranges[-1][1] > start:
                raise ValueError('Original scenery chunks overlap')
            ranges.append([start,start+size])
        source = bytes(packer.banks[bank-packer.first][start:start+size])
        if len(source) != size:
            raise ValueError('Scenery chunk crosses its ROM bank')
        flags = tag & ~511
        if size == 1536:
            high,attrs = source[512:1024],source[1024:]
            if max(high)<8 and not any(a & 0x98 for a in attrs):
                flags = 0x4000
                source = source[:512]+bytes(a | ((v & 3)<<3) | ((v & 4)<<5)
                                            for a,v in zip(attrs,high))
        encoded[tag,address] = flags,source

    required = 1+len(TANGENTS)//4
    banks = [b for b,rs in sorted(extents.items())
             if b < 256 and rs[0][0] == 0 and rs[0][1] >= 12288][:required]
    if len(banks) < required:
        return None
    for i,b in enumerate(banks):
        extents[b][0][0] = 4096 if i==0 else 12288
    holes = [[end-start,b,start] for b,rs in extents.items()
             for start,end in rs if start<end]
    placements = {}
    for key,(tag,data) in sorted(encoded.items(),key=lambda i:(-len(i[1][1]),i[0])):
        n = len(data)
        slot = min((h for h in holes if h[0]>=n), key=lambda h:(h[0]%n,*h), default=None)
        if slot is None:
            return None
        _,bank,start = slot
        placements[key] = bank|tag,start+0x4000
        slot[0] -= n
        slot[2] += n

    for key,(tag,addr) in placements.items():
        data = encoded[key][1]
        start = addr-0x4000
        packer.banks[(tag&511)-packer.first][start:start+len(data)] = data
    for r in records:
        r['chunks'] = [placements[tuple(c)] for c in r['chunks']]
        bank,addr = r['chunk_directory']
        for i,c in enumerate(r['chunks']):
            struct.pack_into('<HH',packer.banks[bank-packer.first],addr-0x4000+4*i,*c)
    for bank,data in product_payloads(banks).items():
        packer.banks[bank-packer.first][:len(data)] = data
    return banks


def bank_sources(sources, manifest, gen, src):
    """Link each reader at its own bank's original graphics base, ahead of its data."""
    banks = manifest['rolling_map_banks']
    expected = product_payloads(banks)
    directory = (src/'roll_rom_directory.inc').read_text()
    products = (src/'roll_rom_products.inc').read_text()
    result = []
    for source in sources:
        m = re.fullmatch(r'level_bank_(\d+)\.c',source.name)
        if not m or int(m[1]) not in expected:
            result.append(source)
            continue
        bank = int(m[1])
        values = source.read_text().split('{',1)[1].split('}',1)[0].strip()
        data = bytes(map(int,values.rstrip(',').split(',')))
        if not data.startswith(expected[bank]):
            raise ValueError(f'Stale rolling projection data in graphics bank {bank}')
        output = [f'.module rolling_map_{bank}', f'.area _CODE_{bank}', f'_level_bank_{bank}::']
        if bank == banks[0]:
            group,skip = 'directory',512
            reader, tiles = bumpy_terrain.directory(gen, src, directory, bank)
            output += ['.globl rom_slope_map,rom_slope_miss',
                       '.globl '+','.join(f'rom_slope_{k}_{i}' for k in ('inputs','project') for i in range(4)),
                       reader]
        else:
            group,skip = 'products',2048
            output += ['.globl slope_fallback_dots,slope_pair_miss,ground_resume_deltas,ground_return',
                       products]
            for i in range(4):
                suffix = str(i) if bank==banks[1] else f'{bank}_{i}'
                output.append(f' map_tangent rom_slope_inputs_{suffix},rom_slope_project_{suffix},{72+i*10},read_x_{i},read_y_{i}')
        output += [f' .ds {skip}-(.-_level_bank_{bank})', f'rolling_payload_{bank}::']
        if group == 'directory':
            output.extend(bumpy_terrain.payload(data, skip, tiles))
        else:
            output.extend(byte_lines(data[skip:]))
        target = gen / f'rolling_{group}_{bank}.s'
        write_if_changed(target,'\n'.join(output)+'\n')
        result.append(target)
    return result


def validate_layout(symbols):
    directory = symbols['rom_slope_find'] >> 16
    first = symbols['rom_slope_inputs_0'] >> 16
    if (symbols['rom_slope_find'] & 65535 != 0x4000 or
            symbols['rom_slope_output_addresses'] != (directory<<16)+0x4100):
        raise ValueError('Invalid rolling hash directory entry addresses')
    readers = 0
    for label,address in symbols.items():
        if not label.startswith('rolling_payload_'):
            continue
        bank = int(label.removeprefix('rolling_payload_'))
        start = (bank<<16)+0x4000
        if (symbols.get(f'_level_bank_{bank}') != start or
                address != start+(512 if bank==directory else 2048)):
            raise ValueError(f'Invalid rolling payload placement in scenery bank {bank}')
        if bank==directory:
            continue
        readers += 1
        for i in range(4):
            for kind in ('inputs','project'):
                entry = f'rom_slope_{kind}_{i}'
                name = entry if bank==first else f'rom_slope_{kind}_{bank}_{i}'
                if symbols.get(name) != (bank<<16)+(symbols[entry]&65535):
                    raise ValueError(f'Rolling bank {bank} needs a common {kind} entry address')
    if readers != len(TANGENTS)//4:
        raise ValueError('Missing linked rolling product readers')
