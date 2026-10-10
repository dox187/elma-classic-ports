"""Measure real ROM presentation and compare step-indexed physical state.

  python test/perf_check.py --rom build/test_play.sfc --reference BASELINE.sfc
  python test/perf_check.py --rom build/test_play.sfc --pal build/test_play_pal.sfc \
      --reference build/analysis/original/test_play.sfc \
      --reference-pal build/analysis/original/test_play_pal.sfc --levels 0,6,10,45,47

Each run saves raw Mesen output, timing samples, 142-byte states, event returns,
JSON statistics and screenshots. Timings include interrupts and DMA. A reference
must use the same physics frequency, level assets and step keys. An identical
prefix is insufficient: the entire trace and final outcome must match. Optional
instrumentation absent from older ROMs is reported as unavailable.
"""

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys

import mesen
from finish_test import read_script
from play import step_keys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
STATE_BYTES = 142
COMPONENTS = [('phys_step', 'phys_step_ret'),
              ('map_set_camera', 'map_set_camera_end'),
              ('bike_draw', 'bike_draw_end'), ('hud_draw', 'hud_draw_end'),
              ('objects_draw', 'objects_draw_end'),
              ('game_render_capture', 'game_render_capture_end'),
              ('game_render_begin', 'game_render_begin_end'),
              ('game_render_end', 'game_render_end_end'),
              ('game_render_previous', 'game_render_previous_end')]
METRICS = ['core_frame_count', 'core_lag_count', 'core_dmaq_bytes', 'core_dmaq_n',
           'map_stat_jobs', 'map_stat_short', 'map_stat_nofree', 'map_stat_resets',
           'map_stat_tiles', 'map_stat_comp', 'map_stat_bytes', 'map_stat_minfree',
           'map_cam_x', 'map_cam_y', 'game_phys_drop_count', 'render_interp',
           'core_dma_overruns', 'core_work_frame', 'core_work_reserve', 'core_frame_lines',
           'game_phys_backlog_count', 'game_phys_backlog_max']


