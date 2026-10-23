#ifndef ELMA_X87_H
#define ELMA_X87_H
#ifdef __cplusplus
extern "C" {
#endif
// Binary64 -> emulated standalone FSIN/FCOS (extended80) -> binary64.
// Round to nearest/even, all exceptions masked. No allocation or global mode.
double elma_x87_sin(double value);
double elma_x87_cos(double value);
// Two standalone instructions, intentionally NOT the FSINCOS instruction.
void elma_x87_sincos(double value, double* sine, double* cosine);
#ifdef __cplusplus
}
#endif
#endif
