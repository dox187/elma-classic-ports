#!/usr/bin/env python3
"""Check native body-angle integration and angular velocity against integer arithmetic."""
import argparse
import json
import random
import re
import struct
import subprocess
from pathlib import Path
from pyboy import PyBoy

BASE = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gen', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    driver = out / 'driver.c'
    driver.write_text('''#include <gb/gb.h>
#include <gb/cgb.h>
#include "physics_core.h"
bike_t Bike;
int32_t angular_residual;
volatile int16_t fragment;
volatile int32_t point_velocity;
volatile uint8_t ready,request;
void riding_full_angle(void) __sdcccall(0);
int32_t body_oms(void) BANKED;
void riding_partial_angle(int16_t fraction) BANKED;
void riding_partial_body_angle(void) BANKED;
void main(void) {
    cpu_fast(); SWITCH_ROM(8); ready=1;
    while (1) {
        if (request==1) riding_full_angle();
        if (request==2) riding_partial_angle(fragment);
        if (request==3) point_velocity=body_oms();
        if (request==4) riding_partial_body_angle();
        request=0; vsync();
    }
}
''')
    rom = out / 'phase.gbc'
    subprocess.run([BASE/'.toolchain/gbdk/bin/lcc', '-msm83:gb', '-Wm-yC',
                    '-Wm-yt0x19', '-Wm-yoA', '-Wl-j', '-I'+str(BASE/'src'),
                    '-I'+str(args.gen.resolve()), '-o', rom, driver, BASE/'src/physics_angle.c',
                    BASE/'src/physics_body_angle.s'], check=True)
    symbols = {k:int(v,16) for k,v in re.findall(r'DEF (_\w+) 0x([0-9a-fA-F]+)', rom.with_suffix('.noi').read_text())}
    emu = PyBoy(str(rom), window='null', sound_emulated=False, cgb=True)
    emu.set_emulation_speed(0)
    omega_edges = sorted({n for bit in range(32) for sign in (-1,1)
                          for d in (-1,0,1) if -(1<<31) <= (n := sign*(1<<bit)+d) < 1<<31})
    fractions = [-(1<<23), -(1<<23)+1, -0x40001, -0x40000, -1, 0, 1, 0x3ffff,
                 0x40000, 0x40001, (1<<23)-1]
    rng = random.Random(9606)
    cases = [(w,r) for w in omega_edges for r in fractions]
    cases.extend((rng.randrange(-(1<<31),1<<31), rng.randrange(-(1<<23),1<<23)) for _ in range(4096))
    constants = (args.gen / 'riding_constants.h').read_text()
    pair = re.search(r'q24_C_OMS\[2\]=\{(\d+),(\d+)\}', constants)
    m = int(pair[1])
    assert m == int(pair[2])
    # Place the combined 56-bit input on both sides of the last rounding
    # threshold before each clamp, including changes of a single residual bit.
    for integer in (-(1<<31)-1, -(1<<31), -1, 0, (1<<31)-2, (1<<31)-1):
        boundary = ((integer << 48) + (1 << 47)) // m
        for delta in range(-4, 5):
            raw = boundary + delta
            whole = (raw + (1 << 23)) >> 24
            cases.append((whole, raw - (whole << 24)))
    def write(addr, fmt, value):
        data=struct.pack(fmt,value)
        emu.memory[addr:addr+len(data)] = data
    try:
        for _ in range(150):
            emu.tick(1, False)
            if emu.memory[symbols['_ready']]: break
        assert emu.memory[symbols['_ready']]
        for w,r in cases:
            initial = rng.getrandbits(32)
            f = r * 27007 >> 24
            for request,delta in ((1,32*w+((r+0x40000)>>19)),(2,(27007*w+f+640)//1280),
                                  (4,(27007*w+f+640)//1280)):
                write(symbols['_Bike']+16,'<I',initial)
                write(symbols['_Bike']+20,'<i',w)
                write(symbols['_angular_residual'],'<i',r)
                write(symbols['_fragment'],'<h',f)
                emu.memory[symbols['_request']] = request
                emu.tick(1,False)
                assert not emu.memory[symbols['_request']]
                actual = int.from_bytes(bytes(emu.memory[symbols['_Bike']+16:symbols['_Bike']+20]),'little')
                assert actual == (initial+delta)&0xffffffff, (request,w,r,initial,actual,delta)
            emu.memory[symbols['_request']] = 3
            emu.tick(1,False)
            assert not emu.memory[symbols['_request']]
            addr = symbols['_point_velocity']
            actual = int.from_bytes(bytes(emu.memory[addr:addr+4]), 'little', signed=True)
            expected = ((((w << 24) + r) * m) + (1 << 47)) >> 48
            assert actual == max(-(1<<31), min((1<<31)-1, expected)), (w,r,actual,expected)
    finally:
        emu.stop(save=False)
    report = dict(passed=True,native_cases=len(cases)*4,omega_edge_values=len(omega_edges))
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report)


if __name__ == '__main__':
    main()
