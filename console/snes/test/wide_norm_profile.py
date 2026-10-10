#!/usr/bin/env python3
"""Aggregate exact caller-tagged norm ranges from frozen C-port traces."""
import argparse
import gzip
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--reference',type=Path)
    args=parser.parse_args()
    ranges={};steps=0;cases=0;identity_rows=0
    for suite in ('fidelity','holdout','endurance'):
        directory=args.build/suite
        for path in sorted(directory.glob('*.stderr.txt')):
            cases+=1
            for line in path.read_text().splitlines():
                if line.startswith('WIDE_STEPS '):steps+=int(line.split()[1])
                if not line.startswith('WIDE_NORM_RANGE '):continue
                row=json.loads(line.split(' ',1)[1]);key=(row['kind'],row['caller'])
                if key not in ranges:ranges[key]=row.copy();continue
                r=ranges[key]
                if r['bits']!=row['bits']:raise ValueError('Mixed fraction sizes')
                for field in ('count','computed'):r[field]+=row[field]
                for field in ('xmin','ymin','lmin'):r[field]=min(r[field],row[field])
                for field in ('xmax','ymax','lmax','normalmax'):r[field]=max(r[field],row[field])
            if args.reference:
                reference=args.reference/suite/(path.name.replace('.stderr.txt','.jsonl.gz'))
                with gzip.open(directory/path.name.replace('.stderr.txt','.jsonl.gz'),'rt') as stream:a=[json.loads(s) for s in stream]
                with gzip.open(reference,'rt') as stream:b=[json.loads(s) for s in stream]
                if a!=b:raise ValueError('Profiling altered trace '+path.name)
                identity_rows+=len(a)
    output=[]
    for key in sorted(ranges):
        row=ranges[key];scale=1<<row['bits']
        row['calls_per_step']=row['count']/steps
        row['computed_per_step']=row['computed']/steps
        row['physical_ranges']={field:row[field]/scale for field in ('xmin','xmax','ymin','ymax','lmin','lmax','normalmax')}
        output.append(row)
    report={'cases':cases,'solver_steps':steps,'bit_identical_rows':identity_rows,'ranges':output,
            'units':'Inputs are metres or metres-per-step depending on caller; squared l fields are metres squared. Unit l is not measured.'}
    args.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'cases':cases,'steps':steps,'bit_identical_rows':identity_rows,'caller_groups':len(output)}))


if __name__=='__main__':main()
