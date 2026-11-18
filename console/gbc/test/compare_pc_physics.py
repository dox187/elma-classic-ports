#!/usr/bin/env python3
"""Compare timed original-PC/GBC HOST trajectories without a fidelity score.

The PC library links the six original physics translation units and
their real headers through the existing PS3 fixture. Its native-double math is
the SDL profile, not a bit-identical reconstruction of the Windows x87 binary.
LEJATSZO.CPP advances a variable frame target with dt <= .0055; it does not run
physics at a fixed 182 Hz. Here each target is one actual GBC physics interval,
with identical held controls throughout its capped PC substeps.

All positions are world meters with Y up. Reported GBC positions are public
poses (including the baseline's half-step rider interpolation), velocities are
internal state converted to m/game-second. Stored future rider position is
never compared to the PC's current rider position. Initial internal positions
and velocities are seeded into the PC once, before simulation starts.

Example:
  python3 console/gbc/test/compare_pc_physics.py --res build-reg/elma.res \
    --baseline-ref 17c1493

The importable build_pc, build_host, Gbc, Pc, and compare_case APIs support
coefficient experiments. Build outputs and resource-derived levels stay in
the ignored output directory. Optional HOST-only source copies observe resolved
wheel contacts without changing numeric computations or production sources.
"""
import argparse
import ctypes as C
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[1]
DEFAULT_OUT = BASE / 'build/pc-comparison-v090'
GBC_SOURCES = ('physics.c', 'physics_core.c', 'physics_contacts.c',
               'physics_math.c', 'physics_math32.c', 'physics_collision.c',
               'physics_sweep.c')
PC_SOURCES = ('LEPTET', 'BEALLIT', 'UTKOZES', 'UTKOZES2', 'SZAKASZ', 'VEKT2')
PARTS = ('body', 'wheel0', 'wheel1', 'rider', 'head')
CONTACT_SCHEMA = 'resolved-wheel-contacts-v1'
sys.path.insert(0, str(ROOT / 'console/snes/tools'))
from elmadata import Resource, internal_levels, Level  # noqa: E402


class Pose(C.Structure):
    _fields_ = [('x', C.c_int32), ('y', C.c_int32), ('angle', C.c_uint16)]


class Public(C.Structure):
    _fields_ = [('body', Pose), ('wheel', Pose * 2), ('rider', Pose),
                ('head', Pose), ('alive', C.c_uint8), ('turned', C.c_uint8)]


class Circle(C.Structure):
    _fields_ = [('rx', C.c_int32), ('ry', C.c_int32), ('vx', C.c_int32),
                ('vy', C.c_int32), ('alfa', C.c_uint32), ('omega', C.c_int16)]


class Bike(C.Structure):
    _fields_ = [('body', Circle), ('wheel', Circle * 2),
                ('rider_x', C.c_int32), ('rider_y', C.c_int32),
                ('rider_vx', C.c_int32), ('rider_vy', C.c_int32),
                ('head_x', C.c_int32), ('head_y', C.c_int32),
                ('turned', C.c_uint8), ('gravity', C.c_uint8),
                ('brake_was', C.c_uint8), ('steps', C.c_uint8),
                ('gfrac', C.c_uint8), ('dbrake', C.c_uint32 * 2),
                ('volt', C.c_uint8 * 2), ('volt_omega', C.c_int16 * 2)]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(command, log):
    result = subprocess.run(list(map(str, command)), capture_output=True, text=True)
    Path(log).write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f'{command[0]} failed; see {log}\n{result.stderr[-8000:]}')


def contact_copy(original, destination, anchor, declaration, observation):
    """Fail closed if the final resolved-contact hook no longer matches once."""
    raw = Path(original).read_bytes()
    needle = anchor.encode()
    if raw.count(needle) != 1:
        raise ValueError(f'Expected exactly one resolved-contact hook in {original}')
    destination = Path(destination)
    destination.write_bytes(declaration.encode() + raw.replace(needle, observation.encode() + needle))
    return {'schema': CONTACT_SCHEMA, 'observational_only': True,
            'original_source': str(Path(original).resolve()), 'compiled_source': str(destination),
            'original_source_sha256': sha256(original), 'compiled_source_sha256': sha256(destination)}


HOST_CONTACT_WRAPPER = r'''
#include <stdlib.h>
static int contact_modes[2] = {-1,-1}, contact_observations[2];
static int contact_changes[6][3], contact_change_count, contact_frame_calls[2];
static double contact_times[6];
int fixture_contact_version(void) {
#ifdef COMPARE_CONTACTS
    return 1;
#else
    return 0;
#endif
}
void fixture_contact_reset(void) {
    int i; for(i=0;i<2;++i) { contact_modes[i]=-1; contact_observations[i]=0; }
    contact_change_count=0;
}
void fixture_contact_begin(void) {
    contact_change_count=0;contact_frame_calls[0]=contact_frame_calls[1]=0;
}
void fixture_observe_contact(const void* circle, int count) {
    int wheel=circle==&Bike.wheel[0]?0:circle==&Bike.wheel[1]?1:-1;
    if(wheel<0 || count<0 || count>2) abort();
    ++contact_observations[wheel];
    ++contact_frame_calls[wheel];
    if(contact_modes[wheel]!=count) {
        if(contact_change_count>=6) abort();
#ifdef RIDING_PC_SCHEDULE
        contact_times[contact_change_count]=contact_frame_calls[wheel]<3 ?
            contact_frame_calls[wheel]*0.0055 : PH_H;
#else
        contact_times[contact_change_count]=PH_H;
#endif
        contact_changes[contact_change_count][0]=wheel;
        contact_changes[contact_change_count][1]=contact_modes[wheel];
        contact_changes[contact_change_count++][2]=count;
        contact_modes[wheel]=count;
    }
}
void fixture_contact_state(int* modes,int* observations) {
    int i; for(i=0;i<2;++i) { modes[i]=contact_modes[i]; observations[i]=contact_observations[i]; }
}
int fixture_contact_count(void) { return contact_change_count; }
void fixture_contact_event(int index,int* values) {
    int i; if(index<0 || index>=contact_change_count) abort();
    for(i=0;i<3;++i) values[i]=contact_changes[index][i];
}
double fixture_contact_time(int index) {
    if(index<0 || index>=contact_change_count)abort();
    return contact_times[index];
}
'''


