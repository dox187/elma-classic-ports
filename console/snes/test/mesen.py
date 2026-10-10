"""Plays a ROM in the test runner of Mesen 2 (no window) with a script of
buttons, saves screenshots and memory, prints values.

  mesen.py ROM "W60 START5 W30 A+RIGHT120 SHOT:out.png" [--out DIR]

Steps of the script, separated by spaces:
  W<n>                  n frames without buttons (W is one frame)
  A+RIGHT<n>            buttons held for n frames (A B X Y L R START SELECT
                        UP DOWN LEFT RIGHT, joined with +; one frame without n)
  SHOT:<file.png>       the screen
  WRAM:<file>  SRAM:<file>  VRAM:<file>  CGRAM:<file>  OAM:<file>
                        the memory
  PEEK:<addr|label>:<n> prints n bytes of the memory of the CPU at a 24-bit
                        address (hex) or a label of the .sym file
  CLOCK                 prints the frame, the master clock and the CPU cycles

The SRAM is cleared before the start (--sram FILE loads it instead, --keep-sram
keeps what Mesen has). The work RAM is cleared too, so that runs repeat
exactly (Mesen fills it at random, like the console); --random-ram keeps it. --lua FILE adds a script of its own (it runs before
the steps; the helpers below are global). The Mesen 2 executable is taken
from $MESEN or the usual places.

As a module: run(rom, script, ...) returns the printed values as a list of
(kind, name, bytes) and writes the files.
"""

import argparse
import binascii
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile
import os
import subprocess
import sys

MESEN_PATHS = [
    os.environ.get('MESEN', ''),
    os.path.expanduser('~/.local/share/elma-snes/mesence-2.2.1/Mesen'),
    os.path.expanduser('~/.local/bin/Mesen'),
    '/usr/bin/mesen',
]

BUTTONS = {'A': 'a', 'B': 'b', 'X': 'x', 'Y': 'y', 'L': 'l', 'R': 'r',
           'START': 'start', 'SELECT': 'select', 'UP': 'up', 'DOWN': 'down',
           'LEFT': 'left', 'RIGHT': 'right'}

MEMTYPES = {'WRAM': 'snesWorkRam', 'SRAM': 'snesSaveRam',
            'VRAM': 'snesVideoRam', 'CGRAM': 'snesCgRam',
            'OAM': 'snesSpriteRam'}

LUA_HEAD = r'''
local frame = 0
local steps = {}      -- frame -> list of actions
local inputs = {}     -- frame -> input table
local last_frame = 0
local function hex(s)
  return (s:gsub(".", function(c) return string.format("%02x", string.byte(c)) end))
end
function out(kind, name, data) print("OUT " .. kind .. " " .. name .. " " .. hex(data)) end
function dump(kind, name, memtype, addr, len)
  local t = {}
  for i = 0, len - 1 do t[#t + 1] = string.char(emu.read(addr + i, memtype)) end
  out(kind, name, table.concat(t))
end
function memsize(memtype) return emu.getMemorySize(memtype) end
'''

LUA_TAIL = r'''
emu.addEventCallback(function()
  local inp = inputs[frame]
  if inp then emu.setInput(inp, 0) else emu.setInput({}, 0) end
end, emu.eventType.inputPolled)
emu.addEventCallback(function()
  frame = frame + 1
  local acts = steps[frame]
  if acts then for _, f in ipairs(acts) do f() end end
  if frame >= last_frame then emu.stop(0) end
end, emu.eventType.endFrame)
'''


def find_mesen():
    for p in MESEN_PATHS:
        if p and os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    raise SystemExit('Mesen 2 not found: set MESEN')


def testrunner_command(rom, lua):
    """Use a deterministic portable profile, independent of desktop settings.

    A default MesenCE installation can have no SNES controller configured:
    inputPolled then never fires and scripted buttons silently do nothing.
    An isolated profile also avoids editing the user's emulator preferences.
    The executable is hardlinked (copied only across filesystems); Mesen
    extracts its bundled native libraries alongside it on first execution.
    """
    source = Path(find_mesen()).resolve()
    stat = source.stat()
    signature = hashlib.sha256(('%s:%d:%d' % (source, stat.st_mtime_ns, stat.st_size)).encode()).hexdigest()[:16]
    folder = Path(tempfile.gettempdir()) / ('elma-mesen-test-' + signature)
    folder.mkdir(exist_ok=True)
    runner = folder / source.name
    if not runner.exists():
        try:
            os.link(source, runner)
        except FileExistsError:
            pass
        except OSError:
            shutil.copy2(source, runner)
    settings = folder / 'settings.json'
    if not settings.exists():
        config = {'Snes': {'Port1': {'Type': 'SnesController'},
                           'RamPowerOnState': 'AllZeros'},
                  'Nes': {'RamPowerOnState': 'AllZeros'}}
        temporary = folder / ('settings-%d.json' % os.getpid())
        temporary.write_text(json.dumps(config))
        os.replace(temporary, settings)
    return [str(runner), '--testrunner', os.path.abspath(rom), os.path.abspath(lua)]


def read_symbols(rom):
    """Labels of the .sym file of the ROM (NO$SNES format, "00808752 main"),
    also of build/elma.sym for build/elma_ntsc.sfc."""
    syms = {}
    base = os.path.splitext(rom)[0]
    for path in (base + '.sym', base.rsplit('_', 1)[0] + '.sym'):
        if os.path.exists(path):
            break
    else:
        return syms
    for line in open(path):
        parts = line.split()
        if len(parts) != 2 or parts[0].startswith(';'):
            continue
        try:
            syms[parts[1]] = int(parts[0].replace(':', ''), 16)
        except ValueError:
            pass
    return syms


