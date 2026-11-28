#!/usr/bin/env python3
"""Run the shared 30 Hz physics cases on the original PS3 PPU engine."""
import argparse
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

from math import isfinite


PS3 = Path(__file__).resolve().parents[1]
LEVEL_EXTRACTOR = PS3.parent / 'psx/test/phys_levels.py'
GUEST_DIR = '/dev_hdd0/game/ELMAC0001/USRDIR'
EVENTS = {'-': None, 'd': 'dead', 'f': 'finish'}
CONFIG = '''Core:
  PPU Decoder: Interpreter (static)
  PPU Threads: 2
  SPU Decoder: Interpreter (dynamic)
Video:
  Renderer: "Null"
Audio:
  Renderer: "Null"
Miscellaneous:
  Exit RPCS3 when process finishes: true
'''


def prepare_cases(resource, cases, guest):
    levels = guest / 'levels'
    subprocess.run(
        [sys.executable, str(LEVEL_EXTRACTOR), str(resource), str(levels)],
        check=True,
    )
    with (guest / 'physics-cases.txt').open('w') as output:
        for case in cases:
            level = f'lev{case["level"]:02d}.txt'
            if not (levels / level).is_file():
                raise ValueError(f'{case["id"]}: resource has no level {case["level"]}')
            inputs = case['inputs']
            if any(type(value) is not int or not 0 <= value <= 15 for value in inputs):
                raise ValueError(f'{case["id"]}: invalid input mask')
            # The fixture reads a 32768-byte protocol line.
            line = f'{GUEST_DIR}/levels/{level} common ' + ''.join(
                format(value, 'x') for value in inputs
            ) + '\n'
            if len(line) >= 32768:
                raise ValueError(f'{case["id"]}: too many input ticks')
            output.write(line)


def parse_trace(path, cases):
    traces = {}
    with path.open() as stream:
        for index, case in enumerate(cases):
            if stream.readline().strip() != f'case {index}':
                raise ValueError(f'{case["id"]}: missing PS3 trace case header')
            samples = []
            for tick in range(len(case['inputs'])):
                fields = stream.readline().split()
                if len(fields) != 5 or fields[0] != 'sample' or fields[4] not in EVENTS:
                    raise ValueError(f'{case["id"]}: invalid PS3 trace sample at tick {tick}')
                x, y, angle = (
                    struct.unpack('>d', bytes.fromhex(value))[0] for value in fields[1:4]
                )
                if not all(map(isfinite, (x, y, angle))):
                    raise ValueError(f'{case["id"]}: non-finite PS3 pose at tick {tick}')
                samples.append(dict(x=x, y=y, angle=angle, event=EVENTS[fields[4]]))
            traces[case['id']] = samples
        if stream.readline().strip() != f'complete {len(cases)}' or stream.read():
            raise ValueError('PS3 trace did not end with the expected completion marker')
    return traces


def run_emulator(emulator, firmware, work, guest_binary, resource, cases):
    macos = sys.platform == 'darwin'
    with tempfile.TemporaryDirectory(prefix='rpcs3-', dir=work) as temporary:
        profile = Path(temporary)
        config = profile / ('Library/Application Support/rpcs3' if macos else 'config/rpcs3')
        guest = config / GUEST_DIR.lstrip('/')
        guest.mkdir(parents=True)
        for name in ('dev_flash', 'dev_flash2', 'dev_flash3'):
            source = firmware / name
            if source.is_dir():
                shutil.copytree(source, config / name)
        settings = config / 'config.yml'
        settings.write_text(CONFIG)
        prepare_cases(resource, cases, guest)
        env = os.environ.copy()
        session_tmp = profile / 'tmp'
        session_tmp.mkdir()
        env.update(
            HOME=str(profile),
            XDG_CONFIG_HOME=str(profile / 'config'),
            XDG_CACHE_HOME=str(profile / 'cache'),
            TMPDIR=str(session_tmp),
        )
        if not macos:
            env.setdefault('QT_QPA_PLATFORM', 'offscreen')
        log = work / 'rpcs3-console.log'
        native = guest / 'physics-trace.txt'
        try:
            with log.open('w') as stream:
                subprocess.run(
                    [emulator, '--headless', '--allow-any-location',
                     '--config', str(settings), str(guest_binary)],
                    cwd=profile, env=env, stdout=stream, stderr=subprocess.STDOUT,
                    timeout=180, check=True,
                )
        finally:
            cache = profile / ('Library/Caches/rpcs3' if macos else 'cache/rpcs3')
            emulator_log = cache / 'RPCS3.log'
            if emulator_log.is_file():
                shutil.copyfile(emulator_log, work / 'RPCS3.log')
            if native.is_file():
                shutil.copyfile(native, work / 'physics-trace.txt')
        if not native.is_file():
            raise RuntimeError(f'RPCS3 produced no physics trace. See {log}')
        return parse_trace(native, cases)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('res', 'work', 'cases', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--rpcs3', default=os.environ.get('RPCS3'))
    parser.add_argument('--firmware', type=Path, help='RPCS3 profile containing installed dev_flash')
    args = parser.parse_args()
    macos = sys.platform == 'darwin'
    emulator = args.rpcs3 or shutil.which('rpcs3')
    if not emulator and macos:
        for bundle in ('/Applications/RPCS3.app', '/Applications/ps3/RPCS3.app'):
            binary = Path(bundle) / 'Contents/MacOS/rpcs3'
            if binary.is_file():
                emulator = str(binary)
                break
    if not emulator:
        parser.error('RPCS3 executable unavailable. Supply --rpcs3')
    emulator = shutil.which(emulator)
    if not emulator:
        parser.error('RPCS3 executable unavailable')
    emulator = str(Path(emulator).resolve())
    if (Path(emulator).parent / 'portable').is_dir():
        parser.error('RPCS3 has a portable profile next to its executable. Use a non-portable installation')
    firmware = args.firmware or (
        Path.home() / 'Library/Application Support/rpcs3' if macos else
        Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'rpcs3'
    )
    if not (firmware / 'dev_flash/sys/external/liblv2.sprx').is_file():
        parser.error('Installed RPCS3 firmware unavailable. Supply --firmware')
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    build = work / 'build'
    sdk = Path(os.environ.get('PS3DEV', PS3 / '.toolchain/ps3dev')).resolve()
    if not (sdk / 'ppu/bin/ppu-g++').is_file():
        parser.error('PSL1GHT toolchain unavailable. Set PS3DEV or run console/ps3/tools/bootstrap.sh')
    env = os.environ.copy()
    env.update(PS3DEV=str(sdk), PSL1GHT=str(sdk), PATH=os.pathsep.join([
        str(sdk / 'bin'), str(sdk / 'ppu/bin'), env.get('PATH', ''),
    ]))
    try:
        stripped = build / 'physics-trace-linked.elf'
        binary = build / 'physics-trace.self'
        with (work / 'build.log').open('w') as log:
            for command in (
                ['cmake', '-S', str(PS3), '-B', str(build),
                 '-DCMAKE_TOOLCHAIN_FILE=' + str(PS3 / 'toolchain.cmake')],
                ['cmake', '--build', str(build), '--target', 'physics-trace', '--parallel', '4'],
                ['ppu-strip', str(build / 'physics-trace.elf'), '-o', str(stripped)],
                ['sprxlinker', str(stripped)],
                ['make_self', str(stripped), str(binary)],
            ):
                subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        traces = run_emulator(
            emulator, firmware, work, binary,
            args.res.resolve(), json.loads(args.cases.read_text()),
        )
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, f'{error}. Logs and traces are under {work}\n')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(traces, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
