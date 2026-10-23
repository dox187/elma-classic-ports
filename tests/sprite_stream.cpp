#include "SPRITE_STREAM.H"
#include <cstdio>
static int errors;
#define CHECK(x) do{if(!(x)){std::fprintf(stderr,"line %d: %s\n",__LINE__,#x);++errors;}}while(0)
int main() {
    const unsigned char valid[]={'K',255,'N',1,'N',127,'K',129};
    CHECK(elma_sprite_stream_valid(valid,sizeof(valid),256,2));
    CHECK(!elma_sprite_stream_valid(valid,sizeof(valid)-1,256,2));
    CHECK(!elma_sprite_stream_valid(valid,sizeof(valid),255,2));
    CHECK(!elma_sprite_stream_valid(valid,sizeof(valid),256,3));
    const unsigned char zero[]={'N',0,'K',1},bad[]={'X',1},over[]={'K',2};
    CHECK(!elma_sprite_stream_valid(zero,sizeof(zero),1,1));
    CHECK(!elma_sprite_stream_valid(bad,sizeof(bad),1,1));
    CHECK(!elma_sprite_stream_valid(over,sizeof(over),1,1));
    const unsigned char padding[]={'K',1,255};
    CHECK(elma_sprite_stream_valid(padding,sizeof(padding),1,1));
    CHECK(!elma_sprite_stream_valid(NULL,100,1,1));
    CHECK(!elma_sprite_stream_valid(valid,sizeof(valid),0,2));
    CHECK(!elma_sprite_stream_valid(valid,sizeof(valid),256,0));
#ifdef ELMA_PS3
    FILE* output=std::fopen("/dev_hdd0/game/ELMAC0001/USRDIR/sprite-stream-result.txt","w");
    if(output){std::fprintf(output,"%s\n",errors?"FAIL":"PASS");std::fclose(output);}
#endif
    std::puts(errors?"FAIL":"PASS: SPR command boundaries, rows, progress and legacy trailing bytes");
    return errors?1:0;
}
