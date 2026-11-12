"""Read the original coefficients. Fail if the source stops matching this kernel."""
import hashlib
import json
from pathlib import Path
import re
import random
import sys

ROOT = Path(__file__).resolve().parents[3]


def generate(out):
    data = (ROOT / 'src/ADATOK.CPP').read_text()
    def number(pattern):
        m = re.search(pattern, data, re.M)
        if m is None:
            raise ValueError('Original physics definition not found: '+pattern)
        return float(m[1])
    spring = number(r'^\s*Drsugar\s*=\s*([\d.]+)\s*;')
    assert spring == number(r'^\s*Drtang\s*=\s*([\d.]+)\s*;'), 'Anisotropic spring requires a new kernel'
    damping = number(r'^\s*Sr\s*=\s*([\d.]+)\s*;')
    body_mass = number(r'^\s*pmot->kor1.m\s*=\s*([\d.]+)\s*;')
    wheel_mass = number(r'^\s*pmot->kor2.m\s*=\s*([\d.]+)\s*;')
    assert wheel_mass == number(r'^\s*pmot->kor4.m\s*=\s*([\d.]+)\s*;')
    m = re.search(r'^\s*pmot->kor1.theta\s*=\s*([\d.]+)\*([\d.]+)\*([\d.]+);', data, re.M)
    if not m:
        raise ValueError('Body inertia definition changed')
    inertia = float(m[1])*float(m[2])*float(m[3])
    # 182 ticks/s and 0.0024 are the original CLOCK conversion. The solver
    # uses steps up to 0.0055, plus a shorter remainder at each render target.
    # Keep a small diagnostic interval here; it is not the final scheduler.
    clock = (ROOT/'src/LEJATSZO.CPP').read_text()
    assert '182.0*0.0024' in clock, 'Recheck the original physics clock'
    match = re.search(r'^\s*double dt\s*=\s*([\d.]+)\s*;',clock,re.M)
    if match is None:
        raise ValueError('Original integration step cap not found')
    original_step_cap=float(match[1])
    dt = .0024
    factors = {'SPRING_W':spring*dt/wheel_mass, 'DAMPING_W':damping*dt/wheel_mass,
               'SPRING_B':spring*dt/body_mass, 'DAMPING_B':damping*dt/body_mass,
               'WHEEL_MASS_OVER_INERTIA':wheel_mass/inertia}
    out = Path(out)
    out.mkdir(parents=True,exist_ok=True)
    (out/'physics_constants.h').write_text('/* Generated from original physics, Q12 coefficients. */\n'
        + '\n'.join('#define %s %d' % (k,round(v*4096)) for k,v in factors.items())+'\n')
    report = dict(spring=spring,damping=damping,body_mass=body_mass,wheel_mass=wheel_mass,
                  inertia=inertia,dt=dt,interval_role='diagnostic, not original fixed-step scheduling',
                  original_clock_ticks_hz=182,original_clock_scale=.0024,
                  original_step_cap=original_step_cap,coefficient_bits=12,
                  source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                      for name in ('src/ADATOK.CPP','src/LEPTET.CPP','src/LEJATSZO.CPP')})
    (out/'physics-reference.json').write_text(json.dumps(report,indent=2)+'\n')
    rng = random.Random(182)
    edges = [-32768,-32767,-1024,-1,0,1,1024,32767]
    vectors = [(x,y) for x in edges for y in edges]
    vectors += [(rng.randint(-32768,32767),rng.randint(-32768,32767)) for _ in range(192)]
    (out/'mul_vectors.h').write_text(
        'typedef struct { int16_t a,b; int32_t product; } mul_vector_t;\n'
        '#define MUL_VECTOR_COUNT 256\nconst mul_vector_t mul_vectors[] = {\n'
        + ',\n'.join('{%d,%d,%dL}' % (x,y,x*y) for x,y in vectors)+'\n};\n')


if __name__=='__main__':
    generate(sys.argv[1])
