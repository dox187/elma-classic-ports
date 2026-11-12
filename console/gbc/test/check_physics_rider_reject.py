"""Exhaust the integer regions skipped by the conservative rider bounds."""
import argparse,json,re
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--gen',type=Path,default=BASE/'build/gen');p.add_argument('--out',type=Path,default=BASE/'build/rider-reject-check');a=p.parse_args();text=(a.gen/'riding_constants.h').read_text();v={key:int(value)for key,value in re.findall(r'#define (\w+) (-?\d+)(?:\n|$)',text)}
row=re.search(r'#define RIDING_ELLIPSE_INSIDE_Y_VALUES ([\d,]+)',text);assert row,'generate current riding_constants.h first';table=list(map(int,row[1].split(',')))
def kmul(x,name):return max(-32768,min(32767,(x*v[name+'_M']+(1<<(v[name+'_E']-1)))>>v[name+'_E']))
right,top=v['RIDER_RIGHT'],v['RIDER_TOP'];shift=v['RIDING_ELLIPSE_BUCKET_SHIFT'];assert len(table)==(right>>shift)+1
ellipse_pairs=0
for x in range(1,right+1):
 xs=kmul(x,'C_ELLIPSE')
 for y in range(1,top+1):
  assert y>table[x>>shift]or xs*xs+y*y<=top*top,(x,y,table[x>>shift])
  ellipse_pairs+=1
seat_pairs=0;low=32767;high=-32768
if v['RIDING_SEAT_FAST_ENABLED']:
 for x in range(-32768,v['RIDING_SEAT_FAST_X']+1):
  sx=x-v['SEAT_X'];assert -32768<=sx<=32767
  nx=kmul(sx,'C_SEAT_NX')
  for y in range(v['RIDING_SEAT_FAST_Y'],top+1):
   sy=y-v['SEAT_Y'];assert -32768<=sy<=32767
   under=kmul(sy,'C_SEAT_NY')-nx
   assert 0<=under<=32767,(x,y,under)
   low=min(low,under);high=max(high,under);seat_pairs+=1
report={'ellipse_integer_pairs':ellipse_pairs,'seat_integer_pairs':seat_pairs,'ellipse_table_bytes':len(table)*2,'minimum_seat_under':low,'maximum_seat_under':high,'differences':0};a.out.mkdir(parents=True,exist_ok=True);(a.out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
