#!/usr/bin/env python3
"""Build/check the private native force probe without changing game objects.

Run from console/snes after building test_phys.sfc and the host physdump.
The probe exercises the new macro before each existing solver step, checks
an independent Python integer oracle, and retains the normal ASM/C checks.
"""

import argparse
import json
import os
from pathlib import Path
import random
import subprocess

import mesen
import physrom
import wide_force_gen


ROOT = Path(__file__).resolve().parent.parent


def toolchain(explicit):
    candidates = [explicit, os.environ.get("PVSNESLIB_HOME")]
    candidates += [str(Path.home() / suffix) for suffix in (
        "pvsneslib", ".local/share/pvsneslib",
        ".local/share/elma-snes/pvsneslib-4.6.0/pvsneslib",
    )]
    candidates.append("/opt/pvsneslib")
    for candidate in candidates:
        if candidate and (Path(candidate) / "devkitsnes/bin/wla-65816").is_file():
            return Path(candidate) / "devkitsnes/bin"
    raise SystemExit("PVSnesLib not found; set PVSNESLIB_HOME or --pvs")


def build(args):
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    wide_force_gen.generate(out / "wide_force_tables.inc")
    source = Path("src/phys.asm").read_text()
    source = source.replace('.include "phys.inc"',
                            '.include "phys.inc"\n.include "wide_native_force.inc"\n.include "wide_force_wrapper.asm"', 1)
    source = source.replace("phys_step:\n", "phys_step:\n\tjsl wide_force_probe\n", 1)
    source += '''
.RAMSECTION ".wide_force_probe_ram" BANK 0 SLOT 1 ALIGN 256
wide_force_ram dsb 256
wide_force_abi_regs dsb 16
wide_force_active_arg dsb 2
.ENDS
.BASE $00
.RAMSECTION ".wide_force_probe_buffers" BANK $7E SLOT 2
wide_force_c_buffers dsb 24
.ENDS
.BASE $80
.SECTION ".wide_force_probe_text" SUPERFREE
wide_force_probe:
php
rep #$30
pha
phx
phy
phb
phd
pea wide_force_ram
pld
sep #$20
lda #$80
pha
plb
rep #$20
jsr wide_force_native
txa
sta.l wide_force_abi_regs
tya
sta.l wide_force_abi_regs+2
tdc
sta.l wide_force_abi_regs+4
phb
sep #$20
pla
sta.l wide_force_abi_regs+6
rep #$20
wide_force_call_begin:
pea $007e
pea ((wide_force_c_buffers+18) & $FFFF)
pea $007e
pea ((wide_force_c_buffers+12) & $FFFF)
lda.b 140
and #$00ff
beq _wide_probe_active_arg
lda #$0100
_wide_probe_active_arg:
pha
pea $007e
pea ((wide_force_c_buffers+6) & $FFFF)
pea $007e
pea (wide_force_c_buffers & $FFFF)
jsl wide_force_component
clc
tsc
adc #18
tcs
wide_force_call_end:
txa
sta.l wide_force_abi_regs+8
tya
sta.l wide_force_abi_regs+10
tdc
sta.l wide_force_abi_regs+12
phb
sep #$20
pla
sta.l wide_force_abi_regs+14
rep #$20
wide_force_abi_end:
pld
plb
ply
plx
pla
plp
rtl
wide_force_native:
WIDE_FORCE_COMPONENT 128,134,140,154,141,144
wide_force_native_end:
rts
.ENDS
'''
    assembly = out / "probe.asm"
    if args.call_mode == "c":
        begin = source.index("wide_force_call_begin:\n")
        end = source.index("wide_force_call_end:\n", begin)
        source = source[:begin] + "wide_force_call_begin:\njsl wide_force_c_call\n" + source[end:]
    assembly.write_text(source)
    obj = out / "probe.obj"
    binaries = toolchain(args.pvs)
    subprocess.run([str(binaries / "wla-65816"), "-h", "-s", "-x",
                    "-I" + str(args.gen), "-Isrc", "-Itest", "-I" + str(out),
                    "-o", str(obj), str(assembly)], check=True)
    entries = args.link.read_text().splitlines()
    original = "build/obj/phys.obj"
    if entries.count(original) != 1:
        raise SystemExit("Expected one build/obj/phys.obj in the base link manifest")
    entries[entries.index(original)] = str(obj)
    if args.call_mode == "c":
        call = out / "call"
        call.with_suffix(".c").write_text('''typedef unsigned char u8;
typedef unsigned short u16;
extern u8 wide_force_c_buffers[];
extern u16 wide_force_active_arg;
void wide_force_component(const u8 *, const u8 *, u16, u8 *, u8 *);
void wide_force_c_call(void) {
    wide_force_component(wide_force_c_buffers, wide_force_c_buffers+6,
                         wide_force_active_arg, wide_force_c_buffers+12,
                         wide_force_c_buffers+18);
}
''')
        dev = binaries.parent
        subprocess.run([str(binaries / "816-tcc"), "-Wall", "-F", "-Isrc",
                        "-I" + str(args.gen),
                        "-I" + str(dev.parent / "pvsneslib/include"),
                        "-I" + str(dev / "include"), "-c", str(call.with_suffix(".c")),
                        "-o", str(call.with_suffix(".ps"))], check=True)
        subprocess.run([str(dev / "tools/816-opt"), "-i", str(call.with_suffix(".ps")),
                        "-o", str(call.with_suffix(".s"))], check=True)
        subprocess.run([str(binaries / "wla-65816"), "-d", "-s", "-x",
                        "-I" + str(args.gen), "-Isrc", "-o", str(call.with_suffix(".obj")),
                        str(call.with_suffix(".s"))], check=True)
        entries.append(str(call.with_suffix(".obj")))
    manifest = out / "probe.link"
    manifest.write_text("\n".join(entries) + "\n")
    rom = out / "probe.sfc"
    with (out / "link.log").open("w") as log:
        subprocess.run([str(binaries / "wlalink"), "-d", "-S", "-A", "-c",
                        str(manifest), str(rom)], stdout=log, stderr=log, check=True)
    return rom