def build_host(out, gen=BASE / 'build/gen', source=BASE / 'src', name='candidate-host', contacts=False):
    """Build the real GBC HOST core; source/gen may be immutable snapshots."""
    out, gen, source = Path(out).resolve(), Path(gen).resolve(), Path(source).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if contacts: name += '-contacts-v1'
    wrapper = out / (name + '.c')
    wrapper.write_text('#include "physics_core.h"\n#include "runtime.h"\n'
                       'uint16_t fixture_internal_size(void){return sizeof(Bike);}\n'
                       'uint16_t fixture_public_size(void){return sizeof(gbc_bike);}\n' +
                       (HOST_CONTACT_WRAPPER if contacts else ''))
    sources = [source / s for s in GBC_SOURCES]
    for optional in ('physics_q24.c','physics_force.c'):
        if (source/optional).is_file():sources.append(source/optional)
    instrumentation = None
    if contacts:
        original = source/'physics_contacts.c'; copied = out/(name+'-physics_contacts.c')
        instrumentation = contact_copy(original, copied, '\tif( n == 0 ) {',
            'extern void fixture_observe_contact(const void*, int);\n',
            '\tfixture_observe_contact(k, n);\n')
        sources[sources.index(original)] = copied
    sources += [gen / 'physics_level_data.c'] + sorted(gen.glob('physics_bank_*.c'))
    library = out / (name + ('.dylib' if sys.platform == 'darwin' else '.so'))
    command = ['cc', '-shared', '-fPIC', '-O0', '-fwrapv', '-Wno-unknown-pragmas',
               '-I' + str(source), '-I' + str(gen),
               *(['-DCOMPARE_CONTACTS=1'] if contacts else []), wrapper, *sources, '-o', library]
    run(command, out / (name + '-compile.log'))
    inputs = [wrapper, *sources, *source.glob('*.h'), *gen.glob('*.h')]
    (out / (name + '-build.json')).write_text(json.dumps({
        'compile_command': list(map(str, command)), 'library_sha256': sha256(library),
        'input_sha256': {str(p): sha256(p) for p in inputs},
        'contact_instrumentation': instrumentation}, indent=2) + '\n')
    return library


def build_pc(out, contacts=False):
    out = Path(out).resolve(); out.mkdir(parents=True, exist_ok=True)
    forwards = out / 'lowercase_headers'; forwards.mkdir(exist_ok=True)
    for header in (ROOT / 'src').glob('*.H'):
        (forwards / header.name.lower()).write_text(f'#include "{header}"\n')
    name = 'pc-reference' + ('-contacts-v1' if contacts else '')
    library = out / (name + ('.dylib' if sys.platform == 'darwin' else '.so'))
    sources = [Path(__file__).with_name('pc_physics_adapter.cpp')]
    sources += [ROOT / 'src' / (s + '.CPP') for s in PC_SOURCES]
    instrumentation = None
    if contacts:
        original = ROOT/'src/BEALLIT.CPP'; copied = out/(name+'-BEALLIT.CPP')
        instrumentation = contact_copy(original, copied, '\tif( talppontszam == 0 ) {',
            'extern "C" void compare_pc_observe_contact(const void*, int);\n',
            '\tif( kelltalppont ) compare_pc_observe_contact(pk, talppontszam);\n')
        sources[sources.index(original)] = copied
    command = ['c++', '-shared', '-fPIC', '-std=gnu++11', '-O2', '-w',
               '-fpermissive', '-fsigned-char', '-fwrapv', '-fno-strict-aliasing',
               '-ffp-contract=off', '-I' + str(ROOT / 'src'),
               '-I' + str(ROOT / 'desktop'), '-I' + str(forwards),
               *(['-DCOMPARE_CONTACTS=1'] if contacts else []), *sources, '-o', library]
    run(command, out / (name + '-compile.log'))
    inputs = sources + list((ROOT / 'src').glob('*.H'))
    inputs += [ROOT / 'console/ps3/test/physics_trace.cpp']
    (out / (name + '-build.json')).write_text(json.dumps({
        'math_profile': 'native double; no ELMA_CLASSIC_X87',
        'compile_command': list(map(str, command)), 'library_sha256': sha256(library),
        'input_sha256': {str(p): sha256(p) for p in inputs},
        'contact_instrumentation': instrumentation}, indent=2) + '\n')
    return library


def freeze_baseline(out, revision, gen, contacts=False, resource=None):
    """Rebuild a Git baseline with that revision's own constants generator."""
    out = Path(out).resolve(); snapshot = out/'baseline-source'
    library = out/('baseline-host.dylib' if sys.platform=='darwin' else 'baseline-host.so')
    revision=subprocess.check_output(['git','rev-parse',revision],cwd=ROOT,text=True).strip()
    metadata=out/'baseline-revision.json'
    if library.exists() and metadata.exists():
        frozen=json.loads(metadata.read_text())
        if frozen['git_revision']!=revision or frozen['library_sha256']!=sha256(library):
            raise ValueError(f'Frozen baseline provenance does not match {revision}: {out}')
        for name,digest in frozen['source_sha256'].items():
            if sha256(snapshot/name)!=digest:raise ValueError(f'Frozen source changed: {name}')
        if sha256(out/'baseline-gen/riding_constants.h')!=frozen['constants_sha256']:
            raise ValueError('Frozen constants changed')
        return (build_host(out,out/'baseline-gen',snapshot/'console/gbc/src','baseline-host',contacts=True)
                if contacts else library)
    if library.exists():raise FileExistsError(f'Refusing to replace frozen baseline {library}')
    files = subprocess.check_output(['git','ls-tree','-r','--name-only',revision,
                                     'console/gbc/src'],cwd=ROOT,text=True).splitlines()
    files += ['console/nes/src/recip.inc','console/nes/src/rsqrt.inc',
              'console/gbc/tools/riding_constants.py','console/gbc/tools/physics_level.py',
              'console/gbc/Makefile']
    for name in files:
        path=snapshot/name; path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(subprocess.check_output(['git','show',revision+':'+name],cwd=ROOT))
    frozen_gen=out/'baseline-gen'; frozen_gen.mkdir(parents=True,exist_ok=True)
    for path in [*Path(gen).glob('*.h'),Path(gen)/'physics_level_data.c',
                 *Path(gen).glob('physics_bank_*.c')]:
        shutil.copy2(path,frozen_gen/path.name)
    makefile=(snapshot/'console/gbc/Makefile').read_text()
    hz=re.search(r'^PHYS_HZ\s*\?=\s*(\d+)',makefile,re.M)[1]
    damper=re.search(r'^DAMPER\s*\?=\s*(\w+)',makefile,re.M)[1]
    run([sys.executable,snapshot/'console/gbc/tools/riding_constants.py',
         frozen_gen/'riding_constants.h',hz,damper],out/'baseline-constants.log')
    # Geometry formats evolve independently of the dynamics. Repack using the
    # frozen revision's packer; never feed today's flagged segments to old code.
    resource=Path(resource) if resource is not None else ROOT/'build-reg/elma.res'
    generated=Path(gen)/'riding_level.json'
    if not generated.exists() or json.loads(generated.read_text())['source_res_sha256']!=sha256(resource):
        raise ValueError('Cannot verify original resource for frozen collision geometry')
    spec=importlib.util.spec_from_file_location('gbc_frozen_geometry',snapshot/'console/gbc/tools/physics_level.py')
    geometry=importlib.util.module_from_spec(spec);spec.loader.exec_module(geometry)
    packer=geometry.BankPacker(geometry.FIRST_BANK)
    pairs=[geometry.pack_level(level,i,packer) for i,level in enumerate(internal_levels(Resource(resource)))]
    geometry.write_outputs(frozen_gen,packer,*zip(*pairs))
    library=build_host(out,frozen_gen,snapshot/'console/gbc/src','baseline-host')
    metadata.write_text(json.dumps({'git_revision':revision,'library_sha256':sha256(library),
        'generated_input_directory':str(Path(gen).resolve()),
        'constants_generator':str(snapshot/'console/gbc/tools/riding_constants.py'),
        'source_sha256':{name:sha256(snapshot/name) for name in files},
        'constants_sha256':sha256(frozen_gen/'riding_constants.h'),
        'physics_hz':hz,'damper':damper},indent=2)+'\n')
    return (build_host(out,frozen_gen,snapshot/'console/gbc/src','baseline-host',contacts=True)
            if contacts else library)


