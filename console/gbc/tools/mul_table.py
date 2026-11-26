"""Exact quarter-square lookup table for signed 16-bit physics products.

Q(n)=floor(n*n/4), n=0..65535, stored little-endian in MBC5 banks20..35.
The only additional sum (65536) is handled directly in the ROM0 routine.
No input game data is embedded in these mathematical tables.
"""
import argparse
import hashlib
import json
from pathlib import Path


def generate(out):
    out=Path(out)
    out.mkdir(parents=True,exist_ok=True)
    records=[]
    for bank in range(20,36):
        first=(bank-20)*4096
        data=b''.join((n*n//4).to_bytes(4,'little')for n in range(first,first+4096))
        rows=[','.join(str(x)for x in data[i:i+32])for i in range(0,len(data),32)]
        name='physics_quarter_%d'%bank
        (out/(name+'.c')).write_text('#include <stdint.h>\n#pragma bank %d\n'%bank
            +'const uint8_t '+name+'[]={\n'+',\n'.join(rows)+'\n};\n')
        records.append({'bank':bank,'first_index':first,'bytes':len(data),
                        'sha256':hashlib.sha256(data).hexdigest()})
    (out/'physics-quarter-manifest.json').write_text(json.dumps(
        {'formula':'floor(n*n/4)','entries':65536,'bytes':262144,'banks':records,
         'special_index':65536,'special_value':1073741824},indent=2)+'\n')
    print('Exact signed16 multiplication table: 256 KiB in MBC5 banks20..35')


def scheduled_squares(gen):
    """Store each unsigned24 square in a directly addressed four-byte slot."""
    from head_clearance import write_if_changed
    path = gen / 'physics_small_squares.s'
    rows = ['.module physics_small_squares', '.area _CODE_28', '_riding_small_squares::']
    for first in range(0, 4096, 8):
        row = b''.join((v*v).to_bytes(4, 'little') for v in range(first, first+8))
        rows.append(' .db '+','.join(map(str, row)))
    write_if_changed(path, '\n'.join(rows) + '\n')
    return path


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    generate(parser.parse_args().out)