def vectors():
    edge = [-(1 << 47), (1 << 47) - 1, -(1 << 38), -(1 << 35),
            -(1 << 35) + 1, (1 << 35) - 1, 1 << 35, (1 << 38) - 1,
            1 << 38, 0, -1, 1]
    cases = [(g, v, active) for g in edge for v in edge for active in (0, 1)]
    rng = random.Random(873)
    cases += [(rng.randrange(-(1 << 36), 1 << 36),
               rng.randrange(-(1 << 39), 1 << 39), rng.randrange(2))
              for _ in range(500)]
    cases += [(rng.randrange(-(1 << 34), 1 << 34),
               rng.randrange(-(1 << 38), 1 << 38), rng.randrange(2))
              for _ in range(800)]
    results = []
    for gumi, rate, active in cases:
        fast = -(1 << 35) <= gumi < 1 << 35 and -(1 << 38) <= rate < 1 << 38
        numerator = active * gumi * 32009962 * 256 + rate * 586263036
        rounded = ((abs(numerator) + (1 << 29)) >> 30) * (-1 if numerator < 0 else 1)
        results.append((gumi, rate, active, int(not fast), rounded & ((1 << 48) - 1)))
    return results


def instrument(symbols, steps):
    rows = ",".join("{%d,%d,%d,%d,%d}" % row for row in vectors())
    return '''
local wmem=emu.memType.snesMemory
local wram=%d
local wcbuf=%d
local wregs=%d
local wactive=%d
local wcases={%s}
local windex=0
local wcallindex=0
local wbad=0
local wtimes={active={},inactive={},fallback={},call_active={},call_inactive={},call_fallback={}}
local wstart=0
local wcallstart=0
local wexpected=nil
local function wwrite(a,v,n)
 for i=0,n-1 do emu.write(a+i,(v>>(i*8))&255,wmem) end
end
local function wread(a,n)
 local v=0
 for i=0,n-1 do v=v|(emu.read(a+i,wmem)<<(i*8)) end
 return v
end
local function wcheck(name,got,want)
 if got~=want then
  wbad=wbad+1
  if wbad<10 then print("FORCEFAIL "..name.." "..windex.." "..got.." "..want) end
 end
end
local function wkind(c)
 return c[4]~=0 and "fallback" or (c[3]~=0 and "active" or "inactive")
end
emu.addMemoryCallback(function()
 windex=windex+1
 local c=wcases[(windex-1)%%#wcases+1]
 wwrite(wram+128,c[1],6) wwrite(wram+134,c[2],6) wwrite(wram+140,c[3],1)
 wwrite(wram+154,0x12456789abcd,6)
 wwrite(wram+142,0xa5,1) wwrite(wram+143,0x5a,1) wwrite(wram+160,0x3c,1)
 wexpected=c wstart=emu.getMasterClock()
end,emu.callbackType.exec,%d,%d)
emu.addMemoryCallback(function()
 local c=wexpected
 wcheck("fallback",wread(wram+141,1),c[4])
 wcheck("gumi_input",wread(wram+128,6),c[1]&((1<<48)-1))
 wcheck("rate_input",wread(wram+134,6),c[2]&((1<<48)-1))
 wcheck("flag_canary",wread(wram+142,1),0xa5)
 wcheck("scratch_before",wread(wram+143,1),0x5a)
 wcheck("output_after",wread(wram+160,1),0x3c)
 wcheck("output",wread(wram+154,6),c[4]==0 and c[5] or 0x12456789abcd)
 local times=wtimes[wkind(c)] times[#times+1]=emu.getMasterClock()-wstart
end,emu.callbackType.exec,%d,%d)
emu.addMemoryCallback(function()
 wcallindex=wcallindex+1
 local c=wexpected
 wwrite(wcbuf,c[1],6) wwrite(wcbuf+6,c[2],6)
 wwrite(wcbuf+12,0x12456789abcd,6) wwrite(wcbuf+18,0x77,1)
 wwrite(wcbuf+19,0xa5,1) wwrite(wcbuf+20,0x5a,1) wwrite(wcbuf+21,0x3c,1)
 wwrite(wactive,c[3]~=0 and 0x100 or 0,2)
 wcallstart=emu.getMasterClock()
end,emu.callbackType.exec,%d,%d)
emu.addMemoryCallback(function()
 local c=wexpected
 wcheck("call_fallback",wread(wcbuf+18,1),c[4])
 wcheck("call_gumi",wread(wcbuf,6),c[1]&((1<<48)-1))
 wcheck("call_rate",wread(wcbuf+6,6),c[2]&((1<<48)-1))
 wcheck("call_flag_canary",wread(wcbuf+19,1),0xa5)
 wcheck("call_output_after",wread(wcbuf+20,1),0x5a)
 wcheck("call_after",wread(wcbuf+21,1),0x3c)
 wcheck("call_output",wread(wcbuf+12,6),c[4]==0 and c[5] or 0x12456789abcd)
 local times=wtimes["call_"..wkind(c)] times[#times+1]=emu.getMasterClock()-wcallstart
end,emu.callbackType.exec,%d,%d)
emu.addMemoryCallback(function()
 for i=0,4,2 do wcheck("call_register_"..i,wread(wregs+i+8,2),wread(wregs+i,2)) end
 wcheck("call_db",wread(wregs+14,1),wread(wregs+6,1))
 if windex==%d then
  local fields={string.format('"cases":%%d,"wrapper_cases":%%d,"failures":%%d',windex,wcallindex,wbad)}
  for name,t in pairs(wtimes) do
   table.sort(t) local sum=0 for _,dt in ipairs(t) do sum=sum+dt end
   fields[#fields+1]=string.format('"%%s":{"count":%%d,"median":%%d,"max":%%d,"total":%%d}',name,#t,t[math.floor((#t+1)/2)] or 0,t[#t] or 0,sum)
  end
  out("NATIVE","native-results.json","{"..table.concat(fields,",").."}")
 end
end,emu.callbackType.exec,%d,%d)
''' % (symbols["wide_force_ram"], symbols["wide_force_c_buffers"],
       symbols["wide_force_abi_regs"], symbols["wide_force_active_arg"], rows,
       symbols["wide_force_native"], symbols["wide_force_native"],
       symbols["wide_force_native_end"], symbols["wide_force_native_end"],
       symbols["wide_force_call_begin"], symbols["wide_force_call_begin"],
       symbols["wide_force_call_end"], symbols["wide_force_call_end"], steps,
       symbols["wide_force_abi_end"], symbols["wide_force_abi_end"])

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("build/wide-force-native"))
    parser.add_argument("--pvs")
    parser.add_argument("--gen", type=Path, default=Path("build/gen"))
    parser.add_argument("--link", type=Path, default=Path("build/test_phys.sfc.link"))
    parser.add_argument("--physdump", default="build/host/physdump")
    parser.add_argument("--cases", default="test/physcases.txt")
    parser.add_argument("--call-mode", choices=("asm", "c"), default="c",
                        help="measure the pointer wrapper via a compiled C caller or assembly")
    args = parser.parse_args()
    os.chdir(ROOT)
    rom = build(args)
    symbols = mesen.read_symbols(str(rom))
    check_dir = args.out / "check"
    original = mesen.run

    def run(probe_rom, script, out_dir, *positional, **kwargs):
        steps = (Path(out_dir) / "host_log.bin").stat().st_size // 6
        lua = Path(kwargs["lua"])
        lua.write_text(lua.read_text() + instrument(symbols, steps))
        return original(probe_rom, script, out_dir, *positional, **kwargs)

    mesen.run = run
    try:
        unchanged = physrom.run(argparse.Namespace(
            rom=str(rom), physdump=args.physdump, gen=str(args.gen), cases=args.cases,
            full=12, full_from=0, out=str(check_dir)))
    finally:
        mesen.run = original
    report = json.loads((check_dir / "native-results.json").read_text())
    report.update(physics_unchanged=bool(unchanged), table_bytes=wide_force_gen.TABLE_BYTES,
                  call_mode=args.call_mode,
                  clock_scope="macro entry through exit excludes RTS; wrapper includes argument pushes, JSL, copies, register saves/restores and caller cleanup")
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if unchanged and report["failures"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
