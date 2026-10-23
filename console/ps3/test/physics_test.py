#!/usr/bin/env python3
"""Generate original-engine traces and compare exact PPU physics results.

The fixtures derive from the user's registered elma.res and stay in build/.
Copy levels/ and physics-cases.txt into ELMAC0001/USRDIR, run physics-trace.self
on PS3/RPCS3, then compare the resulting physics-trace.txt with --compare.
Every IEEE-754 bit and event must match; no tolerance hides divergence.
"""
import argparse
import hashlib
import json
import importlib.util
import pathlib
import random
import subprocess
import sys

REPO=pathlib.Path(__file__).resolve().parents[3]
PSX=REPO/'console/psx/test'
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj

def compare(reference,target):
    with open(reference) as a,open(target) as b:
        case='';step=''
        for lineno,(x,y) in enumerate(__import__('itertools').zip_longest(a,b),1):
            if x and x.startswith('case '):case=x.strip()
            if x!=y:
                print(f'FAIL: first difference at line {lineno}, {case}')
                print('host:',str(x).rstrip());print('PPU: ',str(y).rstrip());return 1
            step=x
        if not step.startswith('complete '):
            print('FAIL: trace has no completion marker');return 1
    print('PASS: all physics state bits and events match; '+step.strip());return 0

def profile_arguments(parser):
    parser.add_argument('--classic-x87-library', type=pathlib.Path,
                        help='Opt in to Classic x87 math/order using this prebuilt host static archive')

def profile_flags(args):
    if args.classic_x87_library is None:return [],[]
    library=args.classic_x87_library.resolve()
    if not library.is_file():raise FileNotFoundError(library)
    return ['-DELMA_CLASSIC_X87','-I'+str(REPO/'third_party/elma_x87')],[str(library)]

def sha256(path):
    digest=hashlib.sha256()
    with pathlib.Path(path).open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()

def write_metadata(args,out,command,cases,checks):
    library=args.classic_x87_library.resolve() if args.classic_x87_library else None
    sources=[pathlib.Path(arg) for arg in command if pathlib.Path(arg).suffix in ('.CPP','.cpp')]
    sources += list((REPO/'src').glob('*.H'))
    sources += [pathlib.Path(__file__).resolve(), pathlib.Path(__file__).with_name('physics_trace.cpp'),
                PSX/'phys_test.py',PSX/'phys_levels.py',PSX/'phys_warmup_finish.txt']
    multiplayer=pathlib.Path(__file__).with_name('physics_multiplayer_test.py')
    if any(p.name=='physics_multiplayer.cpp' for p in sources):sources.append(multiplayer)
    if library:sources += list((REPO/'third_party/elma_x87').glob('*.h'))
    metadata={'profile':'classic-x87' if library else 'sdl',
              'classic_x87_library':{'path':str(library),'sha256':sha256(library)} if library else None,
              'compiler':subprocess.check_output([command[0],'--version'],text=True).splitlines()[0],
              'compile_command':command,'executable_sha256':sha256(command[command.index('-o')+1]),
              'cases':cases,'checks':checks,
              'resource':{'path':str(args.res.resolve()),'sha256':sha256(args.res)},
              'source_sha256':{str(p.relative_to(REPO)):sha256(p) for p in sources},
              'output_sha256':{str(p.relative_to(out)):sha256(p) for p in
                  sorted(out.glob('levels/lev*.txt'))+sorted(out.glob('*cases.txt'))+[out/'host-trace.txt']}}
    (out/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--res',type=pathlib.Path,default=REPO/'elma.res')
    ap.add_argument('--build',type=pathlib.Path,default=REPO/'console/ps3/build/physics-test')
    ap.add_argument('--seeds',type=int,default=2)
    ap.add_argument('--seconds',type=float,default=30)
    ap.add_argument('--compare',type=pathlib.Path)
    profile_arguments(ap)
    args=ap.parse_args();out=args.build.resolve();out.mkdir(parents=True,exist_ok=True)
    if args.compare:return compare(out/'host-trace.txt',args.compare)
    levels=out/'levels';levels.mkdir(exist_ok=True)
    subprocess.run([sys.executable,str(PSX/'phys_levels.py'),str(args.res),str(levels)],check=True)
    forwards=out/'lowercase_headers';forwards.mkdir(exist_ok=True)
    for h in (REPO/'src').glob('*.H'):(forwards/h.name.lower()).write_text(f'#include "{h}"\n')
    exe=out/'physics-trace'
    flags=['-std=gnu++11','-O2','-w','-fpermissive','-fsigned-char','-fwrapv','-fno-strict-aliasing','-ffp-contract=off']
    sources=['LEPTET','BEALLIT','UTKOZES','UTKOZES2','SZAKASZ','VEKT2']
    profile,link=profile_flags(args)
    command=['c++']+flags+profile+['-I'+str(REPO/'src'),'-I'+str(REPO/'desktop'),'-I'+str(forwards),str(pathlib.Path(__file__).with_name('physics_trace.cpp'))]+[str(REPO/'src'/(s+'.CPP')) for s in sources]+link+['-o',str(exe)]
    subprocess.run(command,check=True)
    corpus=module('elma_phys_corpus',PSX/'phys_test.py')
    cases=[];steps=int(args.seconds*.4368/.0055)
    _,warmup=corpus.read_script(PSX/'phys_warmup_finish.txt')
    cases.append(('lev00.txt',0,warmup))
    for lev in sorted(levels.glob('lev*.txt')):
        scripts=[f'G{steps}']+[corpus.random_script(random.Random(1000*int(lev.stem[3:])+seed),steps) for seed in range(args.seeds)]
        for fps in (0,30,60):
            for script in scripts:cases.append((lev.name,fps,script))
    for name,root in [('host-cases.txt',str(levels)),('physics-cases.txt','/dev_hdd0/game/ELMAC0001/USRDIR/levels')]:
        (out/name).write_text(''.join(f'{root}/{lev} {fps} {script}\n' for lev,fps,script in cases))
    subprocess.run([str(exe),str(out/'host-cases.txt'),str(out/'host-trace.txt')],check=True)
    with open(out/'host-trace.txt') as trace:
        warmup_result=None
        for line in trace:
            if line.startswith('case 1'):break
            if line.startswith('result '):warmup_result=line.strip()
    if warmup_result!='result 0 1 1652':
        raise RuntimeError(f'Warm Up regression failed: {warmup_result}')
    write_metadata(args,out,command,len(cases),{'warmup_finish':'result 0 1 1652'})
    print(f'Generated {len(cases)} cases across {len(list(levels.glob("lev*.txt")))} levels in {out}')
    return 0
if __name__=='__main__':sys.exit(main())
