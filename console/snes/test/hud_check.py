"""Plays build/test_hud.sfc in Mesen 2 and checks it: the screenshots of the
held frames against a model of the compact HUD (sprite composition, from
tools/gen_hud.py), and the time and DMA bytes of hud_draw.

  hud_check.py ELMA_RES ELMA_LGR [--rom build/test_hud.sfc] [--out DIR]

Writes DIR/model_*.png and DIR/diff_*.png for the frames that differ, and
prints the master clocks of hud_draw (worst, average, by level) and the
bytes it queued for DMA.
"""

import argparse
import os
import re
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
sys.path.insert(0, HERE)

import elmadata  # noqa: E402
import gen_hud as gh  # noqa: E402
from lgr import Lgr  # noqa: E402
import mesen  # noqa: E402

HOLD = 100                      # test/snes_hud.c TEST_HOLD
BACKDROP = 0x4210

LUA = r'''
local DRAW, DRAW_END = %d, %d
local HOLD, LEVEL, FRAME, DMAB = %d, %d, %d, %d
local t0 = 0
local stats = {}
local done = {}
local last_hold, seen = 0, 0
local function rd16(a) return emu.read(a, emu.memType.snesMemory) + 256 * emu.read(a + 1, emu.memType.snesMemory) end
emu.addMemoryCallback(function() t0 = emu.getMasterClock() end, emu.callbackType.exec, DRAW, DRAW)
emu.addMemoryCallback(function()
  local dt = emu.getMasterClock() - t0
  local lv = rd16(LEVEL)
  local s = stats[lv]
  if not s then s = {n = 0, sum = 0, max = 0, maxf = 0, dmax = 0, dsum = 0} stats[lv] = s end
  local d = rd16(DMAB)
  s.n = s.n + 1
  s.sum = s.sum + dt
  if dt > s.max then s.max = dt s.maxf = rd16(FRAME) end
  s.dsum = s.dsum + d
  if d > s.dmax then s.dmax = d end
end, emu.callbackType.exec, DRAW_END, DRAW_END)
emu.addEventCallback(function()
  -- The screenshot lags the frame (by 2 or more): take it late in a hold.
  local h = rd16(HOLD)
  if h ~= 0 and h == last_hold then
    seen = seen + 1
  else
    seen = 0
  end
  last_hold = h
  if h ~= 0 and seen == 6 then
    local key = rd16(LEVEL) * 10000 + h - 1
    if not done[key] then
      done[key] = true
      out("SHOT", string.format("hud_L%%d_F%%04d.png", rd16(LEVEL), h - 1), emu.takeScreenshot())
    end
  end
  local t = {}
  for lv, s in pairs(stats) do
    t[#t + 1] = string.format("%%d %%d %%d %%d %%d %%d %%d", lv, s.n, s.sum, s.max, s.maxf, s.dsum, s.dmax)
  end
  out("STAT", "hud_stats.txt", table.concat(t, "\n"))
end, emu.eventType.endFrame)
'''


def b5(c):
    return tuple(v >> 3 for v in c)


