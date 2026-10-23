#!/usr/bin/env python3
"""Bounded graphical RPCS3 test using private game data/configuration and Xvfb.

This intentionally keeps the user's RPCS3 saves/settings untouched. It writes
screenshots and logs for review, and never treats a screenshot as a test pass.
"""
from contextlib import contextmanager
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]

class HarnessInterrupted(Exception):
    def __init__(self, signum):
        self.signum = signum
        super().__init__(f'Harness interrupted by signal {signum}')


def durable_json(path, value):
    """Readers see either the previous complete checkpoint or the new one."""
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w') as output:
        json.dump(value, output, indent=2)
        output.write('\n')
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


class RunRecord:
    def __init__(self, base, metadata):
        self.base, self.metadata = base, metadata
        self.processes, self.proc, self.audio_module = [], None, None
        self.started = time.monotonic()
        self.peak = None
        self.host_window = self.resized_at = None
        self.interrupted = False
        self.interrupt_signal = self.error = None
        self.timed_out = False

    def snapshot(self):
        return dict(self.metadata, elapsed_seconds=time.monotonic()-self.started,
            peak_rss_bytes=self.peak, exit_code=self.proc.poll() if self.proc else None,
            host_window_id=self.host_window, host_resized_at_seconds=self.resized_at,
            interrupted=self.interrupted, interrupt_signal=self.interrupt_signal,
            timed_out=self.timed_out, error=self.error,
            note='Execution record only; screenshots and workflows require review.')

    def check_interrupted(self):
        if self.interrupted:
            raise HarnessInterrupted(self.interrupt_signal)

    def checkpoint(self):
        durable_json(self.base/'run-progress.json', self.snapshot())


