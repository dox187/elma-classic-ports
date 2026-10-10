#!/usr/bin/env python3
"""Build a private optional algebraic suspension variant of the integer kernel.

Original contact, spring activation and rider branch conditions are retained.
The optional change combines orthogonal spring/damper components algebraically
and eliminates axle torque normalization via squared distance. This is a host
experiment; fidelity and SNES cycle feasibility must be measured separately.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from wide_probe import ROOT, transform


def exact_replace(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Original source hunk no longer unique: '+old[:80])
    return source.replace(old, new)


def force_variant(source):
    start = source.index('        // Gumieronek szetbontasa ket komponensre:')
    end = source.index('\n    }\n    else {', start)
    source = source[:start]+'''        // Orthogonal components sum to the original Cartesian spring.
        *pFkerek = gumi*Drsugar;
        *pFtest = Vekt2null - *pFkerek;
        *pMtest = -(gumi*forgatas90fokkal(gumis))*Drsugar;'''+source[end:]
    start = source.index('    double kotol = abs( koto );')
    end = source.index('\n    surlodasverseny(', start)
    source = source[:start]+'''    vekt2 kotomer = forgatas90fokkal( koto );
    vekt2 korongrelv = (kotomer*pmot->kor1.omega+pmot->kor1.v)-pkor->v;
    // Same sum of longitudinal and transverse damper forces.
    vekt2 Fdamper = korongrelv*Sr;
    // unit_perp(koto) * torque / |koto| = perp(koto)*torque/|koto|^2.
    // A zero axle distance remains a domain failure, as in the literal kernel.
    vekt2 Ftestnyom = kotomer*(*pMkerek/absnegyzet(koto));
    *pFkerek = *pFkerek + Fdamper - Ftestnyom;
    *pMtest += -(Fdamper*kotomer);
    *pFtest = *pFtest - Fdamper + Ftestnyom;
'''+source[end:]
    return source


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base-build', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    base, out = a.base_build.resolve(), a.out.resolve()
    if out == base or out.exists():
        raise ValueError('Use a fresh isolated output directory')
    shutil.copytree(base, out)
    # Snapshot shared includes/driver: later agent edits cannot alter this build.
    for name in ['wide_fixed.h', 'wide_harness.cpp']:
        if not (out/name).exists():shutil.copy2(ROOT/'test'/name, out/name)
    original = (ROOT/'../../src/LEPTET.CPP').read_text()
    changed = force_variant(original)
    (out/'LEPTET.CPP').write_text(transform(changed))
    build = json.loads((base/'build.json').read_text())
    command = [str(out/'wide_harness.cpp') if x == str(ROOT/'test/wide_harness.cpp')
               else x.replace(str(base), str(out)) for x in build['command']]
    (out/'build.json').write_text(json.dumps({**build,'command':command,'base_build':str(base)},indent=2)+'\n')
    result = subprocess.run(command, capture_output=True, text=True)
    (out/'compile.txt').write_text(result.stdout+result.stderr)
    (out/'force_variant.json').write_text(json.dumps({'change':'Cartesian spring/damper and squared-distance torque reaction identities',
                 'branches_preserved': ['gumi component strict outside +/-0.0001', 'contact selection/release', 'rider constraints'],
                 'base_build': str(base), 'bits': build['bits'], 'command': command,
                 'original_leptet_sha256': hashlib.sha256(original.encode()).hexdigest(),
                 'transformed_leptet_sha256': hashlib.sha256((out/'LEPTET.CPP').read_bytes()).hexdigest()}, indent=2)+'\n')
    if result.returncode:
        print(result.stdout+result.stderr)
        raise SystemExit(result.returncode)
    print(out/'widecheck')


if __name__ == '__main__':
    main()
