"""Writes riding_constants.h, the constants of the physics as integers, for
the Game Boy Color clock, adapted from the existing NES constant converter.

  riding_constants.py OUT [HZ [explicit|exponential]]

A constant c multiplies as KMUL: c = M/2^E with M of 8 bits (128..255),
which takes a multiplication of 16 by 8 bits.
"""

import math
import sys

HZ = int(sys.argv[2]) if len(sys.argv) > 2 else 30
TV = 'gbc'
DAMPER = sys.argv[3] if len(sys.argv) > 3 else 'explicit'
if DAMPER not in ('explicit', 'exponential'):
    raise ValueError('damper must be explicit or exponential')
# Frames counted as a second, and the frames of a second of the clock:
FPS, FRAME_RATE = {'gbc': (60, 4194304.0 / 70224.0)}[TV]
RATE = FRAME_RATE * HZ / FPS  # steps a second
# A step is this much of the game's time, which runs 0.4368 times as fast
# as the clock (182 ticks a second times 0.0024):
H = 0.4368 / RATE
S = 262144.0                  # F per m
ANGLE_UNITS = 8388608 if HZ < 40 else 16777216
ANGLE_SHIFT = 7 if HZ < 40 else 8
AN = ANGLE_UNITS / (2 * math.pi)  # angle units per radian
VS = S * H / 4                # velocity units per m/s (4 F per step)
WS = AN * H / 128             # angular velocity units per rad/s
# The damping of the brake, taken 0.7 times at 60 steps (see BRAKE_W), and
# less with longer steps, the same in a step:
BRAKE_DAMPING = 0.7 * HZ / 60
# Exact velocity impulse of the isolated physical wheel/body damper over H,
# instead of forward Euler's Sr*H/m. The same impulse ratio is applied to
# its body reaction and body torque. K, Sr and the masses are not retuned.
DAMPER_Z = 1000.0 * H / 10.0
DAMPER_RATIO = -math.expm1(-DAMPER_Z) / DAMPER_Z if DAMPER == 'exponential' else 1.0

# name: (value, comment)
FACTORS = [
    ('K_X', 0.85 * 1024 / 16384,
     'the right wheel relative to the body, (0.85, -0.6) m, times cos and sin into u'),
    ('K_Y', 0.6 * 1024 / 16384, ''),
    ('SPRING_W', 1000 * H * VS / 16384,
     'wheel spring: K = 10000 N/m, wheel 10 kg; its length in r16'),
    ('SPRING_B', 50 * H * VS / 16384, 'the same on the body of 200 kg'),
    ('SPRING_T', 10000 / 60.5 * H * WS / (1024 * 16384) * 1024,
     'its torque on the body (moment of inertia 200*0.55^2), from the sum '
     'of lever arm (u) x length (r16) >> 10'),
    ('FRIC_W', 100 * H, 'damping between the wheels and the body: Sr = 1000 Ns/m'),
    ('FRIC_B', 5 * H, ''),
    ('FRIC_T', 1000 / 60.5 * H * WS / (1024 * VS) * 1024,
     'its torque, from the sum of lever arm (u) x velocity >> 10'),
    ('OMS', VS / WS / 1024 * 16384 / 16,
     'the body angular velocity, for mulq14 with a lever arm << 4 (u)'),
    ('REACT', H * VS * 1024 / (4 * 10) / 256,
     'force of a wheel torque on the axle'),
    ('TWENTIETH', 1 / 20, ''),
    ('BRAKE_A', 4000 * 2 * math.pi / (ANGLE_UNITS / 256), 'brake: 1000 Nm/rad'),
    ('BRAKE_W', 400 * BRAKE_DAMPING / WS,
     'and 100 Nms/rad, taken 0.7 times, so that a free wheel does not swing '
     'ever wider with a step this long (the game steps 0.003 s)'),
    ('FREE', 0.25 / 0.32 * H * WS, 'a free wheel turning (moment of inertia 0.32)'),
    ('ROLL_W', WS / (VS * 0.4),
     'a wheel rolling around a contact point (moment of inertia 0.32 + 10*0.3975^2 there)'),
    ('ROLL_T', 4 * 10 * 0.4 / (H * VS), ''),
    ('ROLL_DW', 0.25 / (0.32 + 10 * 0.3975 ** 2) * H * WS, ''),
    ('ROLL_V', 0.4 * VS / WS, ''),
    ('NEW', WS / (1024 * VS) * 1024, ''),
    ('OLD', 4 * 10 / (1024 * H * VS) * 64, ''),
    ('RREST', 0.44, 'the rider: rest 0.44 m above the body, updated every step'),
    ('RIDER_S', 250 * H * VS / 16384, 'its spring, 5 times as strong'),
    ('RIDER_F', 15 * H, 'its damping, 3 times as strong'),
    ('SEAT_NX', 0.23 / 0.54129474, 'the normal of the seat (-0.42, 0.91)'),
    ('SEAT_NY', 0.49 / 0.54129474, ''),
    ('ELLIPSE', 0.48 / 0.26, ''),
    ('H_X', 0.09 * 1024 / 16384, 'the head relative to the rider, (0.09, 0.63) m'),
    ('H_Y', 0.63 * 1024 / 16384, ''),
]
FACTORS = [(name, value * DAMPER_RATIO if name in ('FRIC_W', 'FRIC_B', 'FRIC_T') else value, comment)
           for name, value, comment in FACTORS]

def u(m):
    return int(round(m * 1024))

