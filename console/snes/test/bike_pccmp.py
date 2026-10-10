"""The bike of build/test_bike.sfc (built with BIKE_DUMP, a pcref DUMP)
next to the original game's pictures of the same frames (pcref SHOT or
EVERY pictures, 640x480) reduced to 0.4: a picture for the eye.

  BIKE_DUMP=ride.txt BIKE_LEVEL=N bike_pccmp.py OUT.png PC_PREFIX FRAME...

PC_PREFIX: the pcref pictures, PC_PREFIX%06d.png by the frame of the log.
"""

import os
import subprocess
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mesen

ROM = 'build/test_bike.sfc'
LUA = r'''
local want = { __POSES__ }
local A = { __SYMS__ }
local pending, wait = nil, 0
local function hex(s)
  return (s:gsub(".", function(c) return string.format("%02x", string.byte(c)) end))
end
emu.addMemoryCallback(function()
  local p = emu.read(A.test_pose, emu.memType.snesMemory) + 256 * emu.read(A.test_pose + 1, emu.memType.snesMemory)
  for _, w in ipairs(want) do
    if w == p and pending == nil then pending = p; wait = __WAIT__ end
  end
end, emu.callbackType.exec, A.core_frame_done)
local f = 0
emu.addEventCallback(function()
  f = f + 1
  if pending ~= nil then
    wait = wait - 1
    if wait == 0 then
      print("SHOT " .. pending .. " " .. hex(emu.takeScreenshot()))
      pending = nil
    end
  end
  if f > __LAST__ then emu.stop(0) end
end, emu.eventType.endFrame)
'''


def main():
    out, prefix = sys.argv[1], sys.argv[2]
    frames = [int(x) for x in sys.argv[3:]]
    rows = []
    cols = None
    for line in open(os.environ['BIKE_DUMP']):
        if line.startswith('#'):
            cols = line[1:].split()
            continue
        rows.append(dict(zip(cols, [float(x) for x in line.split()])))
    index = {int(r['frame']): n for n, r in enumerate(rows)}
    poses = [index[f] for f in frames]
    syms = mesen.read_symbols(ROM)
    lua = LUA.replace('__POSES__', ','.join(str(p) for p in poses))
    lua = lua.replace('__SYMS__', ', '.join('%s = 0x%06X' % (n, syms[n]) for n in ('test_pose', 'core_frame_done')))
    lua = lua.replace('__LAST__', str(max(poses) + 40))
    lua = lua.replace('__WAIT__', os.environ.get('BIKE_SHOT_WAIT', '2'))
    path = os.path.abspath(os.path.join(os.path.dirname(out) or '.', 'bike_pccmp.lua'))
    with open(path, 'w') as f:
        f.write(lua)
    p = subprocess.run([mesen.find_mesen(), '--testrunner', os.path.abspath(ROM), path],
                       capture_output=True, text=True, timeout=600)
    shots = {}
    import io
    for line in p.stdout.splitlines():
        if line.startswith('SHOT '):
            _, n, data = line.split(' ', 2)
            shots[int(n)] = Image.open(io.BytesIO(bytes.fromhex(data.strip()))).convert('RGB')
            a = np.array(shots[int(n)])
            xs = np.nonzero((a.sum(-1) < 120).any(0))[0]
            if len(xs):
                print('pose %s: dark pixels x %d..%d' % (n, xs.min(), xs.max()))
    W = 112
    tiles = []
    for f, pi in zip(frames, poses):
        r = rows[pi]
        pc = Image.open('%s%06d.png' % (prefix, f)).convert('RGB').resize((256, 192), Image.BOX)
        bx = (640 / 48 * 0.15 + r['baljobb_h'] * (640 / 48 * 0.7)) * 48 * 0.4
        by = 239 * 0.4
        a = pc.crop((int(bx) - W // 2, int(by) - W // 2, int(bx) + W // 2, int(by) + W // 2))
        sn = shots.get(pi)
        b = Image.new('RGB', (W, W))
        if sn is not None:
            b = sn.crop((int(bx) - W // 2, 112 - W // 2, int(bx) + W // 2, 112 + W // 2))
        t = Image.new('RGB', (2 * W + 4, W), (0, 0, 0))
        t.paste(a, (0, 0))
        t.paste(b, (W + 4, 0))
        tiles.append(t)
    cols_n = 3
    rows_n = (len(tiles) + cols_n - 1) // cols_n
    sheet = Image.new('RGB', (cols_n * (2 * W + 12), rows_n * (W + 8)), (60, 60, 60))
    for n, t in enumerate(tiles):
        sheet.paste(t, ((n % cols_n) * (2 * W + 12), (n // cols_n) * (W + 8)))
    sheet.resize((sheet.width * 3, sheet.height * 3), Image.NEAREST).save(out)


if __name__ == '__main__':
    main()
