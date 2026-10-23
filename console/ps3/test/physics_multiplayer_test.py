#!/usr/bin/env python3
"""Exact original-engine two-player/Tag traces, paired with suspended clocks."""
import argparse,hashlib,pathlib,random,subprocess,sys
from physics_test import REPO,PSX,module,compare,profile_arguments,profile_flags,write_metadata

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build',type=pathlib.Path,default=REPO/'console/ps3/build/multiplayer-test')
    ap.add_argument('--res',type=pathlib.Path,default=REPO/'elma.res')
    ap.add_argument('--compare',type=pathlib.Path)
    ap.add_argument('--fps',type=int,nargs='+',default=[30,60],
                    help='Frame rates to compare; use --fps 50 for a separate PAL corpus')
    profile_arguments(ap)
    args=ap.parse_args();out=args.build.resolve();out.mkdir(parents=True,exist_ok=True)
    if any(rate<1 or rate>240 for rate in args.fps):ap.error('--fps values must be in 1..240')
    if args.compare:return compare(out/'host-trace.txt',args.compare)
    levels=out/'levels';levels.mkdir(exist_ok=True)
    subprocess.run([sys.executable,str(PSX/'phys_levels.py'),str(args.res),str(levels)],check=True)
    headers=out/'headers';headers.mkdir(exist_ok=True)
    for h in (REPO/'src').glob('*.H'):(headers/h.name.lower()).write_text(f'#include "{h}"\n')
    sources=['LEPTET','BEALLIT','UTKOZES','UTKOZES2','SZAKASZ','VEKT2','FOGOCSKA']
    exe=out/'physics-multiplayer'
    profile,link=profile_flags(args)
    command=['c++','-std=gnu++11','-O2','-w','-fpermissive','-fsigned-char','-fwrapv','-fno-strict-aliasing','-ffp-contract=off']+profile+['-I'+str(REPO/'src'),'-I'+str(REPO/'desktop'),'-I'+str(headers),str(pathlib.Path(__file__).with_name('physics_multiplayer.cpp'))]+[str(REPO/'src'/(s+'.CPP')) for s in sources]+link+['-o',str(exe)]
    subprocess.run(command,check=True)
    corpus=module('multiplayer_corpus',PSX/'phys_test.py');cases=[]
    for level in sorted(levels.glob('lev*.txt')):
        seed=int(level.stem[3:]);scripts=[corpus.random_script(random.Random(seed*100+p),1200) for p in (1,2)]
        for tag in (0,1):
            for fps in dict.fromkeys(args.fps):
                for paused in (0,1):cases.append((level.name,fps,tag,paused,*scripts))
    for filename,root in [('host-cases.txt',str(levels)),('multiplayer-cases.txt','/dev_hdd0/game/ELMAC0001/USRDIR/levels')]:
        (out/filename).write_text(''.join(f'{root}/{lev} {fps} {tag} {paused} {a} | {b}\n' for lev,fps,tag,paused,a,b in cases))
    subprocess.run([str(exe),str(out/'host-cases.txt'),str(out/'host-trace.txt')],check=True)
    # Every second case differs only by a long wall-clock suspension.
    blocks=[];block=None
    with (out/'host-trace.txt').open('rb') as trace:
        for line in trace:
            if line.startswith(b'case '):
                if block is not None:blocks.append(block.digest())
                block=hashlib.sha256()
            elif line.startswith((b'coverage ',b'complete ')):
                if block is not None:blocks.append(block.digest());block=None
            elif block is not None:block.update(line)
    assert len(blocks)==len(cases),(len(blocks),len(cases))
    for index in range(0,len(blocks),2):assert blocks[index]==blocks[index+1],f'pause divergence in case {index}'
    write_metadata(args,out,command,len(cases),{'suspended_clock_pairs':len(blocks)//2,'fps':args.fps})
    print(f'PASS: {len(cases)} two-player/Tag cases, all 54 levels, rates {args.fps}; suspended-clock counterparts match exactly')
    return 0
if __name__=='__main__':sys.exit(main())
