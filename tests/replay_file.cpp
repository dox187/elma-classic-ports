// Exercise the actual recorder and its on-disk format on LE host and BE PPU.
#include "all.h"
#undef fopen
#undef access
#undef remove
#undef rename
#include <cerrno>
#include <string>
#include <vector>
#include <sys/stat.h>

double K_pi=3.141592, K_2pi=6.283184;
int Aafogo=0, Kozelvannak=0, Sarvari=0, Palyaszam=55;
static int warnings=0;
static std::string path(const char* name) {
    std::string p(name);for(size_t i=0;i<p.size();++i)if(p[i]=='\\')p[i]='/';
    if(p.empty() || p[0]!='/'){char cwd[1024]={};getcwd(cwd,sizeof(cwd));p=std::string(cwd)+"/"+p;}
    return p;
}
FILE* elma_fopen(const char* name,const char* mode){return fopen(path(name).c_str(),mode);}
int elma_access(const char* name,int mode){return access(path(name).c_str(),mode);}
int elma_remove(const char* name){return remove(path(name).c_str());}
int elma_rename(const char* from,const char* to){
    if(access(path(to).c_str(),0)==0){errno=EEXIST;return -1;}
    return rename(path(from).c_str(),path(to).c_str());
}
FILE* qopen(char* name,char* mode){return elma_fopen(name,mode);}
void qclose(FILE* f){fclose(f);}
int nevanalizis(char*){return 1;}
void hiba(char* a,char* b,char* c){fprintf(stderr,"%s %s %s\n",a,b?b:"",c?c:"");abort();}
void uzenet(char*,char*,char*){++warnings;}
#define CHECK(x) do{if(!(x)){fprintf(stderr,"line %d: %s\n",__LINE__,#x);return 1;}}while(0)

