"""Reproduce Hi Flyer's brake bounce with identical incoming states/inputs.

Run from any directory: python3 console/nes/test/hyflyer.py [--asm] [--scan]
Requires a registered elma.res, a host C compiler, numpy and matplotlib.
Outputs CSV traces, JSON measurements and a figure in
console/nes/build/hyflyer-check.
A generated host-only legacy variant reproduces the pre-beta2 angle wrap.
Never modifies or builds the game ROM.

These are seeded final-section experiments, not complete level replays.
All apples are assumed collected. The reference uses the original brake;
0.003 and 0.0055 are tested as integration caps because the repository's
LEJATSZO.CPP actively uses the latter and comments mention the former.
"""
import argparse
import ctypes as C
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np

NES = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(NES / 'tools'))
from elmadata import Resource, internal_levels  # noqa: E402

D = C.c_double
DP = C.POINTER(D)


def command(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def change_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Physics source changed: review diagnostic replacement: ' + old)
    return source.replace(old, new)


def legacy_source():
    source = (NES / 'src/physics.c').read_text()
    return change_once(source,
        'int32_t da = (int32_t)(Bike.wheel[k].alfa-(Bike.body.alfa+Bike.dbrake[k])) >> 8;',
        'int16_t da = (int16_t)((Bike.wheel[k].alfa-(Bike.body.alfa+Bike.dbrake[k])) >> 8);')


class Probe:
    def __init__(self, library, level):
        self.lib = C.CDLL(str(library))
        for name, args in {
            'probe_level': [C.c_char_p], 'probe_init': [DP],
            'probe_get': [C.c_int, DP],
            'probe_step': [C.c_int, C.c_int, D, D],
            'ref_set_brake_damping': [D], 'probe_seed': [C.c_char_p],
        }.items():
            getattr(self.lib, name).argtypes = args
        self.lib.probe_dt.restype = D
        self.h = self.lib.probe_dt()
        if not self.lib.probe_level(str(level).encode()):
            raise ValueError('Cannot load test geometry')

    def run(self, state, flower, brake_time, fixed, cap=0.003, damping=1.0, duration=1.5):
        self.lib.probe_init(state.ctypes.data_as(DP))
        self.lib.ref_set_brake_damping(damping)
        brake_tick = math.ceil(brake_time/self.h - 1e-10)
        out = []
        s = np.empty(27)
        for tick in range(math.ceil(duration/self.h)):
            inp = 1 if tick < brake_tick else 2
            remaining = self.h
            now = tick*self.h
            while remaining > 1e-12:
                dt = remaining if fixed else min(cap, remaining)
                alive = self.lib.probe_step(fixed, inp, now, dt)
                self.lib.probe_get(fixed, s.ctypes.data_as(DP))
                now += dt
                remaining -= dt
                # Same circular flower test for both models, without pixel
                # broad phase, object quantization or uncollected apples.
                gap = min(math.hypot(s[k]-flower[0], s[k+1]-flower[1])-r
                          for k, r in [(6, .8), (12, .8), (22, .638)])
                if not alive or gap < 0:
                    break
            out.append([now, alive, gap, *s])
            if not alive or gap < 0:
                break
        return np.array(out)


def state_at(x, y, angle, vx, vy):
    c, s = math.cos(angle), math.sin(angle)
    i, j = np.array([c, s]), np.array([-s, c])
    body = np.array([x, y])
    state = np.zeros(27)
    state[:6] = [x, y, vx, vy, angle, 0]
    # Rolling angular velocity about the surface whose inward normal is j.
    spin = -(c*vx+s*vy)/.4
    for k in range(2):
        state[6+6*k:12+6*k] = [*(body+i*(-.85 if k == 0 else .85)-j*.6), vx, vy, angle, spin]
    state[18:22] = [*(body+j*.44), vx, vy]
    state[24] = 1  # Facing down the left wall / down-right on the ramp.
    return state


def metrics(trace):
    crossed = np.flatnonzero(np.max(np.abs(trace[:, 28:30]), axis=1) > math.pi)
    return {
        'flower_reached': bool(trace[-1, 1] and trace[-1, 2] < 0),
        'alive_at_end': bool(trace[-1, 1]),
        'min_flower_gap_m': float(trace[:, 2].min()),
        'peak_body_vy_m_per_sim_s': float(trace[:, 6].max()),
        'end_sim_s': float(trace[-1, 0]),
        'first_brake_deflection_over_pi_sim_s': float(trace[crossed[0], 0]) if len(crossed) else None,
    }


def simulator_check(out, level, cases, probe, mos_bin):
    # Reuse simlines, changing only the translation to match physcmp's +300 m.
    code = (NES / 'test/simlines.py').read_text()
    code = code.replace("    print('// Generated", "    ox = oy = 300\n    print('// Generated", 1)
    converter = out / 'simlines300.py'
    converter.write_text(code)
    with (out / 'simlines.h').open('w') as f:
        command(sys.executable, converter, level, stdout=f)
    seeds = []
    for name, (state, brake) in cases.items():
        probe.lib.probe_init(state.ctypes.data_as(DP))
        path = out / (name + '-seed.inc')
        probe.lib.probe_seed(str(path).encode())
        ticks = math.ceil(brake/probe.h - 1e-10)
        seeds.append((name, path, ticks))
    source = '''#include <stdio.h>
#include <stdint.h>
#include "physics.h"
#include "simgrid.h"
extern bike_t RBike;
uint8_t rph_step(uint8_t);
static int trial(int brake_tick) {
 RBike=Bike;
 for(int step=0;step<172;step++) {
  uint8_t input=step<brake_tick?IN_GAS:IN_BRAKE;
  uint8_t a=ph_step(input),b=rph_step(input);
  const uint8_t* x=(const uint8_t*)&Bike;
  const uint8_t* y=(const uint8_t*)&RBike;
  for(unsigned i=0;i<sizeof(Bike);i++) if(x[i]!=y[i]) {
   printf("step %d byte %u: asm %02x C %02x\\n",step,i,x[i],y[i]);return 1;
  }
  if(a!=b) return 1;
  if(!a) break;
 }
 return 0;
}
int main(void) {
'''
    for name, path, ticks in seeds:
        source += f'#include "{path.name}"\nif(trial({ticks})) return 1;\nprintf("{name}: asm/C identical\\n");\n'
    source += 'return 0;\n}\n'
    (out / 'asm_hyflyer.c').write_text(source)
    cc = mos_bin / 'mos-sim-clang'
    includes = ['-I'+str(out), '-I'+str(NES/'src'), '-I'+str(NES/'test')]
    command(cc, '-O2', *includes, '-DBike=RBike', '-Dph_init=rph_init',
            '-Dph_step=rph_step', '-Dph_turn=rph_turn', '-c', '-o', out/'physics_c.o', NES/'src/physics.c')
    command(cc, '-O2', '-mlto-zp=24', *includes, '-o', out/'asm_hyflyer',
            out/'asm_hyflyer.c', out/'physics_c.o', NES/'src/physics.S', NES/'src/mul.s', NES/'src/fixmath.c')
    result = command(mos_bin/'mos-sim', out/'asm_hyflyer', capture_output=True, text=True)
    print(result.stdout, end='')
    (out/'asm-check.txt').write_text(result.stdout)
    return result.stdout.strip().splitlines()


def plot(out, lev, flower, traces, case):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), layout='constrained')
    colors = {'original_003': '#2166ac', 'nes_legacy': '#c43b35', 'nes_fixed': '#15915a'}
    labels = {'original_003': 'Original equations, <=3 ms', 'nes_legacy': 'NES before beta2', 'nes_fixed': 'NES 0.9 beta2'}
    for grass, pts in lev.polygons:
        if not grass:
            poly = pts + [pts[0]]
            axes[0].plot(*zip(*poly), color='#686868', lw=1)
    axes[0].scatter(*flower, marker='*', s=200, color='#b18000', zorder=4)
    for model in colors:
        r = traces[case][model]
        axes[0].plot(r[:, 3], r[:, 4], label=labels[model], color=colors[model])
        axes[1].plot(r[:, 0], r[:, 6], color=colors[model], label=labels[model])
        axes[2].plot(r[:, 0], np.degrees(r[:, 29]), color=colors[model])
        if r[-1, 1] and r[-1, 2] < 0:
            axes[0].scatter(r[-1, 3], r[-1, 4], marker='o', color=colors[model])
    axes[0].set(xlim=(-30.6, -22.5), ylim=(1.5, 10.5), xlabel='x (m)', ylabel='y (m)', title='Hi Flyer: body trajectory; star = flower')
    axes[0].set_aspect('equal')
    axes[1].axhline(0, color='#555', lw=.8)
    axes[1].set(xlabel='Simulation time (s)', ylabel='Body vertical velocity (m/s)', title='Positive = upward bounce')
    axes[1].legend(fontsize=8)
    axes[2].axhline(-180, color='#555', lw=.8, ls='--')
    axes[2].axhline(180, color='#555', lw=.8, ls='--')
    axes[2].set(xlabel='Simulation time (s)', ylabel='Front wheel brake deflection (degrees)', title='Before beta2: angle wraps at +/-180 degrees')
    for ax in axes:
        ax.grid(alpha=.2)
    fig.suptitle('Seeded final-section experiment; all apples assumed collected; traces stop at death / flower / time limit', fontsize=10)
    fig.savefig(out/'hyflyer-bounce.png', dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--res', type=Path, default=NES.parents[1]/'elma.res')
    parser.add_argument('--out', type=Path, default=NES/'build/hyflyer-check')
    parser.add_argument('--asm', action='store_true')
    parser.add_argument('--scan', action='store_true')
    parser.add_argument('--hz', type=int, choices=[50, 60], default=50)
    parser.add_argument('--tv', choices=['ntsc', 'pal'], default='ntsc')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    resource = Resource(args.res)
    if resource.shareware:
        parser.error('Use the registered resource containing the original Hi Flyer geometry')
    lev = internal_levels(resource)[6]
    if lev.name.lower() != 'hi flyer':
        raise ValueError('Internal level 7 is not Hi Flyer')
    flower = next((x, y) for kind, x, y, _ in lev.objects if kind == 1)
    lines = []
    for grass, pts in lev.polygons:
        if not grass:
            for a, b in zip(pts, pts[1:] + pts[:1]):
                lines.append((*a, b[0]-a[0], b[1]-a[1]))
    level = out/'level7.txt'
    level.write_text(f'{len(lines)} {lev.start()[0]} {lev.start()[1]}\n' +
                     ''.join(' '.join(map(str, line))+'\n' for line in lines))
    command(sys.executable, NES/'tools/physconst.py', out/'physconst.h', args.hz, args.tv)
    (out/'physics_legacy.c').write_text(legacy_source())
    probes = {}
    for name, src in [('nes', NES/'src/physics.c'), ('nes_legacy', out/'physics_legacy.c')]:
        library = out/(name+'.so')
        command(os.environ.get('HOSTCC', 'cc'), '-O2', '-shared', '-fPIC',
                '-I'+str(out), '-I'+str(NES/'src'), '-I'+str(NES/'test'),
                '-o', library, NES/'test/hyflyer_probe.c', NES/'test/refphys.c', src, NES/'src/fixmath.c', '-lm')
        probes[name] = Probe(library, level)
    # Locate the lower ramp by the flower rather than copying all geometry.
    left_to_right = [(x, y, dx, dy) if dx > 0 else (x+dx, y+dy, -dx, -dy)
                     for x, y, dx, dy in lines]
    candidates = [l for l in left_to_right if l[2] > 0 and l[3] < 0 and l[0] < flower[0] and l[1] < flower[1]+2]
    x, y, dx, dy = min(candidates, key=lambda l: abs(l[0]+30.294))
    angle = math.atan2(dy, dx)
    normal = np.array([-math.sin(angle), math.cos(angle)])
    ramp_point = np.array([-28.0, y+dy/dx*(-28-x)])
    cases = {
        'wall20': (state_at(x+1.2, 10, -math.pi/2, 0, -20), .25),
        'wall15': (state_at(x+1.0, 10, -math.pi/2, 0, -15), .30),
        'ramp20': (state_at(*(ramp_point+normal*1.05), angle, 0, -20), 0),
        'ramp25': (state_at(*(ramp_point+normal*1.05), angle, 0, -25), 0),
    }
    configurations = {
        'original_003': ('nes', 0, .003, 1.0),
        'original_0055': ('nes', 0, .0055, 1.0),
        'float_nes_timestep_and_damping': ('nes', 0, probes['nes'].h, .7*args.hz/60),
        'nes_legacy': ('nes_legacy', 1, probes['nes'].h, 1.0),
        'nes_fixed': ('nes', 1, probes['nes'].h, 1.0),
    }
    traces, measurements = {}, {}
    fields = ['sim_s', 'alive', 'flower_gap_m']
    for part in ['body', 'wheel0', 'wheel1']:
        fields += [part+'_'+key for key in ['x','y','vx','vy','angle','omega']]
    fields += ['rider_x','rider_y','rider_vx','rider_vy','head_x','head_y','turned','brake_angle0','brake_angle1']
    for name, (state, brake) in cases.items():
        traces[name], measurements[name] = {}, {}
        for model, (which, fixed, cap, damping) in configurations.items():
            r = probes[which].run(state, flower, brake, fixed, cap, damping)
            traces[name][model] = r
            measurements[name][model] = metrics(r)
            np.savetxt(out/(name+'-'+model+'.csv'), r, delimiter=',', header=','.join(fields), comments='')
            print(f'{name:8} {model:32} flower={metrics(r)["flower_reached"]!s:5} '
                  f'peak_vy={r[:,6].max():7.3f} gap={r[:,2].min():7.3f}')
    # Regression fixtures: the fixed implementation must reach the flower.
    # At 60 Hz even the legacy wall20 trajectory grazes it; wall15 and
    # ramp25 still reproduce the missing bounce at both supported rates.
    for name in ['wall15', 'wall20', 'ramp25']:
        assert measurements[name]['original_003']['flower_reached'], name
        assert measurements[name]['original_0055']['flower_reached'], name
        assert measurements[name]['nes_fixed']['flower_reached'], name
    for name in ['wall15', 'ramp25'] + (['wall20'] if args.hz == 50 else []):
        assert not measurements[name]['nes_legacy']['flower_reached'], name
    report = {
        'level': lev.name, 'physics_h': probes['nes'].h, 'hz': args.hz, 'tv': args.tv,
        'scope': 'Seeded final section, original polygon segments, all apples assumed collected; not a full ROM playthrough.',
        'reference': 'refphys.c, original brake damping restored; integration capped at 0.003 or 0.0055 s, synchronized control ticks.',
        'flower_test': 'Common continuous geometry; wheel+flower radius 0.8 m, head+flower 0.638 m; stops on first touch or death.',
        'cases': {n: {'state': q.tolist(), 'requested_brake_sim_s': b,
                      'actual_brake_sim_s': math.ceil(b/probes['nes'].h-1e-10)*probes['nes'].h}
                  for n, (q, b) in cases.items()},
        'measurements': measurements,
    }
    if args.scan:
        scan = []
        for speed in [5, 10, 15, 20]:
            for gap in [0, .05, .2]:
                state = state_at(x+1+gap, 10, -math.pi/2, 0, -speed)
                for brake in np.arange(.05, .801, .025):
                    row = {'speed': speed, 'wall_gap': gap, 'brake': float(brake)}
                    for model in ['original_003', 'nes_legacy', 'nes_fixed']:
                        which, fixed, cap, damping = configurations[model]
                        row[model] = metrics(probes[which].run(state, flower, float(brake), fixed, cap, damping))
                    scan.append(row)
        (out/'scan.json').write_text(json.dumps(scan, indent=2)+'\n')
        report['scan_flower_hits'] = {m: sum(row[m]['flower_reached'] for row in scan)
                                    for m in ['original_003', 'nes_legacy', 'nes_fixed']}
        report['scan_cases'] = len(scan)
        print('Seeded parameter scan:', report['scan_cases'], report['scan_flower_hits'])
    if args.asm:
        sdk = os.environ.get('LLVM_MOS')
        found = shutil.which('mos-sim-clang')
        mos_bin = Path(sdk)/'bin' if sdk else Path(found).parent if found else Path.home()/'.local/share/llvm-mos/bin'
        report['asm_check'] = simulator_check(out, level, cases, probes['nes'], mos_bin)
    (out/'results.json').write_text(json.dumps(report, indent=2)+'\n')
    plot(out, lev, flower, traces, 'wall20')
    print('Results:', out)


if __name__ == '__main__':
    main()
