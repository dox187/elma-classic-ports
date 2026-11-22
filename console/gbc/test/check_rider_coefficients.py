"""Exhaust the signed16 rider lookup in cartridge code against the full Q24 product."""
import argparse
import json
from pathlib import Path
import re
import subprocess

from pyboy import PyBoy

BASE = Path(__file__).resolve().parents[1]
DRIVER = r'''
#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdint.h>
extern uint8_t riding_subphase;
extern const uint8_t fixture_bank_marker;
int32_t riding_rider_s(int32_t) __sdcccall(0);
int32_t riding_rider_f(int32_t) __sdcccall(0);
int32_t riding_rider_s_wide(int32_t) __sdcccall(0);
int32_t riding_rider_f_wide(int32_t) __sdcccall(0);
volatile uint8_t fixture_done, fixture_failed;
volatile uint32_t fixture_pairs;
volatile int32_t fixture_value;
static uint8_t check(int32_t v) {
    fixture_value = v;
    int32_t spring = riding_rider_s(v);
    if (fixture_bank_marker != 0xa5 || spring != riding_rider_s_wide(v)) return 0;
    int32_t damper = riding_rider_f(v);
    if (fixture_bank_marker != 0xa5 || damper != riding_rider_f_wide(v)) return 0;
    ++fixture_pairs;
    return 1;
}
void main(void) {
    static const int32_t wide[] = {INT32_MIN, -65537, -65536, -32769,
                                   32768, 65535, 65536, INT32_MAX};
    disable_interrupts(); cpu_fast(); SWITCH_ROM(8);
    for (riding_subphase = 0; riding_subphase < 2; ++riding_subphase) {
        uint16_t raw = 0;
        do {
            if (!check((int16_t)raw)) goto failure;
        } while (++raw);
        for (uint8_t i=0; i<sizeof(wide)/sizeof(wide[0]); ++i)
            if (!check(wide[i])) goto failure;
    }
    goto done;
failure:
    fixture_failed=1;
done:
    fixture_done=1;
    while (1) {}
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True,
                        help='object directory from check_scheduled_native.py')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    flags = [BASE/'.toolchain/gbdk/bin/lcc', '-msm83:gb', '-Wf--opt-code-size',
             '-Wm-yC', '-Wm-yt0x19', '-Wm-yoA', '-Wl-j']
    objects = sorted(args.native.glob('[0-9]*.o'))
    driver_index, = [i for i, obj in enumerate(objects) if obj.name.endswith('-driver.o')]
    for name, content in (('driver', DRIVER),
                          ('marker', '#pragma bank 8\nconst unsigned char fixture_bank_marker=0xa5;\n')):
        src = args.out / (name+'.c')
        obj = src.with_suffix('.o')
        src.write_text(content)
        subprocess.run([*flags, '-c', '-o', obj, src], check=True)
        if name == 'driver':
            objects[driver_index] = obj
        else:
            objects.append(obj)
    rom = args.out/'rider-coefficients.gbc'
    subprocess.run([*flags, '-o', rom, *objects], check=True)
    addresses = {k: int(v, 16) for k, v in re.findall(
        r'^DEF _(fixture_\w+) 0x([\da-fA-F]+)', rom.with_suffix('.noi').read_text(), re.M)}
    emulator = PyBoy(str(rom), window='null', sound_emulated=False, cgb=True)
    emulator.set_emulation_speed(0)
    def read(name, size=1, signed=False):
        p = addresses['fixture_'+name]
        return int.from_bytes(bytes(emulator.memory[p:p+size]), 'little', signed=signed)
    try:
        for _ in range(4000):
            emulator.tick(16, False)
            if read('done'):
                break
        pairs = read('pairs', 4)
        passed = bool(read('done') and not read('failed') and pairs == 2*(65536+8))
        result = dict(passed=passed, products=2*pairs, last_input=read('value', 4, True))
    finally:
        emulator.stop(save=False)
    (args.out/'report.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
