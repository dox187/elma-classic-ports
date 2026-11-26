"""Native rider vectors/motion against independent wrap/floor integer formulas."""

import argparse
import hashlib
from io import BytesIO
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


def check_scheduled_rom(rom):
    """Exercise the shipped rider entry points with independently rounded movement."""
    symbols = {name: int(value, 16) for name, value in re.findall(
        r'^DEF (\S+) 0x([0-9a-fA-F]+)', rom.with_suffix('.noi').read_text(), re.M)}
    image = bytearray(rom.read_bytes())
    image[0x100:0x102] = bytes([0x18, 0xfe])
    emu = PyBoy(BytesIO(image), cgb=True, window='null', sound_emulated=False)
    emu.set_emulation_speed(0)
    emu.tick(190, False)
    mem, regs = emu.memory, emu.register_file
    code = symbols['s__HEAP'] + 32
    out, stack = code + 32, 0xdfa0
    assert out + 12 < stack - 64
    bike, residual = symbols['_Bike'], symbols['_move_residual']
    mem[0xffff] = mem[0xff0f] = 0
    mem[0x3000] = 0
    mem[0x2000] = mem[symbols['__current_bank']] = 8

    def invoke(name, arguments):
        address = symbols[name]
        assert address >> 16 == 8
        mem[code:code+5] = [0xcd, address & 255, address >> 8 & 255, 0x18, 0xfe]
        mem[stack:stack+len(arguments)] = arguments
        regs.SP, regs.PC = stack, code
        emu.tick(1, False)
        assert (regs.SP, regs.PC) == (stack, code+3)
        assert bytes(mem[stack:stack+len(arguments)]) == arguments
        assert mem[symbols['__current_bank']] == 8

    rng = random.Random(0x9611)
    cases = rows()
    # Sample both sides of every angular-product width change, as well as
    # negative half ties, signed16 endpoints and full-width saturation.
    spin_edges = (-2**31, -32769, -32768, -32767, -257, -256, -255, -128,
                  -2, -1, 0, 1, 2, 127, 255, 256, 257, 32766, 32767, 32768, 2**31-1)
    try:
        # Check the rounded spin directly. The damper following it can
        # round away a one-unit angular error in the combined response.
        tangents = (-32768, -32767, -16384, -8193, -8192, -8191, -1, 0,
                    1, 8191, 8192, 8193, 16384, 32766, 32767)
        spin_cases = [(w, t) for w in spin_edges for t in tangents]
        spin_cases.extend((rng.randint(-32768, 32767), rng.randint(-32768, 32767))
                          for _ in range(4096))
        # Odd omega times +/-8192 always lands exactly halfway between integers.
        spin_cases.extend((w, t) for w in range(-511, 512, 2) for t in (-8192, 8192))
        # Exercise both signed24 width boundaries and carries between its
        # three unsigned angular digits, including negative half-Q14 ties.
        wide_edges = (-8388609, -8388608, -8388607, -4194304, -131073, -131072,
                      -131071, -65537, -65536, -65535, 65535, 65536, 65537,
                      131071, 131072, 131073, 4194304, 8388606, 8388607, 8388608)
        spin_cases.extend((w, t) for w in wide_edges for t in tangents)
        spin_cases.extend((rng.randint(-8388608, 8388607), rng.randint(-32768, 32767))
                          for _ in range(7000))
        for omega, tangent in spin_cases:
            mem[out:out+4] = struct.pack('<i', omega)
            regs.HL, regs.B, regs.C = out, (tangent >> 8) & 255, tangent & 255
            invoke('_riding_rider_spin14', b'\xa5')  # caller's stack guard
            actual = s32((regs.HL << 16) | (regs.D << 8) | regs.E)
            want = max(-2**31, min(2**31-1, (omega*tangent+8192) >> 14))
            assert actual == want, ('spin', omega, tangent, actual, want)
        if '_riding_restore_small' in symbols:
            edges = (-32768, -513, -512, -511, -257, -256, -255, -1, 0, 1,
                     255, 256, 257, 511, 512, 513, 32767)
            trig = ((16384, 0), (0, -16384), (-16384, 0), (-8192, 8192),
                    (8191, -8193), (11585, 11585), (-11585, -11585))
            rotations = [(x, y, c, s) for x in edges for y in edges for c, s in trig]
            rotations.extend((rng.randint(-511, 511), rng.randint(-511, 511),
                              rng.randint(-16384, 16384), rng.randint(-16384, 16384))
                             for _ in range(4096))
            for x, y, cs, sn in rotations:
                before = bytearray(rng.randbytes(119))
                bx, by = struct.unpack_from('<ii', before)
                mem[bike:bike+119] = before
                pair = symbols['_riding_pose_trig']
                mem[pair:pair+4] = struct.pack('<hh', cs, sn)
                regs.D, regs.E = (x >> 8) & 255, x & 255
                regs.B, regs.C = (y >> 8) & 255, y & 255
                invoke('_riding_restore_small', b'\xa5')
                inside = -511 <= x <= 511 and -511 <= y <= 511
                assert regs.A == inside, (x, y, cs, sn, regs.A)
                if inside:
                    dx = (x*cs - y*sn + 8192) >> 14
                    dy = (y*cs + x*sn + 8192) >> 14
                    struct.pack_into('<ii', before, 72, s32(bx + 256*dx), s32(by + 256*dy))
                assert bytes(mem[bike:bike+119]) == before, (x, y, cs, sn)
                assert bytes(mem[pair:pair+4]) == struct.pack('<hh', cs, sn)
            print(f'{len(rotations)} paired rider rotation and fallback cases passed')
        for i, row in enumerate(cases):
            bx, by, x, y, vx, vy, ax, ay, rx, ry = row
            mem[bike:bike+8] = struct.pack('<ii', bx, by)
            mem[bike+72:bike+80] = struct.pack('<ii', x, y)
            mem[out-1:out+9] = bytes([0xa5])*10
            invoke('_riding_rider_vectors32', struct.pack('<hhH', rx, ry, out))
            assert bytes(mem[out-1:out+9]) == b'\xa5'+expected(row)[:8]+b'\xa5', i
            for phase, coefficient in enumerate((262144, 172845)):
                rs = [rng.randrange(-2**23, 2**23) for _ in range(8)]
                rs[6 + (i & 1)] = (-2**23, -1, 0, 1, 2**23-1)[i % 5]
                mem[residual:residual+32] = struct.pack('<8i', *rs)
                mem[bike+72:bike+88] = struct.pack('<4i', x, y, vx, vy)
                mem[symbols['_riding_subphase']] = phase
                invoke('_riding_rider_move32', struct.pack('<ii', ax, ay))
                velocity = [s32(vx+ax), s32(vy+ay)]
                position = [x, y]
                for axis in range(2):
                    total = velocity[axis]*4*coefficient + rs[6+axis]
                    travel = (total + 2**23) >> 24
                    position[axis] = s32(position[axis]+travel)
                    rs[6+axis] = total - travel*2**24
                assert bytes(mem[residual:residual+32]) == struct.pack('<8i', *rs), (i, phase)
                assert bytes(mem[bike+72:bike+88]) == struct.pack('<4i', *position, *velocity), (i, phase)
                # Exercise both rounded rider forces together. Include narrow and wide
                # relative speeds, the zero damper shortcut and overflow on wrap32.
                omega = (spin_edges[i % len(spin_edges)] if not phase else
                         rng.randint(-32768, 32767) if i & 1 else s32(ax))
                gx, gy = ax, ay
                dx, dy = struct.unpack('<hh', expected(row)[4:8])
                directions = struct.unpack('<hh', expected(row)[:4])
                tangent = [((-dy+32768) % 65536)-32768, dx]
                angular = [max(-2**31, min(2**31-1, (omega*t+8192) >> 14)) for t in tangent]
                bounds = (-32769, -32768, -32767, -1, 0, 1, 32766, 32767, 32768)
                target = (bounds[i % len(bounds)], bounds[(i+3) % len(bounds)]) if i % 2 else (vx, vy)
                body = [s32(v-a-r) for v, a, r in zip((vx,vy), angular, target)]
                mem[bike+8:bike+16] = struct.pack('<ii', *body)
                mem[bike+72:bike+88] = struct.pack('<4i', x, y, vx, vy)
                mem[residual:residual+32] = struct.pack('<8i', *rs)
                invoke('_riding_rider_response32', struct.pack('<hhiii', rx, ry, omega, gx, gy))
                position = [x, y]
                velocity = [vx, vy]
                for axis, gravity in enumerate((gx, gy)):
                    spring = (directions[axis]*(32480690,21416162)[phase]+2**23) >> 24
                    damping = (target[axis]*(1384120,912621)[phase]+2**23) >> 24
                    velocity[axis] = s32(velocity[axis]+spring-damping+gravity)
                    total = velocity[axis]*4*coefficient + rs[6+axis]
                    travel = (total + 2**23) >> 24
                    position[axis] = s32(position[axis]+travel)
                    rs[6+axis] = total - travel*2**24
                assert bytes(mem[residual:residual+32]) == struct.pack('<8i', *rs), ('response', i, phase)
                assert bytes(mem[bike+72:bike+88]) == struct.pack('<4i', *position, *velocity), ('response', i, phase)
    finally:
        emu.stop(save=False)
    print(f'{len(spin_cases)} rider spin, {len(cases)} vector and {2*len(cases)} scheduled movement and response cases passed')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", type=Path, help="validate the scheduled production ROM directly")
    parser.add_argument("--assembly", type=Path, default=BASE / "src/physics_rider_fast.s")
    parser.add_argument("--out", type=Path, default=BASE / "build/rider-check")
    parser.add_argument("--gen", type=Path, default=BASE / "build/gen")
    parser.add_argument("--lcc", type=Path, default=BASE / ".toolchain/gbdk/bin/lcc")
    args = parser.parse_args()
    if args.rom:
        return check_scheduled_rom(args.rom)
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
