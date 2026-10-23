#define _GNU_SOURCE
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
#include <dlfcn.h>
#define WINAPI __attribute__((ms_abi))
extern void* WINAPI LoadLibraryA(const char*);
extern void* WINAPI GetProcAddress(void*,const char*);
extern unsigned long WINAPI GetLastError(void);
extern unsigned long WINAPI GetModuleFileNameA(void*,char*,unsigned long);
typedef double (WINAPI *mathfn)(double);
typedef int (WINAPI *getflag)(void);
typedef int (WINAPI *controlfn)(unsigned*,unsigned,unsigned);
static uint64_t bits(double x){uint64_t value;memcpy(&value,&x,8);return value;}
static uint64_t hash(uint64_t sum,double x){uint64_t value=bits(x);for(int j=0;j<8;++j){sum^=(value>>(j*8))&255;sum*=UINT64_C(1099511628211);}return sum;}
static uint64_t order(double x){uint64_t value=bits(x);return value>>63?~value:value|UINT64_C(0x8000000000000000);}
static uint64_t distance(double a,double b){uint64_t x=order(a),y=order(b);return x>y?x-y:y-x;}
int main(){
 void*m=LoadLibraryA("ucrt-native.dll");if(!m){printf("load error%lu\n",GetLastError());return 2;}
 mathfn native_sin=(mathfn)GetProcAddress(m,"sin"),native_cos=(mathfn)GetProcAddress(m,"cos"),native_sqrt=(mathfn)GetProcAddress(m,"sqrt");
 getflag fma=(getflag)GetProcAddress(m,"_get_FMA3_enable");controlfn control=(controlfn)GetProcAddress(m,"_controlfp_s");
 if(!native_sin||!native_cos||!native_sqrt)return 3;
 char path[1024]={};GetModuleFileNameA(m,path,sizeof(path));unsigned fp=0;if(control)control(&fp,0,0);
 Dl_info info={};dladdr((void*)sin,&info);
 printf("DLL %s\nhost_libm %s\nfma_enabled %d controlfp %08x mxcsr %08x\n",path,info.dli_fname?info.dli_fname:"?",fma?fma():-1,fp,__builtin_ia32_stmxcsr());
 for(int small=0;small<2;++small){
  uint64_t rng=12345678,host_hash=UINT64_C(14695981039346656037),native_hash=host_hash;
  unsigned tested=0,sm=0,cm=0,sqrt_m=0;uint64_t max_s=0,max_c=0,max_q=0;double max_abs_s=0,max_abs_c=0;
  for(int i=0;i<1000000;++i){rng=rng*UINT64_C(6364136223846793005)+1;if(((rng>>52)&2047)==2047)continue;
   double x;memcpy(&x,&rng,8);if(small)x=(double)(rng>>11)*0x1p-53*64-32;
   double hs=sin(x),hc=cos(x),ns=native_sin(x),nc=native_cos(x);
   host_hash=hash(hash(host_hash,hs),hc);native_hash=hash(hash(native_hash,ns),nc);++tested;
   if(bits(hs)!=bits(ns)){if(sm<3)printf("%s sin input=%016llx host=%016llx native=%016llx\n",small?"small":"arbitrary",(unsigned long long)bits(x),(unsigned long long)bits(hs),(unsigned long long)bits(ns));++sm;uint64_t d=distance(hs,ns);if(d>max_s)max_s=d;double delta=fabs(hs-ns);if(delta>max_abs_s)max_abs_s=delta;}
   if(bits(hc)!=bits(nc)){if(cm<3)printf("%s cos input=%016llx host=%016llx native=%016llx\n",small?"small":"arbitrary",(unsigned long long)bits(x),(unsigned long long)bits(hc),(unsigned long long)bits(nc));++cm;uint64_t d=distance(hc,nc);if(d>max_c)max_c=d;double delta=fabs(hc-nc);if(delta>max_abs_c)max_abs_c=delta;}
   if(x>=0){double a=sqrt(x),b=native_sqrt(x);if(bits(a)!=bits(b)){++sqrt_m;uint64_t d=distance(a,b);if(d>max_q)max_q=d;}}
  }
  printf("RESULT %s tested=%u host_hash=%016llx native_hash=%016llx sin_mismatches=%u cos_mismatches=%u max_sin_ulp=%llu max_cos_ulp=%llu max_sin_absolute=%.17g max_cos_absolute=%.17g sqrt_mismatches=%u max_sqrt_ulp=%llu\n",small?"small[-32,32]":"arbitrary",tested,(unsigned long long)host_hash,(unsigned long long)native_hash,sm,cm,(unsigned long long)max_s,(unsigned long long)max_c,max_abs_s,max_abs_c,sqrt_m,(unsigned long long)max_q);
 }
 return 0;
}
