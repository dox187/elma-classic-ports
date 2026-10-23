// Validate the actual PCX writer against an independent bounded decoder.
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "all.h"
#undef fopen
#undef access
#undef remove
#undef rename
#include <cerrno>
#include <vector>
#include <string>
#include <sys/stat.h>

static int failure=0,warnings=0;
struct sprite_format_error {};
static bool expect_sprite_error=false;
static std::string absolute_path(const char* path) {
    if(path[0]=='/')return path;
    char cwd[1024]={};getcwd(cwd,sizeof(cwd));return std::string(cwd)+"/"+path;
}
#ifndef ELMA_PS3_NATIVE_TEST
static ssize_t full_write(void*,const char*,size_t n) {
    if(failure==1){errno=ENOSPC;return -1;}return n;
}
static int full_close(void*) {if(failure==2){errno=ENOSPC;return -1;}return 0;}
#endif
FILE* elma_fopen(const char* path,const char* mode) {
#ifndef ELMA_PS3_NATIVE_TEST
    if(failure && strstr(path,".tmp") && mode[0]=='w') {
        if(failure==3){errno=EACCES;return NULL;}
        cookie_io_functions_t io={};io.write=full_write;io.close=full_close;
        FILE* stream=fopencookie(NULL,"wb",io);
        if(failure==1 && stream)setvbuf(stream,NULL,_IONBF,0);
        return stream;
    }
#endif
    return fopen(absolute_path(path).c_str(),mode);
}
int elma_access(const char* path,int mode){return access(absolute_path(path).c_str(),mode);}
int elma_remove(const char* path){return remove(absolute_path(path).c_str());}
int elma_rename(const char* from,const char* to) {
    if(elma_access(to,0)==0){errno=EEXIST;return -1;}
    return rename(absolute_path(from).c_str(),absolute_path(to).c_str());
}
FILE* qopen(char* path,char* mode){return elma_fopen(path,mode);}
void qclose(FILE* file){fclose(file);}
void hiba(char* a,char* b,char*){if(expect_sprite_error)throw sprite_format_error{};fprintf(stderr,"%s %s\n",a,b?b:"");abort();}
void uzenet(char*,char*,char*){++warnings;}
void putpixel8_l(int,int,unsigned char){abort();}
unsigned ps3_memory_available(){return 128u*1024*1024;}
#define CHECK(c) do{if(!(c)){fprintf(stderr,"line %d: %s\n",__LINE__,#c);return 1;}}while(0)
static std::vector<unsigned char> read_file(const char* path) {
    std::vector<unsigned char> data;FILE* f=elma_fopen(path,"rb");if(!f)return data;
    int c;while((c=fgetc(f))!=EOF)data.push_back(c);fclose(f);return data;
}
static unsigned word(const std::vector<unsigned char>& data,int offset) {
    return data[offset]|unsigned(data[offset+1])<<8;
}
static bool decode_matches(const std::vector<unsigned char>& data,pic8& image,unsigned char* palette) {
    if(data.size()<897 || data[0]!=10 || data[1]!=5 || data[2]!=1 || data[3]!=8 || data[65]!=1)return false;
    const int width=word(data,8)+1,height=word(data,10)+1,stride=word(data,66);
    if(width!=image.getxsize() || height!=image.getysize() || stride!=((width+1)&~1))return false;
    for(int i=16;i<64;++i)if(data[i])return false;
    for(int i=70;i<128;++i)if(data[i])return false;
    size_t offset=128;
    for(int y=0;y<height;++y) {
        for(int x=0;x<stride;) {
            if(offset>=data.size())return false;
            unsigned char color=data[offset++];int count=1;
            if((color&0xc0)==0xc0) {count=color&63;if(!count || offset>=data.size())return false;color=data[offset++];}
            if(count>stride-x)return false;
            for(int n=0;n<count;++n,++x)if(color!=(x<width?image.gpixel(x,y):0))return false;
        }
    }
    if(offset+769!=data.size() || data[offset++]!=12)return false;
    for(int i=0;i<768;++i)if(data[offset+i]!=(palette?static_cast<unsigned char>(palette[i]<<2):i/3))return false;
    return true;
}
int main() {
#ifdef ELMA_PS3_NATIVE_TEST
    const char* directory="/dev_hdd0/game/ELMAC0001/USRDIR/screenshot-file-test";
    CHECK(mkdir(directory,0777)==0 || errno==EEXIST);CHECK(chdir(directory)==0);
#else
    char directory[]="/tmp/elma-pcx-XXXXXX";CHECK(mkdtemp(directory));CHECK(chdir(directory)==0);
#endif
    // Exercise the actual PS3 SPR loader, not only its stream validator.
    unsigned char encoded[]={0x2d,1,0,1,0,42,'S','P','R','I','T','E',0,2,0,'K',1};
    FILE* spr=elma_fopen("valid.spr","wb");CHECK(spr);
    CHECK(fwrite(encoded,1,sizeof(encoded),spr)==sizeof(encoded));CHECK(fclose(spr)==0);
    {pic8 loaded((char*)"valid.spr");CHECK(loaded.getxsize()==1);CHECK(loaded.getysize()==1);CHECK(loaded.gpixel(0,0)==42);}
    encoded[sizeof(encoded)-1]=0;
    spr=elma_fopen("bad.spr","wb");CHECK(spr);
    CHECK(fwrite(encoded,1,sizeof(encoded),spr)==sizeof(encoded));CHECK(fclose(spr)==0);
    bool rejected=false;expect_sprite_error=true;
    try{pic8 malformed((char*)"bad.spr");}catch(const sprite_format_error&){rejected=true;}
    expect_sprite_error=false;CHECK(rejected);
    elma_remove("valid.spr");elma_remove("bad.spr");
    puts("PASS actual SPR loader accepts valid runs and rejects zero-progress bytecode");
    unsigned char palette[768];for(int i=0;i<768;++i)palette[i]=i%64;
    pic8 image(129,7);
    for(int y=0;y<7;++y)for(int x=0;x<129;++x)image.ppixel(x,y,y==0?255:static_cast<unsigned char>(x*11+y*37));
    CHECK(image.save((char*)"screen.pcx",palette));
    const std::vector<unsigned char> original=read_file("screen.pcx");CHECK(decode_matches(original,image,palette));
    CHECK(image.save((char*)"screen.pcx",palette));CHECK(read_file("screen.pcx")==original);
#ifndef ELMA_PS3_NATIVE_TEST
    // Full disk during payload, delayed close failure, and denied open preserve
    // the previous complete capture and return to the game without fatal hiba.
    for(failure=1;failure<=3;++failure) {
        int before=warnings;CHECK(!image.save((char*)"screen.pcx",palette));
        CHECK(warnings==before+1);CHECK(read_file("screen.pcx")==original);
        CHECK(access("screen.pcx.tmp",F_OK)!=0);CHECK(access("screen.pcx.bak",F_OK)!=0);
    }
#endif
    failure=0;pic8 even(128,2);even.fillbox(64);
    CHECK(even.save((char*)"gray.pcx"));CHECK(decode_matches(read_file("gray.pcx"),even,NULL));
    uint64_t hash=UINT64_C(14695981039346656037);
    for(unsigned char byte:original)hash=(hash^byte)*UINT64_C(1099511628211);
    printf("PASS PCX pixels, palette, deterministic headers, replacement, odd/even rows hash=%016llx\n",static_cast<unsigned long long>(hash));
#ifndef ELMA_PS3_NATIVE_TEST
    printf("PASS three injected screenshot storage failures preserve previous capture\n");
    elma_remove("screen.pcx");elma_remove("gray.pcx");CHECK(chdir("/")==0);CHECK(rmdir(directory)==0);
#endif
}
