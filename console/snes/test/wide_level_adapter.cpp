// Host trace adapter for the complete C solver and snapshot loader.
// No original C++ solver or level construction is linked into this executable.
#include "all.h"
#include "pcphys.h"
#define WIDE_PORT_BRIDGE
#include "wide_port.h"
#include <vector>
#include <string>
extern "C" int wp_load_level(const unsigned char*);
extern "C" int wp_load_level_parts(const unsigned char*,const unsigned char* const*);
static std::vector<unsigned char> blob;
#ifdef WIDE_LEVEL_SPLIT_HOST
static std::vector<unsigned char> level_sections[8];
#endif
static int load_snapshot(){
#ifdef WIDE_LEVEL_SPLIT_HOST
    const unsigned char* parts[7];
    level_sections[0].assign(blob.begin(),blob.begin()+20);
    for(unsigned i=0;i<7;++i){
        unsigned first=0,last=0;
        for(unsigned k=0;k<4;++k){
            first|=unsigned(blob[20+4*i+k])<<(8*k);
            last|=unsigned(blob[24+4*i+k])<<(8*k);
        }
        level_sections[i+1].assign(blob.begin()+first,blob.begin()+last);
        parts[i]=level_sections[i+1].data();
    }
    return wp_load_level_parts(level_sections[0].data(),parts);
#else
    return wp_load_level(blob.data());
#endif
}
wide_scalar pc_friction,pc_bump,pc_time;
int pc_eaten,pc_nobjs,pc_obj_type[52],pc_obj_active[52];
static wide_scalar scalar(wp_scalar x){return wide_scalar::from_raw(x);}
static void sync(){
    pc_nobjs=*wp_ptr_pc_nobjs();pc_eaten=*wp_ptr_pc_eaten();
    pc_friction=scalar(*wp_ptr_pc_friction());pc_bump=scalar(*wp_ptr_pc_bump());pc_time=scalar(*wp_ptr_pc_time());
    for(int i=0;i<pc_nobjs;++i){auto* o=(*wp_ptr_Ptop())->kerektomb[i];pc_obj_type[i]=o->tipus;pc_obj_active[i]=o->aktiv;}
}
extern "C" int pc_load(const char* path){
    const char* name=strrchr(path,'/');name=name?name+1:path;int level=-1;
    if(sscanf(name,"lev%d.txt",&level)!=1)return 0;
    char file[1024];snprintf(file,sizeof(file),"%s/lev%02d.bin",WIDE_LEVEL_DIRECTORY,level);
    FILE* f=fopen(file,"rb");if(!f)return 0;fseek(f,0,SEEK_END);long n=ftell(f);rewind(f);
    blob.resize(n);bool ok=fread(blob.data(),1,n,f)==(size_t)n;fclose(f);
    if(!ok||!load_snapshot())return 0;sync();return 1;
}
extern "C" void pc_reset(){if(!load_snapshot())abort();sync();}
extern "C" int pc_step(int input,wide_scalar dt){int ev=wp_pc_step(input,dt.raw);sync();return ev;}
extern "C" void pc_turn(){wp_pc_turn();sync();}
static pc_vec vec(wp_vec v){return {scalar(v.x),scalar(v.y)};}
static wp_vec vec(pc_vec v){return {v.x.raw,v.y.raw};}
extern "C" void pc_get(pc_state* state){
    auto* m=*wp_ptr_Pmot1();wp_kor* circles[]={&m->kor1,&m->kor2,&m->kor4};
    for(int i=0;i<3;++i){auto* c=circles[i];auto& s=state->c[i];
        s.r=vec(c->r);s.v=vec(c->v);s.alfa=scalar(c->alfa);s.omega=scalar(c->omega);}
    state->rider_r=vec(m->vezetor);state->rider_v=vec(m->vezetov);state->head=vec(m->fejr);
    state->turned=m->hatra_f;state->gravity=m->gravirany;state->apples=m->kajaszam;
}
extern "C" void pc_set(const pc_state* state){
    auto* m=*wp_ptr_Pmot1();wp_kor* circles[]={&m->kor1,&m->kor2,&m->kor4};
    for(int i=0;i<3;++i){auto* c=circles[i];auto& s=state->c[i];
        c->r=vec(s.r);c->v=vec(s.v);c->alfa=s.alfa.raw;c->omega=s.omega.raw;}
    m->vezetor=vec(state->rider_r);m->vezetov=vec(state->rider_v);m->fejr=vec(state->head);
    m->hatra_f=state->turned;m->gravirany=state->gravity;m->kajaszam=state->apples;
}
