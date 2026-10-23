#!/usr/bin/env python3
"""Exercise an already-started private two-pad game, with bounded key holds.

This records observed lifetime/telemetry, not an automatic visual or audio PASS.
Prepare Flag Tag with two players using game_smoke.py --two-players first.
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
FRAME = re.compile(r'ELMA PS3 frame: .*free RAM=(\d+) KiB, RSX used=(\d+) bytes, '
                   r'peak=(\d+) bytes, allocations=(\d+), complete=([01]), failures=(\d+)')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--seconds', type=int, default=1800)
    args = parser.parse_args()
    if not 30 <= args.seconds <= 7200:
        parser.error('seconds must be 30..7200')
    base = ROOT/'build'/args.profile
    tty = base/'cache/rpcs3/TTY.log'
    initial = tty.read_bytes()
    enters = list(re.finditer(rb'ELMA PS3 checkpoint: game (enter|leave)', initial))
    if not enters or enters[-1][1] != b'enter':
        raise RuntimeError('Prepare an active game before starting endurance input')
    offset = len(initial)
    pid = (base/'pid').read_text().strip()
    binary = base/'config/rpcs3/dev_hdd0/game/ELMAC0001/USRDIR/EBOOT.BIN'
    report = {'pid': int(pid), 'requested_seconds': args.seconds,
              'eboot_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
              'started_unix_time': time.time(), 'tty_start_offset': offset,
              'cycles': [], 'note': 'Input/lifetime evidence only. Review screenshots, native mode, guest clock and recorded audio separately.'}
    output = base/'endurance.json'
    started = time.monotonic()
    try:
        cycle = 0
        while time.monotonic()-started < args.seconds:
            cycle += 1
            for key, seconds in [('x', 12), ('i', 12), ('v+o', 1), ('x+i', 4)]:
                remaining = args.seconds-(time.monotonic()-started)
                if remaining <= .1:
                    break
                if (base/'pid').read_text().strip() != pid:
                    raise RuntimeError('Private emulator restarted during endurance test')
                subprocess.run([sys.executable, str(ROOT/'test/game_input.py'),
                                '--profile', args.profile, '--keys', f'{key}:{min(seconds,remaining):.3f}',
                                '--wait', '0'], check=True, timeout=75, stdout=subprocess.DEVNULL)
            elapsed = time.monotonic()-started
            log = tty.read_bytes()[offset:].decode(errors='replace')
            if 'checkpoint: game leave' in log or 'checkpoint: shutdown' in log:
                raise RuntimeError('Guest left gameplay during endurance input')
            frames = list(FRAME.finditer(log))
            if not frames:
                raise RuntimeError('No new native frame telemetry; use --sdl-profile')
            latest = frames[-1]
            sample = {'cycle': cycle, 'elapsed_seconds': elapsed,
                      'free_ram_kib': int(latest[1]), 'rsx_used_bytes': int(latest[2]),
                      'rsx_peak_bytes': int(latest[3]), 'rsx_allocations': int(latest[4]),
                      'rsx_tracking_complete': latest[5]=='1', 'rsx_allocation_failures': int(latest[6])}
            if cycle == 1 or cycle % 2 == 0 or elapsed >= args.seconds:
                name = f'endurance-{cycle:03d}.png'
                subprocess.run([sys.executable, str(ROOT/'test/game_input.py'), '--profile', args.profile,
                                '--wait', '0', '--capture-window', '--capture', name],
                               check=True, timeout=20, stdout=subprocess.DEVNULL)
                sample['capture'] = name
            report['cycles'].append(sample)
            output.write_text(json.dumps(report, indent=2)+'\n')
            print(f'Tag endurance {elapsed:.1f}/{args.seconds}s, free {latest[1]} KiB, RSX {latest[2]} bytes', flush=True)
        report['completed_seconds'] = time.monotonic()-started
    except BaseException as error:
        report['error'] = type(error).__name__+': '+str(error)
        raise
    finally:
        output.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