@contextmanager
def recorded_run(base, metadata):
    record = RunRecord(base, metadata)
    def interrupted(signum, frame):
        # Defer raising until spawned children have been registered for cleanup.
        record.interrupted = True
        record.interrupt_signal = signum
    previous = {number: signal.signal(number, interrupted)
                for number in (signal.SIGTERM, signal.SIGINT)}
    try:
        record.checkpoint()
        yield record
    except HarnessInterrupted as error:
        record.interrupted = True
        record.interrupt_signal = error.signum
        raise
    except BaseException as error:
        record.error = str(error)
        raise
    finally:
        # Keep the last observed guest exit separate from a harness-induced
        # termination. An interrupted, still-running guest has unknown exit.
        final = record.snapshot()
        for number in previous:
            signal.signal(number, signal.SIG_IGN)
        cleanup_errors = []
        try:
            for process in reversed(record.processes):
                try:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGTERM)
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired) as error:
                    cleanup_errors.append(str(error))
            if record.audio_module is not None:
                try:
                    subprocess.run(['pactl','unload-module',record.audio_module],
                                   check=False, timeout=10)
                except (OSError, subprocess.TimeoutExpired) as error:
                    cleanup_errors.append(str(error))
            final['cleanup_exit_code'] = record.proc.poll() if record.proc else None
            final['cleanup_errors'] = cleanup_errors
            durable_json(base/'run.json', final)
            durable_json(base/'run-progress.json', final)
        finally:
            for number, handler in previous.items():
                signal.signal(number, handler)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=120)
    parser.add_argument('--resolution', default='1280x720', choices=['1920x1080', '1280x720', '720x480', '720x576'])
    parser.add_argument('--aspect', default='16:9', choices=['16:9', '4:3'])
    parser.add_argument('--profile', default='rpcs3-game')
    parser.add_argument('--cpu-offset',type=int,default=0,help='Use four allowed host CPUs beginning at this offset; default0')
    parser.add_argument('--display', default=':93')
    parser.add_argument('--host-window-size', help='Resize only the RPCS3 host window, e.g.640x360; guest resolution remains unchanged')
    parser.add_argument('--binary', type=Path, help='Explicit private ELF/SELF for renderer experiments; records its hash instead of copying packaged EBOOT')
    parser.add_argument('--package-kind', default='with-data', choices=['with-data', 'code'])
    parser.add_argument('--keyboard', default='Basic', choices=['Basic', 'Null'])
    parser.add_argument('--usb-only',action='store_true',help='Use Null pads so RPCS3 routes Basic keyboard/mouse to emulated USB devices')
    parser.add_argument('--two-players', action='store_true', help='Add a second keyboard-mapped controller (I/O/P/B, 1..6, Y/N)')
    parser.add_argument('--frame-limit', default='Auto', choices=['Auto','PS3 Native','60','Off'])
    parser.add_argument('--vblank-rate',type=int,choices=(50,60),help='Override RPCS3 Vblank Rate; does not change the guest video API refresh report')
    parser.add_argument('--renderer', default='Vulkan', choices=['OpenGL', 'Vulkan'])
    parser.add_argument('--sdl-profile', action='store_true')
    parser.add_argument('--audio-dump', action='store_true')
    parser.add_argument('--audio-renderer', choices=['Null','Cubeb','FAudio'])
    parser.add_argument('--audio-volume', type=int, default=100, choices=range(101), metavar='0..100')
    parser.add_argument('--silent-audio-sink', action='store_true', help='Route Cubeb to a private Pulse/PipeWire null sink without muting the dump')
    args = parser.parse_args()
    window_size = None
    if args.host_window_size:
        try:
            window_size = tuple(map(int,args.host_window_size.lower().split('x')))
            if len(window_size)!=2 or any(x<64 or x>4096 for x in window_size): raise ValueError()
        except ValueError:
            parser.error('--host-window-size requires WIDTHxHEIGHT in64..4096')
    if args.usb_only and (args.two_players or args.keyboard != 'Basic'):
        parser.error('--usb-only requires --keyboard Basic and cannot use --two-players')
    selected_cpus = sorted(os.sched_getaffinity(0))[args.cpu_offset:args.cpu_offset+4] if args.cpu_offset>=0 else []
    if len(selected_cpus)!=4:parser.error('--cpu-offset must select four available CPUs')
    if args.audio_renderer is None:
        args.audio_renderer = 'Cubeb' if args.audio_dump else 'Null'
    if args.silent_audio_sink and args.audio_renderer != 'Cubeb':
        parser.error('--silent-audio-sink requires --audio-renderer Cubeb')
    base = ROOT / 'build' / args.profile
    base.mkdir(parents=True, exist_ok=True)
    for stale in base.glob('frame-*.png'):
        stale.unlink()
    config = base / 'config/rpcs3'
    game = config / 'dev_hdd0/game/ELMAC0001'
    game.mkdir(parents=True, exist_ok=True)
    firmware = Path.home() / '.config/rpcs3'
    for name in ('dev_flash', 'dev_flash2', 'dev_flash3'):
        if not (config/name).exists():
            (config/name).symlink_to(firmware/name, target_is_directory=True)
    usrdir = game/'USRDIR'
    usrdir.mkdir(exist_ok=True)
    version = (ROOT/'VERSION').read_text().strip()
    packaged = ROOT/f'dist/elma-classic-ps3-v{version}-{args.package_kind}/ELMAC0001'
    if args.binary is None and (packaged/'USRDIR/EBOOT.BIN').stat().st_mtime < (ROOT/'build/elma.elf').stat().st_mtime:
        raise RuntimeError('Packaged EBOOT.BIN is older than build/elma.elf; re-run tools/package.sh first')
    shutil.copy2(packaged/'PARAM.SFO', game/'PARAM.SFO')
    binary = args.binary.resolve() if args.binary else packaged/'USRDIR/EBOOT.BIN'
    shutil.copy2(binary, usrdir/'EBOOT.BIN')
    shutil.copy2(args.data/'elma.res', usrdir/'elma.res')
    shutil.copytree(args.data/'lgr', usrdir/'lgr', dirs_exist_ok=True)
    for name in ('lev', 'rec', 'snaps'):
        (usrdir/name).mkdir(exist_ok=True)
    (config/'GuiConfigs').mkdir(exist_ok=True)
    gui = '[main_window]\ninfoBoxEnabledWelcome=false\n'
    if args.usb_only:
        gui += '[GSFrame]\ndisableKbHotkeys=true\ndisableMouse=false\n'
    (config/'GuiConfigs/CurrentSettings.ini').write_text(gui)
    yaml = config/'config.yml'
    yaml.write_text(f'''Core:
  PPU Decoder: Recompiler (LLVM)
  PPU Threads: 2
  Max LLVM Compile Threads: 2
  LLVM Precompilation: false
  SPU Decoder: Recompiler (LLVM)
  Preferred SPU Threads: 1
Video:
  Renderer: {args.renderer}
  Frame limit: "{args.frame_limit}"
{('  Vblank Rate: '+str(args.vblank_rate)+chr(10)+'  Vblank NTSC Fixup: false') if args.vblank_rate else ''}
  Resolution: {args.resolution}
  Aspect ratio: {args.aspect}
  Shader Mode: Legacy Recompiler (single-threaded)
  Shader Compiler Threads: 2
Audio:
  Renderer: "{args.audio_renderer}"
  Master Volume: {args.audio_volume}
  Enable Buffering: false
  Dump to file: {str(args.audio_dump).lower()}
Input/Output:
  Keyboard: "{args.keyboard}"
  Mouse: Basic
  Background input enabled: true
Miscellaneous:
  Exit RPCS3 when process finishes: true
  Start games in fullscreen mode: false
  Show PPU compilation hint: false
  Show shader compilation hint: false
  Pause emulation on RPCS3 focus loss: false
''')
    # --input-config accepts a profile name, not a filesystem path.
    pad_config = config/'input_configs/global/ElmaTest.yml'
    pad_config.parent.mkdir(parents=True, exist_ok=True)
    pad_config.write_text('''Player 1 Input:
  Handler: Keyboard
  Device: Keyboard
  Config:
    Left Stick Left: A
    Left Stick Down: S
    Left Stick Right: D
    Left Stick Up: W
    Right Stick Left: Del
    Right Stick Down: End
    Right Stick Right: PgDown
    Right Stick Up: Home
    Start: Return
    Select: Space
    PS Button: Backspace
    Square: Z
    Cross: X
    Circle: C
    Triangle: V
    Left: Left
    Down: Down
    Right: Right
    Up: Up
    R1: E
    R2: T
    R3: G
    L1: Q
    L2: R
    L3: F
''')
    if args.usb_only:
        pad_config.write_text('Player 1 Input:\n  Handler: Null\n  Device: Null\n')
    if args.two_players:
        with pad_config.open('a') as pad:
            pad.write('''Player 2 Input:
  Handler: Keyboard
  Device: Keyboard
  Config:
    Left Stick Left: H
    Left Stick Down: J
    Left Stick Right: K
    Left Stick Up: U
    Start: Y
    Select: N
    Square: O
    Cross: I
    Circle: P
    Triangle: B
    Left: "7"
    Down: "8"
    Right: "9"
    Up: "0"
    R1: "2"
    R2: "4"
    R3: "6"
    L1: "1"
    L2: "3"
    L3: "5"
''')
    env = os.environ.copy()
    env.update(XDG_CONFIG_HOME=str(base/'config'), XDG_CACHE_HOME=str(base/'cache'),
               QT_QPA_PLATFORM='xcb', DISPLAY=args.display)
    if args.sdl_profile:
        # Host environment variables are not forwarded to the emulated PPU.
        with (usrdir/'elma.cfg').open('a') as game_config:
            game_config.write('\nps3_diagnostics = 1\n')
    def limits():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        # Bound all worker threads, including driver shader compilation.
        os.sched_setaffinity(0, selected_cpus)
    metadata = {
        'binary_source': str(binary),
        'eboot_sha256': hashlib.sha256((usrdir/'EBOOT.BIN').read_bytes()).hexdigest(),
        'host_window_size': window_size,
        'resolution': args.resolution, 'aspect': args.aspect,
        'renderer': args.renderer, 'keyboard': args.keyboard,
        'vblank_rate': args.vblank_rate, 'host_cpus': selected_cpus,
        'two_players': args.two_players, 'usb_only': args.usb_only,
        'audio_renderer': args.audio_renderer, 'audio_volume': args.audio_volume,
        'audio_dump': args.audio_dump, 'silent_audio_sink': args.silent_audio_sink,
        'harness_pid': os.getpid(), 'display': args.display,
    }
    with recorded_run(base, metadata) as record:
        with (base/'xvfb.log').open('w') as xlog, (base/'console.log').open('w') as log:
            xvfb = subprocess.Popen(['Xvfb', args.display, '-screen', '0', '1920x1080x24', '-nolisten', 'tcp'], stdout=xlog, stderr=xlog, start_new_session=True)
            record.processes.append(xvfb)
            record.check_interrupted()
            time.sleep(1)
            record.check_interrupted()
            if xvfb.poll() is not None:
                raise RuntimeError('Private Xvfb display could not start')
            if args.silent_audio_sink:
                sink = f'elma_ps3_{os.getpid()}'
                record.audio_module = subprocess.check_output(['pactl','load-module','module-null-sink',
                    'sink_name='+sink, 'rate=48000', 'channels=2'], text=True).strip()
                env['PULSE_SINK'] = sink
                yaml.write_text(yaml.read_text().replace('Audio:\n', 'Audio:\n  Audio Device: "'+sink+'"\n'))
            proc = subprocess.Popen(['rpcs3', '--no-gui', '--config', str(yaml), '--input-config', 'ElmaTest', str(usrdir/'EBOOT.BIN')], env=env,
                                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True, preexec_fn=limits)
            record.proc = proc
            record.processes.append(proc)
            record.check_interrupted()
            (base/'pid').write_text(str(proc.pid))
            (base/'display').write_text(args.display)
            record.checkpoint()
            next_shot, next_checkpoint = 5, 0
            while proc.poll() is None and time.monotonic()-record.started < args.seconds:
                record.check_interrupted()
                elapsed = time.monotonic()-record.started
                if window_size and record.resized_at is None:
                    windows = subprocess.run(['xdotool','search','--onlyvisible','--pid',str(proc.pid)],env=env,capture_output=True,text=True,timeout=10)
                    if windows.returncode==0 and windows.stdout.strip():
                        record.host_window=windows.stdout.splitlines()[-1]
                        subprocess.run(['xdotool','windowsize',record.host_window,str(window_size[0]),str(window_size[1])],env=env,check=True,timeout=10)
                        record.resized_at=elapsed
                try:
                    rss = next(int(line.split()[1])*1024 for line in Path(f'/proc/{proc.pid}/status').read_text().splitlines() if line.startswith('VmRSS:'))
                except (FileNotFoundError, StopIteration):
                    rss = None
                if rss is not None:
                    record.peak = max(record.peak or 0, rss)
                if elapsed >= next_checkpoint:
                    record.checkpoint()
                    next_checkpoint = elapsed+5
                if rss is not None and rss > 4*1024**3:
                    raise RuntimeError('RPCS3 exceeded the 4 GiB host RSS limit')
                if elapsed >= next_shot:
                    subprocess.run(['import', '-window', 'root', str(base/f'frame-{next_shot:03d}.png')], env=env, timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    next_shot += 15
                time.sleep(.5)
            record.check_interrupted()
            record.timed_out = proc.poll() is None
            peak_text = f'{record.peak/1024**2:.1f}' if record.peak is not None else 'unknown'
            print(f'RPCS3 exit={proc.poll()}, peak={peak_text} MiB, artifacts={base}', flush=True)

if __name__ == '__main__':
    try:
        main()
    except HarnessInterrupted as error:
        raise SystemExit(128+error.signum)
