#include "MEMORY_BUDGET.H"
int main() {
    if(elma_memory_fits(1,24u*1024*1024))return 1;
    if(!elma_memory_fits(32u*1024*1024,64u*1024*1024))return 2;
    if(elma_memory_fits(elma_filter_peak(4096,4096,8192,8192,4),256u*1024*1024))return 3;
    if(!elma_memory_fits(elma_filter_peak(320,240,640,480,2),128u*1024*1024))return 4;
    if(elma_filter_peak(32767,32767,32767,32767,4)<=UINT32_MAX)return 5;
    const uint64_t mb=1024u*1024u;
    // 4x assets plus a small map remain allowed; large map construction
    // is refused. Admission credits buffers freed in each rebuild phase.
    if(!elma_graphics_memory_fits(85*mb,26*mb,20*mb,150*mb,10*mb,5*mb))return 6;
    if(elma_graphics_memory_fits(85*mb,26*mb,160*mb,150*mb,10*mb,5*mb))return 7;
    if(!elma_graphics_memory_fits(80*mb,20*mb,40*mb,50*mb,80*mb,20*mb))return 8;
    // Old brushes are not available during LGR decode, only afterwards.
    if(elma_graphics_memory_fits(80*mb,70*mb,10*mb,50*mb,80*mb,100*mb))return 9;
    if(!elma_framebuffer_fits(1920,1080,640*480,480,64*mb))return 10;
    if(!elma_framebuffer_fits(2048,2048,0,0,64*mb))return 11;
    if(elma_framebuffer_fits(4096,2400,0,0,256*mb))return 12;
    if(elma_framebuffer_fits(INT32_MAX,INT32_MAX,0,0,UINT64_MAX))return 13;
    if(elma_framebuffer_fits(0,480,0,0,UINT64_MAX))return 14;
    // Growth needs the full replacement allocation, since the old vector
    // remains live until allocation succeeds. Reuse requires only reserve.
    const uint64_t rows=1080*sizeof(void*),pixels=1920*1080;
    if(elma_framebuffer_fits(1920,1080,640*480,480,24*mb+pixels+rows+65535))return 15;
    if(!elma_framebuffer_fits(1920,1080,pixels,1080,24*mb+65536))return 16;
    return 0;
}
