// Reading the data banks: a linear address of the data selects a bank of
// 8 KB at $8000.
#ifndef FAR_H
#define FAR_H

#include <stdint.h>

// Maps the bank of a linear address and returns where it is.
const uint8_t* far_ptr( uint32_t lin );

#endif
