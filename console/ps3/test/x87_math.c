// Diagnostic only: Linux x86/x86_64 hardware x87 endpoints versus host glibc.
// FSIN/FCOS/FSQRT are stored to binary64 before comparison; this does not
// emulate a complete x87 instruction stream or establish game-step parity.
// Build: cc -O2 -fno-builtin -ffp-contract=off x87_math.c -lm -o x87-math
#if !defined(__i386__) && !defined(__x86_64__)
#error "This diagnostic requires an x86 host; do not build it for PS3"
#endif
#define _GNU_SOURCE
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <gnu/libc-version.h>
static double fsin64(double x){double y;__asm__ volatile("fldl %1; fsin; fstpl %0":"=m"(y):"m"(x):"st");return y;}
static double fcos64(double x){double y;__asm__ volatile("fldl %1; fcos; fstpl %0":"=m"(y):"m"(x):"st");return y;}
static double fsqrt64(double x){double y;__asm__ volatile("fldl %1; fsqrt; fstpl %0":"=m"(y):"m"(x):"st");return y;}
static uint64_t bits(double x){uint64_t b;memcpy(&b,&x,8);return b;}
static uint64_t ordered(double x){uint64_t b=bits(x);return b>>63?~b:b|UINT64_C(0x8000000000000000);}
static uint64_t distance(double a,double b){uint64_t x=ordered(a),y=ordered(b);return x>y?x-y:y-x;}
static uint64_t hash(uint64_t h,double x){uint64_t b=bits(x);for(int i=0;i<8;++i){h^=(b>>(i*8))&255;h*=UINT64_C(1099511628211);}return h;}
int main(void){
 unsigned short saved;unsigned saved_mxcsr;
 __asm__ volatile("fnstcw %0":"=m"(saved));__asm__ volatile("stmxcsr %0":"=m"(saved_mxcsr));
 unsigned mxcsr=0x1f80;__asm__ volatile("ldmxcsr %0"::"m"(mxcsr));
 printf("glibc %s saved_cw=%04x mxcsr=%08x\n",gnu_get_libc_version(),saved,saved_mxcsr);
 for(int precision=0;precision<2;++precision){
  unsigned short cw=precision?0x037f:0x027f;__asm__ volatile("fldcw %0"::"m"(cw):"memory");
  for(int range=0;range<2;++range){
   const double extent=range?32.:0x1.921fb54442d18p+1;
   uint64_t rng=12345678,hh=UINT64_C(14695981039346656037),xh=hh,max[3]={0};unsigned mismatch[3]={0}; double max_input[3]={0},max_absolute[3]={0};
   double (*host[3])(double)={sin,cos,sqrt};double (*hw[3])(double)={fsin64,fcos64,fsqrt64};
   for(unsigned i=0;i<1000000;++i){
    rng=rng*UINT64_C(6364136223846793005)+1;
    double x=((double)(rng>>11)*0x1p-53*2-1)*extent;
    for(int fn=0;fn<3;++fn){double input=fn==2?fabs(x):x;double a=host[fn](input),b=hw[fn](input);
     hh=hash(hh,a);xh=hash(xh,b);
     if(bits(a)!=bits(b)){if(mismatch[fn]<2)printf("example cw=%04x range=%d fn=%d input=%016llx host=%016llx x87=%016llx\n",cw,range,fn,(unsigned long long)bits(input),(unsigned long long)bits(a),(unsigned long long)bits(b));++mismatch[fn];uint64_t d=distance(a,b);if(d>max[fn]){max[fn]=d;max_input[fn]=input;} double delta=fabs(a-b);if(delta>max_absolute[fn])max_absolute[fn]=delta;}
    }
   }
   printf("result cw=%04x extent=%.17g count=1000000 host_hash=%016llx x87_hash=%016llx sin_differences=%u cos_differences=%u sqrt_differences=%u max_sin_ulp=%llu max_cos_ulp=%llu max_sqrt_ulp=%llu max_sin_ulp_input=%.17g max_cos_ulp_input=%.17g max_sin_absolute=%.17g max_cos_absolute=%.17g\n",cw,extent,(unsigned long long)hh,(unsigned long long)xh,mismatch[0],mismatch[1],mismatch[2],(unsigned long long)max[0],(unsigned long long)max[1],(unsigned long long)max[2],max_input[0],max_input[1],max_absolute[0],max_absolute[1]);
  }
 }
 __asm__ volatile("fldcw %0"::"m"(saved):"memory");__asm__ volatile("ldmxcsr %0"::"m"(saved_mxcsr):"memory");return 0;
}
