#!/usr/bin/env python3
"""Emit bank-contained exact level sections and four-byte PVSnesLib pointers.

The loader accepts independent far pointers, so no pointer arithmetic crosses
LoROM's unmapped lower32KiB. WLA places each SUPERFREE section in one bank.
Catalog and header overhead replace the contiguous file offsets; payloads
are byte-identical. Native linker-map/ROM verification is separate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--levels',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();levels=args.levels.resolve();out=args.out.resolve()
    if out.exists():raise ValueError('Use a fresh output directory')
    out.mkdir(parents=True)
    report=json.loads((levels/'report.json').read_text())
    entries=[];assembly=['.include "hdr.asm"','.BASE $80']
    for level in report['levels']:
        index=level['level'];blob=(levels/('lev%02d.bin'%index)).read_bytes()
        magic,version,bits,nlines,nobj,width,height,nconst,nparts=struct.unpack_from('<4s8H',blob)
        if (magic,version,nparts)!=(b'WLV1',2,7):raise ValueError('Packed v2 levels required')
        offsets=struct.unpack_from('<8I',blob,20)
        assert offsets[0]==52 and offsets[-1]==len(blob)
        parts=[blob[:20]]+[blob[a:b] for a,b in zip(offsets,offsets[1:])]
        labels=[]
        for part,data in enumerate(parts):
            assert 0<len(data)<=32768, 'Each section must fit one LoROM bank'
            label='wide_level_%02d_part_%d'%(index,part);labels.append(label)
            path=out/(label+'.bin');path.write_bytes(data)
            assembly+=['.SECTION ".'+label+'" SUPERFREE',label+':',
                       '.incbin "'+str(path)+'"','.ENDS']
        entries.append({'level':index,'labels':labels,'section_bytes':list(map(len,parts)),
                        'section_sha256':[hashlib.sha256(p).hexdigest() for p in parts]})
    assert [e['level'] for e in entries]==list(range(len(entries))), 'Catalog needs contiguous level IDs'
    assembly+=['.SECTION ".wide_level_catalog" SUPERFREE','wide_level_catalog:']
    for entry in entries:
        for label in entry['labels']:assembly+=['.dl '+label,'.db 0']
    assembly+=['.ENDS']
    (out/'wide_level_banks.asm').write_text('\n'.join(assembly)+'\n')
    (out/'wide_level_catalog.c').write_text('''#include "wide_port.h"
extern const unsigned char* const wide_level_catalog[][8];
int wp_load_level_parts(const unsigned char*,const unsigned char* const*);
int wp_load_level_id(unsigned int level){
    const unsigned char* const* parts;
    if(level>='''+str(len(entries))+''')return 0;
    parts=wide_level_catalog[level];
    return wp_load_level_parts(parts[0],parts+1);
}
''')
    result={'levels':str(levels),'format':'v2 payloads, eight independent far pointers per level',
            'total_rom_bytes':sum(sum(e['section_bytes'])+32 for e in entries),
            'max_section_bytes':max(max(e['section_bytes']) for e in entries),
            'catalog_bytes':32*len(entries),'entries':entries,
            'scope':'Exact section payload generation; native placement/runtime verification pending'}
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='entries'}))


if __name__=='__main__':main()
