#ifndef ELMA_LIBM_ENDIAN_H
#define ELMA_LIBM_ENDIAN_H
#if __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__
#define BIG_ENDI
#define HIGH_HALF 0
#define LOW_HALF 1
#else
#define LITTLE_ENDI
#define HIGH_HALF 1
#define LOW_HALF 0
#endif
#endif
