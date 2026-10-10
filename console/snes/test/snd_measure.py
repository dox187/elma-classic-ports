"""Measures the sound module in Mesen with the test ROM (build/test_snd.sfc):
the time of snd_init, snd_frame, snd_effect and snd_stop on the 65816
(master clocks), the time of the driver's ticks on the SPC700 (its cycles),
and the state of the voices of the DSP at a few frames of the sequence.

  snd_measure.py [ROM] [--frames N] [--out DIR]
"""

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mesen  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# Frames of the sequence (after the upload) to look at the voices: the
# idle, the gas rising, the gas loop, the friction, the effects.
LOOK = [80, 200, 260, 450, 560, 705, 1101]

LUA = r'''
local stats = {}
local t0 = {}
local function clock() return emu.getState()["masterClock"] end
local function spccycle() return emu.getState()["spc.cycle"] end
local function stat(name, v)
  local s = stats[name]
  if not s then s = {n = 0, sum = 0, min = v, max = v}; stats[name] = s end
  s.n = s.n + 1; s.sum = s.sum + v
  if v < s.min then s.min = v end
  if v > s.max then s.max = v end
end
local function enter(name) return function() t0[name] = clock() end end
local function leave(name) return function()
  if t0[name] then stat(name, clock() - t0[name]); t0[name] = nil end
end end
local cpu = emu.cpuType.snes
local exec = emu.callbackType.exec
%(cpu_hooks)s
local tick0 = nil
local frame_seq = -1
emu.addMemoryCallback(function() tick0 = spccycle() end, exec, %(tick)d, %(tick)d, emu.cpuType.spc, emu.memType.spcMemory)
emu.addMemoryCallback(function()
  if tick0 then
    local dt = spccycle() - tick0
    stat("spc_tick", dt)
    if dt > %(long_tick)d then
      print(string.format("LONGTICK %%d cycles at sequence frame %%d", dt, frame_seq))
    end
    tick0 = nil
  end
end, exec, %(tick_ret)d, %(tick_ret)d, emu.cpuType.spc, emu.memType.spcMemory)
local looks = { %(looks)s }
emu.addMemoryCallback(function() frame_seq = frame_seq + 1
  for _, f in ipairs(looks) do
    if f == frame_seq then
      local r = {}
      for v = 0, 7 do
        local b = v * 16
        local function d(o) return emu.read(b + o, emu.memType.spcDspRegisters) end
        r[#r + 1] = string.format("v%%d vol %%3d pitch %%5d srcn %%d gain %%02X env %%3d", v,
          d(0), d(2) + 256 * d(3), d(4), d(7), d(8))
      end
      print("VOICES " .. f .. " | " .. table.concat(r, " | "))
    end
  end
end, exec, %(frame)d, %(frame)d, cpu)
function report()
  for name, s in pairs(stats) do
    print(string.format("STAT %%s n %%d min %%d avg %%d max %%d", name, s.n, s.min,
      math.floor(s.sum / s.n), s.max))
  end
end
'''


def syms(path):
    out = {}
    for line in open(path):
        p = line.split()
        if len(p) == 2 and not p[0].startswith(";") and not p[0].startswith("["):
            try:
                out[p[1]] = int(p[0].replace(":", ""), 16)
            except ValueError:
                pass
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("rom", nargs="?", default=os.path.join(HERE, "..", "build", "test_snd.sfc"))
    ap.add_argument("--frames", type=int, default=1420)
    ap.add_argument("--long-tick", type=int, default=100000,
                    help="print the ticks of the SPC700 longer than this")
    ap.add_argument("--out", default=os.path.join(HERE, "..", "build", "measure"))
    a = ap.parse_args()
    s = syms(os.path.splitext(a.rom)[0] + ".sym")
    d = syms(os.path.join(os.path.dirname(a.rom), "spc", "driver.sym"))
    hooks = []
    # Each function from its entry to its rtl:
    for name, end in (("snd_init", s["snd_frame"] - 1),
                      ("snd_frame", s["_frame_end"] + 2),
                      ("snd_effect", s["_effect_end"] + 2),
                      ("snd_stop", s["_stop_end"] + 2)):
        hooks.append('emu.addMemoryCallback(enter("%s"), exec, %d, %d, cpu)'
                     % (name, s[name], s[name]))
        hooks.append('emu.addMemoryCallback(leave("%s"), exec, %d, %d, cpu)'
                     % (name, end, end))
    lua = LUA % {
        "cpu_hooks": "\n".join(hooks),
        "tick": d["tick"] & 0xFFFF,
        # The ret of tick is the last byte before commands:
        # The ret of tick is its last byte, before commands:
        "tick_ret": (d["commands"] - 1) & 0xFFFF,
        "looks": ", ".join(str(f) for f in LOOK),
        "frame": s["snd_test_mark"],
        "long_tick": a.long_tick,
    }
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "measure.lua")
    with open(path, "w") as f:
        f.write(lua)
    # The report at the last frame:
    script = "W%d" % a.frames
    lua_src = mesen.make_lua(script, a.rom, extra=path)
    lua_src = lua_src.replace("if frame >= last_frame then emu.stop(0) end",
                              "if frame >= last_frame then report(); emu.stop(0) end")
    run = os.path.join(a.out, "run.lua")
    with open(run, "w") as f:
        f.write(lua_src)
    p = subprocess.run([mesen.find_mesen(), "--testrunner", os.path.abspath(a.rom),
                        os.path.abspath(run)], capture_output=True, text=True,
                       timeout=900)
    for line in p.stdout.splitlines():
        if line.split(" ")[0] in ("STAT", "VOICES", "LONGTICK"):
            print(line)
    if p.returncode:
        print(p.stderr)


if __name__ == "__main__":
    main()
