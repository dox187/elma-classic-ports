/* The math functions of the PS1 build. PSn00bSDK has no <math.h>; the
 * double precision functions come from the vendored musl subset
 * (third_party/musl-libm) on libgcc's soft-float doubles. Only what the game
 * core and the musl files use is declared. */
#ifndef ELMA_PSX_MATH_H
#define ELMA_PSX_MATH_H

#ifdef __cplusplus
extern "C" {
#endif

/* GCC evaluates doubles in double precision on the R3000 (FLT_EVAL_METHOD
 * is 0), so these are the plain types: */
typedef double double_t;
typedef float float_t;

#define HUGE_VAL __builtin_huge_val()
#define INFINITY __builtin_inff()
#define NAN __builtin_nanf("")

#define isnan(x) __builtin_isnan(x)
#define isinf(x) __builtin_isinf(x)
#define isfinite(x) __builtin_isfinite(x)
#define signbit(x) __builtin_signbit(x)

#define M_PI 3.14159265358979323846

double sin(double x);
double cos(double x);
double atan(double x);
double atan2(double y, double x);
double exp(double x);
double sqrt(double x);
double floor(double x);
double ceil(double x);
double fabs(double x);
double scalbn(double x, int n);

#ifdef __cplusplus
}
#endif

#endif
