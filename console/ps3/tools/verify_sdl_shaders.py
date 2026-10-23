#!/usr/bin/env python3
"""Reassemble original quad shaders without Cg Toolkit; check embedded bytes."""
import argparse,pathlib,re,struct,subprocess,tempfile
p=argparse.ArgumentParser();p.add_argument('sdl_source',type=pathlib.Path);a=p.parse_args()
root=pathlib.Path(__file__).resolve().parents[1]
source=(a.sdl_source/'src/render/psl1ght/SDL_PSL1GHTrender.c').read_text()
with tempfile.TemporaryDirectory(prefix='elma-quad-') as temp:
 for name,stage,expected_count in [('quad','vp',2),('quad','fp',1),('solid','vp',3),('solid','fp',1),('pixelart','vp',5),('pixelart','fp',16)]:
  binary=pathlib.Path(temp)/(name+'.'+stage+'o')
  subprocess.run(['cgcomp','-a','-'+stage[0],str(root/'sdk'/('elma_'+name+'.'+stage)),str(binary)],check=True)
  identifier='elma_'+('' if name=='quad' else name+'_')+stage
  match=re.search(identifier+r'\[\].*?= \{(.*?)\};',source,re.S)
  if not match:raise SystemExit('Missing embedded '+stage)
  actual_count=struct.unpack_from('>H',binary.read_bytes(),10)[0]
  if actual_count!=expected_count:raise SystemExit('Unexpected instruction count: '+stage)
  embedded=bytes(int(x,16) for x in re.findall(r'0x([0-9a-f]{2})',match.group(1)))
  if embedded!=binary.read_bytes():raise SystemExit('Shader bytes differ: '+stage)
print('PASS: original RSX quad assembly reproduces all embedded shaders')
