"""Exact quarter-square lookup table for signed 16-bit physics products.

Q(n)=floor(n*n/4), n=0..65535, stored little-endian in MBC5 banks20..35.
The only additional sum (65536) is handled directly in the ROM0 routine.
No input game data is embedded in these mathematical tables.
"""
import argparse
import hashlib
import json
from math import isqrt
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
    """Square low bytes repeat every 256 inputs; share that page across rows."""
    from head_clearance import write_if_changed
    path = gen / 'physics_small_squares.s'
    rows = ['.module physics_small_squares', '.area _CODE_28', '_riding_small_squares::']
    def page(first, shift):
        values = [(v*v >> shift) & 255 for v in range(first, first + 256)]
        rows.extend(' .db ' + ','.join(map(str, values[i:i+32])) for i in range(0, 256, 32))
    page(0, 0)
    rows.append('_riding_endpoint_square_rows::')
    for first in range(-512, 4096, 256):
        if first == 0:
            rows.append('_riding_square_rows::')
        page(first, 8)
        page(first, 16)
    rows.append('_riding_merge_limit::')
    limits = [isqrt(102**2 - 1 - x*x) for x in range(102)]
    rows.extend(' .db '+','.join(map(str, limits[i:i+24])) for i in range(0, 102, 24))
    write_if_changed(path, '\n'.join(rows) + '\n')
    return path


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    generate(parser.parse_args().out)
