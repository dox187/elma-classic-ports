#include "PS3_MEMORY.H"
#include <atomic>
#include <cstddef>

extern "C" void* __real_rsxMemalign(uint32_t alignment, uint32_t size);
extern "C" void* __real_rsxMalloc(uint32_t size);
extern "C" void __real_rsxFree(void* pointer);

namespace {
struct Allocation { void* pointer; uint32_t size; };
// Fixed diagnostic storage must never allocate from the heap it observes.
Allocation live[128] = {};
Ps3RsxMemory totals = {0, 0, 0, 0, true};
std::atomic_flag gate = ATOMIC_FLAG_INIT;
struct Lock {
    Lock() { while (gate.test_and_set(std::memory_order_acquire)) {} }
    ~Lock() { gate.clear(std::memory_order_release); }
};
void remember(void* pointer, uint32_t size) {
    if (!pointer) { ++totals.failures; return; }
    for (Allocation& entry : live) if (!entry.pointer) {
        entry.pointer = pointer;
        entry.size = size;
        totals.used += size;
        if (totals.used > totals.peak) totals.peak = totals.used;
        ++totals.allocations;
        return;
    }
    // Preserve the real allocator result even if diagnostic capacity is full.
    // The flag remains false: subsequent counters are only a lower bound.
    totals.complete = false;
}
}

extern "C" void* __wrap_rsxMemalign(uint32_t alignment, uint32_t size) {
    Lock lock;
    void* pointer = __real_rsxMemalign(alignment, size);
    remember(pointer, size);
    return pointer;
}
extern "C" void* __wrap_rsxMalloc(uint32_t size) {
    Lock lock;
    void* pointer = __real_rsxMalloc(size);
    remember(pointer, size);
    return pointer;
}
extern "C" void __wrap_rsxFree(void* pointer) {
    Lock lock;
    if (pointer) for (Allocation& entry : live) if (entry.pointer == pointer) {
        totals.used -= entry.size;
        --totals.allocations;
        entry = Allocation{};
        break;
    }
    __real_rsxFree(pointer);
}
Ps3RsxMemory ps3_rsx_memory() {
    Lock lock;
    return totals;
}
