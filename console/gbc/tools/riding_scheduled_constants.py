"""Generate the original-PC substep schedule with independently scaled velocities.

The physical formulas are shared with riding_constants; only step duration,
velocity storage units, and quantization differ. Q24 coefficients are rounded
once from those formulas, including the combined direct rolling impulse.
"""
import json
import math
from pathlib import Path
import re

from riding_constants import parameters, render_header

OUTER_HZ = 30
RATE = 4194304 / 70224 / 2
FRAME_TIME = .4368 / RATE
VELOCITY_TIME = .352
ANGULAR_TIME = .022
SUBSTEPS = (.0055, .0055, FRAME_TIME - .011)
Q24 = 1 << 24


def q24(value):
    """Round to nearest, with positive half-ties, as the runtime products do."""
    return math.floor(value * Q24 + .5)


def volt_steps():
    # A volt starts at the first substep of an outer frame. Count until the
    # first subsequent substep whose start is strictly past 0.1 game seconds.
    elapsed, count = 0., 0
    while elapsed <= .1:
        elapsed += SUBSTEPS[count % len(SUBSTEPS)]
        count += 1
    return count


def coefficients():
    configs = [parameters(OUTER_HZ, step_time=dt,
                          velocity_time=VELOCITY_TIME, angular_time=ANGULAR_TIME,
                          scheduled=True) for dt in (SUBSTEPS[0], SUBSTEPS[2])]
    factors = [{f'C_{name}': value for name, value, _ in c['FACTORS']}
               for c in configs]
    # Fine F displacements are sixteen times the legacy r16 spring input.
    # Rolling linear velocity is integrated directly, avoiding a rounded
    # angular-velocity round trip. Combine the real factors before rounding.
    for f in factors:
        f['C_SPRING_FW'] = f['C_SPRING_W'] / 16
        f['C_ROLL_DV'] = f['C_ROLL_DW'] * f['C_ROLL_V']
    return configs, {name: [q24(f[name]) for f in factors] for name in factors[0]}


def metadata():
    return {
        'profile': 'scheduled', 'outer_game_seconds': FRAME_TIME,
        'substep_game_seconds': list(SUBSTEPS),
        'velocity_unit_time': VELOCITY_TIME, 'angular_unit_time': ANGULAR_TIME,
        'velocity_units_per_m_per_s': 262144 * VELOCITY_TIME / 4,
        'angular_velocity_units_per_rad_per_s': 8388608 / (2 * math.pi) * ANGULAR_TIME / 128,
        'coefficient_fraction_bits': 24,
        'geometry_units_per_m': 1024, 'position_units_per_m': 262144,
        'contact_onset_position_units': round(.4 * 262144),
        'contact_pushout_position_units': round(.395 * 262144),
        'geometry_subdivision_endpoint_flags': {'internal_start': 0x4000, 'internal_end': 0x8000},
    }


def render():
    configs, quantized = coefficients()
    headers = [render_header(c, max_exponent=32) for c in configs]
    defines = [dict(re.findall(r'^#define (\w+) ([^\n]+)$', h, re.M)) for h in headers]
    header = headers[0]
    arrays = ['#include <stdint.h>', 'extern uint8_t riding_subphase;',
              'extern int32_t move_residual[8];']
    # Keep the legacy M/E contract available to compile guards and unused
    # shared kernels. Scheduled physical products use the full Q24 values.
    for name, value in defines[0].items():
        if name == 'VOLT_STEPS':
            header = header.replace(f'#define {name} {value}', f'#define {name} {volt_steps()}')
        elif name in defines[1] and value != defines[1][name]:
            header = header.replace(f'#define {name} {value}', f'#define {name} phase_{name}[riding_subphase]')
            arrays.append(f'static const int32_t phase_{name}[2]={{{value},{defines[1][name]}}};')
    arrays += ['#ifndef __SDCC']
    arrays += [f'static const int32_t q24_{name}[2]={{{pair[0]},{pair[1]}}};'
               for name, pair in quantized.items()]
    linear = [q24(dt / VELOCITY_TIME) for dt in (SUBSTEPS[0], SUBSTEPS[2])]
    angular = q24(SUBSTEPS[2] / ANGULAR_TIME)
    arrays += [f'''static int32_t qmul32(int32_t x,int32_t m) {{
 int64_t v=((int64_t)x*m+(1L<<23))>>24;
 return v>INT32_MAX?INT32_MAX:v<INT32_MIN?INT32_MIN:(int32_t)v;
}}
static int32_t qround20(int64_t x) {{
 const int64_t d=20LL<<24;x+=d/2;
 return x>=0?(int32_t)(x/d):-(int32_t)((-x+d-1)/d);
}}
static int32_t phase_advance(int32_t v,uint8_t shift,uint8_t slot) {{
 int64_t total=(int64_t)v*(1L<<shift)*(riding_subphase?{linear[1]}:{linear[0]})+move_residual[slot];
 int32_t result=(int32_t)((total+(1L<<23))>>24);
 move_residual[slot]=(int32_t)(total-(int64_t)result*(1L<<24));return result;
}}
static int32_t phase_move(int32_t v,uint8_t shift) {{
 return riding_subphase?(int32_t)(((int64_t)v*(1L<<shift)*{angular}+(1L<<23))>>24):v*(1L<<shift)/4;
}}
#else
/* Native definitions use the same coefficients through banked Q24 tables. */
int32_t qround20(int64_t x);
int32_t phase_advance(int32_t v,uint8_t shift,uint8_t slot);
int32_t phase_move(int32_t v,uint8_t shift);
#endif''']
    header = header.replace('#define PHYSCONST_H', '#define PHYSCONST_H\n' + '\n'.join(arrays), 1)
    header = header.replace('#define PH_RATE ' + defines[0]['PH_RATE'], '\n'.join([
        f'#define PH_RATE {RATE!r}', '#define RIDING_PC_SCHEDULE 1',
        f'#define PH_VELOCITY_UNIT_TIME {VELOCITY_TIME!r}',
        f'#define PH_ANGULAR_UNIT_TIME {ANGULAR_TIME!r}',
        f'#define PH_FRAME_TIME {FRAME_TIME!r}',
        f'#define PH_SUBSTEP_TIME {SUBSTEPS[0]!r}',
        f'#define PH_REMAINDER_TIME {SUBSTEPS[2]!r}']))
    header = header.replace('// Generated by tools/riding_constants.py:',
                            '// Generated by tools/riding_scheduled_constants.py:')
    # The shared formula's explanatory text refers to its legacy brake scale.
    header = header.replace('// and 100 Nms/rad, taken 0.7 times, so that a free wheel does not swing ever wider with a step this long (the game steps 0.003 s):',
                            '// and the original 100 Nms/rad damper at every scheduled substep:')
    return header, quantized


def write_outputs(path, hz=OUTER_HZ):
    if hz != OUTER_HZ:
        raise ValueError('scheduled profile requires 30 Hz outer frames')
    path = Path(path)
    header, quantized = render()
    path.write_text(header)
    path.with_name('q24-coefficients.json').write_text(json.dumps(quantized, indent=2) + '\n')


if __name__ == '__main__':
    import sys
    write_outputs(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else OUTER_HZ)
