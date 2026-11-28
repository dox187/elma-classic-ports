"""Run one controller corpus on five console physics implementations and the PC source."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from corpus import cases

ROOT = Path(__file__).resolve().parents[2]
PORTS = ('nes', 'snes', 'gbc', 'psx', 'ps3')
# In src/ADATOK.CPP, initmotor() places the two axles at x=1.9 and x=3.6.
WHEELBASE = 3.6 - 1.9


def terminal(rows):
    for tick, row in enumerate(rows, 1):
        if row['event'] is not None:
            return row['event'], tick
    return None, None


def read_trace(path, routes):
    trace = json.loads(path.read_text())
    if set(trace) != {route['id'] for route in routes}:
        raise ValueError(f'{path.name}: missing or extra cases')
    for route in routes:
        rows = trace[route['id']]
        if len(rows) != len(route['inputs']):
            raise ValueError(f"{path.name}: wrong sample count for {route['id']}")
        frozen = None
        for row in rows:
            if (row['event'] not in (None, 'dead', 'finish')
                    or not all(math.isfinite(row[key]) for key in ('x','y','angle'))
                    or (frozen is not None and row != frozen)):
                raise ValueError(f"{path.name}: invalid or unfrozen terminal pose in {route['id']}")
            if row['event'] is not None:
                frozen = row
    return trace


def score(reference, candidate):
    positions, angles = [], []
    outcomes = timed = 0
    for name, expected in reference.items():
        rows = candidate[name]
        original_event, original_tick = terminal(expected)
        port_event, port_tick = terminal(rows)
        outcomes += original_event == port_event
        if original_tick and original_event == port_event and abs(port_tick - original_tick) <= 1:
            timed += 1
        # Identical reference window for every port. An early crash freezes
        # the port but does not remove the rider's remaining PC journey.
        count = original_tick or len(expected)
        distances, rotations = [], []
        for a, b in zip(expected[:count], rows[:count]):
            distances.append(math.hypot(a['x'] - b['x'], a['y'] - b['y']))
            rotations.append(abs(math.degrees(math.remainder(a['angle'] - b['angle'], math.tau))))
        positions.append(math.fsum(distances) / count)
        angles.append(math.fsum(rotations) / count)
    return dict(mean_position_percent_wheelbase=100 * math.fsum(positions) / len(positions) / WHEELBASE,
                mean_body_angle_degrees=math.fsum(angles) / len(angles),
                same_outcome=outcomes, same_terminal_within_one_tick=timed)


def summarize(work, routes):
    pc = read_trace(work / 'pc.json', routes)
    outcomes = Counter(terminal(rows)[0] or 'riding' for rows in pc.values())
    if set(outcomes) != {'riding','dead','finish'} or terminal(pc['flat-track-finish'])[0] != 'finish':
        raise ValueError('PC controls did not cover all required outcomes')
    return dict(corpus_version=1, cases=len(routes), courses=len({c['level'] for c in routes}),
                observation_ticks=sum(len(c['inputs']) for c in routes), reference_outcomes=dict(outcomes),
                scores={port: score(pc, read_trace(work / (port + '.json'), routes)) for port in PORTS})


def run(args, work):
    routes = cases()
    case_file = work / 'cases.json'
    case_file.write_text(json.dumps(routes))
    def adapter(port):
        cmd = [sys.executable, ROOT / f'console/{port}/test/common_trace.py',
               '--res', args.res, '--work', work / port, '--cases', case_file,
               '--out', work / (port + '.json')]
        if port == 'psx':
            cmd.extend(['--reference-out', work / 'pc.json'])
        elif port == 'gbc':
            cmd.extend(['--rom', args.gbc_rom, '--gen', args.gbc_gen, '--jobs', str(args.gbc_jobs)])
        if port == 'ps3' and args.firmware:
            cmd.extend(['--firmware', args.firmware])
        try:
            subprocess.run(cmd, check=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE':'1'})
        except subprocess.CalledProcessError:
            for name in ('build.log', 'rpcs3-console.log'):
                log = work / port / name
                if log.is_file():
                    print(log.read_text(errors='replace')[-4000:], file=sys.stderr)
            raise
    with ThreadPoolExecutor(max_workers=len(PORTS)) as pool:
        list(pool.map(adapter, PORTS))
    summary = summarize(work, routes)
    summary['inputs_sha256'] = hashlib.sha256(case_file.read_bytes()).hexdigest()
    summary['resource_sha256'] = hashlib.sha256(args.res.read_bytes()).hexdigest()
    summary['gbc_rom_sha256'] = hashlib.sha256(args.gbc_rom.read_bytes()).hexdigest()
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--res', type=Path, required=True, help='Registered elma.res with 54 courses')
    parser.add_argument('--gbc-rom', type=Path, required=True)
    parser.add_argument('--gbc-gen', type=Path, required=True)
    parser.add_argument('--gbc-jobs', type=int, default=2)
    parser.add_argument('--firmware', type=Path, help='RPCS3 profile containing installed dev_flash')
    parser.add_argument('--output', type=Path, help='Save the score and input hashes as JSON')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='elma-console-physics-') as work:
        result = run(args, Path(work))
    output = json.dumps(result, indent=2, allow_nan=False) + '\n'
    print(output, end='')
    if args.output:
        args.output.write_text(output)


if __name__ == '__main__':
    main()
