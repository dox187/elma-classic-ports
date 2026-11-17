"""Exact native segment-box iterator, cursor/WRAM guards and paired C timings."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import random
import re
import struct
import subprocess
import sys

from pyboy import PyBoy

BASE = Path(__file__).resolve().parents[1]


def function(source, signature):
    start = source.index(signature)
    end = source.index('{', start)
    depth = 1
    end += 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def vectors():
    rng = random.Random(180914)
    rows = []

    def add(bx, by, boxes, offset=None):
        if offset is None:
            offset = rng.randrange(256)
        rows.append((offset, bx, by, boxes))

    # Each unsigned byte against both ends of fixed and degenerate intervals.
    intervals = [(0, 0), (0, 1), (0, 255), (1, 254), (127, 127),
                 (127, 128), (128, 127), (128, 128), (254, 255),
                 (255, 0), (255, 254), (255, 255)]
    for q in range(256):
        for low, high in intervals + [(q, q), (max(0, q-1), min(255, q+1))]:
            add(q, 255-q, [(low, high, 0, 255)])
            add(255-q, q, [(0, 255, low, high)])
    for bx in (0, 1, 127, 128, 254, 255):
        for by in (0, 1, 127, 128, 254, 255):
            for x0, x1 in intervals:
                for y0, y1 in intervals:
                    add(bx, by, [(x0, x1, y0, y1)])
    # Empty input must not dereference, normalize, or advance any pointer.
    for pointer in (0, 1, 0xff, 0x100, 0x7fff, 0x8000, 0xbfff,
                    0xc000, 0xcfff, 0xdfff, 0xff00, 0xffff):
        for bx, by in ((0, 0), (0, 255), (255, 0), (255, 255)):
            add(bx, by, [], pointer)
    for count in (1, 2, 3, 17, 38, 64, 127, 254, 255):
        for offset in (0, 1, 237, 238, 239, 250, 254, 255):
            for mode in ('none', 'all', 'first', 'last', 'alternate'):
                boxes = []
                for i in range(count):
                    match = (mode == 'all' or mode == 'first' and i == 0 or
                             mode == 'last' and i == count-1 or
                             mode == 'alternate' and i % 2 == 0)
                    boxes.append((0, 255, 0, 255) if match else
                                 ((129, 255, 0, 255), (0, 127, 0, 255),
                                  (0, 255, 129, 255), (0, 255, 0, 127))[i % 4])
                add(128, 128, boxes, offset)
    for _ in range(1024):
        count = rng.choice((1, 2, 3, 8, 17, 38))
        bx, by = rng.randrange(256), rng.randrange(256)
        boxes = []
        for _ in range(count):
            if rng.randrange(4) == 0:
                boxes.append((rng.randrange(bx+1), rng.randrange(bx, 256),
                              rng.randrange(by+1), rng.randrange(by, 256)))
            else:
                boxes.append(tuple(rng.randrange(256) for _ in range(4)))
        add(bx, by, boxes)
    return rows


def check_host(out, gen, reference, next_function, rows):
    path = out/'host.c'
    path.write_text('#include "physics_core.h"\nconst seg_t *Seg_cur;\n'
                    'uint8_t Seg_left;\n' + next_function + '\n' +
                    reference.replace('static const', 'const', 1))
    lib = out/('host.dylib' if sys.platform == 'darwin' else 'host.so')
    subprocess.run(['cc', '-shared', '-fPIC', '-O2', '-I'+str(BASE/'src'),
                    '-I'+str(gen), str(path), '-o', str(lib)], check=True)
    host = C.CDLL(str(lib))
    scan = host.segment_next_box
    scan.argtypes = [C.c_uint8, C.c_uint8]
    scan.restype = C.c_void_p
    cursor = C.c_void_p.in_dll(host, 'Seg_cur')
    left = C.c_uint8.in_dll(host, 'Seg_left')
    calls = 0
    for offset, bx, by, boxes in rows:
        data = b''.join(bytes((i*29+j*17) & 255 for j in range(14)) + bytes(box)
                        for i, box in enumerate(boxes))
        arena = (C.c_uint8*(len(data)+256))()
        C.memmove(C.addressof(arena)+offset, data, len(data)) if boxes else None
        start = C.addressof(arena)+offset if boxes else offset
        cursor.value, left.value = start, len(boxes)
        used = 0
        for _ in range(len(boxes)+2):
            want = 0
            while used < len(boxes):
                box = boxes[used]
                used += 1
                if box[0] <= bx <= box[1] and box[2] <= by <= box[3]:
                    want = start+(used-1)*18
                    break
            got = scan(bx, by) or 0
            assert (got, cursor.value or 0, left.value) == (
                want, start+used*18, len(boxes)-used)
            calls += 1
        if boxes:
            assert bytes(arena)[offset:offset+len(data)] == data
    return calls


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=BASE/'build/segment-scan-check')
    parser.add_argument('--gen', type=Path, default=BASE/'build/gen')
    parser.add_argument('--assembly', type=Path, default=BASE/'src/physics_segment_scan.s')
    parser.add_argument('--contacts', type=Path, default=BASE/'src/physics_contacts.c')
    parser.add_argument('--lcc', type=Path, default=BASE/'.toolchain/gbdk/bin/lcc')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    contacts = args.contacts.read_text()
    reference = function(contacts, 'static const seg_t *segment_next_box(')
    next_function = function((BASE/'src/physics_collision.c').read_text(),
                             'const seg_t *seg_next(void)')
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (args.contacts, args.assembly)}
    rows = vectors()
    host_calls = check_host(out, args.gen, reference, next_function, rows)
    header = '#include <stdint.h>\n'
    sources = []
    bank, block, count = 16, bytearray(), 0

    def emit():
        nonlocal bank, block, count, header
        name = 'vectors'+str(bank)
        path = out/(name+'.c')
        path.write_text(f'#pragma bank {bank}\n#include "vectors.h"\n'
                        f'const uint8_t {name}[]={{'+','.join(map(str, block))+'};\n')
        header += f'extern const uint8_t {name}[];\n#define N{bank} {count}\n'
        sources.append((bank, path))
        bank, block, count = bank+1, bytearray(), 0

    for offset, bx, by, boxes in rows:
        row = struct.pack('<HBBB', offset, len(boxes), bx, by)
        row += b''.join(bytes(box) for box in boxes)
        if len(block)+len(row) > 16000:
            emit()
        block.extend(row)
        count += 1
    if block:
        emit()
    (out/'vectors.h').write_text(header)
    native_reference = reference.replace('static const', 'const', 1).replace(
        'segment_next_box(uint8_t bx,uint8_t by)',
        'reference_segment_box(uint8_t bx,uint8_t by) __sdcccall(0)')
    (out/'reference.c').write_text('#pragma bank 9\n#include "physics_core.h"\n' +
                                 native_reference+'\n')
    (out/'next.c').write_text('#include "physics_core.h"\n'+next_function+'\n')
    (out/'case.c').write_text('''#pragma bank 9
#include <gb/gb.h>
#include <stddef.h>
#include "physics_core.h"
typedef char layout[sizeof(seg_t)==18 && offsetof(seg_t,x0)==14 &&
 offsetof(seg_t,x1)==15 && offsetof(seg_t,y0)==16 && offsetof(seg_t,y1)==17?1:-1];
extern uint8_t bx,by,Seg_subcell;
extern volatile uint32_t calls,failures,cursor_failures,left_failures;
extern volatile uint16_t cases,bank_failures,subcell_failures;
const seg_t *reference_segment_box(uint8_t,uint8_t) __sdcccall(0);
const seg_t *riding_segment_box(uint8_t,uint8_t) __sdcccall(0);
void run_case(void) BANKED {
 const seg_t *before,*want,*after,*got;uint8_t remaining,rest,empty=0;
 for(;;){
  before=Seg_cur;remaining=Seg_left;
  want=reference_segment_box(bx,by);after=Seg_cur;rest=Seg_left;
  Seg_cur=before;Seg_left=remaining;
  got=riding_segment_box(bx,by);
  if(got!=want)++failures;
  if(Seg_cur!=after)++cursor_failures;
  if(Seg_left!=rest)++left_failures;
  if(Seg_subcell!=0xa5)++subcell_failures;
  if(CURRENT_BANK!=9)++bank_failures;
  ++calls;Seg_cur=after;Seg_left=rest;
  if(!want && empty++)break;
 }
 ++cases;
}
''')
    driver = '''#include <gb/gb.h>
#include <gb/cgb.h>
#include "physics_core.h"
#include "vectors.h"
const seg_t *Seg_cur;uint8_t Seg_left,Seg_subcell;
uint8_t arena[4864],bx,by;
volatile uint8_t done;
volatile uint32_t calls,failures,cursor_failures,left_failures;
volatile uint16_t cases,bank_failures,subcell_failures;
void run_case(void) BANKED;
static const uint8_t *prepare(const uint8_t *v){
 uint16_t offset,pos;uint8_t i,j,count;
 offset=*v++;offset|=(uint16_t)*v++<<8;count=*v++;bx=*v++;by=*v++;
 if(count){
  pos=offset+14;
  for(i=0;i<count;++i){for(j=0;j<4;++j)arena[pos++]=*v++;pos+=14;}
  Seg_cur=(const seg_t *)(arena+offset);
 }else Seg_cur=(const seg_t *)offset;
 Seg_left=count;Seg_subcell=0xa5;
 return v;
}
void main(void){uint16_t i;const uint8_t *v;
 disable_interrupts();DISPLAY_OFF;cpu_fast();
 for(i=0;i<sizeof(arena);++i)arena[i]=(uint8_t)(i*17u+0xa5u);
'''
    for bank, _ in sources:
        driver += (f'SWITCH_ROM({bank});v=vectors{bank};for(i=0;i<N{bank};++i){{'
                   f'v=prepare(v);run_case();if(CURRENT_BANK!={bank})++bank_failures;}}\n')
    driver += 'done=1;while(1){} }\n'
    (out/'driver.c').write_text(driver)
    flags = [str(args.lcc), '-msm83:gb', '-Wf--opt-code-size',
             '-Wf--max-allocs-per-node', '-Wf100000',
             '-I'+str(BASE/'src'), '-I'+str(args.gen), '-I'+str(out)]
    cmd = flags + ['-Wm-yC', '-Wm-yt0x19', '-Wm-yoA', '-Wl-m', '-Wl-j',
                   '-o', str(out/'check.gbc'), str(out/'driver.c'),
                   str(out/'case.c'), str(out/'reference.c'), str(out/'next.c'),
                   str(args.assembly)] + [str(path) for _, path in sources]
    compiled = subprocess.run(cmd, capture_output=True, text=True)
    (out/'compile.log').write_text(compiled.stdout+compiled.stderr)
    assert compiled.returncode == 0, compiled.stdout+compiled.stderr
    # Check the real production source and its optional C fallback as objects.
    for name, extra in (('contacts', []), ('contacts-c', ['-DPHYSICS_SEGMENT_SCAN_C'])):
        subprocess.run(flags+extra+['-c', '-o', str(out/(name+'.o')),
                                   str(args.contacts)], check=True, capture_output=True)
    symbols = {key: int(value, 16) for key, value in re.findall(
        r'DEF (_\w+) 0x([0-9a-fA-F]+)', (out/'check.noi').read_text())}
    p = PyBoy(str(out/'check.gbc'), window='null', sound_emulated=False, cgb=True)
    p.set_emulation_speed(0)
    pending, return_sites = [], set()
    timings = {name: {} for name in ('c', 'asm')}
    guard_failures = 0
    guard_first = None
    allowed = {symbols['_Seg_cur']-0xc000, symbols['_Seg_cur']-0xc000+1,
               symbols['_Seg_left']-0xc000}

    def returned(key):
        nonlocal guard_failures, guard_first
        if not pending or pending[-1]['return'] != key or pending[-1]['sp'] != p.register_file.SP-2:
            return
        entry = pending.pop()
        elapsed = p._cycles()-entry['time']
        left = p.memory[symbols['_Seg_left']]
        result = p.register_file.E + 256*p.register_file.D
        consumed = entry['left']-left
        kind = ('empty' if not entry['left'] else 'no_match' if not result else
                'first_match' if consumed == 1 else 'skipped_then_match')
        stat = timings[entry['name']].setdefault(kind, {'calls': 0, 'min': elapsed,
                                                      'max': 0, 'total': 0})
        stat['calls'] += 1
        stat['min'] = min(stat['min'], elapsed)
        stat['max'] = max(stat['max'], elapsed)
        stat['total'] += elapsed
        if entry['name'] == 'asm':
            after = bytes(p.memory[0xc000:0xe000])
            if after != entry['wram']:
                bad = [i for i, (a, b) in enumerate(zip(entry['wram'], after))
                       if a != b and i not in allowed]
                if bad:
                    guard_failures += 1
                    if guard_first is None:
                        guard_first = hex(0xc000+bad[0])
            if bytes(p.memory[0xff80:0xffff]) != entry['hram']:
                guard_failures += 1
            if bytes(p.memory[0x4000:0x4010]) != entry['bank']:
                guard_failures += 1

    def entered(name):
        sp = p.register_file.SP
        # SDCC can put the C while-loop back edge at the function symbol.
        if pending and pending[-1]['name'] == name and pending[-1]['sp'] == sp:
            return
        ret = p.memory[sp]+256*p.memory[sp+1]
        key = (9, ret)
        if key not in return_sites:
            p.hook_register(*key, returned, key)
            return_sites.add(key)
        entry = {'name': name, 'return': key, 'sp': sp, 'time': p._cycles(),
                 'left': p.memory[symbols['_Seg_left']]}
        if name == 'asm':
            entry.update(wram=bytes(p.memory[0xc000:0xe000]),
                         hram=bytes(p.memory[0xff80:0xffff]),
                         bank=bytes(p.memory[0x4000:0x4010]))
        pending.append(entry)

    for name, symbol in (('c', '_reference_segment_box'), ('asm', '_riding_segment_box')):
        address = symbols[symbol]
        assert address >> 16 == 9
        p.hook_register(9, address & 65535, entered, name)
    try:
        for _ in range(1000):
            p.tick(100, False)
            if p.memory[symbols['_done']]:
                break

        def value(name, size):
            address = symbols['_'+name]
            return int.from_bytes(bytes(p.memory[address:address+size]), 'little')

        report = {name: value(name, 4) for name in
                  ('calls', 'failures', 'cursor_failures', 'left_failures')}
        report.update({name: value(name, 2) for name in
                       ('cases', 'bank_failures', 'subcell_failures')})
        for groups in timings.values():
            for stat in groups.values():
                stat['mean'] = stat['total']/stat['calls']
        totals = {name: sum(group['total'] for group in groups.values())
                  for name, groups in timings.items()}
        report.update(done=value('done', 1), expected_cases=len(rows),
                      host_calls=host_calls, host_matches_python=True,
                      maximum_records=255, record_bytes=18,
                      guard_failures=guard_failures, guard_first=guard_first,
                      native_cycles=timings, total_cycles=totals,
                      cycle_reduction=1-totals['asm']/totals['c'],
                      source_sha256=hashes, pending_returns=len(pending))
        (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report, indent=2))
        assert report['done'] and report['cases'] == len(rows)
        assert not any(report[name] for name in ('failures', 'cursor_failures',
                       'left_failures', 'bank_failures', 'subcell_failures',
                       'guard_failures', 'pending_returns'))
        for name in ('c', 'asm'):
            assert sum(group['calls'] for group in timings[name].values()) == report['calls']
        assert all(hashlib.sha256(path.read_bytes()).hexdigest() == digest
                   for file, digest in hashes.items() for path in [Path(file)])
    finally:
        p.stop(save=False)


if __name__ == '__main__':
    main()
