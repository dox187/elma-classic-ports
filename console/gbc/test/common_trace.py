"""Sample the linked GBC ROM on the common input and observation clocks."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import shutil
import sys
import struct
import tempfile
from types import SimpleNamespace

from benchmark_gameplay import DEAD, FINISHED, RIDING, run_case_with_driver
from play import BASE, signed_angle

sys.path.insert(0, str(BASE.parents[1] / "tests/console_physics"))
from sampling import sample_30hz

# One scheduled riding update per two LCD refreshes, independent of rendering time.
RATE = Fraction(4194304, 2 * 70224)
BUTTONS = ((1, 'a'), (2, 'b'), (4, 'left'), (8, 'right'))


def pose(state):
    x, y, angle = struct.unpack_from('<iiH', bytes.fromhex(state['gbc_bike_hex']))
    event = {RIDING: None, DEAD: 'dead', FINISHED: 'finish'}[state['state']]
    return dict(x=x / 65536, y=y / 65536, angle=signed_angle(angle), event=event)


def run(case, rom, gen, names, work):
    inputs = case['inputs']
    ratio = RATE / 30
    native_steps = -(-len(inputs) * ratio.numerator // ratio.denominator)
    plan = []
    for step in range(native_steps):
        mask = inputs[step * ratio.denominator // ratio.numerator]
        plan.append(sorted(key for bit, key in BUTTONS if mask & bit))
    args = SimpleNamespace(rom=rom, gen=gen, steps=len(plan), substep_states=False)
    with tempfile.TemporaryDirectory(dir=work) as scratch:
        result, trace = run_case_with_driver(args, case['level'] + 1, case['id'], names,
                                             Path(scratch), plan=plan)
    if not result['correctness_checks_passed']:
        raise ValueError(f"{case['id']}: {result['errors']}")
    states = [pose(trace['initial'])] + [pose(update['state_after']) for update in trace['updates']]
    if len(states) <= native_steps and states[-1]['event'] is None:
        raise ValueError(f"{case['id']}: truncated riding trace")
    return case['id'], sample_30hz(((i / RATE, state) for i, state in enumerate(states)), len(inputs))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('cases', 'res', 'out', 'work', 'rom', 'gen'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args()
    manifest = json.loads((args.gen / 'level_manifest.json').read_text())
    res_hashes = [v for path, v in manifest['source_sha256'].items() if path.lower().endswith('.res')]
    if res_hashes != [hashlib.sha256(args.res.read_bytes()).hexdigest()]:
        raise ValueError('GBC levels were generated from a different resource')
    build = json.loads(args.rom.with_suffix('.build.json').read_text())
    if hashlib.sha256(args.rom.read_bytes()).hexdigest() != build['rom_sha256']:
        raise ValueError('GBC ROM differs from its build manifest')
    names = [level['name'] for level in manifest['levels']]
    cases = json.loads(args.cases.read_text())
    args.work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.work) as scratch:
        # A clean cartridge has no saved profile or remapped controls.
        rom = Path(scratch) / args.rom.name
        shutil.copyfile(args.rom, rom)
        shutil.copyfile(args.rom.with_suffix('.noi'), rom.with_suffix('.noi'))
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            futures = [pool.submit(run, case, rom, args.gen, names, scratch) for case in cases]
            results = dict(future.result() for future in futures)
    args.out.write_text(json.dumps(results, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
