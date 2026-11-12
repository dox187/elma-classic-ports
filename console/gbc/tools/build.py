"""Incremental native-ROM build; cache independent objects, never game assets."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess

BASE=Path(__file__).resolve().parents[1]


def dependencies(path,gen,seen=None):
    seen=set() if seen is None else seen
    path=path.resolve()
    if path in seen:return b''
    seen.add(path)
    data=path.read_bytes();result=str(path).encode()+b'\0'+data
    for name in re.findall(rb'^\s*#\s*include\s*"([^"]+)"',data,re.M):
        for directory in (path.parent,gen,BASE/'src'):
            candidate=directory/name.decode()
            if candidate.is_file():
                result+=dependencies(candidate,gen,seen);break
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sdk',type=Path,default=BASE/'.toolchain/gbdk')
    p.add_argument('--gen',type=Path,default=BASE/'build/gen')
    p.add_argument('--out',type=Path,default=BASE/'build/elma-gbc.gbc')
    p.add_argument('--jobs',type=int,default=4)
    p.add_argument('--sweep-source',type=Path,help='isolated exact head-collision candidate')
    p.add_argument('--collision-source',type=Path,help='isolated exact collision-cache candidate')
    a=p.parse_args();a.gen=a.gen.resolve();a.sdk=a.sdk.resolve();a.out=a.out.resolve()
    a.out.parent.mkdir(parents=True,exist_ok=True)
    compiler=a.sdk/'bin/lcc'
    compile_flags=['-msm83:gb','-Wf--opt-code-size','-Wf--max-allocs-per-node','-Wf100000',
                   '-I'+str(a.gen),'-I'+str(BASE/'src')]
    link_flags=['-msm83:gb','-Wm-yC','-Wm-yt0x1A','-Wm-ya16','-Wm-yoA','-Wm-ynELMA-GBC','-Wl-m','-Wl-j']
    names=['play.c','world.c','world_dma.c','world_memory.s','world_retire_fast.s','world_alloc_fast.s','world_acquire_fast.s','menu.c','bike_render16.c','physics.c','physics_core.c',
           'physics_contacts.c','physics_collision.c','physics_sweep.c','physics_math.c','physics_math32.c','mul16.s','video.s','video_screen_fast.s','video_strip_pair.s','object16.s','objects_touch_fast.s','objects_draw_fast.s','objects_bounds_fast.s']
    sources=[BASE/'src'/name for name in names]
    if a.sweep_source:
        sources=[a.sweep_source.resolve() if path.name=='physics_sweep.c' else path for path in sources]
    if a.collision_source:
        sources=[a.collision_source.resolve() if path.name=='physics_collision.c' else path for path in sources]
    sources += sorted(x for x in (BASE/'src').glob('physics_*.s')if x.name!='physics_mul16.s')
    for pattern in ('physics_quarter_*.c','physics_scale_*.c','physics_sine_*.c','physics_coefficient_*.c','physics_bank_*.c','level_bank_*.c','riding16_body_*.c'):
        sources+=sorted(a.gen.glob(pattern))
    sources.append(a.gen/'physics_coefficient_calls.s')
    sources += [a.gen/name for name in ('level_catalogue.c','menu_assets.c','physics_level_data.c','riding16_parts.c','riding_meta.c')]
    cache=BASE/'build/objects';cache.mkdir(parents=True,exist_ok=True)
    tool_key=[]
    for name in ('lcc','sdcc','sdasgb','sdldgb'):
        path=a.sdk/'bin'/name
        if path.exists():
            stat=path.stat();tool_key.append((str(path),stat.st_size,stat.st_mtime_ns))
    configuration=json.dumps([compile_flags,tool_key]).encode()
    def coefficient_lookup(path):
        return (path.parent==BASE/'src' and path.suffix=='.c' and path.name.startswith('physics')) or any(candidate is not None and path==candidate.resolve()for candidate in(a.sweep_source,a.collision_source))
    def source_key(path):
        extra=b' -DRIDING_COEFFICIENT_LOOKUP' if coefficient_lookup(path) else b''
        return hashlib.sha256(configuration+extra+dependencies(path,a.gen)).hexdigest()
    objects=[];keys=[];pending=[]
    for path in sources:
        key=source_key(path)
        obj=cache/(path.stem+'-'+key[:24]+'.o');objects.append(obj);keys.append(key)
        if not obj.is_file():pending.append((path,obj,key))
    def compile_one(item):
        path,obj,key=item
        extra=['-DRIDING_COEFFICIENT_LOOKUP'] if coefficient_lookup(path) else []
        result=subprocess.run([str(compiler),*compile_flags,*extra,'-c','-o',str(obj),str(path)],capture_output=True,text=True)
        if result.returncode:
            obj.unlink(missing_ok=True)
            raise RuntimeError(str(path)+'\n'+result.stdout+result.stderr)
        if source_key(path)!=key:
            obj.unlink(missing_ok=True)
            raise RuntimeError('Source changed while compiling: '+str(path)+'; rerun the build after edits finish')
        if result.stdout.strip() or result.stderr.strip():print(result.stdout+result.stderr,flush=True)
    print('Objects: %d cached, %d compiling'%(len(objects)-len(pending),len(pending)),flush=True)
    with ThreadPoolExecutor(max_workers=max(1,a.jobs))as pool:
        for _ in pool.map(compile_one,pending):pass
    for path,key in zip(sources,keys):
        if source_key(path)!=key:
            raise RuntimeError('Source changed during the build: '+str(path)+'; rerun after edits finish')
    manifest_path=a.out.with_suffix('.build.json')
    build_key=hashlib.sha256(json.dumps([keys,link_flags,tool_key]).encode()).hexdigest()
    if manifest_path.is_file() and a.out.is_file() and a.out.with_suffix('.noi').is_file():
        previous=json.loads(manifest_path.read_text())
        if previous.get('build_key')==build_key and previous.get('rom_sha256')==hashlib.sha256(a.out.read_bytes()).hexdigest():
            print('ROM unchanged: '+str(a.out));return
    subprocess.run([str(compiler),*link_flags,'-o',str(a.out),*map(str,objects)],check=True)
    report={'build_key':build_key,'rom_sha256':hashlib.sha256(a.out.read_bytes()).hexdigest(),
            'sources':[str(x)for x in sources],'objects':[str(x)for x in objects]}
    manifest_path.write_text(json.dumps(report,indent=2)+'\n')
    print('Built '+str(a.out)+' '+report['rom_sha256'])


if __name__=='__main__':main()
