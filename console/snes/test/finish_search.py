"""Searches a script of keys that finishes a level in the test ROM
build/test_play.sfc, inside Mesen 2 (test/mesen.py) with its save states: a
beam search over short segments of keys, each tried from the state of its
parent in the real game. Its timing (slow frames, the keys read once an
iteration) cannot be predicted on the host, so the search runs in the ROM.

  finish_search.py ROM LEVEL [--width N] [--gens N] [--prefix SCRIPT] [--out FILE]

Level 0 (Warm Up): first to the apple (the first segment turns), then, after
a second turn, to the flower; the bike must not rush near the flower. Mesen
ends a run after about 100 s, so the search goes on in runs of some
generations, each replaying the best script so far (--prefix continues one);
a run that has no way on goes back some frames. The script (syntax of
test/play.py) goes to FILE and to the output; test/finish_test.py checks it.
"""

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mesen  # noqa: E402

NAMES = [(1, 'UP'), (2, 'DOWN'), (4, 'RIGHT'), (8, 'LEFT'), (16, 'SPACE')]

LUA = r'''
local WIDTH, SEED = %(width)d, %(seed)d
local TARGET_APPLE, TARGET_FLOWER = %(apple)f, %(flower)f
local MAXGEN = %(maxgen)d
local PREFIX = {%(prefix)s}
local PREFIX_TURNS = %(turns)d
local VMAX, SPEEDPEN = %(vmax)f, %(speedpen)f
local sym = %(syms)s
local mem = emu.memType.snesMemory
math.randomseed(SEED)
-- keys: 1 up, 2 down, 4 right, 8 left, 16 turn
local ACTS = {0, 1, 1 + 4, 1 + 8, 4, 8, 2}
local DURS = {6, 12, 24}
local BTN = {[1] = "b", [2] = "a", [4] = "right", [8] = "left", [16] = "x"}

local function guard(f)
  return function(...)
    local ok, err = pcall(f, ...)
    if not ok then print("LUAERR " .. tostring(err)) emu.stop(2) end
  end
end
local frame, start, t = 0, nil, 0
local mode = "warm"          -- warm, eval
local cur = nil              -- the candidate in the run
local over, finished = false, false
local beam, nextbeam = {}, {}
local queue, qi = {}, 1
local gen = 0

local LEVEL = %(level)d
local DEBUG = %(debug)s
local function s32(v) if v >= 0x80000000 then return v - 0x100000000 end return v end

emu.addMemoryCallback(guard(function()
  if not start then start = frame end
end), emu.callbackType.exec, sym.phys_step, sym.phys_step)

emu.addMemoryCallback(guard(function()
  local ev = emu.getState()["cpu.x"]
  if ev & 3 ~= 0 then
    over = true
    if ev & 2 ~= 0 then finished = true end
  end
end), emu.callbackType.exec, sym.phys_step_ret, sym.phys_step_ret)

-- The keys of a candidate at the poll of time t: the first poll after a
-- load keeps the keys of the node (lastkey); the keys of the segment are
-- polled from the second on.
local function keyat(c, tt)
  local i = tt - c.T0
  if i == 0 then return c.parent.lastkey end
  if i >= 1 and i <= c.dur then
    local k = c.key
    if c.turn and i == 1 then k = k | 16 end
    return k
  end
  return 0
end

emu.addEventCallback(guard(function()
  local inp = {}
  if mode == "warm" and t >= 1 then
    local k = PREFIX[t] or 0
    for bit, name in pairs(BTN) do if k & bit ~= 0 then inp[name] = true end end
  end
  if mode == "eval" and cur and t >= 1 then
    local k = keyat(cur, t)
    for bit, name in pairs(BTN) do if k & bit ~= 0 then inp[name] = true end end
  end
  emu.setInput(inp, 0)
end), emu.eventType.inputPolled)

local function clear_ram()
  for i = 0, emu.getMemorySize(emu.memType.snesWorkRam) - 1 do emu.write(i, 0, emu.memType.snesWorkRam) end
  for i = 0, emu.getMemorySize(emu.memType.spcRam) - 1 do emu.write(i, 0, emu.memType.spcRam) end
end
clear_ram()

local function view()
  return s32(emu.read32(sym.phys_view, mem)) / 65536, s32(emu.read32(sym.phys_view + 4, mem)) / 65536,
    emu.read16(sym.phys_view + 8, mem)
end

local function score(c, x, y, apples_left)
  local target = (apples_left == 0) and TARGET_FLOWER or TARGET_APPLE
  local s = -math.abs(target - x) - c.T * 0.002
  -- near the end the bike should not rush (a flip or a crash kills it)
  if apples_left == 0 and math.abs(target - x) < 12 then
    local v = math.abs(x - c.parent.x) / math.max(1, c.T - c.parent.T)
    s = s - SPEEDPEN * math.max(0, v - VMAX)
  end
  if apples_left == 0 then s = s + 400 end
  return s + math.random() * 0.05
end

local function keysof(c)
  -- the keys by the time t (the script frame is t - 1)
  local chain = {}
  local n = c
  while n.parent do
    table.insert(chain, 1, n)
    n = n.parent
  end
  local out = {}
  for _, nd in ipairs(chain) do
    nd.T0 = nd.parent.T
    for tt = nd.parent.T, nd.T - 1 do
      out[tt] = keyat(nd, tt)
    end
  end
  for tt = 1, n.T - 1 do out[tt] = PREFIX[tt] or 0 end
  local list = {}
  for tt = 1, c.T - 1 do list[#list + 1] = out[tt] or 0 end
  return list
end

local function next_candidate()
  while qi <= #queue do
    local c = queue[qi]
    qi = qi + 1
    emu.loadSavestate(c.parent.state)
    t = c.parent.T
    c.T0 = t
    over, finished = false, false
    cur = c
    return true
  end
  return false
end

local function expand()
  queue, qi = {}, 1
  for _, p in ipairs(beam) do
    for _, a in ipairs(ACTS) do
      for _, d in ipairs(DURS) do
        for turn = 0, 1 do
          local ok = true
          if p.turns == 0 then ok = (turn == 1)
          elseif turn == 1 then ok = p.apples == 0 and p.turns < 2 end
          if ok then
            queue[#queue + 1] = {parent = p, key = a, dur = d, turn = (turn == 1), turns = p.turns + turn}
          end
        end
      end
    end
  end
end

local made
local function insert_kept(c)
  -- keep the best WIDTH candidates of the generation
  local worst_i, worst = nil, nil
  if #nextbeam >= WIDTH then
    for i, n in ipairs(nextbeam) do
      if not worst or n.score < worst then worst_i, worst = i, n.score end
    end
    if c.score <= worst then return end
  end
  -- (duplicates of the state: the same cell of x, y, angle)
  for i, n in ipairs(nextbeam) do
    if n.cell == c.cell then
      if n.score >= c.score then return end
      table.remove(nextbeam, i)
      worst_i = nil
      break
    end
  end
  c.state = emu.createSavestate()
  made = true
  if worst_i and #nextbeam >= WIDTH then table.remove(nextbeam, worst_i) end
  nextbeam[#nextbeam + 1] = c
end

local function keylist(c)
  local t2 = {}
  for _, k in ipairs(keysof(c)) do t2[#t2 + 1] = tostring(k) end
  return table.concat(t2, ",")
end

function report(c)
  print("SCRIPT " .. keylist(c))
  emu.stop(0)
end

local function finish_candidate()
  local c = cur
  local x, y, ang = view()
  local apples_left = emu.read16(sym.phys_apples_left, mem)
  c.T = t
  c.x = x
  c.lastkey = keyat(c, t - 1)
  c.apples = apples_left
  if DEBUG and gen <= 3 then
    print(string.format("CAND gen %%d T0 %%d key %%d dur %%d turn %%s -> T %%d x %%.3f y %%.3f steps %%d fc %%d", gen, c.T0, c.key, c.dur, tostring(c.turn), c.T, x, y, emu.read16(sym.steps, mem), emu.read16(sym.core_frame_count, mem)))
  end
  if over then
    if finished then print("FINISHED") report(c) end
    return
  end
  c.score = score(c, x, y, apples_left)
  c.cell = string.format("%%d,%%d,%%d,%%d", math.floor(x * 3), math.floor(y * 3), ang // 2048, c.T // 6)
  insert_kept(c)
end

local function new_generation()
  beam = nextbeam
  nextbeam = {}
  gen = gen + 1
  if #beam == 0 then print("NOBEAM") emu.stop(1) return false end
  table.sort(beam, function(a, b) return a.score > b.score end)
  print("PART " .. keylist(beam[1]))
  print(string.format("GEN %%d beam %%d best %%.1f T %%d apples_left %%d", gen, #beam, beam[1].score, beam[1].T, beam[1].apples))
  if gen > MAXGEN then
    print("MAXGEN")
    local b = beam[1]
    emu.loadSavestate(b.state)
    local x, y = view()
    print(string.format("INFO T %%d x %%.3f y %%.3f steps %%d fc %%d", b.T, x, y, emu.read16(sym.steps, mem), emu.read16(sym.core_frame_count, mem)))
    report(b)
    return false
  end
  expand()
  return true
end

-- Once an iteration of the game (the save states need an exec callback, and
-- one operation per call):
local pending = false
local function advance()
  -- loads the next candidate (a generation done: the next generation)
  if not next_candidate() then
    if new_generation() then next_candidate() end
  end
end
emu.addMemoryCallback(guard(function()
  if mode == "warm" then
    if start and t >= 1 and t > #PREFIX then
      local root = {x = view(), state = emu.createSavestate(), T = t, lastkey = PREFIX[t - 1] or 0, turns = PREFIX_TURNS, apples = emu.read16(sym.phys_apples_left, mem), score = 0}
      if t - 1 > #PREFIX then root.lastkey = 0 end
      nextbeam = {root}
      mode = "eval"
      if new_generation() then pending = true end
    end
    return
  end
  if pending then
    pending = false
    advance()
    return
  end
  if over or t >= cur.T0 + cur.dur + 1 then
    made = false
    finish_candidate()
    if made then pending = true else advance() end
  end
end), emu.callbackType.exec, sym.core_frame_done, sym.core_frame_done)

emu.addEventCallback(guard(function()
  frame = frame + 1
  if frame == 120 then
    emu.write16(sym.play_level, LEVEL, mem)
    emu.write16(sym.play_go, 0x5AA5, mem)
  end
  if mode == "warm" then
    if start then t = frame - start end
  else
    t = t + 1
  end
end), emu.eventType.endFrame)
'''


