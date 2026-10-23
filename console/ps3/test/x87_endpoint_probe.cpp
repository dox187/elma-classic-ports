// Diagnostic only: pinned Bochs instruction endpoints versus this x86 CPU.
// The downloaded upstream sources retain their own licenses. No original
// executable/assets or third-party implementation is embedded here.
// Define NO_PROBE_MAIN to link only the candidate wrappers to a step fixture.
#include "bochs/cpu/fpu/fpu_trans.h"
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>
static uint64_t bits(double x) {
    uint64_t b;
    memcpy(&b, &x, 8);
    return b;
}
static double value(uint64_t b) {
    double x;
    memcpy(&x, &b, 8);
    return x;
}
extern "C" double __wrap_sin(double x) {
    softfloat_status_t s = {};
    s.softfloat_exceptionMasks = 0x3f;
    s.extF80_roundingPrecision = 80;
    floatx80 a = f64_to_extF80(bits(x), &s);
    fsin(a, s);
    return value(extF80_to_f64(a, &s));
}
extern "C" double __wrap_cos(double x) {
    softfloat_status_t s = {};
    s.softfloat_exceptionMasks = 0x3f;
    s.extF80_roundingPrecision = 80;
    floatx80 a = f64_to_extF80(bits(x), &s);
    fcos(a, s);
    return value(extF80_to_f64(a, &s));
}
extern "C" void __wrap_sincos(double x, double *s, double *c) {
    *s = __wrap_sin(x);
    *c = __wrap_cos(x);
}
#ifndef NO_PROBE_MAIN
#if !defined(__i386__) && !defined(__x86_64__)
#error "Endpoint hardware comparison requires an x86 host"
#endif
static void cpu_query(unsigned leaf, unsigned *a, unsigned *b, unsigned *c, unsigned *d) {
    __asm__ volatile("cpuid" : "=a"(*a), "=b"(*b), "=c"(*c), "=d"(*d) : "a"(leaf), "c"(0));
}
static uint64_t hash_value(uint64_t hash, double x) {
    uint64_t b = bits(x);
    for (int i = 0; i < 8; ++i) {
        hash ^= (b >> (i * 8)) & 255;
        hash *= UINT64_C(1099511628211);
    }
    return hash;
}
static void cpu_identity() {
    unsigned a, b, c, d;
    char vendor[13] = {}, brand[49] = {};
    cpu_query(0, &a, &b, &c, &d);
    memcpy(vendor, &b, 4);
    memcpy(vendor + 4, &d, 4);
    memcpy(vendor + 8, &c, 4);
    if ((cpu_query(0x80000000, &a, &b, &c, &d), a >= 0x80000004))
        for (unsigned i = 0; i < 3; ++i) {
            cpu_query(0x80000002 + i, &a, &b, &c, &d);
            memcpy(brand + i * 16, &a, 4);
            memcpy(brand + i * 16 + 4, &b, 4);
            memcpy(brand + i * 16 + 8, &c, 4);
            memcpy(brand + i * 16 + 12, &d, 4);
        }
    cpu_query(1, &a, &b, &c, &d);
    printf("CPU vendor=%s leaf1_eax=%08x brand=%s\n", vendor, a, brand);
}
static double hw(double x, bool cosine) {
    double y;
    if (cosine)
        __asm__ volatile("fldl %1; fcos; fstpl %0" : "=m"(y) : "m"(x) : "st");
    else
        __asm__ volatile("fldl %1; fsin; fstpl %0" : "=m"(y) : "m"(x) : "st");
    return y;
}
int main() {
    unsigned short saved, control = 0x027f;
    unsigned saved_mxcsr, mxcsr = 0x1f80;
    __asm__ volatile("fnstcw %0" : "=m"(saved));
    __asm__ volatile("stmxcsr %0" : "=m"(saved_mxcsr));
    __asm__ volatile("fldcw %0" ::"m"(control) : "memory");
    __asm__ volatile("ldmxcsr %0" ::"m"(mxcsr) : "memory");
    cpu_identity();
    printf("FP x87_control=%04x mxcsr=%08x\n", control, mxcsr);
    const clock_t start = clock();
    for (int range = 0; range < 2; ++range) {
        uint64_t rng = 12345678;
        unsigned diffs[2] = {}, libc[2] = {};
        uint64_t em_hash = UINT64_C(14695981039346656037), hw_hash = em_hash, libc_hash = em_hash;
        double extent = range ? 32. : 0x1.921fb54442d18p+1;
        for (unsigned i = 0; i < 1000000; ++i) {
            rng = rng * UINT64_C(6364136223846793005) + 1;
            double x = ((double)(rng >> 11) * 0x1p-53 * 2 - 1) * extent;
            for (int fn = 0; fn < 2; ++fn) {
                double em = fn ? __wrap_cos(x) : __wrap_sin(x), real = hw(x, fn),
                       soft = fn ? cos(x) : sin(x);
                em_hash = hash_value(em_hash, em);
                hw_hash = hash_value(hw_hash, real);
                libc_hash = hash_value(libc_hash, soft);
                if (bits(em) != bits(real)) {
                    if (diffs[fn] < 3)
                        printf("example range%d fn%d x=%016llx em=%016llx hw=%016llx\n", range, fn,
                               (unsigned long long)bits(x), (unsigned long long)bits(em),
                               (unsigned long long)bits(real));
                    ++diffs[fn];
                }
                if (bits(soft) != bits(real))
                    ++libc[fn];
            }
        }
        printf("range%d count1000000 sin_diffs=%u cos_diffs=%u glibc_sin_diffs=%u "
               "glibc_cos_diffs=%u\n",
               range, diffs[0], diffs[1], libc[0], libc[1]);
        printf("hash range%d candidate=%016llx hardware=%016llx glibc=%016llx\n", range,
               (unsigned long long)em_hash, (unsigned long long)hw_hash,
               (unsigned long long)libc_hash);
        fflush(stdout);
    }
    printf("CPU seconds %.3f\n", double(clock() - start) / CLOCKS_PER_SEC);
    __asm__ volatile("fldcw %0" ::"m"(saved) : "memory");
    __asm__ volatile("ldmxcsr %0" ::"m"(saved_mxcsr) : "memory");
    return 0;
}
#endif
