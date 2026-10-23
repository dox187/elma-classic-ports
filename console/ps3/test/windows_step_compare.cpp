// Compare captured private Windows PE physics-step snapshots with shared sources.
// Captures/assets are user-provided ignored build artifacts; no Windows code is linked.
#define main original_fixture_main
#include "physics_trace.cpp"
#undef main
#include <cstddef>
static bool read_motor(const char* directory,const char* stage,int index,motorst* out) {
 char path[1024];snprintf(path,sizeof(path),"%s/%s-%d.bin",directory,stage,index);
 FILE* f=fopen(path,"rb");if(!f)return false;bool okay=fread(out,1,sizeof(*out),f)==sizeof(*out) && fgetc(f)==EOF;fclose(f);return okay;
}
int main(int argc,char** argv) {
 if(argc!=4)return 2;
 static_assert(sizeof(motorst)==440,"PE/common motor layout mismatch");
 static_assert(offsetof(motorst,voltfek)==0x17c,"PE brake layout mismatch");
 if(!load(argv[1]))return 3;
 char path[1024];snprintf(path,sizeof(path),"%s/inputs.txt",argv[2]);FILE* inputs=fopen(path,"r");if(!inputs)return 4;
 FILE* out=fopen(argv[3],"w");if(!out)return 5;
 int index,gaz,fek,u1,u2,total=0,matching=0;unsigned long long mostbits,dtbits;
 while(fscanf(inputs,"%d %llx %llx %d %d %d %d",&index,&mostbits,&dtbits,&gaz,&fek,&u1,&u2)==7) {
  motorst entry,expected;if(!read_motor(argv[2],"entry",index,&entry)||!read_motor(argv[2],"exit",index,&expected))return 6;
  double most,dt;memcpy(&most,&mostbits,8);memcpy(&dt,&dtbits,8);
  leptet(&entry,most,dt,gaz,fek,u1,u2);++total;
  if(!memcmp(&entry,&expected,sizeof(entry)))++matching;
  else {int changed=0;fprintf(out,"case %d",index);
   const unsigned char *actual=(const unsigned char*)&entry,*want=(const unsigned char*)&expected;
   for(size_t off=0;off<sizeof(entry);off+=8)if(memcmp(actual+off,want+off,8)) {
    uint64_t a,b;memcpy(&a,actual+off,8);memcpy(&b,want+off,8);
    if(changed<12)fprintf(out," offset%zu=%016llx/%016llx",off,(unsigned long long)a,(unsigned long long)b);++changed;
   }
   fprintf(out," differing-8byte-blocks=%d\n",changed);
  }
 }
 fprintf(out,"complete %d exact %d differing %d\n",total,matching,total-matching);fclose(out);fclose(inputs);return total>0 && matching==total ? 0 : 1;
}
