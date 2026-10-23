#!/usr/bin/env python3
"""Repeat a prepared menu workflow and require actual guest lifecycle markers.

Prepare the selected level/replay in its browser, or an editor level, first.
Examples (verify the menu and input sequence before starting 50 cycles):
  memory_cycle.py --profile rpcs3-cycles --phase game --after-keys c
  memory_cycle.py --profile rpcs3-cycles --phase replay
  memory_cycle.py --profile rpcs3-cycles --phase editor-play --enter-keys Return

Requires game_smoke.py --sdl-profile. Screenshots need visual review; this tool
only asserts transitions and records guest allocator use, not gameplay quality.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
MARKER = re.compile(r'ELMA PS3 checkpoint: ([a-z-]+) (enter|leave), '
                    r'free RAM=(\d+) KiB, heap used=(\d+) bytes'
                    r'(?:, RSX used=(\d+) bytes, peak=(\d+) bytes, allocations=(\d+), '
                    r'complete=([01]), failures=(\d+))?')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--phase', choices=['game', 'replay', 'editor-play'], required=True)
    parser.add_argument('--cycles', type=int, default=50)
    parser.add_argument('--enter-keys', nargs='+', default=['x'])
    parser.add_argument('--leave-keys', nargs='+', default=['space'])
    parser.add_argument('--after-keys', nargs='*', default=[])
    parser.add_argument('--capture-every', type=int, default=10)
    parser.add_argument('--dwell', type=float, default=1)
    parser.add_argument('--timeout', type=float, default=30)
    parser.add_argument('--output', default='memory-cycles.json')
    args = parser.parse_args()
    if not 1 <= args.capture_every <= 1000:
        parser.error('capture-every must be 1..1000')
    if not 1 <= args.cycles <= 1000 or not .2 <= args.dwell <= 60 or not 1 <= args.timeout <= 60:
        parser.error('cycles must be 1..1000; dwell .2..60 and timeout 1..60 seconds')
    base = ROOT / 'build' / args.profile
    tty = base / 'cache/rpcs3/TTY.log'
    position = tty.stat().st_size
    pid = (base/'pid').read_text().strip()
    eboot = base/'config/rpcs3/dev_hdd0/game/ELMAC0001/USRDIR/EBOOT.BIN'
    report = {'phase': args.phase, 'requested_cycles': args.cycles, 'cycles': [],
              'pid': int(pid), 'started_unix_time': time.time(),
              'eboot_sha256': hashlib.sha256(eboot.read_bytes()).hexdigest(),
              'inputs': {'enter': args.enter_keys, 'leave': args.leave_keys,
                         'after': args.after_keys, 'dwell_seconds': args.dwell},
              'note': 'Guest transition and allocator evidence; screenshots require visual review.'}
    target = base / Path(args.output).name

    def inputs(keys, wait=0, capture=None):
        if (base/'pid').read_text().strip() != pid:
            raise RuntimeError('Private test restarted during the workflow')
        command = [sys.executable, str(ROOT/'test/game_input.py'), '--profile', args.profile,
                   '--wait', str(wait)]
        if keys:
            command += ['--keys', *keys]
        if capture:
            command += ['--capture', capture, '--capture-window']
        subprocess.run(command, check=True, timeout=90, stdout=subprocess.DEVNULL)

    def checkpoint(action):
        nonlocal position
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            with tty.open('rb') as log:
                log.seek(position)
                while True:
                    start = log.tell()
                    raw = log.readline()
                    if not raw.endswith(b'\n'):
                        position = start
                        break
                    position = log.tell()
                    match = MARKER.search(raw.decode('utf-8', errors='replace'))
                    if match and match[1] == args.phase:
                        if match[2] != action:
                            raise RuntimeError(f'Expected {action}; received {match[2]} at byte {start}')
                        sample = {'free_ram_kib': int(match[3]), 'heap_used_bytes': int(match[4]),
                                  'tty_offset': start}
                        if match[5] is not None:
                            sample.update(rsx_used_bytes=int(match[5]), rsx_peak_bytes=int(match[6]),
                                          rsx_allocations=int(match[7]), rsx_tracking_complete=match[8]=='1',
                                          rsx_allocation_failures=int(match[9]))
                        return sample
            time.sleep(.1)
        raise RuntimeError(f'No guest {args.phase} {action} within {args.timeout} seconds')

    try:
        for cycle in range(1, args.cycles + 1):
            inputs(args.enter_keys)
            entered = checkpoint('enter')
            capture = f'{Path(args.output).stem}-{cycle:03d}.png' if cycle == 1 or cycle % args.capture_every == 0 else None
            inputs([], wait=args.dwell, capture=capture)
            inputs(args.leave_keys)
            left = checkpoint('leave')
            if args.after_keys:
                inputs(args.after_keys, wait=.3)
            report['cycles'].append({'cycle': cycle, 'enter': entered, 'leave': left, 'capture': capture})
            target.write_text(json.dumps(report, indent=2)+'\n')
            print(f'{args.phase} {cycle}/{args.cycles}: free {left["free_ram_kib"]} KiB, '
                  f'heap {left["heap_used_bytes"]} bytes', flush=True)
        # Exclude the first five cycles so one-time lazy allocations are visible
        # separately from the steady-state trend. Do not turn a tolerance into
        # a claim that arbitrary smaller leaks have been disproved.
        steady = report['cycles'][5:] or report['cycles']
        heaps = [cycle['leave']['heap_used_bytes'] for cycle in steady]
        free = [cycle['leave']['free_ram_kib'] for cycle in steady]
        window = min(10, len(heaps))
        report['completed_cycles'] = len(report['cycles'])
        report['steady_state'] = {
            'first_cycle': steady[0]['cycle'], 'heap_min_bytes': min(heaps),
            'heap_max_bytes': max(heaps), 'minimum_free_ram_kib': min(free),
            'last_window_minus_first_window_heap_min_bytes': min(heaps[-window:])-min(heaps[:window])}
        if all('rsx_used_bytes' in cycle['leave'] for cycle in steady):
            rsx = [cycle['leave']['rsx_used_bytes'] for cycle in steady]
            report['steady_state'].update(
                rsx_min_bytes=min(rsx), rsx_max_bytes=max(rsx),
                last_window_minus_first_window_rsx_min_bytes=min(rsx[-window:])-min(rsx[:window]),
                rsx_tracking_complete=all(cycle['leave']['rsx_tracking_complete'] for cycle in steady),
                rsx_allocation_failures=max(cycle['leave']['rsx_allocation_failures'] for cycle in steady))
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        target.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
