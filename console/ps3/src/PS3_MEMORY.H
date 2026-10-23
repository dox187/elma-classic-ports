#ifndef ELMA_PS3_MEMORY_H
#define ELMA_PS3_MEMORY_H
#include <cstdint>

struct Ps3RsxMemory {
    uint32_t used, peak, allocations, failures;
    bool complete;
};
// Requested application allocations, excluding allocator metadata and firmware
// reservations. This is not a query for total free video memory.
Ps3RsxMemory ps3_rsx_memory();
#endif
