"""Native rider vectors/motion against independent wrap/floor integer formulas."""

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
MASK32 = (1 << 32) - 1


def s32(value):
    return ((value + (1 << 31)) & MASK32) - (1 << 31)


def sat16(value):
    return max(-32768, min(32767, value))


def expected(row):
    bx, by, x, y, vx, vy, ax, ay, restx, resty = row
    vectors = (
        sat16((s32(bx - x) >> 4) + restx),
        sat16((s32(by - y) >> 4) + resty),
        sat16(s32(x - bx) >> 4),
        sat16(s32(y - by) >> 4),
    )
    vx, vy = s32(vx + ax), s32(vy + ay)
    return struct.pack("<hhhhiiii", *vectors, s32(x + vx * 4),
                       s32(y + vy * 4), vx, vy)


def rows():
    rng = random.Random(1096674)
    limits = [0, 1, -1, 0x7fffffff, -0x80000000, 0x3fffffff,
              -0x40000000, 32767, -32768, 65535, -65536, 255, -256]
    cases = []

    def add(delta, other, restx, resty):
        i = len(cases)
        bx, by = limits[i % len(limits)], limits[(i + 4) % len(limits)]
        cases.append((bx, by, s32(bx - delta), s32(by - other),
                      limits[(i + 2) % len(limits)],
                      limits[(i + 5) % len(limits)],
                      limits[(i + 7) % len(limits)],
                      limits[(i + 9) % len(limits)], restx, resty))

    # Every low nibble around both delta and offset saturation boundaries.
    for rest in (-32768, -32767, -1, 0, 1, 32766, 32767):
        qvalues = {-65537, -65536, -65535, -32769, -32768, -32767,
                   -1, 0, 1, 32766, 32767, 32768, 65534, 65535, 65536}
        qvalues.update(value - rest for value in
                       (-32769, -32768, -32767, 32766, 32767, 32768))
        for q in sorted(qvalues):
            for low in range(16):
                delta = q * 16 + low
                add(delta, s32(-delta), rest, -rest if rest != -32768 else 32767)

    # The wrapped negation of INT32_MIN is deliberately still negative.
    for delta in list(range(-0x80000000, -0x80000000 + 33)) + list(
            range(0x7fffffff - 32, 0x80000000)):
        for rest in (-32768, -1, 0, 1, 32767):
            add(delta, s32(-delta), rest, rest)

    # Carry chains and motion wrapping independently of the vector bounds.
    for i, velocity in enumerate(limits):
        for j, acceleration in enumerate(limits):
            for k, position in enumerate(limits[:7]):
                cases.append((limits[(i + j) % len(limits)],
                              limits[(j + k) % len(limits)], position,
                              limits[(k + 3) % len(limits)], velocity,
                              limits[(i + 1) % len(limits)], acceleration,
                              limits[(j + 2) % len(limits)],
                              -32768 if i & 1 else 32767,
                              -1 if j & 1 else 1))

    for _ in range(1024):
        cases.append(tuple(rng.randint(-2**31, 2**31 - 1) for _ in range(8))
                     + tuple(rng.randint(-32768, 32767) for _ in range(2)))
    for _ in range(512):
        bx, by = (rng.randint(-2**31, 2**31 - 1) for _ in range(2))
        cases.append((bx, by, s32(bx + rng.randint(-600000, 600000)),
                      s32(by + rng.randint(-600000, 600000)),
                      *(rng.randint(-1000000, 1000000) for _ in range(4)),
                      *(rng.randint(-32768, 32767) for _ in range(2))))
    return cases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--assembly", type=Path, default=BASE / "src/physics_rider_fast.s")
    parser.add_argument("--out", type=Path, default=BASE / "build/rider-check")
    parser.add_argument("--gen", type=Path, default=BASE / "build/gen")
    parser.add_argument("--lcc", type=Path, default=BASE / ".toolchain/gbdk/bin/lcc")
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    source_hash = hashlib.sha256(args.assembly.read_bytes()).hexdigest()
    cases = rows()
    packed = [(struct.pack("<iiiiiiiihh", *row), expected(row)) for row in cases]
    header = "#include <stdint.h>\ntypedef struct {uint8_t input[36],want[24];} vector_t;\n"
    sources = []
    banks = (bank for bank in range(1, 256) if bank != 8)
    for start in range(0, len(packed), 256):
        bank = next(banks)
        subset = packed[start:start + 256]
        name = f"vectors{bank}"
        header += f"extern const vector_t {name}[];\n#define COUNT{bank} {len(subset)}\n"
        source = out / f"{name}.c"
        source.write_text(f'#pragma bank {bank}\n#include "vectors.h"\nconst vector_t {name}[]={{\n'
                          + ",\n".join("{{" + ",".join(map(str, before)) + "},{"
                                      + ",".join(map(str, after)) + "}}"
                                      for before, after in subset) + "\n};\n")
        sources.append((bank, source))
    (out / "vectors.h").write_text(header)
    (out / "case.c").write_text('''#pragma bank 8
#include <gb/gb.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "physics_core.h"
#include "vectors.h"
typedef char packed109[sizeof(bike_t)==109?1:-1];
typedef char packed_offsets[offsetof(bike_t,body)==0&&offsetof(circle_t,rx)==0&&offsetof(circle_t,ry)==4&&offsetof(bike_t,rider_x)==66&&offsetof(bike_t,rider_y)==70&&offsetof(bike_t,rider_vx)==74&&offsetof(bike_t,rider_vy)==78?1:-1];
void riding_rider_vectors32(int16_t,int16_t,int16_t *) __sdcccall(0);
void riding_rider_move32(int32_t,int32_t) __sdcccall(0);
bike_t Bike;uint8_t arena[64],snapshot[109];extern vector_t copy;
volatile uint16_t vector_failures,move_failures,guard_failures,bank_failures,cases;
volatile uint16_t first_bad_case;volatile uint8_t first_bad_byte;
void check_case(void) BANKED {
 uint8_t j,pos=8+(uint8_t)(cases&31);int16_t restx,resty;int32_t ax,ay;
 memset(&Bike,0xa5,sizeof(Bike));memcpy(&Bike.body.rx,copy.input,8);memcpy(&Bike.rider_x,copy.input+8,16);
 memcpy(snapshot,&Bike,sizeof(Bike));memcpy(&ax,copy.input+24,4);memcpy(&ay,copy.input+28,4);
 memcpy(&restx,copy.input+32,2);memcpy(&resty,copy.input+34,2);
 for(j=0;j<64;++j)arena[j]=(uint8_t)(0xa5^j^cases);
 riding_rider_vectors32(restx,resty,(int16_t *)(arena+pos));
 if(CURRENT_BANK!=8)++bank_failures;
 for(j=0;j<8;++j)if(arena[pos+j]!=copy.want[j]){if(!vector_failures){first_bad_case=cases;first_bad_byte=j;}++vector_failures;}
 for(j=0;j<64;++j)if((j<pos||j>=pos+8)&&arena[j]!=(uint8_t)(0xa5^j^cases))++guard_failures;
 for(j=0;j<109;++j)if(((uint8_t *)&Bike)[j]!=snapshot[j])++guard_failures;
 riding_rider_move32(ax,ay);
 if(CURRENT_BANK!=8)++bank_failures;
 for(j=0;j<16;++j)if(((uint8_t *)&Bike.rider_x)[j]!=copy.want[8+j])++move_failures;
 for(j=0;j<109;++j)if((j<66||j>=82)&&((uint8_t *)&Bike)[j]!=snapshot[j])++guard_failures;
 ++cases;
}
''')
    driver = '''#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdint.h>
#include <string.h>
#include "vectors.h"
vector_t copy;volatile uint8_t done;volatile uint16_t restore_failures;
void check_case(void) BANKED;
void main(void){uint16_t i;disable_interrupts();DISPLAY_OFF;cpu_fast();
'''
    for bank, _ in sources:
        driver += (f"SWITCH_ROM({bank});for(i=0;i<COUNT{bank};++i){{"
                   f"memcpy(&copy,&vectors{bank}[i],sizeof(copy));check_case();"
                   f"if(CURRENT_BANK!={bank})++restore_failures;}}\n")
    driver += "done=1;while(1){} }\n"
    (out / "driver.c").write_text(driver)
    command = [str(args.lcc), "-msm83:gb", "-Wf--opt-code-size",
               "-Wf--max-allocs-per-node", "-Wf100000", "-Wm-yC", "-Wm-yt0x19",
               "-Wm-yoA", "-Wl-m", "-Wl-j", "-I" + str(BASE / "src"),
               "-I" + str(args.gen), "-I" + str(out), "-o", str(out / "check.gbc"),
               str(out / "driver.c"), str(out / "case.c"), str(args.assembly)]
    command += [str(source) for _, source in sources]
    compiled = subprocess.run(command, capture_output=True, text=True)
    (out / "compile.log").write_text(compiled.stdout + compiled.stderr)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    symbols = {name: int(value, 16) for name, value in
               re.findall(r"DEF (_\w+) 0x([0-9a-fA-F]+)", (out / "check.noi").read_text())}
    pyboy = PyBoy(str(out / "check.gbc"), window="null", sound_emulated=False, cgb=True)
    pyboy.set_emulation_speed(0)
    pending = []
    returns = set()
    cycles = {"vectors": [], "move": []}
    stack_failures = []

    def returned(key):
        if not pending or pending[-1][0] != key:
            return
        _, name, sp, started = pending.pop()
        if pyboy.register_file.SP != sp + 2:
            stack_failures.append((name, sp, pyboy.register_file.SP))
        cycles[name].append(pyboy._cycles() - started)

    def entered(name):
        sp = pyboy.register_file.SP
        pc = pyboy.memory[sp] + 256 * pyboy.memory[sp + 1]
        key = (8, pc)
        if key not in returns:
            pyboy.hook_register(*key, returned, key)
            returns.add(key)
        pending.append((key, name, sp, pyboy._cycles()))

    for name, symbol in (("vectors", "_riding_rider_vectors32"),
                         ("move", "_riding_rider_move32")):
        address = symbols[symbol]
        assert address >> 16 == 8, (symbol, address)
        pyboy.hook_register(8, address & 65535, entered, name)
    try:
        for _ in range(1000):
            pyboy.tick(100, False)
            if pyboy.memory[symbols["_done"]]:
                break

        def value(name, size=2):
            address = symbols["_" + name]
            return int.from_bytes(bytes(pyboy.memory[address:address + size]), "little")

        report = {name: value(name) for name in
                  ("cases", "vector_failures", "move_failures", "guard_failures",
                   "bank_failures", "restore_failures", "first_bad_case")}
        report.update(done=value("done", 1), first_bad_byte=value("first_bad_byte", 1),
                      expected_cases=len(cases), packed_bike_bytes=109,
                      stack_failures=stack_failures, pending_returns=len(pending),
                      assembly_sha256=source_hash,
                      api_cycles={name: {"calls": len(values), "min": min(values) if values else None,
                                         "max": max(values) if values else None,
                                         "mean": sum(values) / len(values) if values else None}
                                  for name, values in cycles.items()})
        assert hashlib.sha256(args.assembly.read_bytes()).hexdigest() == source_hash, "Assembly changed during check"
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        assert report["done"] and report["cases"] == len(cases), report
        assert not any(report[name] for name in
                       ("vector_failures", "move_failures", "guard_failures",
                        "bank_failures", "restore_failures", "stack_failures", "pending_returns")), report
        assert all(len(values) == len(cases) for values in cycles.values()), report
    finally:
        pyboy.stop(save=False)


if __name__ == "__main__":
    main()
