"""Exact contact sign shortcut against the original complete force formula."""
from pathlib import Path
import subprocess,ctypes as C,random,json
B=Path(__file__).resolve().parents[1];P=B/'build/contact-sign-check';P.mkdir(parents=True,exist_ok=True)
wrap='''#ifdef REFERENCE
#define sure_new candidate_new
#define sure_old candidate_old
#endif
#include "physics_contacts.c"
#ifdef REFERENCE
#undef sure_new
#undef sure_old
static uint8_t sure_new(const contact_t *a,const contact_t *b,const circle_t *k){int32_t vn=riding_dotq32(k->vx,k->vy,-b->ny,b->nx,14);int32_t m=k->omega+KMUL32(riding_mulshift32(vn,b->l,10),C_NEW);int16_t d=dotq14(a->tx-b->tx,a->ty-b->ty,-b->ny,b->nx);return same_side(d,m);}
static uint8_t sure_old(const contact_t *a,const contact_t *b,int32_t vx,int32_t vy,int16_t tq){int32_t vn=riding_dotq32(vx,vy,-b->ny,b->nx,14);int32_t p=riding_mulshift32(vn,b->l,6);int32_t m=(int32_t)tq+KMUL32(p,C_OLD);int16_t d=dotq14(a->tx-b->tx,a->ty-b->ty,-b->ny,b->nx);return same_side(d,m);}
#endif
void seg_query(uint8_t x,uint8_t y,uint8_t s){}const seg_t *seg_next(void){return 0;}
uint8_t check_new(int16_t x,int16_t y,int16_t nx,int16_t ny,int16_t l,int32_t vx,int32_t vy,int16_t omega){contact_t a={0,0,0,x,y},b={nx,ny,l,0,0};circle_t k={0};k.vx=vx;k.vy=vy;k.omega=omega;return sure_new(&a,&b,&k);}
uint8_t check_old(int16_t x,int16_t y,int16_t nx,int16_t ny,int16_t l,int32_t vx,int32_t vy,int16_t tq){contact_t a={0,0,0,x,y},b={nx,ny,l,0,0};return sure_old(&a,&b,vx,vy,tq);}
'''
libs=[]
for name,folder in(('original',B/'src'),('candidate',B/'src')):
 path=P/(name+'-sign.c');path.write_text(wrap);lib=P/(name+'-sign.dylib');subprocess.run(['cc','-shared','-fPIC','-O2',*(['-DREFERENCE']if name=='original'else[]),'-fwrapv','-Wno-unknown-pragmas','-I'+str(folder),'-I'+str(B/'src'),'-I'+str(B/'build/all-physics'),str(path),str(B/'src/physics_math.c'),str(B/'src/physics_math32.c'),'-o',str(lib)],check=True);libs.append(C.CDLL(str(lib)))
 for key in('check_new','check_old'):getattr(libs[-1],key).argtypes=[C.c_int16]*5+[C.c_int32]*2+[C.c_int16]
r=random.Random(545456);cases=[];v=[-2**31,-32769,-32768,-1,0,1,32767,32768,2**31-1];w=[-32768,-1,0,1,32767];ls=[-32768,-1,0,1,244,410,32767]
for speed in v:
 for omega in w:
  for length in ls:
   for nx,ny in((0,16384),(16384,0),(10000,-12000),(-32768,32767)):
    for x,y in((0,0),(1,0),(-1,0),(10,-20)):
     cases.append((x,y,nx,ny,length,speed,v[(v.index(speed)+2)%len(v)],omega))
for _ in range(50000):cases.append(tuple(r.randint(-32768,32767)for _ in range(5))+tuple(r.randint(-2**31,2**31-1)for _ in range(2))+(r.randint(-32768,32767),))
for i,args in enumerate(cases):
 for key in('check_new','check_old'):
  a,b=(getattr(lib,key)(*args)for lib in libs)
  assert a==b,(i,key,args,a,b)
report={'cases_per_function':len(cases),'functions':2,'differences':0};(P/'sign-report.json').write_text(json.dumps(report,indent=2)+'\n');print(report)
