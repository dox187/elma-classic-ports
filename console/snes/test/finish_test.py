"""Finishes level 1 "Warm Up" (index 0) in the test ROM build/test_play.sfc
with the keys of test/warmup_finish.txt: the bike turns, rides to the apple,
eats it, turns back and rides to the flower. Checks that the level is
finished and that its time is plausible.

  finish_test.py [--rom build/test_play.sfc] [--script test/warmup_finish.txt]

The script was found by test/finish_search.py with the game in Mesen 2. It
depends on the exact timing of the game (the physics runs 80 steps a second
and the keys are read once an iteration), so a change of the speed of the
game, of the physics or of the level may need a new search.
"""

import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# The original game finishes it in about 15 s; the script is no faster than
# a quick ride and no slower than a minute.
MIN_TIME, MAX_TIME = 8.0, 60.0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--rom', default=os.path.join(ROOT, 'build', 'test_play.sfc'))
    ap.add_argument('--script', default=os.path.join(HERE, 'warmup_finish.txt'))
    ap.add_argument('--level', type=int, default=0)
    a = ap.parse_args()
    script = ' '.join(l.split('#')[0].strip() for l in open(a.script) if l.split('#')[0].strip())
    p = subprocess.run([sys.executable, os.path.join(HERE, 'play.py'), a.rom, str(a.level), script],
                       capture_output=True, text=True)
    out = p.stdout.strip()
    print(out)
    m = re.match(r'finished in (\d+):(\d+):(\d+)', out)
    if p.returncode or not m:
        print('FAIL: the level is not finished')
        return 1
    time = int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3)) / 100
    if not MIN_TIME <= time <= MAX_TIME:
        print('FAIL: the time %.2f s is not plausible' % time)
        return 1
    print('OK: finished in %.2f s' % time)
    return 0


if __name__ == '__main__':
    sys.exit(main())
