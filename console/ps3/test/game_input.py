#!/usr/bin/env python3
"""Send pad-key presses only to a verified private game_smoke.py instance.

Example: game_input.py --keys x Down x x --capture warm-up.png
Keys are the keyboard-to-pad mapping recorded by game_smoke.py. Longer holds
use KEY:SECONDS, for example x:5. A chord such as e+Home:0.2 holds
R1 and the right stick up together. This tool records inputs, not test verdicts.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', default='rpcs3-game')
    parser.add_argument('--keys', nargs='*', default=[])
    parser.add_argument('--wait', type=float, default=1)
    parser.add_argument('--capture')
    parser.add_argument('--capture-window', action='store_true', help='Capture only the verified game window instead of its private Xvfb screen')
    parser.add_argument('--mouse', nargs=2, type=int, metavar=('X','Y'), help='Move the Basic USB mouse within the verified game window')
    parser.add_argument('--mouse-relative',nargs=2,type=int,metavar=('DX','DY'),help='Relative movement for the emulated USB mouse')
    parser.add_argument('--click', type=int, choices=(1,3), help='Click the Basic USB left/right mouse button')
    args = parser.parse_args()
    base = ROOT / 'build' / args.profile
    pid = int((base / 'pid').read_text())
    proc = Path('/proc') / str(pid)
    command = (proc / 'cmdline').read_bytes().split(b'\0')
    expected = str(base / 'config/rpcs3/config.yml').encode()
    if (proc / 'comm').read_text().strip() != 'rpcs3' or expected not in command:
        raise RuntimeError('PID does not identify this private RPCS3 test')
    env = dict(os.environ, DISPLAY=(base / 'display').read_text().strip())
    def run(*command):
        return subprocess.run(command, env=env, check=True, capture_output=True,
                              text=True, timeout=10).stdout.strip()
    windows = run('xdotool', 'search', '--onlyvisible', '--pid', str(pid)).splitlines()
    if not windows:
        raise RuntimeError('No visible window belongs to the private test')
    run('xdotool', 'windowfocus', '--sync', windows[-1])
    if args.mouse:
        if any(coordinate < 0 or coordinate > 8192 for coordinate in args.mouse):
            raise ValueError('Mouse coordinates must be between 0 and 8192')
        run('xdotool', 'mousemove', '--sync', '--window', windows[-1], *map(str,args.mouse))
    if args.mouse_relative:
        if any(abs(coordinate)>8192 for coordinate in args.mouse_relative):raise ValueError('Relative mouse movement exceeds8192')
        run('xdotool','mousemove_relative','--sync','--',*map(str,args.mouse_relative))
    if args.click:
        run('xdotool','mousedown',str(args.click))
        try:time.sleep(.15)
        finally:run('xdotool','mouseup',str(args.click))
    records = []
    for spec in args.keys:
        key, _, hold = spec.partition(':')
        duration = float(hold) if hold else .15
        if not 0 < duration <= 60:
            raise ValueError('Key holds must be between 0 and 60 seconds')
        chord = key.split('+')
        if not all(chord):
            raise ValueError('Chord key names must be nonempty')
        pressed = []
        try:
            for member in chord:
                run('xdotool', 'keydown', member)
                pressed.append(member)
            time.sleep(duration)
        finally:
            for member in reversed(pressed):
                run('xdotool', 'keyup', member)
        records.append({'key': key, 'seconds': duration})
        time.sleep(.2)
    time.sleep(max(0, min(args.wait, 60)))
    if args.capture:
        capture = base / Path(args.capture).name
        run('import', '-window', windows[-1] if args.capture_window else 'root', str(capture))
        print(capture)
    with (base / 'inputs.jsonl').open('a') as log:
        log.write(json.dumps({'time': time.time(), 'pid': pid, 'keys': records,
                              'capture': args.capture, 'capture_window': args.capture_window, 'mouse': args.mouse, 'mouse_relative': args.mouse_relative, 'click': args.click}) + '\n')


if __name__ == '__main__':
    main()
