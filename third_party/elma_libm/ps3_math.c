// The PSL1GHT newlib trigonometry uses a low precision approximation, even
// cos(0) differs from 1. Use the desktop reference implementation unchanged.
extern double elma_sin(double);
extern double elma_cos(double);
double sin(double x) { return elma_sin(x); }
double cos(double x) { return elma_cos(x); }
void sincos(double x,double* s,double* c) { *s=elma_sin(x);*c=elma_cos(x); }
