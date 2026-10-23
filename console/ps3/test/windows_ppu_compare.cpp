// Feed captured original Windows 1.11a one-step states to the native PPU engine.
// No Windows binary/code is linked; private captures remain outside source packages.
#define main original_fixture_main
#include "physics_trace.cpp"
#undef main
#include <cstddef>

static_assert(sizeof(double)==8 && sizeof(int)==4,"captured scalar widths");
static_assert(sizeof(vekt2)==16 && offsetof(vekt2,x)==0 && offsetof(vekt2,y)==8,"vector layout");
static_assert(sizeof(kor)==104 && offsetof(kor,nev)==0 && NEVHOSSZ==30,"circle/name layout");
#define OFF(type,field,value) static_assert(offsetof(type,field)==value,"captured " #type "." #field " layout")
OFF(kor,alfa,32); OFF(kor,omega,40); OFF(kor,sugar,48); OFF(kor,m,56); OFF(kor,theta,64); OFF(kor,r,72); OFF(kor,v,88);
static_assert(sizeof(motorst)==440,"captured motor layout");
OFF(motorst,kor1,0); OFF(motorst,kor2,104); OFF(motorst,kor4,208); OFF(motorst,fejr,312);
OFF(motorst,hatra_f,328); OFF(motorst,hatra_h,332); OFF(motorst,gravirany,336);
OFF(motorst,vezetor,344); OFF(motorst,vezetov,360); OFF(motorst,kajaszam,376); OFF(motorst,voltfek,380);
OFF(motorst,dfek2,384); OFF(motorst,dfek4,392); OFF(motorst,ugrasban1,400); OFF(motorst,ugrasban2,404);
OFF(motorst,ugras1kezd,408); OFF(motorst,ugras2kezd,416); OFF(motorst,kezdoomega1,424); OFF(motorst,kezdoomega2,432);
#undef OFF
static const size_t doubles[]={32,40,48,56,64,72,80,88,96,136,144,152,160,168,176,184,192,200,240,248,256,264,272,280,288,296,304,312,320,344,352,360,368,384,392,408,416,424,432};
static const size_t integers[]={328,332,336,376,380,400,404};
static uint64_t read64(const unsigned char* p) {uint64_t n=0;for(int i=7;i>=0;--i)n=(n<<8)|p[i];return n;}
static uint32_t read32(const unsigned char* p) {uint32_t n=0;for(int i=3;i>=0;--i)n=(n<<8)|p[i];return n;}
static void write64(unsigned char* p,uint64_t n) {for(int i=0;i<8;++i){p[i]=(unsigned char)n;n>>=8;}}
static void write32(unsigned char* p,uint32_t n) {for(int i=0;i<4;++i){p[i]=(unsigned char)n;n>>=8;}}
static void decode(const unsigned char raw[440],motorst* out) {
 // Preserve names and every opaque padding byte, then translate each scalar.
 memcpy(out,raw,440);unsigned char* dst=(unsigned char*)out;
 for(size_t off:doubles){uint64_t bits=read64(raw+off);memcpy(dst+off,&bits,8);}
 for(size_t off:integers){uint32_t bits=read32(raw+off);memcpy(dst+off,&bits,4);}
}
static void encode(const motorst& in,unsigned char raw[440]) {
 memcpy(raw,&in,440);const unsigned char* src=(const unsigned char*)&in;
 for(size_t off:doubles){uint64_t bits;memcpy(&bits,src+off,8);write64(raw+off,bits);}
 for(size_t off:integers){uint32_t bits;memcpy(&bits,src+off,4);write32(raw+off,bits);}
}
static bool read_motor(const char* directory,const char* stage,int index,unsigned char raw[440]) {
 char path[1024];snprintf(path,sizeof(path),"%s/%s-%d.bin",directory,stage,index);FILE* f=fopen(path,"rb");if(!f)return false;
 bool okay=fread(raw,1,440,f)==440&&fgetc(f)==EOF;fclose(f);return okay;
}
static uint64_t hash(uint64_t h,const unsigned char* data){for(size_t i=0;i<440;++i)h=(h^data[i])*UINT64_C(1099511628211);return h;}
static bool compare(const char* name,const char* level,const char* directory,FILE* report,int* count,int* exact) {
 if(!load(level))return false;
 char path[1024];snprintf(path,sizeof(path),"%s/inputs.txt",directory);FILE* inputs=fopen(path,"r");if(!inputs)return false;
 #ifdef ELMA_PS3
 snprintf(path,sizeof(path),"%s/ppu-canonical.bin",directory);
#else
 snprintf(path,sizeof(path),"%s/host-canonical.bin",directory);
#endif
 FILE* canonical=fopen(path,"wb");if(!canonical){fclose(inputs);return false;}
 int index,gaz,fek,u1,u2,total=0,matching=0,fields;
 unsigned long long mostbits,dtbits;uint64_t actualhash=UINT64_C(14695981039346656037),expectedhash=actualhash;
 while((fields=fscanf(inputs,"%d %llx %llx %d %d %d %d",&index,&mostbits,&dtbits,&gaz,&fek,&u1,&u2))==7) {
  unsigned char entryraw[440],expected[440],actual[440],roundtrip[440];motorst entry;
  if(!read_motor(directory,"entry",index,entryraw)||!read_motor(directory,"exit",index,expected)){fclose(inputs);fclose(canonical);return false;}
  decode(entryraw,&entry);encode(entry,roundtrip);
  if(memcmp(entryraw,roundtrip,440)){fprintf(report,"FAIL endian roundtrip %s index%d\n",name,index);fclose(inputs);fclose(canonical);return false;}
  double most,dt;memcpy(&most,&mostbits,8);memcpy(&dt,&dtbits,8);
  leptet(&entry,most,dt,gaz,fek,u1,u2);encode(entry,actual);++total;
  if(fwrite(actual,1,440,canonical)!=440){fclose(inputs);fclose(canonical);return false;}
  actualhash=hash(actualhash,actual);expectedhash=hash(expectedhash,expected);
  if(!memcmp(actual,expected,440))++matching;
  else {int changed=0;fprintf(report,"case %s index%d",name,index);
   for(size_t off=0;off<440;off+=8)if(memcmp(actual+off,expected+off,8)) {
    if(changed<12)fprintf(report," offset%u=%016llx/%016llx",(unsigned)off,(unsigned long long)read64(actual+off),(unsigned long long)read64(expected+off));++changed;
   }fprintf(report," differing-8byte-blocks=%d\n",changed);
  }
 }
 bool okay=fields==EOF&&!ferror(inputs)&&total>0;fclose(inputs);if(fclose(canonical))okay=false;
 fprintf(report,"complete %s %d exact %d differing %d actual-fnv64 %016llx expected-fnv64 %016llx\n",name,total,matching,total-matching,(unsigned long long)actualhash,(unsigned long long)expectedhash);fflush(report);
 *count+=total;*exact+=matching;return okay;
}
int main(int argc,char** argv) {
 setvbuf(stdout,NULL,_IONBF,0);
 const char* base="/dev_hdd0/game/ELMAC0001/USRDIR/windows-compare";
#ifndef ELMA_PS3
 if(argc!=2)return 2;
 base=argv[1];
#endif
 char path[1024];snprintf(path,sizeof(path),"%s/jobs.txt",base);FILE* jobs=fopen(path,"r");if(!jobs)return 2;
 snprintf(path,sizeof(path),"%s/ppu-result.txt",base);FILE* report=fopen(path,"w");if(!report)return 3;
 char name[128],level[1024],directory[1024];int total=0,exact=0,jobs_count=0,fields;bool okay=true;
 while((fields=fscanf(jobs,"%127s %1023s %1023s",name,level,directory))==3){++jobs_count;if(!compare(name,level,directory,report,&total,&exact)){okay=false;break;}}
 okay=okay&&fields==EOF&&!ferror(jobs)&&jobs_count>0;fclose(jobs);
 fprintf(report,"ALL %s jobs %d complete %d exact %d differing %d\n",okay&&total==exact?"PASS":"FAIL",jobs_count,total,exact,total-exact);fclose(report);
 printf("WINDOWS PPU RESULT %s jobs %d complete %d exact %d differing %d\n",okay&&total==exact?"PASS":"FAIL",jobs_count,total,exact,total-exact);return okay&&total==exact?0:1;
}
