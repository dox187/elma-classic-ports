"""Losslessly reorder an existing original-LGR atlas for global 8x16 OBJ mode.

No resampling, color fitting or physical model changes occur here. Link these
alternative body/parts files with the ORIGINAL riding_meta.c; symbol names and
192 body-frame indices remain unchanged.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

BODY_ORDER=(0,4,1,5,2,6,3,7,8,12,9,13,10,14,11,15)
WHEEL_ORDER=(0,2,1,3)


def read_array(path,name):
    match=re.search(r'\b'+re.escape(name)+r'\s*\[\s*\]\s*=\s*\{(.*?)\};',path.read_text(),re.S)
    if not match:raise ValueError('Missing array '+name+' in '+str(path))
    return bytes(int(token,0)for token in re.findall(r'0x[0-9a-fA-F]+|\d+',match[1]))


def array(name,data):
    rows=[','.join(str(v)for v in data[i:i+32])for i in range(0,len(data),32)]
    return 'const uint8_t '+name+'[]={\n'+',\n'.join(rows)+'\n};\n'


def paired_metadata(gen):
    """Fold two source visibility bits into each physical 8x16 sprite."""
    source = (gen / 'riding_meta.c').read_text()
    pattern = r'const uint16_t riding_masks\[\]\s*=\s*\{([^}]*)\};'
    match = re.search(pattern, source)
    if match is None:
        raise ValueError('Missing original 8x8 body visibility masks')
    masks = [int(v.strip(), 0) for v in match[1].split(',') if v.strip()]
    if len(masks) != 192 or any(not 0 <= v <= 0xffff for v in masks):
        raise ValueError('Expected a 16-sprite visibility mask for each of the 192 body frames')
    pairs = [sum(bool(mask & ((1 << top) | (1 << bottom))) << bit
                 for bit, (top, bottom) in enumerate(zip(BODY_ORDER[::2], BODY_ORDER[1::2])))
             for mask in masks]
    dst = gen / 'riding16_meta.c'
    data = source[:match.start()] + array('riding_body_pair_masks', pairs) + source[match.end():]
    if not dst.exists() or dst.read_text() != data:
        dst.write_text(data)
    return dst


def reorder(data,order):
    stride=len(order)*16
    if len(data)%stride:raise ValueError('Incomplete tile frame')
    result=bytearray()
    for offset in range(0,len(data),stride):
        frame=data[offset:offset+stride]
        encoded=b''.join(frame[tile*16:tile*16+16]for tile in order)
        restored=bytearray(stride)
        for tile,original in enumerate(order):restored[original*16:original*16+16]=encoded[tile*16:tile*16+16]
        if restored!=frame:raise AssertionError('Tile permutation was not lossless')
        result.extend(encoded)
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source','--in',dest='source',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    sources={};outputs={}
    for bank in range(3):
        path=a.source/('riding_body_%d.c'%bank)
        data=read_array(path,'riding_body_%d'%bank)
        if len(data)!=16384:raise ValueError('Body bank must contain 64 complete frames')
        encoded=reorder(data,BODY_ORDER)
        (a.out/('riding16_body_%d.c'%bank)).write_text('#include <stdint.h>\n#pragma bank %d\n'%(10+bank)+array('riding_body_%d'%bank,encoded))
        sources[path.name]=hashlib.sha256(data).hexdigest();outputs['body%d'%bank]=hashlib.sha256(encoded).hexdigest()
    parts=a.source/'riding_parts.c'
    head=read_array(parts,'riding_heads');wheel=read_array(parts,'riding_wheels')
    if len(head)!=256*16 or len(wheel)!=8*64:raise ValueError('Expected 256 half-pixel head frames and 8 wheel phases')
    heads=b''.join(head[i:i+16]+bytes(16)for i in range(0,len(head),16))
    wheels=reorder(wheel,WHEEL_ORDER)
    if any(heads[i*32:i*32+16]!=head[i*16:i*16+16]or any(heads[i*32+16:i*32+32])for i in range(256)):
        raise AssertionError('Head padding changed original pixels')
    (a.out/'riding16_parts.c').write_text('#include <stdint.h>\n#pragma bank 13\n'+array('riding_heads',heads)+array('riding_wheels',wheels))
    report={'conversion':'lossless 8x8 tile pairing; same original-LGR colors and pixels',
            'body_frames':192,'body_permutation':BODY_ORDER,'wheel_permutation':WHEEL_ORDER,
            'head_frames':256,'head_frame_bytes':32,'head_bottom':'transparent',
            'body_oam':8,'wheels_oam':4,'head_oam':1,'bike_oam':13,
            'max_bike_sprites_per_scanline':9,'head_vram_pairs':[[216,217],[218,219]],
            'sprite_vram_range':[192,219],'body_source_sha256':sources,'body_output_sha256':outputs,
            'original_head_sha256':hashlib.sha256(head).hexdigest(),'original_wheel_sha256':hashlib.sha256(wheel).hexdigest(),
            'parts_bank_bytes':len(heads)+len(wheels),'metadata':'link original riding_meta.c unchanged'}
    (a.out/'riding16-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()