INTEGERS = [
    ('R_WHEEL', u(0.4), 'sizes in u (1 m = 1024)'),
    ('R_HEAD', u(0.238), ''),
    ('BAND', u(0.005), 'the wheel is kept this much inside the ground (Belsosav)'),
    ('MERGE', u(0.1), 'contact points closer are merged (Talppontegybeolvadasitav)'),
    ('G_INT', int(10 * H * VS), 'gravity in a step, with its fraction in 1/256'),
    ('G_FRAC', int(round((10 * H * VS - int(10 * H * VS)) * 256)), ''),
    ('LOKET', int(12 * WS + 0.5), 'a volt (Loket) and what is left of it (Omegavalt)'),
    ('OMEGAVALT', int(3 * WS + 0.5), ''),
    ('VOLT_STEPS', int(0.1 / H + 1), 'a volt lasts 0.1 s (Ugroturelem*0.25)'),
    ('WHEEL_MAXW', int(110 * WS), 'highest angular velocity of the driven wheel'),
    ('ELSZ', int(0.01 * VS + 0.5), 'separation speed limit, 0.01 m/s'),
    ('VEL_1MS', int(VS + 0.5), '1 m/s'),
    ('GAS_TQ', 600 * 4, 'gas: 600 Nm, in 1/4 Nm'),
    ('F_BODY_X', int(0.85 * S), 'the bike at the start, from its left wheel, in F'),
    ('F_BODY_Y', int(0.6 * S), ''),
    ('F_WHEELBASE', int(1.7 * S), ''),
    ('F_RIDER_Y', int(1.04 * S), ''),
    ('F_HEAD_Y', int(0.63 * S), ''),
    ('SEAT_X', u(-0.35), 'where the rider may be relative to the body'),
    ('SEAT_Y', u(0.13), ''),
    ('RIDER_TOP', u(0.48), ''),
    ('RIDER_LEFT', u(-0.5), ''),
    ('RIDER_RIGHT', u(0.26), ''),
]


def factor(c):
    """M and E of c = M/2^E, M of 8 bits; E from 1 to 16."""
    e = 0
    while c * (1 << e) < 127.5:
        e += 1
    while c * (1 << e) >= 255.5:
        e -= 1
    m = int(round(c * (1 << e)))
    if not 1 <= e <= 16:
        raise ValueError(c)
    return m, e


def main():
    lines = ['// Generated by tools/riding_constants.py: the constants of the GBC physics.',
             '#ifndef PHYSCONST_H', '#define PHYSCONST_H', '',
             '// Frames counted as a second (%s), the steps in them, and in a second:' % TV.upper(),
             '#define PH_FPS %d' % FPS,
             '#define PH_HZ %d' % HZ,
             '#define PH_RATE %r' % RATE,
             '#define RIDING_ANGLE_UNITS %dL' % ANGLE_UNITS,
             '#define RIDING_ANGLE_SHIFT %d' % ANGLE_SHIFT,
             '#define RIDING_EXPONENTIAL_DAMPER %d' % (DAMPER == 'exponential'),
             '// Physical Sr=1000 Ns/m, wheel mass=10 kg; damper impulse ratio %.17g' % DAMPER_RATIO, '']
    for name, v, comment in INTEGERS:
        if comment:
            lines.append('// ' + comment + ':')
        lines.append('#define %s %d' % (name, v))
    lines.append('')
    lines.append('// Factors c as M/2^E:')
    for name, c, comment in FACTORS:
        m, e = factor(c)
        if comment:
            lines.append('// ' + comment + ':')
        lines.append('#define C_%s_M %d' % (name, m))
        lines.append('#define C_%s_E %d' % (name, e))
    # The SNES rider also rejects guaranteed-inside seat/ellipse regions
    # before products. Derive this kernel's bounds from its rounded factors.
    iv = {name:value for name,value,comment in INTEGERS}
    fv = {name:factor(value) for name,value,comment in FACTORS}
    def scaled(value, name):
        m,e = fv[name]
        return max(-32768,min(32767,(value*m+(1<<(e-1)))>>e))
    top,right = iv['RIDER_TOP'],iv['RIDER_RIGHT']
    seat_x,seat_y = right//2,top*4//5
    sx,sy = iv['SEAT_X'],iv['SEAT_Y']
    seat_valid = (-32768 <= -32768-sx and seat_x-sx <= 32767
                  and -32768 <= seat_y-sy and top-sy <= 32767)
    if seat_valid:
        low = scaled(seat_y-sy,'SEAT_NY')-scaled(seat_x-sx,'SEAT_NX')
        high = scaled(top-sy,'SEAT_NY')-scaled(-32768-sx,'SEAT_NX')
        seat_valid = 0 <= low <= high <= 32767
    ellipse_y = []
    for i in range((right>>3)+1):
        x = min(right,(i+1)*8-1)
        xs = scaled(x,'ELLIPSE')
        ellipse_y.append(math.isqrt(max(0,top*top-xs*xs)))
    lines += ['', '// Exact conservative rider rejection bounds:',
              '#define RIDING_SEAT_FAST_ENABLED %d' % seat_valid,
              '#define RIDING_SEAT_FAST_X %d' % seat_x,
              '#define RIDING_SEAT_FAST_Y %d' % seat_y,
              '#define RIDING_ELLIPSE_BUCKET_SHIFT 3',
              '#define RIDING_ELLIPSE_INSIDE_Y_VALUES '+','.join(map(str,ellipse_y))]
    lines += ['', '#endif', '']
    with open(sys.argv[1], 'w') as f:
        f.write('\n'.join(lines))


if __name__ == '__main__':
    main()