def fixture_levels():
    flat=Level(); flat.name='Controlled horizontal surface'
    flat.polygons=[(False,[(-64.,0.),(64.,0.),(64.,-20.),(-64.,-20.)]),
                   (False,[(-64.,80.),(64.,80.),(64.,81.),(-64.,81.)])]
    flat.objects=[(4,-.85,1.,0,0)]
    air=Level(); air.name='Controlled air inside distant boundary'
    air.polygons=[(False,[(-64.,-64.),(64.,-64.),(64.,64.),(-64.,64.)])]
    air.objects=[(4,-.85,20.,0,0)]
    return [flat,air]


def build_fixtures(out, constants_path, source, name, contacts=False):
    """Use the production geometry packer and collision reader for fixtures."""
    path=Path(source).parent/'tools/physics_level.py'
    if not path.is_file():
        if 'baseline-source' in Path(source).parts:
            raise ValueError('Frozen baseline lacks its geometry packer; use a fresh output directory')
        path=BASE/'tools/physics_level.py'
    spec=importlib.util.spec_from_file_location('gbc_compare_geometry',path)
    geometry=importlib.util.module_from_spec(spec);spec.loader.exec_module(geometry)
    gen=Path(out)/(name+'-gen');gen.mkdir(parents=True,exist_ok=True)
    levels=fixture_levels(); packer=geometry.BankPacker(geometry.FIRST_BANK)
    pairs=[geometry.pack_level(level,i,packer) for i,level in enumerate(levels)]
    geometry.write_outputs(gen,packer,*zip(*pairs))
    shutil.copy2(constants_path,gen/'riding_constants.h')
    library=build_host(out,gen,source,name,contacts=contacts)
    for i,level in enumerate(levels):write_level(gen/f'fixture{i}.txt',level)
    return library,gen,levels


def constants(path):
    source = Path(path).read_text()
    def value(key, default=None):
        match = re.search(r'^#define ' + key + r' ([\d.eE+-]+)', source, re.M)
        return float(match[1]) if match else default
    rate, angle = value('PH_RATE'), int(value('RIDING_ANGLE_UNITS'))
    dt = .4368 / rate
    velocity_time = value('PH_VELOCITY_UNIT_TIME', dt)
    angular_time = value('PH_ANGULAR_UNIT_TIME', dt)
    return {'rate': rate, 'dt': dt, 'angle': angle,
            'pc_schedule': bool(value('RIDING_PC_SCHEDULE', 0)),
            'velocity_scale': 262144 * velocity_time / 4,
            'omega_scale': angle / (2 * math.pi) * angular_time / 128}


def angle_delta(a, b):
    return (a - b + math.pi) % (2 * math.pi) - math.pi


def contact_provenance(library, enabled):
    if not enabled: return None
    path = Path(library).with_name(Path(library).stem + '-build.json')
    if not path.exists(): return None
    metadata = json.loads(path.read_text())
    provenance = metadata.get('contact_instrumentation')
    if not provenance or metadata.get('library_sha256') != sha256(library): return None
    for kind in ('original', 'compiled'):
        if sha256(provenance[kind+'_source']) != provenance[kind+'_source_sha256']:
            raise ValueError(f'Contact instrumentation source changed: {path}')
    return {**provenance, 'library_sha256': metadata['library_sha256']}


def contact_snapshot(function):
    # Initial counts are unknown until the solver has actually observed them.
    modes, observations = (C.c_int * 2)(), (C.c_int * 2)()
    function(modes, observations)
    return {'wheel_contacts': {f'wheel{i}': n if n >= 0 else None for i, n in enumerate(modes)},
            'contact_observations': list(observations)}


