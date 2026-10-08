"""Plays a level of the game in the test ROM build/test_play.sfc (Mesen 2,
test/mesen.py) with the keys of the original game, a script in the syntax of
the PC reference tool: W<n> frames without keys, KEY<n> keys held (UP gas,
DOWN brake, LEFT and RIGHT volts, SPACE turn, ESC; joined with +), from the
first frame of the level.

  play.py ROM LEVEL "SPACE1 UP90 W78 ..." [--out DIR] [--shots N] [--lua FILE]

Prints whether the level was finished and its time; --shots N saves a
picture every N frames; --lua FILE adds a script of its own (measurements,
for example) and prints the other lines it prints.
"""

import argparse
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mesen  # noqa: E402

KEYS = {'UP': 'b', 'DOWN': 'a', 'LEFT': 'left', 'RIGHT': 'right',
        'SPACE': 'x', 'ESC': 'start'}


def frames(script):
    out = []
    for tok in script.split():
        name = tok.rstrip('0123456789')
        n = int(tok[len(name):] or 1)
        keys = [] if name == 'W' else name.split('+')
        for k in keys:
            if k not in KEYS:
                raise SystemExit('unknown key: %s' % k)
        out += [keys] * n
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('rom')
    ap.add_argument('level', type=int)
    ap.add_argument('script')
    ap.add_argument('--out', default='.')
    ap.add_argument('--shots', type=int, default=0)
    ap.add_argument('--trace', type=int, default=0,
                    help='print the steps and the position of the bike every N frames')
    ap.add_argument('--random-ram', action='store_true',
                    help='keep the random work RAM of Mesen (else cleared)')
    ap.add_argument('--after', type=int, default=120,
                    help='frames to wait for the end after the keys')
    ap.add_argument('--lua', help='a Lua script added to the run')
    a = ap.parse_args()
    syms = mesen.read_symbols(a.rom)
    keys = frames(a.script)
    lua = ['local frame, start = 0, nil', 'local lev = {}']
    for i, k in enumerate(keys):
        if k:
            lua.append('lev[%d] = {%s}' % (i, ', '.join('%s = true' % KEYS[x] for x in k)))
    lua.append('local total, shots = %d, %d' % (len(keys) + a.after, a.shots))
    for name in ('play_go', 'play_level', 'play_done', 'play_finished', 'play_time',
                 'phys_step'):
        lua.append('local %s = %d' % (name, syms[name]))
    lua.append('local level = %d' % a.level)
    lua.append('local trace = %d' % a.trace)
    lua.append('local fc_at = %d' % syms['core_frame_count'])
    lua.append('local steps_at = %d' % syms.get('tccs_build/obj/game.s_Steps', 0))
    lua.append('local view_at = %d' % syms['phys_view'])
    lua.append('local CLEAR = %s' % ('false' if a.random_ram else 'true'))
    lua.append(r'''
local mem = emu.memType.snesMemory
local function hex(s) return (s:gsub(".", function(c) return string.format("%02x", string.byte(c)) end)) end
local function shot(name) print("SHOT " .. name .. " " .. hex(emu.takeScreenshot())) end
-- At the load of the script the CPU has not started yet:
if CLEAR then
  for i = 0, emu.getMemorySize(emu.memType.snesWorkRam) - 1 do emu.write(i, 0, emu.memType.snesWorkRam) end
  for i = 0, emu.getMemorySize(emu.memType.spcRam) - 1 do emu.write(i, 0, emu.memType.spcRam) end
end
local itlog = {}
emu.addMemoryCallback(function()
  local fc = emu.read16(fc_at, mem)
  local n = #itlog
  if n > 0 and itlog[n][1] == fc then itlog[n][2] = itlog[n][2] + 1 else itlog[n + 1] = {fc, 1} end
end, emu.callbackType.exec, phys_step, phys_step)
emu.addMemoryCallback(function() if not start then start = frame end end,
  emu.callbackType.exec, phys_step, phys_step)
emu.addEventCallback(function()
  local inp = {}
  -- the first frame of the level (the first steps) has run when start is set:
  if start then inp = lev[frame - start - 1] or {} end
  emu.setInput(inp, 0)
end, emu.eventType.inputPolled)
emu.addEventCallback(function()
  frame = frame + 1
  if frame == 120 then
    emu.write16(play_level, level, mem)
    emu.write16(play_go, 0x5AA5, mem)
  end
  if start then
    local i = frame - start
    if trace > 0 and i % trace == 0 then
      print(string.format("TRACE %d %d %d %d", emu.read16(fc_at, mem), emu.read16(steps_at, mem),
        emu.read32(view_at, mem), emu.read32(view_at + 4, mem)))
    end
    if shots > 0 and i % shots == 0 then shot(string.format("f%05d.png", i)) end
    if emu.read16(play_done, mem) == 1 or i >= total then
      if trace > 0 then
        local t = {}
        for _, e in ipairs(itlog) do t[#t + 1] = e[1] .. ":" .. e[2] end
        print("ITER " .. table.concat(t, " "))
      end
      print(string.format("RESULT %d %d %d %d", emu.read16(play_done, mem),
        emu.read16(play_finished, mem), emu.read32(play_time, mem), i))
      shot("end.png")
      emu.stop(0)
    end
  end
  if frame > 120 + total + 600 then print("RESULT 0 0 0 -1") emu.stop(1) end
end, emu.eventType.endFrame)
''')
    if a.lua:
        with open(a.lua) as f:
            lua.append(f.read())
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, '.play.lua')
    with open(path, 'w') as f:
        f.write('\n'.join(lua))
    p = subprocess.run([mesen.find_mesen(), '--testrunner', os.path.abspath(a.rom),
                        os.path.abspath(path)], capture_output=True, text=True)
    for line in p.stdout.splitlines():
        if line.startswith('SHOT '):
            _, name, data = line.split(' ', 2)
            with open(os.path.join(a.out, name), 'wb') as f:
                f.write(bytes.fromhex(data.strip()))
        elif line.startswith('TRACE '):
            i, steps, x, y = (int(v) for v in line.split()[1:])
            x, y = (v - (1 << 32) if v >= 1 << 31 else v for v in (x, y))
            print('frame %d steps %d x %.2f y %.2f' % (i, steps, x / 65536, y / 65536))
        elif line.startswith('ITER '):
            print(line)
        elif line.startswith('RESULT '):
            done, fin, time, n = (int(v) for v in line.split()[1:])
            if not done:
                print('the level did not end (%d frames)' % n)
            elif fin:
                print('finished in %02d:%02d:%02d (frame %d)' % (time // 6000, time // 100 % 60, time % 100, n))
            else:
                print('not finished (frame %d)' % n)
        elif a.lua:
            print(line)


if __name__ == '__main__':
    main()
