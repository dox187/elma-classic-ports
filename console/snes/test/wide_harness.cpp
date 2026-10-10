// Trace adapter for the isolated wide integer PC kernel. Output conversions
// use host double only to serialize numerical state for the fidelity reader.
#include <string>
#include <vector>
#include "all.h"
#include "pcphys.h"

struct wide_item {int key=0,turn=0,n=0,warp=-2;};
static std::vector<wide_item> parse(const char* p){
    std::vector<wide_item> out;
    while(*p){while(*p==' '||*p=='\t')++p;if(!*p)break;wide_item item;
        if(*p=='W'||*p=='X'){bool leave=*p++=='X';item.warp=(int)strtol(p,(char**)&p,10);if(leave)item.warp=-1;out.push_back(item);continue;}
        while(*p&&strchr("GBRLTN",*p)){switch(*p++){case 'G':item.key|=1;break;case 'B':item.key|=2;break;case 'R':item.key|=4;break;case 'L':item.key|=8;break;case 'T':item.turn=1;break;}}
        item.n=(int)strtol(p,(char**)&p,10);if(item.n<=0)item.n=1;out.push_back(item);
    }return out;
}
static void emit(int step,int key,int turn,int event,int stopped){
    auto statistics=wide_stats; // serialization's unit conversion is not solver work
    pc_state s;pc_get(&s);std::vector<wide_scalar> fields;
    const auto speed=wide_scalar::literal("0.4368");
    for(auto c:s.c){fields.insert(fields.end(),{c.r.x,c.r.y,c.v.x*speed,c.v.y*speed,c.alfa,c.omega*speed});}
    fields.insert(fields.end(),{s.rider_r.x,s.rider_r.y,s.rider_v.x*speed,s.rider_v.y*speed,s.head.x,s.head.y});
    printf("{\"step\":%d,\"key\":%d,\"turn\":%d,\"pc_time_game\":%.17g,\"pc_event\":%d,\"pc_stopped\":%d,\"pc\":[",step,key,turn,pc_time.output_double(),event,stopped);
    for(size_t i=0;i<fields.size();++i)printf("%s%.17g",i?",":"",fields[i].output_double());
    printf("],\"pc_discrete\":[%d,%d,%d],\"pc_objects\":[",s.turned,s.gravity,s.apples);
    for(int i=0;i<pc_nobjs;++i)printf("%s%d",i?",":"",pc_obj_active[i]);
    printf("],\"pc_apple_object\":%d}\n",event&4?pc_eaten:-1);
    wide_stats=statistics;
}
static int32_t signed32(const std::vector<unsigned char>& b,size_t p){return int32_t(uint32_t(b[p])|(uint32_t(b[p+1])<<8)|(uint32_t(b[p+2])<<16)|(uint32_t(b[p+3])<<24));}
static void warp(int object,const std::vector<unsigned char>& blob){
    pc_state s;pc_get(&s);wide_scalar dx=2000,dy=0;
    if(object>=0){unsigned p=blob[18]+256*blob[19]+12*object;
        dx=wide_scalar::from_raw(wide_checked((__int128)signed32(blob,p+4)*(int64_t(1)<<(WIDE_BITS-16)),"warp x"))-s.c[1].r.x;
        dy=wide_scalar::from_raw(wide_checked((__int128)signed32(blob,p+8)*(int64_t(1)<<(WIDE_BITS-16)),"warp y"))-s.c[1].r.y;}
    for(auto& c:s.c){c.r.x+=dx;c.r.y+=dy;}s.rider_r.x+=dx;s.rider_r.y+=dy;s.head.x+=dx;s.head.y+=dy;pc_set(&s);
}
int main(int argc,char** argv){
    if(argc<5){fprintf(stderr,"widecheck GEN LEVDUMP LEVEL SCRIPT --trace-json\n");return 2;}
    int level=atoi(argv[3]);char path[1024];snprintf(path,sizeof(path),"%s/lev%02d.txt",argv[2],level);
    if(!pc_load(path)){fprintf(stderr,"wide load failed: %s\n",path);return 2;}
    wide_print_stats("initialization",wide_stats);wide_stats={};
    snprintf(path,sizeof(path),"%s/phys/lev%02d.bin",argv[1],level);FILE* f=fopen(path,"rb");if(!f)return 2;
    std::vector<unsigned char> blob(65536);size_t size=fread(blob.data(),1,blob.size(),f);fclose(f);blob.resize(size);
    std::vector<int> keys,turns,warps;
    for(auto item:parse(argv[4])){if(item.warp!=-2){warps.resize(keys.size()+1,-2);warps[keys.size()]=item.warp;}
        else for(int i=0;i<item.n;++i){keys.push_back(item.key);turns.push_back(item.turn&&i==0);}}
    warps.resize(keys.size()+1,-2);int stopped=0,steps=0;
    const auto dt=wide_scalar::literal("0.00546");
    emit(0,0,0,0,0);
    for(size_t i=0;i<keys.size();++i){if(warps[i]!=-2)warp(warps[i],blob);int event=0;
        if(!stopped){event=pc_step(keys[i],dt);++steps;stopped=(event&3)!=0;if(turns[i]&&!stopped)pc_turn();}
        emit(int(i+1),keys[i],turns[i],event,stopped);
        // Frozen termination extension is performed by the strict comparator.
        if(stopped)break;
    }
    fprintf(stderr,"WIDE_STEPS %d\n",steps);wide_print_stats("simulation",wide_stats);
}