class Gbc:
    def __init__(self, library, settings):
        self.library = Path(library).resolve(); self.settings = settings
        self.f = C.CDLL(str(self.library))
        self.f.physics_step.argtypes = [C.c_uint8]
        self.f.physics_select_level.argtypes = [C.c_uint8]
        self.f.physics_reset.argtypes = [C.c_int32, C.c_int32]
        self.f.physics_set_gravity.argtypes = [C.c_uint8]
        assert self.f.fixture_internal_size() == C.sizeof(Bike)
        assert self.f.fixture_public_size() == C.sizeof(Public)
        self.b = Bike.in_dll(self.f, 'Bike'); self.p = Public.in_dll(self.f, 'gbc_bike')
        self.contacts = hasattr(self.f, 'fixture_contact_version') and self.f.fixture_contact_version() == 1
        if self.contacts:
            self.f.fixture_contact_state.argtypes = [C.POINTER(C.c_int), C.POINTER(C.c_int)]
            self.f.fixture_contact_event.argtypes = [C.c_int, C.POINTER(C.c_int)]
            if hasattr(self.f, 'fixture_contact_time'):
                self.f.fixture_contact_time.argtypes = [C.c_int]
                self.f.fixture_contact_time.restype = C.c_double

    def reset(self, level, turned=True, start=None, objects=None):
        assert self.f.physics_select_level(level)
        if start is None:
            self.f.physics_reset_current()
        else:
            self.f.physics_reset(*[math.floor(x * 65536 + .5) for x in start])
        if turned: self.f.physics_turn()
        self.ox = C.c_int32.in_dll(self.f, 'physics_level_origin_x').value / 65536
        self.oy = C.c_int32.in_dll(self.f, 'physics_level_origin_y').value / 65536
        self.t = 0; self.volt_wait = 0; self.events = []; self.finished = False;self.dead=False
        self.contact_events = []
        if self.contacts: self.f.fixture_contact_reset()
        self.objects = [(t,round(x*65536),round(y*65536),g,i)
                        for i,(t,x,y,g,_) in enumerate(objects or []) if t in (1,2,3)]
        self.active = {o[4] for o in self.objects}
        self.apples = sum(o[0]==2 for o in self.objects)

    def seed_values(self):
        b, s = self.b, self.settings
        values = []
        for k in (b.body, *b.wheel):
            values += [k.rx / 262144 + self.ox, k.ry / 262144 + self.oy,
                       k.vx / s['velocity_scale'], k.vy / s['velocity_scale'],
                       (k.alfa % s['angle']) * 2 * math.pi / s['angle'], k.omega / s['omega_scale']]
        values += [b.rider_x / 262144 + self.ox, b.rider_y / 262144 + self.oy,
                   b.rider_vx / s['velocity_scale'], b.rider_vy / s['velocity_scale'],
                   b.head_x / 262144 + self.ox, b.head_y / 262144 + self.oy]
        return values

    def snapshot(self):
        b, p, s = self.b, self.p, self.settings
        pose = {name: [v.x / 65536, v.y / 65536]
                for name, v in zip(PARTS, (p.body, *p.wheel, p.rider, p.head))}
        velocity = {name: [k.vx / s['velocity_scale'], k.vy / s['velocity_scale']]
                    for name, k in zip(PARTS, (b.body, *b.wheel))}
        velocity['rider'] = [b.rider_vx / s['velocity_scale'], b.rider_vy / s['velocity_scale']]
        angles = {name: angle_delta(k.alfa * 2 * math.pi / s['angle'], 0)
                  for name, k in zip(PARTS[:3], (b.body, *b.wheel))}
        angular_velocity = {name: k.omega / s['omega_scale']
                            for name, k in zip(PARTS[:3], (b.body, *b.wheel))}
        return {**(contact_snapshot(self.f.fixture_contact_state) if getattr(self, 'contacts', False) else {}),
                't_game': self.t, 't_wall': self.t / .4368, 'position': pose,
                'velocity': velocity, 'body_angle': angle_delta(b.body.alfa * 2 * math.pi / s['angle'], 0),
                'body_omega': b.body.omega / s['omega_scale'], 'dead': self.dead,
                'finished': self.finished, 'turned': int(b.turned), 'gravity': int(b.gravity),
                'angles': angles, 'angular_velocity': angular_velocity,
                'gravity_direction': ('up', 'down', 'left', 'right')[b.gravity],
                'apples_collected': sum(o[0] == 2 for o in self.objects) - self.apples}

    def step(self, keys):
        if self.dead or self.finished:return
        if keys & 16:self.f.physics_turn()
        # play.c decrements then gates held volt keys. GAS/BRAKE remain held.
        if self.volt_wait: self.volt_wait -= 1
        actual = keys & 3
        if not self.volt_wait and keys & 12:
            actual |= keys & 12
            self.volt_wait = int(.4 / self.settings['dt']) + 1
        if self.contacts: self.f.fixture_contact_begin()
        self.f.physics_step(actual); self.t += self.settings['dt']
        if self.contacts:
            for i in range(self.f.fixture_contact_count()):
                values = (C.c_int * 3)(); self.f.fixture_contact_event(i, values)
                event_time = self.t
                if self.settings.get('pc_schedule'):
                    event_time = self.t-self.settings['dt']+self.f.fixture_contact_time(i)
                self.contact_events.append({'wheel': values[0], 'from': values[1] if values[1] >= 0 else None,
                                            'count': values[2], 't_game': event_time})
        if any(abs(C.c_int32(getattr(part,axis)-getattr(self.p.body,axis)).value)>3*65536
               for part in (*self.p.wheel,self.p.rider) for axis in ('x','y')):
            self.p.alive=0
        if not self.p.alive:
            self.dead=True
            self.events.append({'type': 'death', 'object': None, 't_game': self.t})
            return
        # play.c/check_objects and objects_touch_fast.s; retain resource order.
        # This is the platform event pass, outside the core shared library.
        for kind,x,y,gravity,index in self.objects:
            if index not in self.active or kind==1 and self.apples:continue
            hit=False
            for pose,radius in ((self.p.wheel[0],819),(self.p.wheel[1],819),(self.p.head,653)):
                dx=C.c_int32(pose.x-x).value;dy=C.c_int32(pose.y-y).value
                if abs(dx)<=52429 and abs(dy)<=52429 and (dx>>6)**2+(dy>>6)**2<=radius*radius:
                    hit=True;break
            if not hit:continue
            if kind==2:
                self.active.remove(index);self.apples-=1
                if gravity:self.f.physics_set_gravity(gravity)
                event='apple'
            elif kind==1:self.finished=True;self.dead=False;event='finish'
            else:self.p.alive=0;self.dead=True;self.finished=False;event='death'
            self.events.append({'type':event,'object':index,'t_game':self.t})


class Pc:
    def __init__(self, library):
        self.library = Path(library).resolve()
        self.f = C.CDLL(str(self.library))
        self.f.compare_pc_load.argtypes = [C.c_char_p]
        self.f.compare_pc_seed.argtypes = [C.POINTER(C.c_double), C.c_int]
        self.f.compare_pc_get.argtypes = [C.POINTER(C.c_double), C.POINTER(C.c_int)]
        self.f.compare_pc_step.argtypes = [C.c_int, C.c_double]
        self.f.compare_pc_step.restype = C.c_double
        self.f.compare_pc_event.argtypes = [C.c_int, C.POINTER(C.c_int), C.POINTER(C.c_double)]
        self.f.compare_pc_pi.restype = C.c_double
        assert self.f.compare_pc_pi() == 3.141592
        self.contacts = hasattr(self.f, 'compare_pc_contact_version') and self.f.compare_pc_contact_version() == 1
        if self.contacts:
            self.f.compare_pc_contact_state.argtypes = [C.POINTER(C.c_int), C.POINTER(C.c_int)]
            self.f.compare_pc_contact_event.argtypes = [C.c_int, C.POINTER(C.c_int), C.POINTER(C.c_double)]

    def reset(self, path, seed=None, turned=False):
        assert self.f.compare_pc_load(str(Path(path).resolve()).encode())
        if seed is not None:self.f.compare_pc_seed((C.c_double * 24)(*seed), int(turned))
        elif turned:self.f.compare_pc_turn()
        self.t = 0

    def snapshot(self):
        v = (C.c_double * 24)(); flags = (C.c_int * 5)()
        self.f.compare_pc_get(v, flags)
        pose = {name: list(v[i*6:i*6+2]) for i, name in enumerate(PARTS[:3])}
        pose.update(rider=list(v[18:20]), head=list(v[22:24]))
        velocity = {name: list(v[i*6+2:i*6+4]) for i, name in enumerate(PARTS[:3])}
        velocity['rider'] = list(v[20:22])
        return {**(contact_snapshot(self.f.compare_pc_contact_state) if getattr(self, 'contacts', False) else {}),
                't_game': self.t, 't_wall': self.t / .4368, 'position': pose,
                'velocity': velocity, 'body_angle': angle_delta(v[4], 0), 'body_omega': v[5],
                'dead': bool(flags[0]), 'finished': bool(flags[1]), 'turned': flags[2], 'gravity': flags[3],
                'angles': {name: angle_delta(v[i*6+4], 0) for i, name in enumerate(PARTS[:3])},
                'angular_velocity': {name: v[i*6+5] for i, name in enumerate(PARTS[:3])},
                'gravity_direction': ('up', 'down', 'left', 'right')[flags[3]],
                'apples_collected': flags[4]}

    def step(self, keys, dt):
        if keys & 16:self.f.compare_pc_turn()
        self.t = self.f.compare_pc_step(keys & 15, dt)

    def events(self):
        out = []
        for i in range(self.f.compare_pc_event_count()):
            k = (C.c_int * 2)(); t = (C.c_double * 2)()
            self.f.compare_pc_event(i, k, t)
            out.append({'type': {'d': 'death', 'a': 'apple', 'f': 'finish'}[chr(k[0])],
                        'object': k[1] if k[1] >= 0 else None,
                        't_game': t[1], 'original_event_time': t[0]})
        return out

    def contact_events(self):
        if not self.contacts: return []
        out = []
        for i in range(self.f.compare_pc_contact_count()):
            values, time = (C.c_int * 3)(), C.c_double()
            self.f.compare_pc_contact_event(i, values, C.byref(time))
            out.append({'wheel': values[0], 'from': values[1] if values[1] >= 0 else None,
                        'count': values[2], 't_game': time.value})
        return out

    def state_bytes(self):
        self.f.compare_pc_state_bytes.argtypes = [C.POINTER(C.c_ubyte)]
        count = self.f.compare_pc_state_bytes(None)
        out = (C.c_ubyte * count)(); self.f.compare_pc_state_bytes(out)
        return bytes(out)


