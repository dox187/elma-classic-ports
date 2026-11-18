"""Pack all original internal collision levels for banked GBC contact queries."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'console/snes/tools'))
from elmadata import Resource, internal_levels

BANK_SIZE = 16384
DESCRIPTOR_BANK = 15
FIRST_BANK = 44
DENSE_THRESHOLD = 16
SEG_INTERNAL_START = 0x4000
SEG_INTERNAL_END = 0x8000


def roundi(x):
    return math.floor(x+.5)


class BankPacker:
    """Every allocation remains within one physical MBC5 ROM bank."""
    def __init__(self, first):
        self.first = first
        self.banks = [bytearray()]

    @property
    def bank(self):
        return self.first+len(self.banks)-1

    def allocate(self, data):
        assert 0 < len(data) <= BANK_SIZE
        if len(self.banks[-1])+len(data) > BANK_SIZE:
            self.banks.append(bytearray())
        bank, address = self.bank, 0x4000+len(self.banks[-1])
        self.banks[-1].extend(data)
        assert bank < 512, 'collision data exceeds the MBC5 address space'
        return bank, address


def geometry(level):
    points = [p for grass,poly in level.polygons if not grass for p in poly]
    ox = math.floor(min(x for x,y in points))-2
    oy = math.floor(min(y for x,y in points))-2
    width = math.ceil((max(x for x,y in points)-ox+2)/4)
    height = math.ceil((max(y for x,y in points)-oy+2)/4)
    assert width < 255 and height < 255
    segments, original_edges = [], 0
    for grass,poly in level.polygons:
        if grass:
            continue
        for i,(x,y) in enumerate(poly):
            original_edges += 1
            qx,qy = poly[(i+1)%len(poly)]
            dx,dy = qx-x,qy-y
            pieces = int(math.hypot(dx,dy)/8)+1
            for k in range(pieces):
                px = roundi((x-ox+dx*k/pieces)*1024)
                py = roundi((y-oy+dy*k/pieces)*1024)
                ex = roundi((x-ox+dx*(k+1)/pieces)*1024)
                ey = roundi((y-oy+dy*(k+1)/pieces)*1024)
                vx,vy = ex-px,ey-py
                length = math.hypot(vx,vy)
                if length < .5:
                    continue
                # Subdivision points are not vertices of the original polygon.
                # Keep them out of radial endpoint contact generation.
                encoded_length = roundi(length)
                assert encoded_length < 0x4000
                if k: encoded_length |= SEG_INTERNAL_START
                if k+1 < pieces: encoded_length |= SEG_INTERNAL_END
                if encoded_length >= 0x8000: encoded_length -= 0x10000
                segments.append((px,py,vx,vy,roundi(vx/length*16384),
                                 roundi(vy/length*16384),encoded_length))
    cells = [[] for _ in range(width*height)]
    for segment in segments:
        px,py,dx,dy,*_ = segment
        # Inclusive intersection with the 0.5 m margin used by the old grid.
        x0 = max(0,math.ceil((min(px,px+dx)-4608)/4096))
        x1 = min(width-1,(max(px,px+dx)+512)//4096)
        y0 = max(0,math.ceil((min(py,py+dy)-4608)/4096))
        y1 = min(height-1,(max(py,py+dy)+512)//4096)
        for cy in range(y0,y1+1):
            for cx in range(x0,x1+1):
                cells[cy*width+cx].append(segment)
    return ox,oy,width,height,segments,cells,original_edges


def overlaps(segment, x,y,size):
    px,py,dx,dy,*_ = segment
    return not (max(px,px+dx)<x-512 or min(px,px+dx)>x+size+512 or
                max(py,py+dy)<y-512 or min(py,py+dy)>y+size+512)


def record(segment,cx,cy):
    px,py,dx,dy,ex,ey,length = segment
    px -= cx*4096
    py -= cy*4096
    values = px,py,dx,dy,ex,ey,length
    assert all(-32768<=v<=32767 for v in values)
    def box(v):
        return max(0,min(255,(v>>6)+128))
    bounds = (box(min(px,px+dx)-410),box(max(px,px+dx)+410),
              box(min(py,py+dy)-410),box(max(py,py+dy)+410))
    return struct.pack('<hhhhhhhBBBB',*values,*bounds)


def pack_level(level,index,packer):
    ox,oy,width,height,segments,cells,edge_count = geometry(level)
    base = packer.bank
    directory = bytearray()
    dedup = {}
    maximum = references = subdivisions = 0
    def pointer(data,count):
        if not count:
            return b'\0\0\0\0'
        if data not in dedup:
            dedup[data] = packer.allocate(data)
        bank,address = dedup[data]
        assert 0 <= bank-base <= 255
        return struct.pack('<HBB',address,bank-base,count)
    for ci,cell in enumerate(cells):
        cx,cy = ci%width,ci//width
        if len(cell) <= DENSE_THRESHOLD:
            maximum = max(maximum,len(cell))
            references += len(cell)
            directory.extend(pointer(b''.join(record(s,cx,cy) for s in cell),len(cell)))
            continue
        subdivisions += 1
        children = bytearray()
        for sy in range(4):
            for sx in range(4):
                leaf = [s for s in cell if overlaps(s,cx*4096+sx*1024,
                                                  cy*4096+sy*1024,1024)]
                maximum = max(maximum,len(leaf))
                references += len(leaf)
                children.extend(pointer(b''.join(record(s,cx,cy) for s in leaf),len(leaf)))
        directory.extend(pointer(bytes(children),255))
    bank,address = packer.allocate(bytes(directory))
    start_x,start_y = level.start()
    desc = [ox*65536,oy*65536,roundi(start_x*65536),roundi(start_y*65536),
            base,bank,address,width,height]
    report = {'index':index,'name':level.name,'origin_m':[ox,oy],
              'start_q16':desc[2:4],'grid':[width,height],
              'original_edges':edge_count,'split_segments':len(segments),
              'coarse_cell_max':max(map(len,cells)), 'cell_max_segments':maximum,
              'cell_segment_references':references,'subdivided_cells':subdivisions,
              'base_bank':base,'directory_bank':bank,'directory_address':address,
              'objects':len(level.objects)}
    return desc, report


def write_outputs(out,packer,descriptors,reports):
    maximum = max(r['cell_max_segments'] for r in reports)
    header = '''#ifndef GBC_RIDING_LEVEL_H
#define GBC_RIDING_LEVEL_H
#include <stdint.h>
#define RIDING_LEVEL_COUNT %d
#define RIDING_CELL_MAX %d
#define RIDING_FIRST_BANK %d
#define RIDING_BANK_COUNT %d
#define RIDING_DESCRIPTOR_BANK %d
/* Directory: uint16 address, uint8 bank relative to base_bank, uint8 count.
 * Count255 selects a 16-entry 1 m child directory; records use a 4 m origin. */
typedef struct {
 int32_t origin_x,origin_y,start_x,start_y;
 uint16_t base_bank,directory_bank,directory_address;
 uint8_t width,height;
} physics_level_desc_t;
extern const physics_level_desc_t physics_levels[RIDING_LEVEL_COUNT];
#ifndef __SDCC
extern const uint8_t *const physics_bank_data[RIDING_BANK_COUNT];
#endif
extern int32_t physics_level_origin_x,physics_level_origin_y;
extern int32_t physics_level_start_x,physics_level_start_y;
extern uint8_t physics_level_index;
#endif
''' % (len(reports),maximum,packer.first,len(packer.banks),DESCRIPTOR_BANK)
    (out/'riding_level.h').write_text(header)
    source = ['#include "riding_level.h"','#pragma bank %d'%DESCRIPTOR_BANK,
              'const physics_level_desc_t physics_levels[RIDING_LEVEL_COUNT]={']
    for row in descriptors:
        source.append('{'+','.join(str(v)+('L' if i<4 else '') for i,v in enumerate(row))+'},')
    source += ['};','#ifndef __SDCC']
    banks = list(range(packer.first,packer.bank+1))
    source += ['extern const uint8_t physics_bank_%d[];'%bank for bank in banks]
    source += ['const uint8_t *const physics_bank_data[RIDING_BANK_COUNT]={'+
               ','.join('physics_bank_%d'%bank for bank in banks)+'};','#endif']
    (out/'physics_level_data.c').write_text('\n'.join(source)+'\n')
    for path in out.glob('physics_bank_*.c'):
        path.unlink()
    for bank,data in zip(banks,packer.banks):
        data = data + bytes([255])*(BANK_SIZE-len(data))
        rows = [','.join(str(v) for v in data[i:i+32]) for i in range(0,len(data),32)]
        (out/('physics_bank_%d.c'%bank)).write_text('#include <stdint.h>\n#pragma bank %d\n'%bank+
            'const uint8_t physics_bank_%d[16384]={\n'%bank+',\n'.join(rows)+'\n};\n')
    manifest = {'segment_format':'length14-internal-endpoints-v1','descriptor_bank':DESCRIPTOR_BANK,'first_bank':packer.first,
                'banks':banks,'next_free_bank':packer.bank+1,
                'cache_max':maximum,'cache_slots':3,'cache_bytes':3*maximum*18,
                'payload_bytes':sum(map(len,packer.banks)),
                'rom_bytes':len(packer.banks)*BANK_SIZE,'levels':reports}
    (out/'physics_bank_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--res',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--hz',type=int,choices=(30,60),default=30)
    p.add_argument('--damper',choices=('explicit','exponential','scheduled'),default='explicit')
    p.add_argument('--bank-base',type=int,default=FIRST_BANK)
    a = p.parse_args()
    if a.damper == 'scheduled' and a.hz != 30:
        p.error('the scheduled profile requires --hz 30')
    a.out.mkdir(parents=True,exist_ok=True)
    levels = internal_levels(Resource(a.res))
    assert len(levels)<=255
    packer = BankPacker(a.bank_base)
    pairs = [pack_level(level,i,packer) for i,level in enumerate(levels)]
    descriptors,reports = zip(*pairs)
    manifest = write_outputs(a.out,packer,descriptors,reports)
    subprocess.run([sys.executable,str(Path(__file__).with_name('riding_constants.py')),
                    str(a.out/'riding_constants.h'),str(a.hz),a.damper],check=True)
    rate = 4194304/70224*a.hz/60
    h = .4368/rate
    z = 1000*h/10
    report = {'source_res_sha256':hashlib.sha256(a.res.read_bytes()).hexdigest(),
              'level_count':len(levels),'physics_hz':rate,'nominal_hz':a.hz,
              'angle_units':8388608 if a.hz<40 else 16777216,'clock_rate':.4368,
              'core':'original-derived fixed-point C, SM83 math',
              'damper_integrator':a.damper,'physical_damper_Ns_per_m':1000,
              'wheel_mass_kg':10,'spring_N_per_m':10000,'step_game_seconds':h,
              'damper_impulse_ratio':-math.expm1(-z)/z if a.damper=='exponential' else 1.,
              'levels':reports}
    if a.damper == 'scheduled':
        from riding_scheduled_constants import metadata
        report.update(metadata())
        report['damper_integrator'] = 'explicit scheduled substeps'
    (a.out/'riding_level.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in manifest.items() if k!='levels'}))


if __name__=='__main__':
    main()
