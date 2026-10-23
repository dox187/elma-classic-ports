#ifndef ELMA_LGR_BUDGET_H
#define ELMA_LGR_BUDGET_H
#include "LE_IO.H"
#include "MEMORY_BUDGET.H"
#include <algorithm>
#include <cmath>
#include <vector>
#include <cctype>
#include <climits>
struct elma_lgr_budget { uint64_t persistent, temporary; };
struct elma_lgr_shape { char name[21]; unsigned width,height; };
// Read only format metadata. No pixel arrays or filter buffers are allocated.
// Include conservative worst-case RLE/mask storage, original decoded image,
// and the largest simultaneously retained destination/compression buffers.
inline bool elma_estimate_lgr(FILE* f,double zoom,elma_lgr_budget* result,double texture_zoom=-1,double grass_zoom=-1,std::vector<elma_lgr_shape>* shapes=NULL) {
    if(!f || !(zoom>0) || zoom>100)return false;
    if(texture_zoom<0)texture_zoom=zoom;if(grass_zoom<0)grass_zoom=zoom;
    if(!(texture_zoom>0) || !(grass_zoom>0) || texture_zoom>100 || grass_zoom>100)return false;
    char magic[6]={};int32_t pictures=0,version=0,count=0;
    if(fread(magic,1,5,f)!=5 || (strcmp(magic,"LGR12") && strcmp(magic,"LGR13")) ||
       elma_read(&pictures,4,1,f)!=1 || pictures<10 || pictures>3500 ||
       elma_read(&version,4,1,f)!=1 || version!=1002 ||
       elma_read(&count,4,1,f)!=1 || count<0 || count>3000) return false;
    std::vector<char> names(size_t(count)*10);
    std::vector<int32_t> types(count);
    if(fread(names.data(),10,count,f)!=size_t(count) || elma_read(types.data(),4,count,f)!=size_t(count) || fseek(f,long(count)*12,SEEK_CUR)) return false;
    for(int i=0;i<count;++i)if(!memchr(names.data()+size_t(i)*10,0,10))return false;
    uint64_t total=4u*1024*1024,maxsource=0,maxextra=0;
    for(int i=0;i<pictures;++i) {
        char name[21]={};int16_t tx=0,ty=0;int32_t length=0;
        if(fread(name,1,20,f)!=20 || !memchr(name,0,20)) return false;
        if(magic[4]=='3' && (elma_read(&tx,2,1,f)!=1 || elma_read(&ty,2,1,f)!=1))return false;
        if(elma_read(&length,4,1,f)!=1 || length<5 || length>10000000)return false;
        long start=ftell(f);if(start<0 || length>LONG_MAX-start)return false;
        unsigned char pcx[128]={};
        size_t header=std::min(size_t(length),sizeof(pcx));
        if(fread(pcx,1,header,f)!=header)return false;
        unsigned sx=0,sy=0;
        if(pcx[0]==10 && header==128 && pcx[1]==5 && pcx[2]==1 && pcx[3]==8 && pcx[65]==1) {
            unsigned x0=pcx[4]|unsigned(pcx[5])<<8,y0=pcx[6]|unsigned(pcx[7])<<8;
            unsigned x1=pcx[8]|unsigned(pcx[9])<<8,y1=pcx[10]|unsigned(pcx[11])<<8;
            if(x1<x0 || y1<y0)return false;
            sx=x1-x0+1;sy=y1-y0+1;
            unsigned stride=pcx[66]|unsigned(pcx[67])<<8;
            if(stride<sx || stride>32767)return false;
        } else if(pcx[0]==0x2d) {
            sx=pcx[1]|unsigned(pcx[2])<<8;sy=pcx[3]|unsigned(pcx[4])<<8;
            if(!sx || !sy)return false;
        } else return false;
        for(size_t k=0;k<20;++k)name[k]=char(std::tolower(static_cast<unsigned char>(name[k])));
        int type=0;
        for(int j=0;j<count;++j) {
            const char* candidate=&names[size_t(j)*10];size_t n=0;while(n<10 && candidate[n])++n;
            bool equal=true;for(size_t k=0;k<n;++k)if(name[k]!=std::tolower(static_cast<unsigned char>(candidate[k])))equal=false;
            if(equal && (name[n]=='.' || name[n]==0)){type=types[j];break;}
        }
        bool grass=!strncmp(name,"qup_",4) || !strncmp(name,"qdown_",6) || !strcmp(name,"qgrass.pcx") || !strcmp(name,"qgrass.spr");
        double factor=grass?grass_zoom:type==101?texture_zoom:zoom;
        if(!strncmp(name,"q1bike.",7) || !strncmp(name,"q2bike.",7) || !strncmp(name,"qcolors.",8) || !strncmp(name,"qframe.",7))factor=1;
        const double dx=ceil((tx>0?tx:sx)*factor),dy=ceil((ty>0?ty:sy)*factor);
        if(dx<1 || dy<1 || dx>32767 || dy>32767 || sx>32767 || sy>32767)return false;
        if(shapes) {
            elma_lgr_shape shape={};strcpy(shape.name,name);
            char* dot=strchr(shape.name,'.');if(dot)*dot=0;
            shape.width=unsigned(dx);shape.height=unsigned(dy);shapes->push_back(shape);
        }
        // The software renderer repeats narrow textures to at least 600 pixels.
        uint64_t width=uint64_t(dx);
        if((type==101 || !strncmp(name,"qgrass.",7)) && width<600)width*=((600+width-1)/width);
        uint64_t pixels=width*uint64_t(dy);
        unsigned multiplier=type==101?1:type==100?3:type==102?8:2;
        total+=pixels*multiplier+uint64_t(dy)*64;
        maxsource=std::max(maxsource,uint64_t(sx)*sy+uint64_t(sy)*16);
        maxextra=std::max(maxextra,pixels*multiplier);
        if(fseek(f,start+length,SEEK_SET))return false;
    }
    int32_t checksum=0;if(elma_read(&checksum,4,1,f)!=1 || checksum!=187565543)return false;
    result->persistent=total;result->temporary=maxsource+maxextra+2u*1024*1024;
    return true;
}
// The old library is released only after this admission succeeds. Credit it
// exactly once; existing brushes remain live and are already excluded from free.
enum elma_lgr_admission { ELMA_LGR_INVALID, ELMA_LGR_TOO_LARGE, ELMA_LGR_ACCEPT };
inline elma_lgr_admission elma_admit_lgr(FILE* file,double zoom,double texture_zoom,
                                        double grass_zoom,uint64_t available,uint64_t old_lgr) {
    elma_lgr_budget budget={};
    if(!elma_estimate_lgr(file,zoom,&budget,texture_zoom,grass_zoom))return ELMA_LGR_INVALID;
    return elma_memory_fits(budget.persistent+budget.temporary,available+old_lgr)
        ? ELMA_LGR_ACCEPT : ELMA_LGR_TOO_LARGE;
}
#endif