def write_level(path, level):
    rows = [f'# {level.name}', f'{len(level.polygons)} {len(level.objects)}']
    for grass, points in level.polygons:
        rows += [f'{int(bool(grass))} {len(points)}']
        rows += [f'{x!r} {-y!r}' for x, y in points]
    rows += [f'{t} {x!r} {y!r} {g} {a}' for t, x, y, g, a in level.objects]
    Path(path).write_text('\n'.join(rows) + '\n')


def describe_errors(reference, target):
    """Only common, live sample times; never include frozen terminal repeats."""
    rows = [(a, b) for a, b in zip(reference, target)
            if not a['dead'] and not b['dead'] and not a['finished'] and not b['finished']
            and abs(a['t_game'] - b['t_game']) < 1e-8]
    def stats(deltas):
        norms = [math.hypot(*v) for v in deltas]
        return {'rmse': math.sqrt(sum(x*x for x in norms) / len(norms)),
                'maximum': max(norms), 'final_signed_xy': deltas[-1],
                'mean_signed_xy': [sum(v[i] for v in deltas)/len(deltas) for i in range(2)]}
    out = {'samples': len(rows), 'last_game_time': rows[-1][0]['t_game'] if rows else None}
    if not rows: return out
    for field in ('position', 'velocity'):
        out[field] = {}
        for name in rows[0][0][field]:
            out[field][name] = stats([[b[field][name][j]-a[field][name][j] for j in range(2)] for a, b in rows])
    out['relative_to_body'] = {}
    for name in ('wheel0', 'wheel1', 'rider', 'head'):
        out['relative_to_body'][name] = stats([
            [(b['position'][name][j]-b['position']['body'][j])-
             (a['position'][name][j]-a['position']['body'][j]) for j in range(2)] for a,b in rows])
    for field in ('body_angle', 'body_omega'):
        deltas = [angle_delta(b[field],a[field]) if field=='body_angle' else b[field]-a[field] for a,b in rows]
        out[field] = {'rmse': math.sqrt(sum(v*v for v in deltas)/len(deltas)),
                      'maximum_absolute': max(map(abs,deltas)), 'final_signed': deltas[-1],
                      'mean_signed': sum(deltas)/len(deltas)}
    return out


def compare_case(pc, host, level_path, level_index, inputs, turned=True, start=None, objects=None):
    host.reset(level_index, turned, start, objects)
    pc.reset(level_path, host.seed_values(), turned)
    original, gbc = [pc.snapshot()], [host.snapshot()]
    for keys in inputs:
        if not original[-1]['dead'] and not original[-1]['finished']:
            pc.step(keys, host.settings['dt']); original.append(pc.snapshot())
        if not gbc[-1]['dead'] and not gbc[-1]['finished']:
            host.step(keys); gbc.append(host.snapshot())
        if (original[-1]['dead'] or original[-1]['finished']) and (gbc[-1]['dead'] or gbc[-1]['finished']):
            break
    for trace in (original,gbc):
        for i,state in enumerate(trace):
            if i:
                previous=trace[i-1];dt=state['t_game']-previous['t_game']
                state['velocity']['head']=[(state['position']['head'][j]-previous['position']['head'][j])/dt
                                           for j in range(2)]
            else:
                state['velocity']['head']=[0.,0.]
    pc_events=pc.events()
    if objects:
        order=sorted(range(len(objects)),key=lambda i:{3:1,2:2,1:3}.get(objects[i][0],10))
        for e in pc_events:
            if e['object'] is not None:e['object']=order[e['object']]
    return {'pc': original, 'gbc': gbc, 'errors': describe_errors(original, gbc),
            'events': {'pc': pc_events, 'gbc': host.events},
            'contact_events': {'pc': pc.contact_events(), 'gbc': host.contact_events},
            'contact_instrumentation': {key: contact_provenance(engine.library, engine.contacts)
                                        for key, engine in (('pc', pc), ('gbc', host))},
            'horizon_game_seconds': len(inputs)*host.settings['dt']}


def event_comparison(pc_events, gbc_events):
    result=[]
    for i in range(max(len(pc_events),len(gbc_events))):
        a=pc_events[i] if i<len(pc_events) else None
        b=gbc_events[i] if i<len(gbc_events) else None
        same=bool(a and b and (a['type'],a['object'])==(b['type'],b['object']))
        result.append({'pc':a,'gbc':b,'same_type_and_object':same,
                       'signed_game_time_delta':b['t_game']-a['t_game'] if same else None})
    return {'sequence_matches':all(x['same_type_and_object'] for x in result),
            'count_delta':len(gbc_events)-len(pc_events),'events':result}