static uint64_t byte_hash(uint64_t hash,unsigned char byte){return (hash^byte)*UINT64_C(1099511628211);}
static uint64_t number_hash(uint64_t hash,double value){
    uint64_t bits;memcpy(&bits,&value,8);
    for(int i=0;i<8;++i)hash=byte_hash(hash,static_cast<unsigned char>(bits>>(8*i)));
    return hash;
}
static uint64_t playback_hash(recorder& rec){
    uint64_t hash=UINT64_C(14695981039346656037);rec.rewind();
    for(int i=0;i<160;++i){
        motorst m={};hanginfo h={};
        hash=byte_hash(hash,rec.recall(&m,double(i)/64,&h));
        const double values[]={m.kor1.r.x,m.kor1.r.y,m.kor2.r.x,m.kor2.r.y,
            m.kor4.r.x,m.kor4.r.y,m.vezetor.x,m.vezetor.y,m.kor1.alfa,
            m.kor2.alfa,m.kor4.alfa,h.frekvencia,h.surlero};
        for(double value:values)hash=number_hash(hash,value);
        hash=byte_hash(hash,h.gaz);hash=byte_hash(hash,m.hatra_f);
        hash=byte_hash(hash,Aafogo);hash=byte_hash(hash,Kozelvannak);
    }
    return hash;
}
static uint64_t file_hash(const char* name){
    FILE* f=elma_fopen(name,"rb");if(!f)return 0;
    uint64_t hash=UINT64_C(14695981039346656037);int byte;
    while((byte=fgetc(f))!=EOF)hash=byte_hash(hash,byte);fclose(f);return hash;
}
static void record(recorder& rec,int player){
    rec.erase((char*)"QWQUU001.LEV");
    for(int i=0;i<160;++i){
        motorst m={};double x=player*32+double(i)/8, y=-double(i)/16;
        m.kor1.r=vekt2(x,y);m.kor2.r=vekt2(x-.75,y-.5);
        m.kor4.r=vekt2(x+.875,y-.5);m.vezetor=vekt2(x,y+.25);
        m.kor1.alfa=(i%80)/16.;m.kor2.alfa=(i%48)/8.;m.kor4.alfa=(i%40)/8.;
        m.hatra_f=i%2;Aafogo=(i/4)%2;Kozelvannak=(i/8)%2;
        hanginfo h={1.5,static_cast<char>(i%2),.75};
        rec.store(&m,double(i)/64,&h);
    }
    rec.addhang(.25,2,.5,7);rec.addhang(.5,4,.25,-1);
}
int main(){
#ifdef ELMA_PS3_NATIVE_TEST
    const char* root="/dev_hdd0/game/ELMAC0001/USRDIR/replay-file-test";
    mkdir(root,0777);CHECK(chdir(root)==0);
#else
    char root[]="/tmp/elma-replay-XXXXXX";CHECK(mkdtemp(root));CHECK(chdir(root)==0);
#endif
    CHECK(mkdir(path("rec").c_str(),0777)==0 || errno==EEXIST);
    Prec1=new recorder;Prec2=new recorder;
    for(int multi=0;multi<2;++multi){
        record(*Prec1,0);record(*Prec2,1);Multirec=multi;
        uint64_t before1=playback_hash(*Prec1),before2=playback_hash(*Prec2);
        const char* name=multi?"MULTI.rec":"SINGLE.rec";
        saverecek((char*)name,0x12345678,multi);
        uint64_t first=file_hash(multi?"rec/MULTI.rec":"rec/SINGLE.rec");CHECK(first);
        // Golden bytes from the Linux little-endian recorder, including the
        // two serialized riders and sound-event records in multiplayer.
        CHECK(first==(multi?UINT64_C(0x35582120fa62b5b2):UINT64_C(0x98a0ba57ae05a2ce)));
        CHECK(before1==UINT64_C(0x8dceea78862cde2e));
        CHECK(before2==UINT64_C(0xb52f6381789c686d));
        saverecek((char*)name,0x12345678,multi); // Existing-file replace path.
        CHECK(first==file_hash(multi?"rec/MULTI.rec":"rec/SINGLE.rec"));
        Prec1->erase((char*)"CLEARED");Prec2->erase((char*)"CLEARED");Multirec=1-multi;
        CHECK(loadrecek((char*)name,0)==0x12345678);CHECK(Multirec==multi);
        CHECK(ps3_replay_loaded());
        CHECK(!strcmp(Prec1->palyanev,"QWQUU001.LEV"));CHECK(Prec1->gettag()==multi);
        CHECK(playback_hash(*Prec1)==before1);
        if(multi){CHECK(playback_hash(*Prec2)==before2);CHECK(Prec2->gettag()==1);}
        Prec1->rewind();char wav=0;double volume=0;int object=0;
        CHECK(!Prec1->gethang(.125,&wav,&volume,&object));
        CHECK(Prec1->gethang(.25,&wav,&volume,&object));CHECK(wav==2 && volume==.5 && object==7);
        CHECK(Prec1->gethang(.5,&wav,&volume,&object));CHECK(wav==4 && volume==.25 && object==-1);
        CHECK(!Prec1->gethang(9,&wav,&volume,&object));CHECK(warnings==0);
        // Validation checks presence only; it must not dereference objects.
        kerek* objects[MAXKEREK]={};
        CHECK(!Prec1->objects_exist(objects));objects[7]=reinterpret_cast<kerek*>(Prec1);
        CHECK(Prec1->objects_exist(objects));
        printf("replay-%s file=%016llx rider1=%016llx rider2=%016llx\n",multi?"multi":"single",
            (unsigned long long)first,(unsigned long long)before1,(unsigned long long)before2);
    }
    CHECK(loadrecek((char*)"MISSING.rec",0)==0);CHECK(!ps3_replay_loaded());CHECK(warnings==1);
    FILE* good=elma_fopen("rec/MULTI.rec","rb");CHECK(good);
    CHECK(fseek(good,0,SEEK_END)==0);long length=ftell(good);CHECK(length>100);
    rewind(good);std::vector<unsigned char> original(size_t(length),0);
    CHECK(fread(original.data(),1,original.size(),good)==original.size());fclose(good);
    const unsigned frames=original[0]|unsigned(original[1])<<8|unsigned(original[2])<<16|unsigned(original[3])<<24;
    for(int damage=0;damage<8;++damage){
        std::vector<unsigned char> bad=original;
        switch(damage){
        case 0: bad.resize(35);break; // Truncated header.
        case 1: bad[0]=bad[1]=bad[2]=bad[3]=255;break; // Negative frame count.
        case 2: bad[8]=2;break; // Invalid rider count.
        case 3: bad[36]=0;bad[37]=0;bad[38]=192;bad[39]=127;break; // NaN coordinate.
        case 4: bad[36+27*frames]=255;bad[37+27*frames]=127;break; // Excess sound count.
        case 5: bad.back()^=1;break; // Second rider's marker.
        case 6: memset(bad.data()+20,'A',16);break; // Unterminated name.
        case 7: bad[36+27*frames+4+16+10]=127;break; // Effect outside loaded bank.
        }
        FILE* f=elma_fopen("rec/BAD.rec","wb");CHECK(f);
        CHECK(fwrite(bad.data(),1,bad.size(),f)==bad.size());CHECK(fclose(f)==0);
        CHECK(loadrecek((char*)"BAD.rec",0)==0);CHECK(!ps3_replay_loaded());
        CHECK(warnings==damage+2);CHECK(playback_hash(*Prec1)==UINT64_C(0x8dceea78862cde2e));
    }
    saverecek((char*)"ZERO.rec",0,1); // Zero is a valid original-level stamp.
    CHECK(loadrecek((char*)"ZERO.rec",0)==0);CHECK(ps3_replay_loaded());
    puts("PASS: replay bytes, poses, sounds, replacement and corruption rejection");
#ifndef ELMA_PS3_NATIVE_TEST
    remove("rec/SINGLE.rec");remove("rec/MULTI.rec");remove("rec/BAD.rec");remove("rec/ZERO.rec");
    rmdir("rec");chdir("/");rmdir(root);
#endif
    return 0;
}
