#!/usr/bin/env python3
"""Isolated Q44 cubic grid12/Q48 coefficients with exact36-bit phase remainder.

The existing powergrid generator emits the same coefficients at u32; this
variant changes only the remainder scale to u36. PhaseQ48 d is copied exactly,
so no remainder rounding is introduced. Gameplay tolerance stays unchanged.
"""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--base',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 subprocess.run([sys.executable,'test/wide_native_trig_variant.py','--base',str(a.base),'--out',str(a.out),'--grid-shift','12','--remainder-bits','32','--coefficient-bits','48','--degree','3'],check=True)
 table=a.out/'wide_trig_table.h';source=table.read_text();assert '#define WIDE_NATIVE_TRIG_U_BITS 32' in source;table.write_text(source.replace('#define WIDE_NATIVE_TRIG_U_BITS 32','#define WIDE_NATIVE_TRIG_U_BITS 36'))
 meta=json.loads((a.out/'build.json').read_text());command=meta['command'];p=subprocess.run(command,capture_output=True,text=True);(a.out/'compile-u36.txt').write_text(p.stdout+p.stderr);p.check_returncode();meta['remainder_bits']=36;meta['change']=__doc__;meta['scalar_header_sha256']=hashlib.sha256((a.out/'wide_fixed.h').read_bytes()).hexdigest();meta['table_sha256']=hashlib.sha256(table.read_bytes()).hexdigest();(a.out/'build.json').write_text(json.dumps(meta,indent=2)+'\n');print(a.out/'widecheck')
if __name__=='__main__':main()
