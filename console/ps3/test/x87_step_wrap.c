// Host-only diagnostic for original Windows physics captures.
// Link the source-step fixture with --wrap=sin,--wrap=cos,--wrap=sincos.
// Each endpoint executes this CPU's separate x87 instruction and stores its
// result to binary64. This is not a portable PS3 implementation and does not
// emulate an entire x87 instruction stream. Keep production math unchanged.
#if !defined(__i386__) && !defined(__x86_64__)
#error "This diagnostic requires an x86 host"
#endif
#include <stdio.h>

static unsigned long long sine_calls, cosine_calls, combined_calls;

static double endpoint(double x, int cosine) {
    unsigned short saved, control = 0x027f;
    double result;
    __asm__ volatile("fnstcw %0" : "=m"(saved));
    __asm__ volatile("fldcw %0" :: "m"(control) : "memory");
    if (cosine)
        __asm__ volatile("fldl %1; fcos; fstpl %0"
                         : "=m"(result) : "m"(x) : "st");
    else
        __asm__ volatile("fldl %1; fsin; fstpl %0"
                         : "=m"(result) : "m"(x) : "st");
    __asm__ volatile("fldcw %0" :: "m"(saved) : "memory");
    return result;
}

double __wrap_sin(double x) {
    ++sine_calls;
    return endpoint(x, 0);
}
double __wrap_cos(double x) {
    ++cosine_calls;
    return endpoint(x, 1);
}
void __wrap_sincos(double x, double* sine, double* cosine) {
    ++combined_calls;
    *sine = endpoint(x, 0);
    *cosine = endpoint(x, 1);
}

__attribute__((destructor)) static void report(void) {
    fprintf(stderr, "x87 endpoint calls: sin=%llu cos=%llu sincos=%llu\n",
            sine_calls, cosine_calls, combined_calls);
}