def compress(script):
    toks = []
    i = 0
    while i < len(script):
        k = script[i]
        j = i + 1
        if not k & 16:
            while j < len(script) and script[j] == k:
                j += 1
        names = [n for b, n in NAMES if k & b]
        toks.append('%s%d' % ('+'.join(names) if names else 'W', j - i))
        i = j
    return ' '.join(toks)


def expand(text):
    keys = {n: b for b, n in NAMES}
    out = []
    for tok in text.split():
        name = tok.rstrip('0123456789')
        n = int(tok[len(name):] or 1)
        k = 0 if name == 'W' else sum(keys[x] for x in name.split('+'))
        out += [k] * n
    return out


def chunk(a, prefix):
    """One run of Mesen (it ends after about 100 s, so a run is only some
    generations of the search): returns (finished, script)."""
    syms = mesen.read_symbols(a.rom)
    names = ['core_frame_count', 'play_go', 'play_level', 'phys_step', 'phys_step_ret',
             'core_frame_done', 'phys_view', 'phys_apples_left']
    luasyms = '{' + ', '.join('%s = %d' % (n, syms[n]) for n in names) + \
        ', steps = %d}' % syms['tccs_build/obj/game.s_Steps']
    lua = LUA % dict(width=a.width, seed=a.seed, syms=luasyms, maxgen=a.gens, level=a.level,
                     debug='false', apple=a.apple, flower=a.flower,
                     prefix=','.join(str(k) for k in prefix), vmax=a.vmax, speedpen=a.speedpen,
                     turns=sum(1 for k in prefix if k & 16))
    os.makedirs(a.work, exist_ok=True)
    path = os.path.join(a.work, '.finish.lua')
    with open(path, 'w') as f:
        f.write(lua)
    p = subprocess.Popen([mesen.find_mesen(), '--testrunner', os.path.abspath(a.rom), os.path.abspath(path)],
                         stdout=subprocess.PIPE, text=True)
    script = part = None
    finished = False
    for line in p.stdout:
        line = line.rstrip()
        if line.startswith('SCRIPT '):
            script = [int(v) for v in line[7:].split(',')]
        elif line.startswith('PART '):
            part = [int(v) for v in line[5:].split(',')]
        elif line == 'FINISHED':
            finished = True
        elif line.startswith(('GEN', 'INFO', 'NOBEAM', 'LUAERR', 'CAND')):
            print(line, flush=True)
    p.wait()
    return finished, script or part


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('rom')
    ap.add_argument('level', type=int)
    ap.add_argument('--width', type=int, default=8)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--gens', type=int, default=7, help='generations a run of the emulator')
    ap.add_argument('--chunks', type=int, default=60)
    ap.add_argument('--apple', type=float, default=17.92)
    ap.add_argument('--flower', type=float, default=-11.45)
    ap.add_argument('--vmax', type=float, default=0.04, help='m a frame, near the flower')
    ap.add_argument('--speedpen', type=float, default=150.0)
    ap.add_argument('--prefix', default='', help='a script to continue from')
    ap.add_argument('--out', default='')
    ap.add_argument('--work', default='.')
    a = ap.parse_args()
    prefix = expand(a.prefix)
    stuck = 0
    for i in range(a.chunks):
        finished, script = chunk(a, prefix)
        if script is None:
            raise SystemExit('the search ended without a script')
        if len(script) <= len(prefix) + 1 and not finished:
            # Every way on died: go back and try again from earlier.
            back = 60 * (1 + stuck)
            stuck += 1
            script = script[:max(0, len(script) - back)]
            print('stuck, back to %d frames' % len(script), flush=True)
        else:
            stuck = 0
        prefix = script
        text = compress(prefix)
        print('chunk %d: %d frames%s' % (i, len(prefix), ', FINISHED' if finished else ''), flush=True)
        print(text, flush=True)
        if a.out:
            with open(a.out, 'w') as f:
                f.write(text + '\n')
        if finished:
            return
        a.seed += 1
    raise SystemExit('not finished after %d chunks' % a.chunks)


if __name__ == '__main__':
    main()