def summary(values):
    if not values:
        return None
    v = sorted(values)
    return {'n': len(v), 'mean': statistics.mean(v), 'p50': v[len(v) // 2],
            'p95': v[min(len(v) - 1, int(len(v) * .95))], 'max': v[-1], 'min': v[0]}


def make_lua(s, max_steps):
    required = ['phys_step', 'phys_step_ret', 'phys_dpa', 'core_nmi_fast',
                'core_frame_ready', 'core_frame_done', '_dmadone']
    missing = [n for n in required if n not in s]
    if missing:
        raise ValueError('Missing profiling symbols: ' + ', '.join(missing))
    lines = [r'''
local pmem = emu.memType.snesMemory
local active, starts, state_count = false, {}, 0
local function rd(a) return emu.read16(a, pmem) end
local function cb(a, f) emu.addMemoryCallback(f, emu.callbackType.exec, a, a) end
local function clock() return emu.getMasterClock() end
''']
    lines.append('local max_steps = %d' % max_steps)
    for name, end in COMPONENTS:
        if name not in s or end not in s:
            continue
        lines.append('cb(%d,function() %s if active then starts[%r]=clock() end end)' %
                     (s[name], 'active=(state_count<max_steps)' if name == 'phys_step' else '', name))
        lines.append('cb(%d,function() if active and starts[%r] then print("PERF_COST %s " .. starts[%r] .. " " .. (clock()-starts[%r])) starts[%r]=nil end end)' %
                     (s[end], name, name, name, name, name))
    # The return ABI stores events in tcc__r0 before phys_step_ret. It is
    # outside phys_dpa and does not depend on PH_QUICK presentation outputs.
    event = 'rd(%d)' % s['tcc__r0'] if 'tcc__r0' in s else '-1'
    lines.append('cb(%d,function() if active then state_count=state_count+1 local t={} for i=0,%d do t[#t+1]=string.format("%%02x",emu.read(%d+i,pmem)) end print("PERF_STATE " .. table.concat(t) .. " " .. %s) end end)' %
                 (s['phys_step_ret'], STATE_BYTES - 1, s['phys_dpa'], event))
    names = [n for n in METRICS if n in s]
    reads = ','.join('rd(%d)' % s[n] for n in names)
    publication = s.get('core_frame_submit', s['core_frame_done'])
    lines.append('cb(%d,function() if active then print("PERF_SUBMIT " .. clock() .. " " .. emu.read(%d,pmem)) end end)' %
                 (publication, s['core_frame_ready']))
    lines.append('cb(%d,function() if active then print(string.format("PERF_DRAW %%d %s",clock(),%s)) end end)' %
                 (publication, ' '.join(['%d'] * len(names)), reads))
    lines.append('cb(%d,function() if active then print("PERF_NMI " .. clock() .. " " .. emu.read(%d,pmem)) end end)' %
                 (s['core_nmi_fast'], s['core_frame_ready']))
    lines.append('cb(%d,function() if active then local st=emu.getState() print("PERF_DMA " .. clock() .. " " .. tostring(st["ppu.scanline"])) end end)' % s['_dmadone'])
    return '\n'.join(lines), names


def run(rom, level, script, out, shots, timeout):
    rom = Path(rom).resolve()
    out.mkdir(parents=True, exist_ok=True)
    symbols = mesen.read_symbols(str(rom))
    lua, names = make_lua(symbols, len(step_keys(script)))
    (out / 'profile.lua').write_text(lua)
    cmd = [sys.executable, str(HERE / 'play.py'), str(rom), str(level), script,
           '--steps', '--out', str(out), '--lua', str(out / 'profile.lua'),
           '--shots', str(shots), '--stop-after-steps', str(len(step_keys(script)))]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    (out / 'raw.txt').write_text(proc.stdout + '\n' + proc.stderr)
    if proc.returncode:
        raise RuntimeError('ROM run failed (%s): %s' % (proc.returncode, out / 'raw.txt'))
    costs, states, events, draws, nmis, dma, submissions = {}, [], [], [], [], [], []
    outcome = None
    for line in proc.stdout.splitlines():
        f = line.split()
        if not f:
            continue
        if f[0] == 'PERF_COST':
            costs.setdefault(f[1], []).append([int(f[2]), int(f[3])])
        elif f[0] == 'PERF_STATE':
            state = bytes.fromhex(f[1])
            if len(state) != STATE_BYTES:
                raise RuntimeError('Malformed state trace')
            states.append(state)
            events.append(int(f[2]))
        elif f[0] == 'PERF_DRAW':
            draws.append(list(map(int, f[1:])))
        elif f[0] == 'PERF_NMI':
            nmis.append(list(map(int, f[1:])))
        elif f[0] == 'PERF_SUBMIT':
            submissions.append(list(map(int, f[1:])))
        elif f[0] == 'PERF_DMA':
            dma.append([int(f[1]), int(f[2])])
        elif line.startswith(('finished in ', 'not finished ', 'the level ')):
            # Frame count is presentation-dependent; outcome and finish time aren't.
            outcome = line.split(' (')[0]
    if not states or not costs.get('phys_step') or outcome is None:
        raise RuntimeError('Missing physics trace or outcome: %s' % (out / 'raw.txt'))
    first = costs['phys_step'][0][0]
    last = sum(costs['phys_step'][-1])
    costs = {k: [r for r in rows if first <= r[0] <= last] for k, rows in costs.items()}
    draws = [r for r in draws if first <= r[0] <= last]
    nmis = [r for r in nmis if first <= r[0] <= last]
    dma = [r for r in dma if first <= r[0] <= last]
    rom_bytes = rom.read_bytes()
    pal = rom_bytes[0x7fd9] == 2
    clock_hz = 21281370 if pal else 945000000 / 44
    seconds = (last - first) / clock_hz
    if not nmis or seconds <= 0:
        raise RuntimeError('No measurable presentation interval')
    presented = sum(r[1] != 0 for r in nmis)
    metric_summary = {n: summary([r[i + 1] for r in draws]) for i, n in enumerate(names)}
    drop_i = names.index('game_phys_drop_count') + 1 if 'game_phys_drop_count' in names else None
    drops = max((r[drop_i] for r in draws), default=0) if drop_i else None
    # VBlank ends at scanline 0 in both regions. This game uses 224 lines;
    # DMA that finishes on a visible scanline has overrun its legal window.
    overruns = sum(0 <= r[1] < 225 for r in dma)
    data = b''.join(states)
    (out / 'states.bin').write_bytes(data)
    (out / 'events.json').write_text(json.dumps(events) + '\n')
    (out / 'samples.json').write_text(json.dumps({'draw_columns': ['clock'] + names,
        'draws': draws, 'nmis': nmis, 'submissions': submissions,
        'dma_end': dma, 'costs': costs}, indent=2) + '\n')
    result = {'rom': str(rom), 'rom_sha256': hashlib.sha256(rom_bytes).hexdigest(),
              'region': 'pal' if pal else 'ntsc', 'level': level,
              'script': script, 'script_steps': len(step_keys(script)),
              'physics_steps': len(states), 'seconds': seconds,
              'physics_hz': (len(states) - 1) / seconds, 'nmis': len(nmis),
              'presented_frames': presented, 'presented_fps': presented / seconds,
              'lag_frames': len(nmis) - presented,
              'lag_percent': 100 * (len(nmis) - presented) / len(nmis),
              'dma_batches': len(dma), 'dma_overruns': overruns,
              'dma_end_scanlines': summary([r[1] for r in dma]),
              'physics_dropped_steps': drops,
              'dma_budget_overruns': max((r[names.index('core_dma_overruns') + 1] for r in draws), default=0) if 'core_dma_overruns' in names else None,
              'cost_master_clocks': {k: summary([r[1] for r in rows]) for k, rows in costs.items()},
              'draw_stats': metric_summary, 'unavailable_metrics': [n for n in METRICS if n not in symbols],
              'events_available': 'tcc__r0' in symbols,
              'states_sha256': hashlib.sha256(data).hexdigest(), 'outcome': outcome,
              'screenshot': str(out / 'end.png')}
    (out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    return result, states, events


def compare(candidate, reference):
    cr, cs, ce = candidate
    rr, rs, re = reference
    first = next((i for i, (x, y) in enumerate(zip(cs, rs)) if x != y), None)
    detail = None
    if first is not None:
        offset = next(i for i, (x, y) in enumerate(zip(cs[first], rs[first])) if x != y)
        detail = {'step': first + 1, 'byte_offset': offset,
                  'candidate': cs[first][offset], 'reference': rs[first][offset]}
    events_match = ce == re if cr['events_available'] and rr['events_available'] else None
    ok = cs == rs and cr['outcome'] == rr['outcome'] and events_match is not False
    return {'ok': ok, 'states_bit_exact': cs == rs, 'events_match': events_match,
            'outcome_match': cr['outcome'] == rr['outcome'],
            'candidate_steps': len(cs), 'reference_steps': len(rs),
            'first_state_difference': detail}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--rom', default=str(ROOT / 'build/test_play.sfc'))
    ap.add_argument('--pal', help='additional PAL ROM to run with identical scripts')
    ap.add_argument('--reference', help='baseline NTSC ROM (.sym alongside it)')
    ap.add_argument('--reference-pal', help='baseline PAL ROM')
    ap.add_argument('--level', type=int, default=0)
    ap.add_argument('--levels', help='comma separated level indices, e.g. 0,6,10,45,47')
    ap.add_argument('--script', help='step-indexed keys; defaults to warmup_finish.txt')
    ap.add_argument('--script-file', help='finish_test-format script file')
    ap.add_argument('--out', default=str(ROOT / 'build/perf'))
    ap.add_argument('--shots', type=int, default=120)
    ap.add_argument('--timeout', type=int, default=300)
    ap.add_argument('--min-fps', type=float, help='fail if presented FPS falls below this')
    ap.add_argument('--max-lag-percent', type=float, help='fail if lag exceeds this')
    a = ap.parse_args()
    script = a.script or read_script(a.script_file or HERE / 'warmup_finish.txt')[1]
    levels = [int(x) for x in a.levels.split(',')] if a.levels else [a.level]
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    results, failures = [], []
    regions = [('ntsc', a.rom, a.reference)]
    if a.pal:
        regions.append(('pal', a.pal, a.reference_pal or a.reference))
    for region, rom, ref in regions:
        for level in levels:
            tag = '%s-level%02d' % (region, level)
            try:
                candidate = run(rom, level, script, out / tag / 'candidate', a.shots, a.timeout)
                result = candidate[0]
                if ref:
                    reference = run(ref, level, script, out / tag / 'reference', 0, a.timeout)
                    result['reference'] = reference[0]
                    result['comparison'] = compare(candidate, reference)
                    if not result['comparison']['ok']:
                        failures.append(tag + ': physics or outcome differs from reference')
                if result['dma_budget_overruns']:
                    failures.append(tag + ': core DMA budget exceeded')
                if result['dma_overruns']:
                    failures.append(tag + ': DMA extends into visible scanlines')
                if result['physics_dropped_steps']:
                    failures.append(tag + ': simulation steps were dropped')
                if a.min_fps is not None and result['presented_fps'] < a.min_fps:
                    failures.append(tag + ': presented FPS below threshold')
                if a.max_lag_percent is not None and result['lag_percent'] > a.max_lag_percent:
                    failures.append(tag + ': lag above threshold')
                results.append(result)
                print('%s: %.2f FPS, %.1f%% lag, %d steps%s' % (tag, result['presented_fps'],
                      result['lag_percent'], result['physics_steps'],
                      ', bit-exact=' + str(result['comparison']['ok']) if ref else ''), flush=True)
            except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
                failures.append(tag + ': ' + str(exc))
                print(failures[-1], file=sys.stderr, flush=True)
    report = {'ok': not failures, 'failures': failures, 'runs': results}
    (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Report: %s' % (out / 'summary.json'))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
