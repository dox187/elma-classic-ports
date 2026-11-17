"""Compare production frame preparation with frozen C in an isolated SM83 ROM.

DMA is replaced with an identical recorder in both translation units. Native
calls must select the same bank, source bytes, tile destinations and lengths,
and preserve the same head publication state across repeated display frames.
An independent integer model also checks every resulting frame selection.
"""

import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import struct
import subprocess

from pyboy import PyBoy


BASE = Path(__file__).resolve().parents[1]
FROZEN_PREPARE = r'''
void bike_render_prepare(const gbc_bike_t *bike) {
    uint8_t angle,compression,body,head,wheel,bank,oldbank,i,phase;
    uint16_t fraction;
    uint16_t frame;
    int16_t projection,rx,ry;
    angle=(uint8_t)((bike->body.angle+1024U)>>11)&31;
    rx=(int16_t)((bike->rider.x-bike->body.x)>>8);
    ry=(int16_t)((bike->rider.y-bike->body.y)>>8);
    if(rx < -256 || rx > 256 || ry < -256 || ry > 256)compression=2;
    else {
        projection=((rx*riding_up_x[angle])>>1)-((ry*riding_up_y[angle])>>1);
        compression=projection<5933 ? 0 : projection>8372 ? 2 : 1;
    }
    body=(bike->turned ? 96 : 0)+compression*32+angle;
    fraction=(uint16_t)bike->head.x;
    fraction=(fraction<<3)+(fraction<<2);
    phase=fraction>>15;
    fraction=0-(uint16_t)bike->head.y;
    fraction=(fraction<<3)+(fraction<<2);
    phase|=(fraction>>15)<<1;
    head=(((bike->turned ? 32 : 0)+angle)<<2)|phase;
    oldbank=CURRENT_BANK;
    prepared_changed=body!=last_body;
    VBK_REG=1;
    if(body!=last_body) {
        bank=body>>6;
        SWITCH_ROM(10+bank);
        upload(192,16,riding_bodies[bank]+((uint16_t)(body&63)<<8));
        last_body=body;
    }
    __critical {frame=sys_time;}
    if(head!=last_head && (last_head==256 || frame!=head_upload_frame)) {
        head_tile=head_tile==BIKE_HEAD_TILE ? BIKE_HEAD_BACK_TILE : BIKE_HEAD_TILE;
        SWITCH_ROM(13);
        upload(head_tile,1,riding_heads+((uint16_t)head<<5));
        shadow_OAM[12].tile=head_tile;
        head_upload_frame=frame;
        last_head=head;
    }
    for(i=0;i<2;++i) {
        wheel=(uint8_t)((bike->wheel[i].angle+4096U)>>13)&7;
        if(wheel!=last_wheel[i]) {
            SWITCH_ROM(13);
            upload(208+i*4,4,riding_wheels+((uint16_t)wheel<<6));
            last_wheel[i]=wheel;
        }
    }
    SWITCH_ROM(oldbank);
    VBK_REG=0;
    prepared=1;
}
'''

FIXTURE = r'''
#include <gb/gb.h>
#include <gb/cgb.h>
#include <stddef.h>
#include <string.h>
#include "bike_render16.h"
#include "riding_assets.h"
static uint8_t last_body,last_wheel[2],head_tile,prepared,prepared_changed;
static uint16_t last_head,head_upload_frame;
static uint8_t count,records[20];
static void upload(uint8_t tile,uint8_t length,const uint8_t *source) {
    uint8_t *p=records+count*5;
    p[0]=CURRENT_BANK;p[1]=tile;p[2]=length;
    p[3]=(uint16_t)source;p[4]=(uint16_t)source>>8;++count;
}
'''

SUFFIX = r'''
void reset_KIND(void) {
    last_body=last_wheel[0]=last_wheel[1]=255;
    last_head=256;head_tile=BIKE_HEAD_TILE;
    head_upload_frame=0;prepared=0;
}
void run_KIND(const gbc_bike_t *bike,uint8_t *out) {
    count=0;memset(records,0,20);shadow_OAM[12].tile=head_tile;
    bike_render_prepare(bike);
    out[0]=last_body;out[1]=last_wheel[0];out[2]=last_wheel[1];
    out[3]=last_head;out[4]=last_head>>8;
    out[5]=head_upload_frame;out[6]=head_upload_frame>>8;
    out[7]=head_tile;out[8]=prepared_changed;
    out[9]=prepared;out[10]=shadow_OAM[12].tile;
    out[11]=VBK_REG&1;out[12]=CURRENT_BANK;out[13]=count;
    memcpy(out+14,records,20);
}
'''