def trajectory_features(trace, inputs, dt, horizontal_surface=False):
    alive=[row for row in trace if not row['dead'] and not row['finished']]
    last=trace[-1]
    result={'last_observed_game_time':last['t_game'],
            'terminal': 'death' if last['dead'] else 'finish' if last['finished'] else None,
            'last_body_velocity':last['velocity']['body'],
            'body_displacement':[last['position']['body'][i]-trace[0]['position']['body'][i] for i in range(2)],
            'max_abs_horizontal_speed':max(abs(row['velocity']['body'][0]) for row in alive),
            'peak_downward_speed':max(-row['velocity']['body'][1] for row in alive)}
    def deflection(row,index):
        x,y=row['position']['wheel'+str(index)]
        bx,by=row['position']['body'];a=row['body_angle'];dx=(-.85,.85)[index]
        return math.hypot(x-bx-(dx*math.cos(a)+.6*math.sin(a)),
                          y-by-(dx*math.sin(a)-.6*math.cos(a)))
    result['peak_suspension_deflection_m']=[max(deflection(row,k) for row in alive) for k in range(2)]
    brake=next((i for i,k in enumerate(inputs) if k&2),None)
    if brake is not None and brake<len(trace):
        begin=trace[brake]
        stop=next((row for row in trace[brake+1:] if abs(row['velocity']['body'][0])<.1),None)
        result['braking']={'start_game_time':brake*dt,'start_horizontal_speed':begin['velocity']['body'][0],
                           'time_to_abs_vx_below_0_1':stop['t_game']-begin['t_game'] if stop else None,
                           'distance_to_last_sample':last['position']['body'][0]-begin['position']['body'][0]}
    if horizontal_surface:
        for index in range(2):
            hit=next((row for row in trace if row.get('wheel_contacts',{}).get('wheel'+str(index)) in (1,2)),None)
            result['wheel'+str(index)+'_first_surface_sample']=hit['t_game'] if hit else None
        result['surface_sample_source']='resolved wheel contact mode; unavailable for uninstrumented traces'
    return result


def metric_changes(before,after):
    """Signed changes in physical-unit RMSE; negative means less error."""
    out={}
    for field in ('position','velocity','relative_to_body'):
        out[field]={name:after[field][name]['rmse']-before[field][name]['rmse'] for name in before[field]}
    for field in ('body_angle','body_omega'):out[field]=after[field]['rmse']-before[field]['rmse']
    return out


def validate_reference(out, pc, level_path, settings):
    """Bit-check adapter checkpoints against the existing standalone fixture."""
    out=Path(out); executable=out/'pc-reference-validation'
    sources=[ROOT/'console/ps3/test/physics_trace.cpp']+[ROOT/'src'/(s+'.CPP') for s in PC_SOURCES]
    command=['c++','-std=gnu++11','-O2','-w','-fpermissive','-fsigned-char','-fwrapv',
             '-fno-strict-aliasing','-ffp-contract=off','-I'+str(ROOT/'src'),
             '-I'+str(ROOT/'desktop'),'-I'+str(out/'lowercase_headers'),*sources,'-o',executable]
    run(command,out/'pc-reference-validation-compile.log')
    cases=out/'pc-reference-validation-cases.txt'; trace=out/'pc-reference-validation.txt'
    cases.write_text(f'{Path(level_path).resolve()} {settings["rate"]!r} G200\n')
    run([executable,cases,trace],out/'pc-reference-validation.log')
    checkpoints={}
    for line in trace.read_text().splitlines():
        fields=line.split()
        if not fields or not fields[0].isdigit():continue
        doubles=[struct.unpack('>d',bytes.fromhex(word))[0] for word in fields[1:42]]
        t=doubles[0];index=round(t/settings['dt'])
        if abs(t-index*settings['dt'])>1e-10:continue
        circles=doubles[1:28];state=[]
        for i in range(3):
            c=circles[9*i:9*i+9];state += c[5:9]+c[0:2]
        state += doubles[30:34]+doubles[28:30]
        checkpoints[index]=state
    pc.reset(level_path)
    checked=0
    for i in range(min(30,max(checkpoints))+1):
        if i:pc.step(1,settings['dt'])
        if i not in checkpoints:raise AssertionError(f'Missing standalone checkpoint {i}')
        actual=(C.c_double*24)();flags=(C.c_int*5)();pc.f.compare_pc_get(actual,flags)
        want=b''.join(struct.pack('>d',x) for x in checkpoints[i])
        got=b''.join(struct.pack('>d',x) for x in actual)
        if got!=want:raise AssertionError(f'PC adapter differs from standalone fixture at frame {i}')
        checked+=1
    return {'standalone_checkpoints':checked,'state_double_values_per_checkpoint':24,
            'match':'bit exact','original_pi':pc.f.compare_pc_pi(),
            'initialization_source':'src/ADATOK.CPP initmotor/initadatok; src/TOPOL.CPP setallaktiv',
            'scheduling_source':'src/LEJATSZO.CPP belsoresz and eddig/cel loop',
            'native_double_only':True}


def build_contact_control(library):
    """Compile the same command with the original source and no contact hook."""
    library = Path(library)
    metadata = json.loads(library.with_name(library.stem+'-build.json').read_text())
    instrumentation = metadata['contact_instrumentation']
    control = library.with_name(library.stem+'-control'+library.suffix)
    replacements = {str(library): str(control), instrumentation['compiled_source']: instrumentation['original_source']}
    command = [replacements.get(arg, arg) for arg in metadata['compile_command'] if arg != '-DCOMPARE_CONTACTS=1']
    run(command, control.with_suffix('.log'))
    return control


