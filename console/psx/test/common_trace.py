#!/usr/bin/env python3
"""Sample native host PC and PS1 fixed-point physics at 30 Hz.

Each case has an id, a zero-based internal level number, and an inputs
array of masks (gas 1, brake 2, left 4, right 8). One mask covers one real
1/30 second tick, using original game steps capped at 0.0055 plus the
remainder. Samples give the bike body's x, y (up), and angle in radians
in original world coordinates. The final pose and event persist after a
death or finish.

The reference uses the SDL profile for the original PC physics, with
native double, host libm, and floating-point contraction disabled. The
PS1 trace uses the port's fixed-point core and glue on the host.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess

from phys_levels import Resource, internal_levels, write_level
from phys_test import build


EVENTS = {"-": None, "d": "dead", "f": "finish"}


def sample(fields):
    x, y, angle, event = fields
    return dict(x=float(x), y=float(y), angle=float(angle), event=EVENTS[event])


def read_cases(path, level_count):
    cases = json.loads(path.read_text())
    if not isinstance(cases, list):
        raise ValueError("cases must be an array")
    seen = set()
    for case in cases:
        case_id, level, inputs = (case[key] for key in ("id", "level", "inputs"))
        if type(case_id) not in (str, int) or str(case_id) in seen:
            raise ValueError(f"case ID must be a unique string or integer: {case_id!r}")
        if type(level) is not int or not 0 <= level < level_count:
            raise ValueError(f"case {case_id!r}: internal level {level!r} is unavailable")
        if not isinstance(inputs, list) or any(type(mask) is not int or not 0 <= mask <= 15
                                               for mask in inputs):
            raise ValueError(f"case {case_id!r}: expected an array of input masks from 0 to 15")
        seen.add(str(case_id))
        yield str(case_id), level, inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("res", "work", "cases", "out", "reference-out"):
        parser.add_argument("--" + flag, required=True, type=Path)
    args = parser.parse_args()
    if args.out.resolve() == args.reference_out.resolve():
        parser.error("--out and --reference-out must refer to different files")

    levels = internal_levels(Resource(args.res))
    cases = list(read_cases(args.cases, len(levels)))
    args.work.mkdir(parents=True, exist_ok=True)
    executable = build(str(args.work.resolve()))
    paths = {}
    for level in sorted({case[1] for case in cases}):
        paths[level] = args.work / f"lev{level:02d}.txt"
        write_level(paths[level], levels[level])

    reference, ps1 = {}, {}
    for case_id, level, inputs in cases:
        result = subprocess.run(
            [executable, paths[level], "--common-trace"],
            input="".join(f"{mask}\n" for mask in inputs),
            stdout=subprocess.PIPE, text=True, check=True,
            env={**os.environ, "LC_ALL": "C"},
        )
        lines = result.stdout.splitlines()
        if len(lines) != len(inputs):
            raise RuntimeError(f"case {case_id!r}: expected {len(inputs)} samples, got {len(lines)}")
        reference[case_id], ps1[case_id] = [], []
        for line in lines:
            fields = line.split()
            reference[case_id].append(sample(fields[:4]))
            ps1[case_id].append(sample(fields[4:]))
    for path, trace in ((args.reference_out, reference), (args.out, ps1)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(trace, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
