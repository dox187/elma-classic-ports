#!/usr/bin/env python3
"""Build an isolated integer kernel with exact two-angle trig memoization.

This only reuses values for identical raw angle inputs. It changes neither
numeric precision nor trigonometric approximation. The existing trig counter
therefore records actual evaluations after cache misses, not every request.
The host prototype needs separate SNES implementation and cycle validation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from wide_probe import ROOT, UNITS


def cache_trig(source):
    declaration = 'inline wide_scalar wide_trig(wide_scalar x,bool cosine){'
    hook = 'inline wide_scalar sin(wide_scalar x){return wide_trig(x,false);}'
    if source.count(declaration) != 1 or source.count(hook) != 1:
        raise ValueError('Expected one unmodified wide trig implementation')
    source = source.replace(declaration, declaration.replace('wide_trig(', 'wide_trig_uncached('))
    cache = '''// Each entry remains valid across levels: the function is pure.
inline wide_scalar wide_trig(wide_scalar x,bool cosine){
    struct entry {int64_t angle=0; wide_scalar values[2]; unsigned valid=0;};
    static entry entries[2];
    static unsigned next=0;
    entry* found=nullptr;
    for(auto& item:entries) if(item.valid && item.angle==x.raw){found=&item;break;}
    if(!found){found=&entries[next];next^=1;found->angle=x.raw;found->valid=0;}
    const unsigned flag=1u<<unsigned(cosine);
    if(!(found->valid&flag)){
        found->values[cosine]=wide_trig_uncached(x,cosine);
        found->valid|=flag;
    }
    return found->values[cosine];
}
'''
    return source.replace(hook, cache+hook)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base-build', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--quarter-turn-identity', action='store_true',
                    help='also replace rider angle-minus-pi/2 by sin,-cos; requires new fidelity validation')
    a = ap.parse_args()
    base, out = a.base_build.resolve(), a.out.resolve()
    if out.exists():
        raise ValueError('Use a fresh isolated output directory')
    out.mkdir(parents=True)
    for path in base.iterdir():
        if path.is_file() and path.suffix.lower() in ('.h', '.cpp'):
            shutil.copy2(path, out/path.name)
    header = out/'wide_fixed.h'
    header.write_text(cache_trig(header.read_text()))
    if a.quarter_turn_identity:
        unit = out/'LEPTET.CPP'
        source = unit.read_text()
        old = 'vekt2 joirany( cos( pmot->kor1.alfa-K_pip2 ), sin( pmot->kor1.alfa-K_pip2 ) );'
        if source.count(old) != 1:
            raise ValueError('Expected one original rider orientation expression')
        unit.write_text(source.replace(old,
            'vekt2 joirany( sin( pmot->kor1.alfa ), -cos( pmot->kor1.alfa ) );'))
    bits = json.loads((base/'build.json').read_text())['bits']
    command = ['c++', '-std=c++17', '-O2', '-w', '-DWIDE_BITS=%d' % bits,
               '-I'+str(out), '-I'+str(ROOT/'test'), '-o', str(out/'widecheck'),
               str(out/'wide_harness.cpp'), str(out/'pcphys.cpp'),
               *[str(out/name) for name in UNITS]]
    result = subprocess.run(command, capture_output=True, text=True)
    (out/'compile.txt').write_text(result.stdout+result.stderr)
    (out/'build.json').write_text(json.dumps({'bits':bits, 'command':command,
          'base_build':str(base), 'change':'Exact memoization for two raw input angles',
          'quarter_turn_identity':a.quarter_turn_identity,
          'base_header_sha256':hashlib.sha256((base/'wide_fixed.h').read_bytes()).hexdigest(),
          'header_sha256':hashlib.sha256(header.read_bytes()).hexdigest()}, indent=2)+'\n')
    if result.returncode:
        print(result.stdout+result.stderr)
        raise SystemExit(result.returncode)
    print(out/'widecheck')


if __name__ == '__main__':
    main()
