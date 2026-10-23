#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <math.h>
#ifndef ELMA_MATH_REFERENCE
extern double elma_sin(double);
extern double elma_cos(double);
#define TEST_SIN elma_sin
#define TEST_COS elma_cos
#else
#define TEST_SIN sin
#define TEST_COS cos
#endif
// Frozen glibc FMA reference over arbitrary finite binary64 inputs. Hash
// numeric IEEE bits, not byte addresses, so big and little endian agree.
static uint64_t hash(uint64_t sum,double d) {
    uint64_t bits;memcpy(&bits,&d,8);
    for(int i=0;i<8;++i) {sum^=(bits>>(i*8))&255u;sum*=UINT64_C(1099511628211);}
    return sum;
}
int main(void) {
    uint64_t rng=12345678,sum=UINT64_C(14695981039346656037);
    for(int i=0;i<1000000;++i) {
        rng=rng*UINT64_C(6364136223846793005)+1;
        if(((rng>>52)&2047)==2047)continue;
        double x;memcpy(&x,&rng,8);
        sum=hash(sum,TEST_SIN(x));sum=hash(sum,TEST_COS(x));
    }
    printf("%016llx\n",(unsigned long long)sum);
#ifdef ELMA_MATH_REFERENCE
    return 0;
#else
    return sum!=UINT64_C(0xd606934ef31fc787);
#endif
}
