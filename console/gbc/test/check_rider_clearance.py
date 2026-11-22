"""Prove the native phase strips and exercise their exact projections on SM83."""
import argparse
import collections
import json
from pathlib import Path
import random
import re
import struct
import subprocess

BASE = Path(__file__).resolve().parents[1]


def read_rows(source):
    parts = re.split(r"(?m)^rider_strip_(\d+):\n", source.read_text())
    rows = []
    for index, data in zip(parts[1::2], parts[2::2]):
        assert int(index) == len(rows)
        origin, size, *values = map(int, re.findall(r"\b\d+\b", data))
        assert len(values) == size * 2
        rows.append((origin, list(zip(values[::2], values[1::2]))))
    assert len(rows) == 32
    return rows


def sine_values(source):
    values = list(map(int, re.findall(r"-?\d+", re.search(r"Sintab\[257\] = \{([^}]+)\}", source.read_text())[1])))
    return [values[p >> 8] + ((values[(p >> 8) + 1] - values[p >> 8]) * (p & 255) >> 8)
            for p in range(65536)]


def world(u, v, octant):
    return ((u, v), (-v, -u), (-v, u), (u, -v),
            (-u, -v), (v, u), (v, -u), (-u, v))[octant]


def local(x, y, cs, sn):
    def rounded(n):
        return max(-32768, min(32767, (n + 8192) >> 14))
    return rounded(x * cs + y * sn), rounded(y * cs - x * sn)


def phase_row(phase):
    octant = phase >> 13
    row = (phase >> 8) & 31
    return octant, 31 - row if octant & 1 else row


def prove(source, sine_source, constants):
    rows, sine = read_rows(source), sine_values(sine_source)
    text = constants.read_text()
    defines = dict((name, int(value)) for name, value in
                   re.findall(r"^#define (\w+) (-?\d+)$", text, re.M))
    seat_x, seat_y = defines["SEAT_X"], defines["SEAT_Y"]
    left, right, top = (defines[key] for key in ("RIDER_LEFT", "RIDER_RIGHT", "RIDER_TOP"))
    factors = []
    for name in ("C_SEAT_NX", "C_SEAT_NY", "C_ELLIPSE"):
        m = re.search(r"q24_" + name + r"\[2\]=\{([^}]+)\}", text)
        factors.append(tuple(map(int, m[1].split(","))) if m else
                       (defines[name + "_M"] << (24 - defines[name + "_E"]),))
    profiles = sorted(set(zip(*factors)))
    checked, points = 0, 0
    # Check the four actual world-space dots at the true sine/cosine for
    # EACH phase. Rounding and saturation are monotone. Interval subdivision
    # recovers tight bounds when the seat and ellipse extrema differ.
    for phase in range(65536):
        cs, sn = sine[(phase + 16384) & 65535], sine[phase]
        octant, row = phase_row(phase)
        base, spans = rows[row]
        for i, (low, high) in enumerate(spans):
            if low > high:
                continue
            u = (base + i) * 16 - 512
            points += 16 * (high - low + 1) * 2 * 2
            pending = [(low, high)]
            while pending:
                low, high = pending.pop()
                corners = [local(*world(x, y, octant), cs, sn)
                           for x in (u, u + 15) for y in (2 * low, 2 * high + 1)]
                # Including both facings makes the reflected tie case explicit.
                bound = max(abs(x) for x, _ in corners)
                ymin, ymax = min(y for _, y in corners), max(y for _, y in corners)
                valid = -bound >= left and bound <= right and ymax <= top
                for nx, ny, ellipse in profiles:
                    mid = 1 << 23
                    lower = (((ymin-seat_y)*ny+mid) >> 24) - (((bound-seat_x)*nx+mid) >> 24)
                    upper = (((ymax-seat_y)*ny+mid) >> 24) - (((-bound-seat_x)*nx+mid) >> 24)
                    xs = (bound*ellipse+mid) >> 24
                    valid &= 0 <= lower <= upper <= 32767 and xs*xs + max(0, ymax)**2 <= top*top
                if valid:
                    checked += 1
                else:
                    assert low < high, (phase, octant, u, low, high, corners)
                    middle = (low + high) // 2
                    pending.extend(((low, middle), (middle+1, high)))
    return dict(phases=65536, certified_rectangles=checked, poses_with_both_facings=points)


