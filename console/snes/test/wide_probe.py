"""Create and compile isolated integer copies of the original PC equations."""
import argparse
import json
import math
from pathlib import Path
import re
import subprocess
import shutil

ROOT = Path(__file__).resolve().parent.parent
UNITS = ['LEPTET.CPP', 'BEALLIT.CPP', 'UTKOZES.CPP', 'UTKOZES2.CPP', 'SZAKASZ.CPP', 'VEKT2.CPP']
HEADERS = ['VEKT2.H', 'KOR.H', 'ADATOK.H', 'BEALLIT.H', 'LEPTET.H', 'UTKOZES.H', 'SZAKASZ.H', 'UTKOZES2.H']
TOKEN = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|\bdouble\b|(?<![\w.])(?:\d+\.\d*|\.\d+|\d+[eE][+-]?\d+)(?:[eE][+-]?\d+)?', re.S)


def transform(source):
    def replace(match):
        text = match.group()
        if text == 'double':
            return 'wide_scalar'
        if text.startswith(('//', '/*', '"', "'")):
            return text
        return 'wide_scalar::literal("%s")' % text
    return TOKEN.sub(replace, source)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, default=ROOT / 'build/wide-q32')
    ap.add_argument('--bits', type=int, default=32)
    ap.add_argument('--trig-intervals', type=int, default=4096)
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    for name in ('wide_fixed.h', 'wide_harness.cpp', 'wide_probe.py'):
        shutil.copy2(ROOT / 'test' / name, out / name)
    for unit in UNITS:
        source = (ROOT / '../../src' / unit).read_text(errors='surrogateescape')
        (out / unit).write_text(transform(source), errors='surrogateescape')
    for header in HEADERS:
        source = (ROOT / '../../src' / header).read_text(errors='surrogateescape')
        (out / header.lower()).write_text(transform(source), errors='surrogateescape')
    source = (ROOT / 'test/pcphys/all.h').read_text().replace('#include <math.h>', '#include "wide_fixed.h"')
    (out / 'all.h').write_text(transform(source))
    (out / 'pcphys.h').write_text('#include "wide_fixed.h"\n' + transform((ROOT / 'test/pcphys/pcphys.h').read_text()))
    source = (ROOT / 'test/pcphys/pcphys.cpp').read_text()
    source = source.replace('fscanf( f, "%lf %lf", &g->ponttomb[j].x, &g->ponttomb[j].y )',
                            'wide_scan_pair( f, &g->ponttomb[j].x, &g->ponttomb[j].y )')
    source = source.replace('fscanf( f, "%d %lf %lf %d %d", &k->tipus, &k->r.x, &k->r.y,\n\t\t\t\t\t&k->kajatipus, &k->foodsorszam )',
                            'wide_scan_object( f, &k->tipus, &k->r.x, &k->r.y, &k->kajatipus, &k->foodsorszam )')
    if '%lf' in source:
        raise ValueError('An unconverted floating scanf target remains')
    (out / 'pcphys.cpp').write_text(transform(source))
    pi = round(math.pi * 2**48)
    n = args.trig_intervals
    arrays = ['#pragma once', '#define WIDE_TRIG_INTERVALS %d' % n, 'static constexpr int64_t WIDE_PI_Q48=%d;' % pi]
    for name, function in (('sin', math.sin), ('cos', math.cos)):
        values = [round(function((i * (pi // 2) // n) / 2**48) * 2**48) for i in range(n + 1)]
        arrays.append('static const int64_t wide_%s_q48[]={%s};' % (name, ','.join(map(str, values))))
    (out / 'wide_trig_table.h').write_text('\n'.join(arrays) + '\n')
    host = out / 'widecheck'
    command = ['c++', '-std=c++17', '-O2', '-w', '-DWIDE_BITS=%d' % args.bits,
               '-I' + str(out), '-I' + str(ROOT / 'test'), '-o', str(host),
               str(out / 'wide_harness.cpp'), str(out / 'pcphys.cpp')] + [str(out / u) for u in UNITS]
    result = subprocess.run(command, capture_output=True, text=True)
    (out / 'compile.txt').write_text(result.stdout + result.stderr)
    (out / 'build.json').write_text(json.dumps({'bits': args.bits, 'trig_intervals': n, 'command': command}, indent=2) + '\n')
    print(result.stdout + result.stderr, end='')
    if result.returncode:
        raise SystemExit(result.returncode)
    print('Built integer PC kernel:', host)


if __name__ == '__main__':
    main()
