#!/usr/bin/env python3
"""Require byte-identical complete traces from two host kernels on fixed corpora."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--reference',type=Path,required=True)
    ap.add_argument('--candidate',type=Path,required=True)
    ap.add_argument('--corpus',type=Path,action='append',required=True)
    ap.add_argument('--gen',type=Path,default=Path('build/gen'))
    ap.add_argument('--levdump',type=Path,default=Path('build/host/levdump'))
    ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    cases={}
    for path in a.corpus:
        for c in json.loads(path.read_text()):
            key=(c['level'],c['script'])
            if key not in cases:cases[key]={'level':key[0],'script':key[1],'aliases':[]}
            cases[key]['aliases'].append(str(path.parent)+':'+c['id'])
    runs=[];started=time.monotonic()
    for case in cases.values():
        results=[]
        for name,host in [('reference',a.reference),('candidate',a.candidate)]:
            p=subprocess.run([str(host.resolve()),str(a.gen),str(a.levdump),str(case['level']),case['script'],'--trace-json'],
                             capture_output=True,text=True,timeout=180)
            if p.returncode:
                (a.out/(name+'-failure.stderr')).write_text(p.stderr)
                raise RuntimeError(name+' failed on '+str(case))
            results.append(p.stdout)
        if results[0]!=results[1]:
            for name,result in zip(['reference','candidate'],results):
                (a.out/(name+'-mismatch.jsonl')).write_text(result)
            (a.out/'failure-case.json').write_text(json.dumps(case,indent=2)+'\n')
            raise RuntimeError('Trace mismatch in '+str(case))
        runs.append({**case,'rows':results[0].count('\n'),
                     'trace_sha256':hashlib.sha256(results[0].encode()).hexdigest()})
    report={'exact':True,'unique_cases':len(runs),'rows':sum(x['rows'] for x in runs),
            'compared':'All serialized fields, full event masks, discrete/object state and actual candidate clock; identical bytes',
            'reference':str(a.reference),'candidate':str(a.candidate),
            'reference_sha256':digest(a.reference),'candidate_sha256':digest(a.candidate),
            'corpora_sha256':{str(p):digest(p) for p in a.corpus},'elapsed_seconds':time.monotonic()-started,'runs':runs}
    (a.out/'identity.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='runs'}))


if __name__=='__main__':main()
