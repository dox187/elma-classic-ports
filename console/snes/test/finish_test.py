"""Finishes level 1 "Warm Up" (index 0) in the test ROM build/test_play.sfc
with the keys of test/warmup_finish.txt: the bike turns, rides to the apple,
eats it, turns back and rides to the flower. Checks that the level is
finished in the time of the script, to the hundredth.

  finish_test.py [--rom build/test_play.sfc] [--script test/warmup_finish.txt]

The script was found by test/finish_search.py with the C description of the
physics. Its keys are those of the steps of the physics (test/play.py
--steps), so the ride does not depend on how long the frames take; a change
of the physics or of the level may need a new search.
"""

import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def read_script(path):
    """The time (mm:ss:hh) and the keys of a script file."""
    time, keys = None, []
    for line in open(path):
        line = line.split('#')[0].strip()
        if line.startswith('time '):
            time = line.split()[1]
        elif line:
            keys.append(line)
    if not time:
        raise SystemExit('%s: no time line' % path)
    return time, ' '.join(keys)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--rom', default=os.path.join(ROOT, 'build', 'test_play.sfc'))
    ap.add_argument('--script', default=os.path.join(HERE, 'warmup_finish.txt'))
    ap.add_argument('--level', type=int, default=0)
    a = ap.parse_args()
    want, script = read_script(a.script)
    p = subprocess.run([sys.executable, os.path.join(HERE, 'play.py'), a.rom, str(a.level), script,
                        '--steps', '--out', os.path.join(ROOT, 'build', 'finish')],
                       capture_output=True, text=True)
    out = p.stdout.strip()
    print(out)
    m = re.match(r'finished in (\d+:\d+:\d+)', out)
    if p.returncode or not m:
        print('FAIL: the level is not finished')
        return 1
    if m.group(1) != want:
        print('FAIL: finished in %s instead of %s' % (m.group(1), want))
        return 1
    print('OK: finished in %s' % want)
    return 0


if __name__ == '__main__':
    sys.exit(main())
