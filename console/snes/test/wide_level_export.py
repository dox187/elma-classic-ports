#!/usr/bin/env python3
"""Export exact candidate initialization for a future native level loader.

The binary keeps every cached segment integer and the original grid-list
order. Identical lists and consecutive row cells are shared losslessly.
This is offline preparation; it does not change the production ROM.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess

from wide_probe import ROOT, UNITS


def i64(values):
    return b''.join(struct.pack('<q', x) for x in values)


def pack_lines(lines):
    points=list(dict.fromkeys((line[0],line[1]) for line in lines))
    indices={p:i for i,p in enumerate(points)}
    packed=bytearray(struct.pack('<H',len(points)))
    for point in points:
        for value in point:packed+=value.to_bytes(7,'little',signed=True)
    for line in lines:
        start=tuple(line[:2]);end=(line[0]+line[2],line[1]+line[3])
        assert line[8:10]==[-line[5],line[4]]
        packed+=struct.pack('<2H',indices[start],indices[end])
        for value in line[4:6]:packed+=value.to_bytes(6,'little',signed=True)
        packed+=line[10].to_bytes(7,'little',signed=False)
        packed+=struct.pack('<2h',line[6]-end[0],line[7]-end[1])
    return bytes(packed)


def unpack_lines(blob,count):
    n=struct.unpack_from('<H',blob)[0]
    points=[tuple(int.from_bytes(blob[2+14*i+7*k:2+14*i+7*(k+1)],'little',signed=True)
                  for k in range(2)) for i in range(n)]
    lines=[]
    for i in range(count):
        p=2+14*n+27*i
        start,end=struct.unpack_from('<2H',blob,p);r=points[start];e=points[end]
        unit=[int.from_bytes(blob[p+4+6*k:p+10+6*k],'little',signed=True) for k in range(2)]
        length=int.from_bytes(blob[p+16:p+23],'little')
        dx,dy=struct.unpack_from('<2h',blob,p+23)
        lines.append([*r,e[0]-r[0],e[1]-r[1],*unit,e[0]+dx,e[1]+dy,-unit[1],unit[0],length])
    assert len(blob)==2+14*n+27*count
    return lines


def encode(data,compact_geometry=False):
    width, height = data['grid_shape']
    assert width <= 255 and height <= 255
    unique = {}
    lists = bytearray()
    offsets = []
    for cell in data['cells']:
        key = tuple(cell)
        if key not in unique:
            unique[key] = len(lists)
            assert len(cell) <= 65535
            lists += struct.pack('<H', len(cell))
            for index in cell:
                assert 0 <= index < len(data['lines'])
                lists += struct.pack('<H', index)
        offsets.append(unique[key])
    assert len(lists) <= 65535, 'Grid list section needs wider offsets'
    runs = bytearray()
    rows = bytearray()
    for y in range(height):
        rows += struct.pack('<H', len(runs))
        previous = None
        for x in range(width):
            offset = offsets[y*width+x]
            if offset != previous:
                runs += struct.pack('<BH', x, offset)
                previous = offset
    rows += struct.pack('<H', len(runs))
    assert len(runs) <= 65535, 'Grid runs need wider offsets'
    names = sorted(data['constants'])
    sections = [i64(data['grid_scalars']+data['brush']+data['motor_scalars'])+
                struct.pack('<7h', *data['motor_flags']),
                i64([data['constants'][name] for name in names]),
                b''.join(i64(o[:2])+struct.pack('<4h', *o[2:]) for o in data['objects']),
                pack_lines(data['lines']) if compact_geometry else b''.join(i64(line) for line in data['lines']), bytes(rows), bytes(runs), bytes(lists)]
    version=2 if compact_geometry else 1
    header = bytearray(struct.pack('<4sHHHHHHHH', b'WLV1', version, data['bits'],
                                  len(data['lines']), len(data['objects']), width, height,
                                  len(names), len(sections)))
    start = len(header)+4*(len(sections)+1)
    section_offsets = [start]
    for section in sections:
        start += len(section)
        section_offsets.append(start)
    header += struct.pack('<'+'I'*len(section_offsets), *section_offsets)
    blob = bytes(header)+b''.join(sections)
    return blob, names, {'section_offsets': section_offsets, 'section_bytes': list(map(len, sections)),
                         'unique_grid_lists': len(unique), 'grid_nodes': sum(map(len, data['cells']))}


def verify(data, blob, names):
    magic, version, bits, nlines, nobjects, width, height, nconstants, nsections = struct.unpack_from('<4s8H', blob)
    assert version in (1,2)
    assert (magic,bits,nlines,nobjects,width,height,nconstants,nsections) == (
        b'WLV1',data['bits'],len(data['lines']),len(data['objects']),*data['grid_shape'],len(names),7)
    offsets = struct.unpack_from('<8I', blob, 20)
    assert offsets[-1] == len(blob)
    blocks = [blob[a:b] for a,b in zip(offsets, offsets[1:])]
    values = data['grid_scalars']+data['brush']+data['motor_scalars']
    assert blocks[0] == i64(values)+struct.pack('<7h', *data['motor_flags'])
    assert blocks[1] == i64([data['constants'][name] for name in names])
    for i, original in enumerate(data['objects']):
        assert list(struct.unpack_from('<2q4h', blocks[2], i*24)) == original
    if version==2:
        assert unpack_lines(blocks[3],nlines)==data['lines']
    else:
        for i, original in enumerate(data['lines']):
            assert list(struct.unpack_from('<11q', blocks[3], i*88)) == original
    count = 0
    for y in range(height):
        start, end = struct.unpack_from('<2H', blocks[4], y*2)
        row = [struct.unpack_from('<BH', blocks[5], p) for p in range(start,end,3)]
        assert row[0][0] == 0
        for j, (x, offset) in enumerate(row):
            limit = row[j+1][0] if j+1 < len(row) else width
            n = struct.unpack_from('<H', blocks[6], offset)[0]
            cell = list(struct.unpack_from('<'+'H'*n, blocks[6], offset+2))
            for cx in range(x, limit):
                assert cell == data['cells'][y*width+cx]
                count += 1
    return count


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--levdump', type=Path, default=ROOT/'build/host/levdump')
    ap.add_argument('--levels', default=','.join(map(str, range(54))))
    ap.add_argument('--compact-geometry',action='store_true',help='Losslessly pack shared points, unit normals and cached-endpoint residuals')
    a = ap.parse_args()
    base, out = a.base.resolve(), a.out.resolve()
    if out.exists():
        raise ValueError('Use a fresh output directory')
    out.mkdir(parents=True)
    sources = {}
    for path in base.iterdir():
        if path.is_file() and path.suffix.lower() in ('.h', '.cpp'):
            shutil.copy2(path, out/path.name)
            sources[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    header = out/'szakasz.h'
    source = header.read_text()
    assert source.count('class szakaszok {') == 1
    header.write_text(source.replace('class szakaszok {','class szakaszok {\npublic: // offline export only'))
    shutil.copy2(ROOT/'test/wide_level_export.cpp', out/'wide_level_export.cpp')
    bits = json.loads((base/'build.json').read_text())['bits']
    command = ['c++','-std=c++17','-O2','-w','-DWIDE_BITS='+str(bits),'-I'+str(out),
               '-I'+str(ROOT/'test'),'-o',str(out/'export'),str(out/'wide_level_export.cpp'),
               str(out/'pcphys.cpp'),*[str(out/name) for name in UNITS]]
    result = subprocess.run(command, capture_output=True, text=True)
    (out/'compile.txt').write_text(result.stdout+result.stderr)
    result.check_returncode()
    reports = []
    for level in map(int, a.levels.split(',')):
        result = subprocess.run([str(out/'export'),str(a.levdump/('lev%02d.txt'%level))],
                                capture_output=True, text=True)
        (out/('lev%02d.stderr.txt'%level)).write_text(result.stderr)
        result.check_returncode()
        data = json.loads(result.stdout)
        blob, names, report = encode(data,a.compact_geometry)
        cells = verify(data, blob, names)
        (out/('lev%02d.json'%level)).write_text(result.stdout)
        (out/('lev%02d.bin'%level)).write_bytes(blob)
        report.update(level=level, bytes=len(blob), lines=len(data['lines']), objects=len(data['objects']),
                      exact_grid_cells=cells, sha256=hashlib.sha256(blob).hexdigest(), constant_order=names,
                      native_line_ram_bytes=88*len(data['lines']),
                      native_linked_grid_ram_bytes=4*cells+8*report['grid_nodes'])
        reports.append(report)
    report = {'bits': bits, 'base':str(base), 'sources_sha256':sources, 'levels':reports,
              'format_version':2 if a.compact_geometry else 1,
              'export_driver_sha256':hashlib.sha256((out/'wide_level_export.cpp').read_bytes()).hexdigest(),
              'packer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'total_bytes':sum(r['bytes'] for r in reports),
              'exact_grid_cells':sum(r['exact_grid_cells'] for r in reports),
              'maximum_level_bytes':max(r['bytes'] for r in reports),
              'scope':'Exact offline binary roundtrip; native loader and ROM integration pending'}
    (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('levels','sources_sha256')}))


if __name__ == '__main__':
    main()
