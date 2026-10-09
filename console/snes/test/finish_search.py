"""Searches a script of keys that finishes a level, with the C description of
the physics on the host (test/physplay.c, build/host/physplay.so; it is the
same as the assembly to the bit): a beam search over short segments of keys
in steps of the physics, each tried from the saved state of its parent.

  finish_search.py LEVEL [--gen build/gen] [--width N] [--out FILE]

Level 0 (Warm Up): first to the apple (the first segment turns), then, after
a second turn, to the flower; the bike must not rush near the flower. The
script is in the syntax of test/play.py --steps; written to FILE with the
time of the finish, test/finish_test.py plays it in the ROM. Build the
library first: make build/host/physplay.so.
"""

import argparse
import ctypes
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import play  # noqa: E402

GAS, BRAKE, VOLT_R, VOLT_L = 1, 2, 4, 8
DEAD, FINISH = 1, 2
TURN = play.STEP_TURN
HZ = 80
# The segments: the keys and their steps.
ACTS = [0, GAS, GAS | VOLT_R, GAS | VOLT_L, VOLT_R, VOLT_L, BRAKE]
DURS = [8, 16, 32]


class Physics:
    def __init__(self, gen, level):
        path = os.path.join(gen, '..', 'host', 'physplay.so')
        if not os.path.exists(path):
            raise SystemExit('%s not found: make build/host/physplay.so' % path)
        self.lib = ctypes.CDLL(os.path.abspath(path))
        if self.lib.pp_level(os.path.join(gen, 'phys', 'lev%02d.bin' % level).encode()):
            raise SystemExit('level %d not found in %s' % (level, gen))
        self.size = self.lib.pp_state_size()
        self.view_ = (ctypes.c_int32 * 9)()

    def save(self):
        s = ctypes.create_string_buffer(self.size)
        self.lib.pp_save(s)
        return s

    def load(self, s):
        self.lib.pp_load(s)

    def run(self, keys):
        ev = ctypes.c_uint16()
        n = self.lib.pp_run(bytes(keys), len(keys), ctypes.byref(ev))
        return n, ev.value

    def view(self):
        """x, y of the body in m, its speed in m a step, its angle (2^-28
        rad), the apples left and the direction."""
        self.lib.pp_view(self.view_)
        v = self.view_
        return (v[0] / 65536, v[1] / 65536, v[2] / 2 ** 24, v[3] / 2 ** 24, v[4], v[7], v[8])


class Node:
    __slots__ = ('parent', 'keys', 'state', 'T', 'x', 'y', 'apples', 'turns', 'score')


def script_of(node):
    """The keys of the steps from the start to the node."""
    parts = []
    while node.parent:
        parts.append(node.keys)
        node = node.parent
    out = []
    for p in reversed(parts):
        out += p
    return out


def compress(keys):
    """The keys of the steps in the syntax of test/play.py --steps."""
    names = [(GAS, 'G'), (BRAKE, 'B'), (VOLT_R, 'R'), (VOLT_L, 'L')]
    toks = []
    i = 0
    while i < len(keys):
        k = keys[i]
        j = i + 1
        while j < len(keys) and keys[j] == k & ~TURN:
            j += 1
        name = ''.join(n for b, n in names if k & b) or 'N'
        toks.append('%s%s%d' % (name, 'T' if k & TURN else '', j - i))
        i = j
    return ' '.join(toks)


def score(a, x, vx, apples, T):
    target = a.flower if apples == 0 else a.apple
    s = -abs(target - x) - T * a.timepen
    # near the end the bike should not rush (a flip or a crash kills it):
    if apples == 0:
        s += 400
        if abs(target - x) < 12:
            s -= a.speedpen * max(0.0, abs(vx) - a.vmax)
    return s + a.rand.random() * 0.05


def search(a):
    ph = Physics(a.gen, a.level)
    root = Node()
    root.parent, root.keys, root.state, root.T = None, [], ph.save(), 0
    root.x, root.y, _, _, _, root.apples, _ = ph.view()
    root.turns, root.score = 0, 0.0
    beam = [root]
    for gen in range(a.gens):
        kept = {}
        for p in beam:
            for act in ACTS:
                for dur in DURS:
                    for turn in (0, 1):
                        # the first segment turns, a second turn after the apple:
                        if p.turns == 0 and not turn:
                            continue
                        if p.turns and turn and (p.apples or p.turns >= 2):
                            continue
                        keys = [act | (TURN if turn else 0)] + [act] * (dur - 1)
                        ph.load(p.state)
                        n, ev = ph.run(keys)
                        if ev & FINISH:
                            c = Node()
                            c.parent, c.keys, c.T = p, keys[:n], p.T + n
                            return c
                        if ev & DEAD:
                            continue
                        x, y, vx, vy, ang, apples, _ = ph.view()
                        T = p.T + n
                        s = score(a, x, vx, apples, T)
                        # one of the states in a cell of the position, angle and time:
                        cell = (int(x * 3 // 1), int(y * 3 // 1), ang >> 25, T // 8, apples)
                        if cell in kept and kept[cell].score >= s:
                            continue
                        c = Node()
                        c.parent, c.keys, c.state, c.T = p, keys, ph.save(), T
                        c.x, c.y, c.apples, c.score = x, y, apples, s
                        c.turns = p.turns + turn
                        kept[cell] = c
        beam = sorted(kept.values(), key=lambda c: -c.score)[:a.width]
        if not beam:
            raise SystemExit('no way on after %d generations' % gen)
        b = beam[0]
        if gen % 10 == 0:
            print('gen %d: %d kept, best %.1f at %.2f s, x %.2f, apples left %d'
                  % (gen, len(kept), b.score, b.T / HZ, b.x, b.apples), flush=True)
    raise SystemExit('not finished after %d generations' % a.gens)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('level', type=int)
    ap.add_argument('--gen', default=os.path.join(ROOT, 'build', 'gen'))
    ap.add_argument('--width', type=int, default=64)
    ap.add_argument('--gens', type=int, default=400)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--apple', type=float, default=17.92, help='x of the apple (m)')
    ap.add_argument('--flower', type=float, default=-11.45, help='x of the flower (m)')
    ap.add_argument('--vmax', type=float, default=0.03, help='m a step, near the flower')
    ap.add_argument('--speedpen', type=float, default=200.0)
    ap.add_argument('--timepen', type=float, default=0.0015, help='a step')
    ap.add_argument('--out', default='')
    a = ap.parse_args()
    a.rand = random.Random(a.seed)
    end = search(a)
    keys = script_of(end)
    # the time of the game: the hundredths of the steps before the finish
    hs = (end.T - 1) * 100 // HZ
    time = '%02d:%02d:%02d' % (hs // 6000, hs // 100 % 60, hs % 100)
    text = compress(keys)
    print('finished in %s (%d steps)' % (time, end.T))
    print(text)
    if a.out:
        with open(a.out, 'w') as f:
            f.write('# Finishes level %d on the SNES (test/finish_test.py). Found by\n'
                    '# test/finish_search.py with the C description of the physics; the\n'
                    '# keys of the steps of the physics, the syntax of test/play.py --steps.\n'
                    'time %s\n%s\n' % (a.level + 1, time, text))


if __name__ == '__main__':
    main()