def signed(value, bits=32):
    return ((value + (1 << (bits - 1))) & ((1 << bits) - 1)) - (1 << (bits - 1))


def vectors(up_x, up_y):
    rng = random.Random(0xB1CE091)
    rows = []

    def add(rx, ry, angle, turned=None, head=None, wheels=None):
        bx, by = (rng.randrange(-2**31, 2**31) for _ in range(2))
        # Independent low-byte borrows and discarded high-byte differences.
        dx = (rx << 8) + rng.randrange(256) + (rng.randrange(256) << 24)
        dy = (ry << 8) + rng.randrange(256) + (rng.randrange(256) << 24)
        rider = signed(bx + dx), signed(by + dy)
        if head is None:
            head = tuple(rng.randrange(-2**31, 2**31) for _ in range(2))
        if wheels is None:
            wheels = tuple(rng.randrange(65536) for _ in range(2))
        if turned is None:
            turned = (0, 1, 2, 128, 255)[len(rows) % 5]
        poses = [(bx, by, angle & 65535)]
        poses += [(rng.randrange(-2**31, 2**31), rng.randrange(-2**31, 2**31), a)
                  for a in wheels]
        poses += [(*rider, rng.randrange(65536)), (*head, rng.randrange(65536))]
        raw = b''.join(struct.pack('<iiH', *pose) for pose in poses)
        rows.append(raw + bytes((rng.randrange(256), turned)))

    limits = (-32768, -257, -256, -255, -1, 0, 1, 255, 256, 257, 32767)
    for angle in range(32):
        for rx in limits:
            for ry in limits:
                for turned in (0, 1):
                    add(rx, ry, angle << 11, turned)
        # Both sides of every reachable compression transition, including
        # odd signed products whose individual floors must not be combined.
        for rx in (-256, -255, -129, -1, 0, 1, 127, 128, 255, 256):
            for threshold in (5933, 8373):
                y = min(range(-256, 257), key=lambda ry:
                        abs(((rx * up_x[angle]) >> 1) -
                            ((ry * up_y[angle]) >> 1) - threshold))
                for ry in (y - 1, y, y + 1):
                    add(rx, ry, angle << 11)
    for angle in range(32):
        for offset in (-1025, -1024, -1023, 0, 1023, 1024, 1025):
            for turned in (0, 1, 2, 128, 255):
                wheel = ((angle & 7) * 8192 + offset * 4) & 65535
                add(77, 113, angle * 2048 + offset, turned,
                    wheels=(wheel, (wheel + 1) & 65535))
    for step in range(24):
        boundary = (step * 65536 + 23) // 24
        for offset in (-2, -1, 0, 1, 2):
            add(0, 128, rng.randrange(65536),
                head=(boundary + offset, -(boundary - offset)))
    for _ in range(4096):
        bound = 257 if rng.randrange(2) else 32768
        add(rng.randrange(-bound, bound), rng.randrange(-bound, bound),
            rng.randrange(65536))

    last_body, last_head, head_frame, head_tile = 255, 256, 0, 216
    result = []
    for index, raw in enumerate(rows):
        poses = [struct.unpack_from('<iiH', raw, i * 10) for i in range(5)]
        rx = signed(signed(poses[3][0] - poses[0][0]) >> 8, 16)
        ry = signed(signed(poses[3][1] - poses[0][1]) >> 8, 16)
        angle = ((poses[0][2] + 1024) >> 11) & 31
        in_range = -256 <= rx <= 256 and -256 <= ry <= 256
        projection = ((rx * up_x[angle]) >> 1) - ((ry * up_y[angle]) >> 1)
        compression = 2 if not in_range else 0 if projection < 5933 else 2 if projection > 8372 else 1
        body = (96 if raw[51] else 0) + compression * 32 + angle
        phase = ((poses[4][0] * 12) & 65535) >> 15
        phase |= (((-poses[4][1] * 12) & 65535) >> 15) << 1
        head = (((32 if raw[51] else 0) + angle) << 2) | phase
        # Three preparations per frame, including the uint16 frame rollover.
        frame = (index // 3 + 65530) & 65535
        if head != last_head and (last_head == 256 or frame != head_frame):
            last_head, head_frame = head, frame
            head_tile = 218 if head_tile == 216 else 216
        wheels = [((pose[2] + 4096) >> 13) & 7 for pose in poses[1:3]]
        expected = struct.pack('<BBBHHBB', body, *wheels, last_head,
                               head_frame, head_tile, body != last_body)
        last_body = body
        result.append(raw + struct.pack('<H', frame) + expected + bytes((in_range,)))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=BASE.parents[1] / 'build/v091-bike-prepare')
    parser.add_argument('--gen', type=Path, default=BASE / 'build/gen')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    source = BASE / 'src/bike_render16.c'
    original = source.read_text()
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    start = original.index('/* The cast after >>8')
    prepare = original.index('void bike_render_prepare')
    end = original.index('\nvoid bike_render_draw', prepare)
    helper, candidate = original[start:prepare], original[prepare:end]
    meta = (args.gen / 'riding_meta.c').read_text()
    up = [list(map(int, re.findall(r'-?\d+', re.search(
        r'riding_up_' + axis + r'\[\]\s*=\s*\{(.*?)\}', meta, re.S)[1])))
        for axis in ('x', 'y')]
    rows = vectors(*up)
    sources = []
    calls = []
    declarations = '#include <stdint.h>\ntypedef struct{uint8_t bike[52];uint16_t frame;uint8_t expected[9],in_range;}case_t;\n'
    for bank, first in enumerate(range(0, len(rows), 256), 16):
        block = rows[first:first + 256]
        name = f'cases_{bank}'
        declarations += f'extern const uint8_t {name}[];\n'
        path = out / f'{name}.c'
        path.write_text(f'#include <stdint.h>\n#pragma bank {bank}\nconst uint8_t {name}[]={{' +
                        ','.join(map(str, b''.join(block))) + '};\n')
        sources.append(path)
        calls.append(f'SWITCH_ROM({bank});batch((const case_t *){name},{len(block)},{bank});')
    (out / 'vectors.h').write_text(declarations)
    for kind, body in (('baseline', FROZEN_PREPARE), ('fast', helper + candidate)):
        path = out / f'fixture_{kind}.c'
        path.write_text('#define bike_render_prepare prepare_' + kind + '\n' +
                        FIXTURE + body + SUFFIX.replace('KIND', kind))
        sources.append(path)
    (out / 'assets.c').write_text('''#include "riding_assets.h"
const uint8_t riding_body_0[1]={0},riding_body_1[1]={0},riding_body_2[1]={0};
const uint8_t riding_heads[1]={0},riding_wheels[1]={0};
''' + meta)
    sources.append(out / 'assets.c')
    (out / 'driver.c').write_text(r'''
#include <gb/gb.h>
#include <gb/cgb.h>
#include <string.h>
#include "bike_render16.h"
#include "vectors.h"
void run_baseline(const gbc_bike_t *,uint8_t *);
void run_fast(const gbc_bike_t *,uint8_t *);
void reset_baseline(void);void reset_fast(void);
uint8_t guarded_bike[56],snapshot[56],baseline[38],fast[38];
volatile uint16_t completed,failures,model_failures,guard_failures,bank_failures,irq_failures;
volatile uint8_t done,case_in_range;
typedef char vector_size[sizeof(case_t)==64?1:-1];
static void batch(const case_t *source,uint16_t length,uint8_t bank) {
    uint16_t i;case_t v;
    for(i=0;i<length;++i){
        memcpy(&v,source+i,sizeof(v));case_in_range=v.in_range;
        memset(guarded_bike,0xa5,56);memcpy(guarded_bike+2,v.bike,52);
        memcpy(snapshot,guarded_bike,56);
        memset(baseline,0xa5,38);memset(fast,0xa5,38);
        SWITCH_ROM(9);sys_time=v.frame;IE_REG=0;IF_REG=4;
        run_baseline((const gbc_bike_t *)(guarded_bike+2),baseline+2);
        run_fast((const gbc_bike_t *)(guarded_bike+2),fast+2);
        if(memcmp(baseline,fast,38))++failures;
        if(memcmp(fast+2,v.expected,9))++model_failures;
        if(memcmp(snapshot,guarded_bike,56)||fast[0]!=0xa5||fast[1]!=0xa5||fast[36]!=0xa5||fast[37]!=0xa5)++guard_failures;
        if(CURRENT_BANK!=9||fast[13]||fast[14]!=9)++bank_failures;
        if(IE_REG||(IF_REG&31)!=4)++irq_failures;
        SWITCH_ROM(bank);++completed;
    }
}
void main(void){
    disable_interrupts();DISPLAY_OFF;cpu_fast();TAC_REG=0;SC_REG=0;
    reset_baseline();reset_fast();
''' + '\n'.join(calls) + '\ndone=1;while(1){}\n}\n')
    compiler = BASE / '.toolchain/gbdk/bin/lcc'
    flags = ['-msm83:gb', '-Wf--opt-code-size', '-Wf--max-allocs-per-node', '-Wf100000',
             '-I' + str(BASE / 'src'), '-I' + str(args.gen.resolve()), '-I' + str(out)]
    command = [str(compiler), *flags, '-Wm-yC', '-Wm-yt0x19', '-Wm-yoA',
               '-Wl-m', '-Wl-j', '-o', str(out / 'check.gbc'),
               str(out / 'driver.c'), *map(str, sources)]
    subprocess.run(command, check=True, capture_output=True, text=True)
    symbols = {name: int(value, 16) for name, value in re.findall(
        r'DEF (_\w+) 0x([0-9a-fA-F]+)', (out / 'check.noi').read_text())}
    emulator = PyBoy(str(out / 'check.gbc'), window='null', sound_emulated=False, cgb=True)
    emulator.set_emulation_speed(0)
    active, returns = [], set()
    timing = {kind: {label: [] for label in ('bounded', 'outside')} for kind in ('baseline', 'fast')}

    def returned(key):
        if not active or active[-1][0] != key or active[-1][1] + 2 != emulator.register_file.SP:
            return
        _, _, kind, label, start = active.pop()
        timing[kind][label].append(emulator._cycles() - start)

    def entered(kind):
        sp = emulator.register_file.SP
        ret = emulator.memory[sp] + 256 * emulator.memory[sp + 1]
        key = (0 if ret < 0x4000 else emulator.memory[symbols['__current_bank']], ret)
        if key not in returns:
            emulator.hook_register(*key, returned, key)
            returns.add(key)
        label = 'bounded' if emulator.memory[symbols['_case_in_range']] else 'outside'
        active.append((key, sp, kind, label, emulator._cycles()))

    for kind in timing:
        address = symbols['_prepare_' + kind]
        emulator.hook_register(address >> 16, address & 65535, entered, kind)
    try:
        for _ in range(1200):
            emulator.tick(100, False)
            if emulator.memory[symbols['_done']]:
                break

        def read(name, length=2):
            address = symbols['_' + name]
            return int.from_bytes(bytes(emulator.memory[address:address + length]), 'little')

        report = {name: read(name) for name in ('completed', 'failures', 'model_failures',
                  'guard_failures', 'bank_failures', 'irq_failures')}
        report.update(done=read('done', 1), expected_cases=len(rows), source_sha256=source_hash,
                      prepare_cycles={kind: {label: {'calls': len(values), 'min': min(values),
                          'mean': sum(values) / len(values), 'max': max(values)}
                          for label, values in groups.items()} for kind, groups in timing.items()})
    finally:
        emulator.stop(save=False)
    # Compile complete production units as well: the measured ROM/RAM delta
    # includes the helper, compiler spill changes and the unmodified DMA code.
    size = {}
    baseline = original[:start] + FROZEN_PREPARE + original[end:]
    for kind, content in (('baseline_size', baseline), ('fast_size', original)):
        path = out / (kind + '.c')
        path.write_text(content)
        subprocess.run([str(compiler), *flags, '-c', '-Wa-l', '-o', str(path.with_suffix('.o')),
                        str(path)], check=True, capture_output=True, text=True)
        size[kind] = {name: int(value, 16) for name, value in re.findall(
            r'^A (_CODE|_DATA) size ([0-9A-Fa-f]+)', path.with_suffix('.o').read_text(), re.M)}
    report['object_bytes'] = size
    report['rom_delta'] = size['fast_size']['_CODE'] - size['baseline_size']['_CODE']
    report['ram_delta'] = size['fast_size']['_DATA'] - size['baseline_size']['_DATA']
    report['current_full_rom_maps'] = {}
    for profile in ('4m', '8m'):
        path = BASE / ('build/elma-gbc-v0.91-' + profile + '.map')
        if path.exists():
            areas = re.findall(r'^(_CODE|_HOME|_INITIALIZER|_GSINIT|_GSFINAL)\s+([0-9A-Fa-f]+)\s+([0-9A-Fa-f]+)\s+=', path.read_text(), re.M)
            last = max(int(address, 16) + int(length, 16) for _, address, length in areas)
            report['current_full_rom_maps'][profile] = {
                'rom0_end': last, 'free_bytes': 0x4000 - last,
                'projected_free_bytes': 0x4000 - last - report['rom_delta']}
            assert last + report['rom_delta'] <= 0x4000
    assert source_hash == hashlib.sha256(source.read_bytes()).hexdigest(), 'Production source changed during check'
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    assert report['done'] and report['completed'] == len(rows), report
    assert not any(report[name] for name in ('failures', 'model_failures', 'guard_failures',
                                            'bank_failures', 'irq_failures')), report


if __name__ == '__main__':
    main()