def native(assembly, sine_source, out, lcc, captures):
    from pyboy import PyBoy

    out.mkdir(parents=True, exist_ok=True)
    rows, sine = read_rows(assembly), sine_values(sine_source)
    rng = random.Random(43180923)
    inputs = []
    # Every strip, all octants, both sides of its inclusive edges and guard.
    for p in range(0, 65536, 256):
        octant, row = phase_row(p)
        origin, spans = rows[row]
        for i, (lo, hi) in enumerate(spans):
            u = (origin + i) * 16 - 512
            for x, y in ((u, 2*lo), (u+15, 2*hi+1), (u+15, 2*lo-1), (u, 2*hi+2)):
                inputs.append((p + rng.choice((0, 1, 127, 255)), *world(x, y, octant)))
    limits = (-8388608, -8388607, -32769, -32768, -32767, -513, -512, -1,
              0, 1, 511, 512, 32766, 32767, 32768, 8388607)
    for p in list(range(0, 65536, 8192)) + [1, 8191, 8193, 16383, 16385, 65535]:
        for x in limits:
            for y in limits:
                inputs.append((p, x, y))
    for _ in range(2500):
        inputs.append((rng.randrange(65536), rng.randrange(-8388608, 8388608),
                       rng.randrange(-8388608, 8388608)))
    if captures:
        inputs.extend((p, dx, dy) for _, _, dx, dy, p, _ in json.loads(captures.read_text()))

    # Independent C dot also checks the register / stack ABI on the fallback.
    driver = out / "driver.c"
    driver.write_text('''#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdint.h>
uint8_t Bike[119],guard[12];
uint16_t riding_pose_phase;
int16_t riding_pose_trig[2];
volatile uint8_t result,done;
uint8_t riding_rider_phase_local(int16_t *xy);
int16_t dotq14(int16_t a,int16_t b,int16_t c,int16_t d) {
    int32_t r=((int32_t)a*c+(int32_t)b*d+8192)>>14;
    return r< -32768L ? -32768 : r>32767 ? 32767 : (int16_t)r;
}
void configure(void){}
void check_result(void){}
void main(void){
    uint32_t i;cpu_fast();disable_interrupts();DISPLAY_OFF;SWITCH_ROM(8);
    for(i=0;i<CASE_COUNT;++i){configure();
        result=riding_rider_phase_local((int16_t *)(guard+3));check_result();}
    done=1;while(1){}
}
''')
    # Only the limiter shares this fixture. The response above it has a
    # separate set of acceleration and motion dependencies.
    limiter = out / "rider-limit.s"
    start = assembly.read_text().index(".macro rider_delta ")
    limiter.write_text(".module rider_limit_check\n.area _CODE_8\n" + assembly.read_text()[start:])
    rom = out / "rider-check.gbc"
    subprocess.run([lcc, "-Wm-yC", "-Wm-yt0x19", "-Wm-yoA", "-Wl-j",
                    f"-DCASE_COUNT={len(inputs)}ul", "-o", rom, driver, limiter], check=True)
    symbols = {k: int(v, 16) for k, v in re.findall(r"DEF (_\w+) 0x([0-9a-fA-F]+)",
                                                     rom.with_suffix(".noi").read_text())}
    emulator = PyBoy(str(rom), window="null", sound_emulated=False, cgb=True)
    emulator.set_emulation_speed(0)
    stats = collections.Counter()
    guard = bytes(range(87, 99))
    current = {}

    def write(name, value):
        address = symbols["_" + name]
        emulator.memory[address:address+len(value)] = value

    def read(name, size):
        address = symbols["_" + name]
        return bytes(emulator.memory[address:address+size])

    def signed32(x):
        return ((x + (1 << 31)) & 0xffffffff) - (1 << 31)

    def setup(_):
        p, dx, dy = inputs[stats["cases"]]
        cs, sn = sine[(p + 16384) & 65535], sine[p]
        state = bytearray(rng.randbytes(119))
        bx, by = (rng.choice((-2**31, 2**31-1, rng.randrange(-2**31, 2**31))) for _ in range(2))
        rx, ry = bx + dx*256 + rng.randrange(256), by + dy*256 + rng.randrange(256)
        stats["wrapped"] += (rx != signed32(rx) or ry != signed32(ry))
        struct.pack_into("<ii", state, 0, bx, by)
        struct.pack_into("<ii", state, 72, signed32(rx), signed32(ry))
        write("Bike", state)
        pose = struct.pack("<hh", cs, sn)
        write("riding_pose_trig", pose)
        write("riding_pose_phase", struct.pack("<H", p))
        write("guard", guard)
        x, y = (min(32767, max(-32768, i)) for i in (dx, dy))
        stats["saturated"] += ((x, y) != (dx, dy))
        octant, row = phase_row(p)
        u, v = ((x, y), (-y, -x), (y, -x), (x, -y),
                (-x, -y), (y, x), (-y, x), (-x, y))[octant]
        origin, spans = rows[row]
        index = (u + 512) // 16 - origin
        inside = 0 <= index < len(spans) and spans[index][0] <= v//2 <= spans[index][1]
        stats["accepted"] += inside
        stats["cardinal_projections"] += not inside and p % 16384 == 0
        expected = guard if inside else guard[:3] + struct.pack("<hh", *local(x, y, cs, sn)) + guard[7:]
        current.update(sp=emulator.register_file.SP, bike=bytes(state), expected=expected, inside=inside, pose=pose)

    def check(_):
        case = stats["cases"]
        assert read("guard", 12) == current["expected"], (case, inputs[case], read("guard", 12), current["expected"])
        assert read("result", 1)[0] == current["inside"], (case, inputs[case])
        assert read("Bike", 119) == current["bike"]
        assert read("riding_pose_phase", 2) == struct.pack("<H", inputs[case][0])
        assert read("riding_pose_trig", 4) == current["pose"]
        assert read("_current_bank", 1) == b"\x08" and emulator.register_file.SP == current["sp"]
        stats["cases"] += 1
    emulator.hook_register(0, symbols["_configure"], setup, None)
    emulator.hook_register(0, symbols["_check_result"], check, None)
    try:
        for _ in range(1000):
            emulator.tick(30, False)
            if read("done", 1)[0]:
                break
        assert read("done", 1)[0] and stats["cases"] == len(inputs), stats
    finally:
        emulator.stop(save=False)
    return dict(stats)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assembly", type=Path, default=BASE/"src/physics_rider_response.s")
    parser.add_argument("--sine-source", type=Path, default=BASE/"src/physics_math.c")
    parser.add_argument("--constants", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=BASE/"build/rider-clearance-check")
    parser.add_argument("--lcc", type=Path, default=BASE/".toolchain/gbdk/bin/lcc")
    parser.add_argument("--captures", type=Path)
    args = parser.parse_args()
    report = dict(proof=prove(args.assembly, args.sine_source, args.constants),
                  native=native(args.assembly.resolve(), args.sine_source, args.out.resolve(),
                                args.lcc.resolve(), args.captures))
    (args.out/"report.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report))
