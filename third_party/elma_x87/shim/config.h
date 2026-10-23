#ifndef ELMA_X87_BOCHS_CONFIG_H
#define ELMA_X87_BOCHS_CONFIG_H
// Standalone build adapter; not an upstream Bochs configure output.
#include <stdint.h>
typedef uint16_t Bit16u;
typedef int16_t Bit16s;
typedef uint32_t Bit32u;
typedef int32_t Bit32s;
typedef uint64_t Bit64u;
typedef int64_t Bit64s;
#define BX_CONST64(x) x##ULL
#define BX_CPP_INLINE inline
#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
#define BX_LITTLE_ENDIAN 1
#elif defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__
#define BX_BIG_ENDIAN 1
#else
#error "elma_x87 requires compiler-provided byte order"
#endif
#if defined(__GNUC__) || defined(__clang__)
#define BX_HAVE___BUILTIN_CLZ 1
#else
#define BX_HAVE___BUILTIN_CLZ 0
#endif
#ifdef __SIZEOF_INT128__
#define BX_HAVE_INT128 1
#else
#define BX_HAVE_INT128 0
#endif
static_assert(sizeof(Bit16u)==2 && sizeof(Bit32u)==4 && sizeof(Bit64u)==8,
              "Bochs fixed-width integer ABI");
#endif