class Model:
    """Independent sprite composition of the HUD test ROM in 5-bit RGB."""

    def __init__(self, res, lgr):
        self.levels = elmadata.internal_levels(elmadata.Resource(res))
        self.test_levels = gh.test_levels(self.levels)
        self.paths = {i: gh.test_path(self.levels[i]) for i in self.test_levels}
        self.apple, pal = gh.apple_image(Lgr(lgr))
        self.palette = np.asarray(pal, np.uint8) >> 3

    def blit(self, scr, pix, x, y):
        yy, xx = np.nonzero(pix)
        scr[y + yy, x + xx] = self.palette[pix[yy, xx]]

    def screen(self, k, f):
        li = self.test_levels[k]
        lev, path = self.levels[li], self.paths[li]
        scr = np.zeros((224, 256, 3), np.uint8)
        bd = (0x4210, 0x7FFF, 0, 0x7E44)[k]
        scr[:, :] = (bd & 31, bd >> 5 & 31, bd >> 10 & 31)
        eaten = {e for _, _, _, e in path[:f + 1] if e >= 0}
        show_apples = not (k == 1 and (200 <= f < 300 or 400 <= f < 500))
        show_time = not (k == 1 and 300 <= f < 500)
        if show_time:
            t = f * 5 // 3 + (359000 if k == 2 else 0)
            best = {0: None, 1: 1970, 2: 123456, 3: 400000}[k]
            if k == 1 and 600 <= f < 700:
                best = None
            if k == 1 and f >= 700:
                best = 400
            self.digits(scr, gh.ido2string(t), 1)
            if best is not None:
                self.digits(scr, gh.ido2string(best), 0)
        if show_apples:
            count = sum(t == elmadata.T_APPLE and i not in eaten
                        for i, (t, *_) in enumerate(lev.objects))
            if k == 0 and f < 400:
                count = (64, 0, 99, 65535)[f // 100]
            count = min(count, 99)
            self.blit(scr, self.apple, gh.APPLE_X, gh.APPLE_Y)
            for i, d in enumerate('%02d' % count):
                self.blit(scr, gh.glyph_image(d), gh.COUNT_X + i * 7, gh.APPLE_Y)
        return scr

    def digits(self, scr, s, which):
        for p, ch in enumerate(s[0:2] + s[3:5] + s[6:8]):
            self.blit(scr, gh.glyph_image(ch, p in (1, 3)),
                      gh.TIME_X[which] + gh.DIGIT_X[p], gh.TIME_Y)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('res')
    ap.add_argument('lgr')
    ap.add_argument('--rom', default=os.path.join(HERE, '..', 'build', 'test_hud.sfc'))
    ap.add_argument('--out', default='hud_check')
    ap.add_argument('--frames', type=int, default=4300)
    a = ap.parse_args()
    syms = mesen.read_symbols(a.rom)
    lua = LUA % (syms['hud_draw'], syms['hud_draw_end'], syms['test_hold'],
                 syms['test_level'], syms['test_frame'], syms['core_dmaq_bytes'])
    os.makedirs(a.out, exist_ok=True)
    lua_path = os.path.join(a.out, 'hud_check.lua')
    with open(lua_path, 'w') as f:
        f.write(lua)
    results = mesen.run(a.rom, 'W%d' % a.frames, a.out, lua=lua_path)
    model = Model(a.res, a.lgr)
    bad = 0
    shots = sorted(name for kind, name, _ in results if kind == 'SHOT')
    for name in shots:
        m = re.match(r'hud_L(\d+)_F(\d+)\.png', name)
        k, f = int(m.group(1)), int(m.group(2))
        if k >= len(model.test_levels):
            continue
        got = np.array(Image.open(os.path.join(a.out, name)).convert('RGB')) >> 3
        want = model.screen(k, f)
        diff = np.any(got != want, axis=2)
        if diff.any():
            bad += 1
            ys, xs = np.nonzero(diff)
            print('%s: %d pixels differ, first at x %d y %d' % (name, diff.sum(), xs[0], ys[0]))
            Image.fromarray((want << 3).astype(np.uint8)).save(os.path.join(a.out, 'model_' + name))
            d = (got << 3).astype(np.uint8)
            d[diff] = (255, 0, 255)
            Image.fromarray(d).save(os.path.join(a.out, 'diff_' + name))
    print('%d screenshots, %d differ from the model' % (len(shots), bad))
    stats = [r for r in results if r[0] == 'STAT']
    if stats:
        print('level calls clocks_avg clocks_max (frame) dma_avg dma_max')
        for line in stats[-1][2].decode().splitlines():
            lv, n, s, mx, mxf, ds, dm = (int(v) for v in line.split())
            print('%5d %5d %10d %10d (%4d) %7d %7d' % (lv, n, s // max(n, 1), mx, mxf,
                                                        ds // max(n, 1), dm))
    expected = len(model.test_levels) * (gh.TEST_FRAMES // HOLD)
    if len(shots) != expected:
        print('expected %d screenshots, received %d' % (expected, len(shots)))
        bad += 1
    if stats and any(int(line.split()[-1]) for line in stats[-1][2].decode().splitlines()):
        print('compact HUD unexpectedly queued DMA')
        bad += 1
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
