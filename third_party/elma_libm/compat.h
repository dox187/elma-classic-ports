#ifndef ELMA_LIBM_COMPAT_H
#define ELMA_LIBM_COMPAT_H
// The game uses IEEE binary64 in round-to-nearest throughout; it does not
// change the floating-point environment or inspect underflow exception flags.
#define SET_RESTORE_ROUND_53BIT(mode) ((void)0)
#define math_check_force_underflow(x) ((void)0)
#define __set_errno(value) (errno=(value))
#ifndef __always_inline
#define __always_inline __attribute__((always_inline)) inline
#endif
#endif
