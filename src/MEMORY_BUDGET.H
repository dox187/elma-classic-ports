#ifndef ELMA_MEMORY_BUDGET_H
#define ELMA_MEMORY_BUDGET_H
#include <cstdint>
// Conservative peak estimates include both source and destination plus all
// intermediate RGB/mask/filter buffers. They do not affect physics.
inline uint64_t elma_filter_peak(int xs,int ys,int dx,int dy,int scale) {
    return uint64_t(xs+4)*uint64_t(ys+4)*(uint64_t(20)*scale*scale+24)
         + uint64_t(dx)*uint64_t(dy)*6 + 512*1024;
}
inline bool elma_memory_fits(uint64_t needed,uint64_t available) {
    const uint64_t reserve=24u*1024u*1024u;
    return available>reserve && needed<=available-reserve;
}
// PS3 logical framebuffers are bounded separately from sharp-scaling targets.
// Existing vector capacities remain live while a growing vector allocates its
// replacement. Do not credit those allocations before the operation succeeds.
inline bool elma_framebuffer_fits(int w,int h,uint64_t pixel_capacity,uint64_t row_capacity,uint64_t available) {
    if(w<=0 || h<=0 || w>4096 || h>2400)return false;
    const uint64_t pixels=uint64_t(w)*uint64_t(h);
    if(pixels>4u*1024u*1024u)return false;
    const uint64_t growth=(pixels>pixel_capacity?pixels:0)
        +(uint64_t(h)>row_capacity?uint64_t(h)*sizeof(void*):0)+65536;
    return elma_memory_fits(growth,available);
}
// The old LGR is freed before decoding its replacement. Brushes remain
// until decoding finishes, then are freed before constructing new brushes.
inline bool elma_graphics_memory_fits(uint64_t lgr,uint64_t temporary,uint64_t brush,
                                      uint64_t available,uint64_t old_lgr,uint64_t old_brush) {
    return elma_memory_fits(lgr+temporary,available+old_lgr)
        && elma_memory_fits(lgr+brush,available+old_lgr+old_brush);
}
#ifdef ELMA_PS3
#include <cstddef>
unsigned ps3_memory_available();
#endif
#endif