def validate_contact_identity(pc, plain_pc, host, plain_host, level_path, level_index, inputs,
                              turned=True, start=None, objects=None):
    """Compare every checkpoint bitwise, plus events, against unhooked sources."""
    for engine in (host, plain_host): engine.reset(level_index, turned, start, objects)
    for engine in (pc, plain_pc): engine.reset(level_path, host.seed_values(), turned)
    checked = {'pc': 0, 'gbc': 0}

    def checkpoint():
        if pc.state_bytes() != plain_pc.state_bytes() or pc.events() != plain_pc.events():
            raise AssertionError(f'PC contact instrumentation changed state at {pc.t}')
        for attr in ('b', 'p'):
            if bytes(getattr(host, attr)) != bytes(getattr(plain_host, attr)):
                raise AssertionError(f'GBC contact instrumentation changed {attr} at {host.t}')
        if (host.events, host.dead, host.finished, host.apples, host.active, host.t) != (
                plain_host.events, plain_host.dead, plain_host.finished, plain_host.apples, plain_host.active, plain_host.t):
            raise AssertionError(f'GBC contact instrumentation changed runtime events at {host.t}')
        checked['pc'] += 1; checked['gbc'] += 1

    checkpoint()
    for keys in inputs:
        for engine in (pc, plain_pc):
            state = engine.snapshot()
            if not state['dead'] and not state['finished']: engine.step(keys, host.settings['dt'])
        for engine in (host, plain_host): engine.step(keys)
        checkpoint()
        if (pc.snapshot()['dead'] or pc.snapshot()['finished']) and (host.dead or host.finished): break
    for kind, engine, control in (('pc', pc, plain_pc), ('gbc', host, plain_host)):
        if not engine.contacts: continue
        path = engine.library.with_name(engine.library.stem+'-build.json')
        metadata = json.loads(path.read_text())
        proof = metadata['contact_instrumentation'].setdefault('state_identity', {'match': 'bit exact', 'checks': []})
        proof['checks'].append({'level': str(Path(level_path).resolve()), 'checkpoints': checked[kind],
            'control_library_sha256': sha256(control.library),
            'state_fields': 'all numeric motor/engine state and object activation' if kind == 'pc'
                            else 'complete internal Bike/public pose bytes and runtime event state',
            'contact_transitions': len(engine.contact_events() if kind == 'pc' else engine.contact_events)})
        proof['checkpoints'] = sum(check['checkpoints'] for check in proof['checks'])
        path.write_text(json.dumps(metadata, indent=2)+'\n')
    return {'match': 'bit exact', 'checkpoints': checked}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--res', type=Path, default=ROOT / 'build-reg/elma.res')
    parser.add_argument('--gen', type=Path, default=BASE / 'build/gen')
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    baseline=parser.add_mutually_exclusive_group()
    baseline.add_argument('--baseline-host', type=Path, help='immutable HOST library, instead of building a Git revision')
    baseline.add_argument('--baseline-ref', default=None, help='Git baseline, defaults to 17c1493')
    parser.add_argument('--baseline-source',type=Path,help='source matching a supplied baseline HOST, for synthetic fixtures')
    parser.add_argument('--baseline-constants',type=Path,help='constants matching a supplied baseline HOST')
    parser.add_argument('--candidate-host', type=Path)
    parser.add_argument('--candidate-source',type=Path,help='candidate source; defaults to the working tree')
    parser.add_argument('--candidate-fixture-host',type=Path,help='matching fixture library when supplying --candidate-host')
    parser.add_argument('--no-fixtures',action='store_true',help='only replay actual levels')
    parser.add_argument('--levels', default='0,1,6,10,43,47', help='zero-based internal level IDs')
    args = parser.parse_args(); out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    levels = internal_levels(Resource(args.res)); level_dir = out/'levels'; level_dir.mkdir(exist_ok=True)
    settings = constants(args.gen/'riding_constants.h')
    if not math.isclose(settings['rate'],4194304/70224/2,rel_tol=1e-12):
        raise ValueError('This comparison corpus targets the actual 30 Hz GBC profile')
    generated_metadata=args.gen/'riding_level.json'
    if generated_metadata.exists():
        data=json.loads(generated_metadata.read_text())
        if data['source_res_sha256']!=sha256(args.res):raise ValueError('GBC generated geometry uses a different resource')
    pc = Pc(build_pc(out, contacts=True))
    plain_pc = Pc(build_contact_control(pc.library))
    candidate_source=args.candidate_source or BASE/'src'
    candidate = args.candidate_host or build_host(out,args.gen,candidate_source,contacts=True)
    baseline_ref=None
    if args.baseline_host:
        baseline_host=args.baseline_host
        baseline_source=args.baseline_source
        if baseline_source is None:
            possible=baseline_host.parent/'baseline-source/console/gbc/src'
            if possible.is_dir():baseline_source=possible
        baseline_constants=args.baseline_constants
        if baseline_constants is None:
            for possible in (baseline_host.parent/'riding_constants.h',baseline_host.parent/'baseline-gen/riding_constants.h'):
                if possible.is_file():baseline_constants=possible;break
    else:
        baseline_ref=args.baseline_ref or '17c1493'
        revision=subprocess.check_output(['git','rev-parse',baseline_ref],cwd=ROOT,text=True).strip()
        frozen=out/('baseline-'+revision[:12])
        baseline_host=freeze_baseline(frozen,revision,args.gen,contacts=True,resource=args.res)
        baseline_source=frozen/'baseline-source/console/gbc/src'
        baseline_constants=frozen/'baseline-gen/riding_constants.h'
        baseline_ref=revision
    baseline_settings=constants(baseline_constants) if baseline_constants else settings
    if baseline_settings!=settings:raise ValueError('Baseline/candidate time or unit scales differ')
    supplied_baseline_control = None
    if args.baseline_host and baseline_source and baseline_constants:
        legacy = Gbc(baseline_host, baseline_settings)
        matching_gen = Path(baseline_constants).parent
        if not legacy.contacts and (matching_gen/'physics_level_data.c').is_file():
            # Keep a supplied frozen library immutable; verify the new variant
            # directly against that supplied binary before claiming coverage.
            supplied_baseline_control = legacy
            baseline_host = build_host(out, matching_gen, baseline_source, 'supplied-baseline-host', contacts=True)
    hosts = {'baseline': Gbc(baseline_host,baseline_settings), 'candidate': Gbc(candidate,settings)}
    report = {'schema_version': 3, 'resource_sha256': sha256(args.res),
              'baseline_ref':baseline_ref,
              'libraries':{k:{'path':str(v.library),'sha256':sha256(v.library)} for k,v in hosts.items()},
              'scheduler': {'interval_game_seconds': settings['dt'], 'pc_max_substep': .0055,
                            'pc_substeps': [.0055,.0055,settings['dt']-.011],
                            'input_encoding': 'held runtime GAS=1 BRAKE=2 LEFT=4 RIGHT=8; frame-boundary TURN=16',
                            'turn_timing':'initial orientation before t=0; bit 16 turns once before the frame step',
                            'description':'frame targets at GBC sample times; original cap plus remainder, not fixed 182 Hz'},
              'math_profile': 'native double original sources; not Windows x87',
              'units':{'position':'world meters, Y up; GBC public pose',
                       'velocity':'meters/game-second; head is a sample finite difference, other parts are internal velocity',
                       'body_angle':'radians, wrapped difference in [-pi,pi)',
                       'body_omega':'radians/game-second','signed_error':'GBC minus PC',
                       'rmse_change':'candidate minus baseline, negative is lower error'},
              'limitations':['Native double source reference does not reproduce Windows x87 rounding/order.',
                             'The selected frame schedule is reproducible; the original game had variable frame targets.',
                             'GBC geometry is quantized by its production packer; PC uses original double vertices.',
                             'This HOST study measures trajectories, not ROM cycle budgets or input/display latency.',
                             'GBC object events and the +/-3 m coordinate safety guard mirror play.c outside the physics library.'],
              'cases': {}}
    validation_level=level_dir/'lev00.txt';write_level(validation_level,levels[0])
    report['reference_validation']=validate_reference(out,pc,validation_level,settings)
    cases=[]
    for i in map(int,args.levels.split(',')):
        path=level_dir/f'lev{i:02}.txt'; write_level(path,levels[i])
        for tag,inputs in [('acceleration',[1]*120),('braking',[1]*30+[2]*90),
                           ('volt_left',[0]*10+[4]+[0]*39),('volt_right',[0]*10+[8]+[0]*39)]:
            cases.append({'name':f'level_{i:02}_{tag}','level_index':i,'level_name':levels[i].name,
                          'inputs':inputs,'hosts':hosts,'path':path,'objects':levels[i].objects})
    finish_path=Path(__file__).with_name('fixtures')/'pc_warmup_finish.json'
    finish=json.loads(finish_path.read_text())
    if not math.isclose(finish['physics_rate'],settings['rate'],rel_tol=1e-12):
        raise ValueError('Warm Up completion fixture uses a different input clock')
    cases.append({'name':'pc_warmup_finish','level_index':0,'level_name':levels[0].name,
                  'inputs':finish['inputs'],'hosts':hosts,'path':validation_level,
                  'objects':levels[0].objects,'turned':finish['initial_turned'],
                  'expected_pc_events':finish['expected_pc_events']})
    if not args.no_fixtures:
        if baseline_source is None or baseline_constants is None:
            report['limitations'].append('Synthetic fixtures skipped: supplied baseline has no matching source/constants; pass --baseline-ref or explicit paths.')
        elif args.candidate_host and not args.candidate_fixture_host and not args.candidate_source:
            report['limitations'].append('Synthetic fixtures skipped: supplied candidate needs --candidate-fixture-host or --candidate-source.')
        else:
            baseline_fixture,fixture_gen,fixtures=build_fixtures(out,baseline_constants,baseline_source,'baseline-fixtures',contacts=True)
            if args.candidate_fixture_host:candidate_fixture=args.candidate_fixture_host
            else:candidate_fixture,_,_=build_fixtures(out,args.gen/'riding_constants.h',candidate_source,'candidate-fixtures',contacts=True)
            fixture_hosts={'baseline':Gbc(baseline_fixture,settings),'candidate':Gbc(candidate_fixture,settings)}
            report['fixture_libraries']={k:{'path':str(v.library),'sha256':sha256(v.library)} for k,v in fixture_hosts.items()}
            for name,inputs,start in [('flat_acceleration',[1]*120,(-.85,.4)),
                                      ('flat_braking',[1]*40+[2]*100,(-.85,.4)),
                                      ('drop_landing',[0]*120,(-.85,4.)),
                                      ('suspension_settle',[0]*90,(-.85,1.))]:
                cases.append({'name':name,'level_index':0,'level_name':fixtures[0].name,
                              'inputs':inputs,'hosts':fixture_hosts,'path':fixture_gen/'fixture0.txt',
                              'start':start,'horizontal_surface':True})
            cases.append({'name':'air_coast','level_index':1,'level_name':fixtures[1].name,
                          'inputs':[0]*90,'hosts':fixture_hosts,'path':fixture_gen/'fixture1.txt'})
            for turned in (False,True):
                for delay in (0,1):
                    for direction,keys in [('left',4),('right',8)]:
                        cases.append({'name':f'air_volt_{direction}_turned{int(turned)}_delay{delay}',
                                      'level_index':1,'level_name':fixtures[1].name,
                                      'inputs':[0]*delay+[keys]+[0]*9,'hosts':fixture_hosts,
                                      'path':fixture_gen/'fixture1.txt','turned':turned,'volt_step':delay})
            for direction,keys in [('left',4),('right',8)]:
                cases.append({'name':'air_held_volt_'+direction,'level_index':1,'level_name':fixtures[1].name,
                              'inputs':[keys]*65,'hosts':fixture_hosts,'path':fixture_gen/'fixture1.txt','volt_step':0})
    validated = set()
    report['contact_state_identity'] = {}
    for definition in cases:
        for host in definition['hosts'].values():
            if not host.contacts or host.library in validated: continue
            control = (supplied_baseline_control if supplied_baseline_control is not None and
                       host.library == Path(baseline_host).resolve() else
                       Gbc(build_contact_control(host.library), host.settings))
            report['contact_state_identity'][str(host.library)] = validate_contact_identity(
                pc, plain_pc, host, control, definition['path'], definition['level_index'], definition['inputs'],
                definition.get('turned',True), definition.get('start'), definition.get('objects'))
            validated.add(host.library)
    for definition in cases:
        name=definition['name'];inputs=definition['inputs'];data={}
        case={key:definition[key] for key in ('level_index','level_name','inputs')}
        case['initial_turned']=definition.get('turned',True);case['start']=definition.get('start')
        for label,host in definition['hosts'].items():
            data[label]=compare_case(pc,host,definition['path'],definition['level_index'],inputs,
                                     definition.get('turned',True),definition.get('start'),definition.get('objects'))
        if data['baseline']['pc']!=data['candidate']['pc']:
            raise AssertionError(f'{name}: baseline/candidate did not produce the identical seeded PC reference')
        if 'expected_pc_events' in definition:
            actual=data['baseline']['events']['pc'];wanted=definition['expected_pc_events']
            if len(actual)!=len(wanted) or any(
                    (a['type'],a['object'])!=(b['type'],b['object']) or
                    not math.isclose(a['t_game'],b['t_game'],abs_tol=1e-10,rel_tol=0)
                    for a,b in zip(actual,wanted)):
                raise AssertionError(f'{name}: original PC completion fixture changed: {actual}')
        common=min(len(run[k]) for run in data.values() for k in ('pc','gbc'))
        for i in range(common):
            if any(run[k][i]['dead'] or run[k][i]['finished'] for run in data.values() for k in ('pc','gbc')):
                common=i;break
        if common<2:raise AssertionError(f'{name}: no meaningful common live interval')
        case['common_live']={'samples':common,'last_game_time':data['baseline']['pc'][common-1]['t_game'],
                             'definition':'initial sample and equal-time live samples before the first PC/baseline/candidate terminal event'}
        case['horizon_game_seconds']=len(inputs)*settings['dt'];case['runs']={}
        for label,run in data.items():
            error=describe_errors(run['pc'][:common],run['gbc'][:common])
            summary={'errors':error,'events':event_comparison(run['events']['pc'],run['events']['gbc']),
                     'samples':{k:len(run[k]) for k in ('pc','gbc')},
                     'features':{k:trajectory_features(run[k],inputs,settings['dt'],definition.get('horizontal_surface',False))
                                 for k in ('pc','gbc')}}
            if 'volt_step' in definition:
                i=definition['volt_step']+1
                if i<common:summary['first_volt_step_error']=describe_errors(run['pc'][i:i+1],run['gbc'][i:i+1])
            run['individual_live_errors']=run.pop('errors');run['common_live_errors']=error
            trace=out/(name+'-'+label+'.json');trace.write_text(json.dumps(run)+'\n')
            summary['trace']=str(trace);case['runs'][label]=summary
        case['rmse_change_candidate_minus_baseline']=metric_changes(case['runs']['baseline']['errors'],case['runs']['candidate']['errors'])
        report['cases'][name]=case
    report['case_count']=len(report['cases'])
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'report':str(out/'report.json'),'cases':len(report['cases']),
                      'reference_validation':report['reference_validation']}))


if __name__ == '__main__':
    main()
