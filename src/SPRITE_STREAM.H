#ifndef ELMA_SPRITE_STREAM_H
#define ELMA_SPRITE_STREAM_H
#include <cstddef>
// SPR commands describe each complete row as visible (K) or skipped (N)
// positive-length runs. The renderer assumes these bounds once loading succeeds.
inline bool elma_sprite_stream_valid(const unsigned char* data,std::size_t length,int width,int height) {
    if(!data || width<=0 || height<=0)return false;
    std::size_t position=0;
    for(int y=0;y<height;++y) {
        int x=0;
        while(x<width) {
            if(position>=length || length-position<2)return false;
            const unsigned char command=data[position++],count=data[position++];
            if((command!='K' && command!='N') || !count || count>width-x)return false;
            x+=count;
        }
    }
    // Older writers may retain unused trailing bytes; rendering ignores them.
    return true;
}
#endif