def make_lua(script, rom, sram=None, keep_sram=False, extra=None, random_ram=False):
    syms = read_symbols(rom)
    lines = [LUA_HEAD]
    frame = 0
    actions = {}

    def act(code):
        actions.setdefault(frame, []).append(code)

    for step in script.split():
        if ':' in step and step.split(':')[0] in MEMTYPES or step.startswith('SHOT:') \
                or step.startswith('PEEK:'):
            kind, rest = step.split(':', 1)
            if kind == 'SHOT':
                act('out("SHOT", %r, emu.takeScreenshot())' % rest)
            elif kind == 'PEEK':
                where, n = rest.rsplit(':', 1)
                addr = syms[where] if where in syms else int(where, 16)
                act('dump("PEEK", %r, emu.memType.snesMemory, %d, %d)' % (where, addr, int(n)))
            else:
                mt = 'emu.memType.' + MEMTYPES[kind]
                act('dump(%r, %r, %s, 0, memsize(%s))' % (kind, rest, mt, mt))
            continue
        if step == 'CLOCK':
            act('print(string.format("CLOCK %d %d %d", frame, emu.getMasterClock(), '
                'emu.getCpuCycleCount and emu.getCpuCycleCount(0) or -1))')
            continue
        name = step.rstrip('0123456789')
        n = int(step[len(name):]) if len(name) < len(step) else 1
        if name == 'W':
            frame += n
            continue
        keys = name.split('+')
        for k in keys:
            if k not in BUTTONS:
                raise SystemExit('unknown step: %s' % step)
        table = '{' + ', '.join('%s = true' % BUTTONS[k] for k in keys) + '}'
        for f in range(frame, frame + n):
            lines.append('inputs[%d] = %s' % (f, table))
        frame += n
    last = max([frame] + list(actions)) or 1
    for f, codes in sorted(actions.items()):
        lines.append('steps[%d] = { %s }' % (max(f, 1), ', '.join(
            'function() %s end' % c for c in codes)))
    lines.append('last_frame = %d' % max(last, 1))
    # The SRAM before the first frame:
    if not keep_sram:
        data = open(sram, 'rb').read() if sram else b''
        lines.append('local sram = "%s"' % binascii.hexlify(data).decode())
        lines.append(r'''
local sram_done = false
emu.addEventCallback(function()
  if sram_done then return end
  sram_done = true
  local n = memsize(emu.memType.snesSaveRam)
  for i = 0, n - 1 do
    local b = 0
    if 2 * i + 2 <= #sram then b = tonumber(sram:sub(2 * i + 1, 2 * i + 2), 16) end
    emu.write(i, b, emu.memType.snesSaveRam)
  end
end, emu.eventType.startFrame)''')
    if not random_ram:
        # At the load of the script the CPU has not started yet:
        lines.append(r'''
for i = 0, memsize(emu.memType.snesWorkRam) - 1 do emu.write(i, 0, emu.memType.snesWorkRam) end
for i = 0, memsize(emu.memType.spcRam) - 1 do emu.write(i, 0, emu.memType.spcRam) end''')
    if extra:
        lines.append(open(extra).read())
    lines.append(LUA_TAIL)
    return '\n'.join(lines)


def run(rom, script, out_dir='.', sram=None, keep_sram=False, lua=None,
        timeout=600, verbose=False, random_ram=False):
    lua_src = make_lua(script, rom, sram, keep_sram, lua, random_ram)
    lua_path = os.path.join(out_dir, '.mesen_run.lua')
    os.makedirs(out_dir, exist_ok=True)
    with open(lua_path, 'w') as f:
        f.write(lua_src)
    # The emulator has its own100-second default timeout. Forward the requested
    # duration and leave time for it to return/flush diagnostics before Python kills it.
    runner_timeout = max(1, math.ceil(timeout))
    command = testrunner_command(rom, lua_path) + ['--timeout=%d' % runner_timeout]
    p = subprocess.run(command, capture_output=True,
                       text=True, timeout=runner_timeout + 5)
    results = []
    for line in p.stdout.splitlines():
        if line.startswith('OUT '):
            _, kind, name, data = line.split(' ', 3)
            data = binascii.unhexlify(data.strip())
            results.append((kind, name, data))
            if kind != 'PEEK':
                path = os.path.join(out_dir, name)
                os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
                with open(path, 'wb') as f:
                    f.write(data)
        elif verbose or not line.startswith('OUT'):
            print(line)
    if p.returncode != 0:
        sys.stderr.write(p.stderr)
        raise SystemExit('Mesen ended with %d' % p.returncode)
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('rom')
    ap.add_argument('script')
    ap.add_argument('--out', default='.')
    ap.add_argument('--sram')
    ap.add_argument('--keep-sram', action='store_true')
    ap.add_argument('--lua')
    ap.add_argument('--timeout', type=int, default=600)
    ap.add_argument('--random-ram', action='store_true')
    a = ap.parse_args()
    for kind, name, data in run(a.rom, a.script, a.out, a.sram, a.keep_sram,
                                a.lua, a.timeout, random_ram=a.random_ram):
        if kind == 'PEEK':
            print('%s %s' % (name, binascii.hexlify(data).decode()))


if __name__ == '__main__':
    main()
