#!/usr/bin/env python3
"""Run one PS3 binary in an isolated RPCS3 profile with bounded resources."""
import argparse, os, pathlib, resource, shutil, signal, subprocess, time

root = pathlib.Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument('binary', type=pathlib.Path)
p.add_argument('--seconds', type=int, default=120)
p.add_argument('--resolution', default='1280x720', choices=['1920x1080','1280x720','720x480','720x576'])
p.add_argument('--aspect', default='16:9', choices=['16:9','4:3'])
p.add_argument('--frame-limit', default='Auto', choices=['Auto','PS3 Native','60','Off'])
p.add_argument('--gui', action='store_true')
p.add_argument('--ppu',choices=['static','llvm'],default='static')
p.add_argument('--renderer', choices=['Vulkan','OpenGL'], default='Vulkan')
a = p.parse_args()
base = root / 'build/rpcs3-test'
config = base / 'config/rpcs3'
config.mkdir(parents=True, exist_ok=True)
source = pathlib.Path.home() / '.config/rpcs3'
for name in ('dev_flash', 'dev_flash2', 'dev_flash3'):
    dest = config / name
    if not dest.exists():
        dest.symlink_to(source / name, target_is_directory=True)
(config / 'GuiConfigs').mkdir(exist_ok=True)
(config / 'GuiConfigs/CurrentSettings.ini').write_text('[main_window]\ninfoBoxEnabledWelcome=false\n')
# Deliberately do not reuse the user's config, caches or writable game data.
yaml = config / 'config.yml'
yaml.write_text('''Core:
  PPU Decoder: Interpreter (static)
  PPU Threads: 2
  Max LLVM Compile Threads: 1
  LLVM Precompilation: false
  SPU Decoder: Interpreter (dynamic)
  Preferred SPU Threads: 1
Video:
  Shader Mode: Legacy Recompiler (single-threaded)
  Shader Compiler Threads: 2
  Write Color Buffers: true
  Renderer: "Null"
Audio:
  Renderer: "Null"
Miscellaneous:
  Exit RPCS3 when process finishes: true
''')
yaml.write_text(yaml.read_text().replace('Video:\n','Video:\n  Resolution: '+a.resolution+'\n  Aspect ratio: '+a.aspect+'\n'))
yaml.write_text(yaml.read_text().replace('  Shader Mode:', '  Frame limit: "'+a.frame_limit+'"\n  Shader Mode:'))
if a.ppu == 'llvm':
    yaml.write_text(yaml.read_text().replace('PPU Decoder: Interpreter (static)', 'PPU Decoder: Recompiler (LLVM)'))
if a.gui:
    yaml.write_text(yaml.read_text().replace('Renderer: "Null"', 'Renderer: '+a.renderer, 1))
env = os.environ.copy()
env.update(XDG_CONFIG_HOME=str(base / 'config'), XDG_CACHE_HOME=str(base / 'cache'),
           QT_QPA_PLATFORM='xcb')
cmd = ['rpcs3', '--no-gui', '--config', str(yaml), str(a.binary.resolve())]
if not env.get('DISPLAY'):
    cmd = ['xvfb-run', '-a', '-s', '-screen 0 1280x720x24'] + cmd

def limits():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:4])

log = base / 'console.log'
with log.open('w') as output:
    proc = subprocess.Popen(cmd, env=env, stdout=output, stderr=subprocess.STDOUT,
                            start_new_session=True, preexec_fn=limits)
    started = time.monotonic()
    peak = 0
    reason = 'finished'
    while proc.poll() is None:
        try:
            pending, rss, seen = [proc.pid], 0, set()
            while pending:
                pid = pending.pop()
                if pid in seen:
                    continue
                seen.add(pid)
                try:
                    status = pathlib.Path(f'/proc/{pid}/status').read_text()
                    rss += next(int(x.split()[1]) * 1024 for x in status.splitlines() if x.startswith('VmRSS:'))
                    pending.extend(map(int, pathlib.Path(f'/proc/{pid}/task/{pid}/children').read_text().split()))
                except (OSError, StopIteration):
                    pass
            peak = max(peak, rss)
        except (OSError, StopIteration):
            rss = 0
        if rss > 4 * 1024**3 or time.monotonic() - started > a.seconds:
            reason = 'memory limit' if rss > 4 * 1024**3 else 'timeout'
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
            break
        time.sleep(0.5)
    proc.wait()
print(f'{reason}; exit={proc.returncode}; peak RSS={peak / 1024**2:.1f} MiB; log={log}')
