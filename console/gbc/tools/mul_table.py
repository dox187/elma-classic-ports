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
    # Each 32-input group crosses at most one contact-point rounding
    # boundary. Its first value differs by 0..6 from the high-byte base.
    # Groups repeat after 64 high bytes, when the base increases by length.
    rows.append('_riding_contact_high::')
    for length in range(404, 410):
        rnd = lambda value: (value*length + 8192) >> 14
        bases = [rnd(((digit ^ 128) - 128)*256) for digit in range(256)]
        pages = [[(v >> shift) & 255 for v in bases] for shift in (0, 8)]
        groups = []
        for group in range(512):
            start = group * 32
            first = rnd(start)
            delta = first - rnd(start & ~255)
            last = next((x-1 for x in range(1, 32) if rnd(start+x) != first), 31)
            assert 0 <= delta < 8 and rnd(start+31) - first <= 1
            groups.append(last*8 + delta)
        for data in (*pages, groups):
            rows.extend(' .db '+','.join(map(str, data[i:i+32])) for i in range(0, len(data), 32))
    rows.append('_riding_merge_limit::')
    limits = [isqrt(102**2 - 1 - x*x) for x in range(102)]
    rows.extend(' .db '+','.join(map(str, limits[i:i+24])) for i in range(0, 102, 24))
    write_if_changed(path, '\n'.join(rows) + '\n')
    return path


def object_circles(gen):
    """Store the first exterior Y for the original inclusive pickup radii."""
    from head_clearance import write_if_changed
    lines = ['.module object_circle_limits']
    for radius, bank, label in ((819, 31, 'wheel'), (653, 31, 'head')):
        lines.extend((f'.area _CODE_{bank}', f'_object_{label}_limit::'))
        values = [isqrt(radius*radius-x*x)+1 if x <= radius else 0 for x in range(821)]
        lines.extend(' .dw '+','.join(map(str, values[i:i+16])) for i in range(0, 821, 16))
    target = gen/'object_circle_limits.s'
    write_if_changed(target, '\n'.join(lines)+'\n')
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    generate(parser.parse_args().out)
