#include "elma_x87.h"
#include <stdint.h>
#include <cstdio>
#include <cstring>
#ifdef ELMA_X87_REFERENCE
extern "C" double __wrap_sin(double);
extern "C" double __wrap_cos(double);
#define SIN __wrap_sin
#define COS __wrap_cos
#else
#define SIN elma_x87_sin
#define COS elma_x87_cos
#endif
static uint64_t bits(double x) { uint64_t b; std::memcpy(&b,&x,8); return b; }
static uint64_t fold(uint64_t h,uint64_t b) {
    for(unsigned j=0;j<8;++j) { h^=(b>>(8*j))&255; h*=UINT64_C(1099511628211); }
    return h;
}
int main(int argc,char**) {
    // Exact signed-zero endpoints, independently known from x87 semantics.
    if(bits(SIN(0.0))!=0 || bits(SIN(-0.0))!=UINT64_C(0x8000000000000000)
       || bits(COS(0.0))!=UINT64_C(0x3ff0000000000000)
       || bits(COS(-0.0))!=UINT64_C(0x3ff0000000000000)) return 3;
    const unsigned count=argc>1?1000000:10000;
    for(unsigned range=0;range<2;++range) {
        uint64_t rng=12345678,h=UINT64_C(14695981039346656037);
        const double extent=range?32.0:3.141592653589793238462643383279502884;
        for(unsigned i=0;i<count;++i) {
            rng=rng*UINT64_C(6364136223846793005)+1;
            const double x=(double(rng>>11)*(1.0/9007199254740992.0)*2-1)*extent;
            const double s=SIN(x),c=COS(x);
#ifndef ELMA_X87_REFERENCE
            double bothS,bothC; elma_x87_sincos(x,&bothS,&bothC);
            if(bits(s)!=bits(bothS)||bits(c)!=bits(bothC)) return 2;
#endif
            h=fold(fold(h,bits(s)),bits(c));
        }
        std::printf("range%u count%u hash%016llx\n",range,count,(unsigned long long)h);
#ifndef ELMA_X87_REFERENCE
        // Generated with the separately built pinned reference, before this adapter.
        const uint64_t expected[2][2]={
            {UINT64_C(0x79edf89af501d600),UINT64_C(0xe8f21dec65cd14b8)},
            {UINT64_C(0xc0584f68b64d30e7),UINT64_C(0xbaf0ac95586293eb)}};
        if(h!=expected[argc>1?1:0][range]) return 1;
#endif
    }
    return 0;
}
