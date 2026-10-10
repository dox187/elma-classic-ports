#!/usr/bin/env python3
"""Check long PC reference traces keep exactly one matched80Hz step per sample."""
import argparse
import json
from pathlib import Path
import subprocess


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--host', type=Path, default=Path('build/host/physcheck'))
    ap.add_argument('--gen', type=Path, default=Path('build/gen'))
    ap.add_argument('--levdump', type=Path, default=Path('build/host/levdump'))
    ap.add_argument('--steps', type=int, default=8000)
    a = ap.parse_args()
    if a.steps < 4800:
        ap.error('Use at least4800steps to cover the accumulated-clock regression')
    dt = .4368 / 80
    for cap in (None, .0055):
        command = [str(a.host.resolve()), str(a.gen), str(a.levdump),
                   '0', 'N'+str(a.steps), '--trace-json']
        if cap is not None:
            command += ['-t', str(cap)]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        assert len(rows) == a.steps+1, 'Stationary WarmUp trace ended early'
        previous = 0.
        for step, row in enumerate(rows[1:], 1):
            assert row['step'] == step and not row['pc_stopped']
            elapsed = row['pc_time_game'] - previous
            assert abs(elapsed-dt) < 1e-10, (cap, step, elapsed, dt)
            previous = row['pc_time_game']
        print(f'PASS {a.steps}steps: cap={cap}, elapsed={previous:.12f}')


if __name__ == '__main__':
    main()
