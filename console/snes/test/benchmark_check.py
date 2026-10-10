"""Require sustained new 60Hz presentations and real frame work budgets.

  python test/benchmark_check.py --rom build/test_play.sfc --levels 0,6,10,45,47

Runs step-indexed cases with Mesen's unmodified master clock. Initialization
and terminal animation are excluded; duplicate NMI presentations are misses,
not frames. Every observed steady NMI must receive a freshly completed frame,
and each submitted picture must be consumed once within one NTSC frame.
A pipeline may wait for
the preceding picture's NMI before reusing its OAM/DMA buffers; record this
explicit idle interval separately, just as the blocking loop's wait after
publication was outside its work interval. Elapsed time is always retained.
Samples and ROM hashes are retained. This target is separate from 80Hz physics.
"""
import argparse
import bisect
import json
from pathlib import Path

import perf_check
from finish_test import read_script

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--rom', default=str(ROOT / 'build/test_play.sfc'))
    ap.add_argument('--levels', default='0,6,10,45,47')
    ap.add_argument('--script', help='step script; default full Warm Up')
    ap.add_argument('--script-file')
    ap.add_argument('--out', default=str(ROOT / 'build/benchmark'))
    ap.add_argument('--warmup-presentations', type=int, default=2,
                    help='exclude first two steady NMIs for startup boundary uncertainty')
    a = ap.parse_args()
    script = a.script or read_script(a.script_file or ROOT / 'test/warmup_finish.txt')[1]
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    original = perf_check.make_lua

    def instrument(symbols, max_steps):
        lua, names = original(symbols, max_steps)
        lua += '''\nlocal frame_work_start=nil
local frame_idle_start=nil
local frame_idle_clocks=0
cb(%d,function() frame_work_start=clock() frame_idle_clocks=0 end)
cb(%d,function() if active and frame_work_start then
 print("FRAME_WORK "..frame_work_start.." "..(clock()-frame_work_start).." "..frame_idle_clocks)
 frame_work_start=nil end end)
''' % (symbols['core_work_begin'], symbols.get('core_frame_submit', symbols['core_frame_done']))
        if 'core_frame_wait' in symbols and 'core_frame_wait_end' in symbols:
            lua += '''
cb(%d,function() if frame_work_start then frame_idle_start=clock() end end)
cb(%d,function() if frame_work_start and frame_idle_start then
 frame_idle_clocks=frame_idle_clocks+clock()-frame_idle_start frame_idle_start=nil end end)
''' % (symbols['core_frame_wait'], symbols['core_frame_wait_end'])
        return lua, names

    perf_check.make_lua = instrument
    runs = []
    for level in [int(x) for x in a.levels.split(',')]:
        folder = out / ('level%02d' % level)
        result, states, events = perf_check.run(a.rom, level, script, folder, 0, 300)
        if result['region'] != 'ntsc':
            raise ValueError('Sustained60Hz target requires an NTSC ROM')
        samples = json.loads((folder / 'samples.json').read_text())
        costs = samples['costs']['phys_step']
        first, last = costs[0][0], sum(costs[-1])
        nmis = samples['nmis'][a.warmup_presentations:]
        work, active_work, idle_work = [], [], []
        steady_begin = nmis[0][0] if nmis else last
        for line in (folder / 'raw.txt').read_text().splitlines():
            f = line.split()
            if f and f[0] == 'FRAME_WORK':
                start, duration = map(int, f[1:3])
                idle = int(f[3]) if len(f) > 3 else 0
                if not 0 <= idle <= duration:
                    raise ValueError('Malformed presentation wait interval')
                if max(first, steady_begin) <= start and start + duration <= last:
                    work.append([start, duration])
                    active_work.append([start, duration - idle])
                    idle_work.append([start, idle])
        # Mesen emulates nominal SNES60.10 NTSC video, not an artificial
        # exactly60Hz clock. Compare against the actual one-frame budget.
        hz = 945000000 / 44
        frame_clocks = 262 * 1364
        budgets = perf_check.summary([x[1] for x in work])
        active_budgets = perf_check.summary([x[1] for x in active_work])
        misses = sum(n[1] == 0 for n in nmis)
        submissions = samples['submissions']
        submit_times = [s[0] for s in submissions]
        latencies, consumed = [], set()
        reused, unmatched = 0, 0
        for nmi_time, ready in nmis:
            if not ready:
                continue
            index = bisect.bisect_right(submit_times, nmi_time) - 1
            if index < 0:
                unmatched += 1
                continue
            if index in consumed:
                reused += 1
            consumed.add(index)
            latencies.append(nmi_time - submit_times[index])
        latency = perf_check.summary(latencies)
        overwritten = sum(bool(pending) for t, pending in submissions
                          if steady_begin <= t <= last)
        enough = len(nmis) >= 60
        ok = bool(enough and misses == 0 and latency and latency['max'] <= frame_clocks
                  and reused == 0 and unmatched == 0 and overwritten == 0
                  and result['physics_dropped_steps'] in (None, 0)
                  and result['dma_overruns'] == 0 and result['dma_budget_overruns'] in (None, 0))
        row = {'level': level, 'ok': ok, 'steady_nmis': len(nmis),
               'missed_presentations': misses, 'new_presentations': len(nmis) - misses,
               'steady_nominal_fps': (len(nmis) - misses) / len(nmis) * hz / frame_clocks if nmis else 0,
               'frame_budget_master_clocks': frame_clocks,
               'frame_work_master_clocks': budgets,
               'frame_active_master_clocks': active_budgets,
               'frame_idle_master_clocks': perf_check.summary([x[1] for x in idle_work]),
               'submission_to_nmi_master_clocks': latency,
               'reused_submissions': reused, 'unmatched_presentations': unmatched,
               'overwritten_pending_submissions': overwritten,
               'physics_steps': len(states),
               'physics_hz': result['physics_hz'], 'rom_sha256': result['rom_sha256'],
               'sufficient_duration': enough, 'samples': str(folder / 'samples.json')}
        runs.append(row)
        (folder / 'work.json').write_text(json.dumps(work) + '\n')
        (folder / 'active-work.json').write_text(json.dumps(active_work) + '\n')
        (folder / 'idle-work.json').write_text(json.dumps(idle_work) + '\n')
        print('level%d: %s; %d/%d missed, activep95=%s max=%s; elapsedmax=%s' %
              (level, 'PASS' if ok else 'FAIL', misses, len(nmis),
               active_budgets and active_budgets['p95'], active_budgets and active_budgets['max'],
               budgets and budgets['max']), flush=True)
    report = {'target': 'every steady NTSC NMI consumes a distinct new frame within one video interval of submission; no overwritten pending frame or DMA overrun',
              'budget_basis': 'elapsed work minus explicit wait for preceding presentation; both retained',
              'work_budget_is_diagnostic': 'overlapped physics work can span NMIs while each scheduled picture is delivered on time',
              'ok': all(r['ok'] for r in runs), 'script': script,
              'warmup_nmis_excluded': a.warmup_presentations, 'runs': runs}
    (out / 'benchmark.json').write_text(json.dumps(report, indent=2) + '\n')
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
