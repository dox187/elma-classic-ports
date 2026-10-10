#!/usr/bin/env python3
"""Compare separately built trig iterations over an identical case prefix."""
import argparse,hashlib,json,statistics
from pathlib import Path

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--samples',type=int,default=100);ap.add_argument('--out',type=Path,default=Path('build/native-q44-trig-iterations.json'));ap.add_argument('artifacts',type=Path,nargs='*');a=ap.parse_args();folders=a.artifacts or [Path('build')/p for p in ['native-q44-trig-generic-final','native-q44-trig-small-final','native-q44-trig-fast-final','native-q44-trig-square-v1','native-q44-trig-best-final','native-q44-trig-index-final']];records=[];reference=None;errors=[]
 for folder in folders:
  report=json.loads((folder/'check.json').read_text());raw=(folder/'results.bin').read_bytes();clocks=list(map(int,(folder/'clocks.txt').read_text().split()));count=min(a.samples,report['cases']);outputs=[raw[20*i:20*i+18]for i in range(count)]
  if count!=a.samples:errors.append(str(folder)+': insufficient identical-prefix samples')
  if report['differences']:errors.append(str(folder)+': failed correctness check')
  if reference is None:reference=outputs
  elif outputs!=reference:errors.append(str(folder)+': output prefix differs')
  groups={}
  for name,flag in [('miss',0),('hit',1)]:
   values=[clocks[i]for i in range(count)if int.from_bytes(raw[20*i+18:20*i+20],'little')==flag]
   groups[name]={'samples':len(values),'median':statistics.median(values),'mean':statistics.mean(values),'min':min(values),'max':max(values)}
  records.append({'artifact':str(folder),'validated_cases':report['cases'],'latch_injections':report['latch_injections'],'rom_sha256':report['rom_sha256'],'same_prefix_master_clocks':groups,'flags':{k:report.get(k,False)for k in ['specialized_products','control_fast','square_fast','short_products','index_fast']}})
 first=records[0]['same_prefix_master_clocks']['miss']['median']
 for r in records:r['miss_median_reduction_vs_first_percent']=100*(1-r['same_prefix_master_clocks']['miss']['median']/first)
 result={'scope':'Isolated original-Q48 trig precision-preserving native iterations; entry/exit clocks exclude caller setup/JSL/RTL. No full solver fidelity or sustained FPS claim. Prefix contains deterministic edges and seeded inputs; anchor-heavy full runs are not used for this comparison.','samples_per_iteration':a.samples,'same_output_prefix':not errors,'errors':errors,'iterations':records};a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return bool(errors)
if __name__=='__main__':raise SystemExit(main())
