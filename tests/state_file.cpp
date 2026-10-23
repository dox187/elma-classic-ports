// Actual encrypted state serializer, with PS3's no-replace rename semantics.
#include "all.h"
#undef fopen
#undef access
#undef remove
#undef rename
#include <cerrno>
#include <sys/stat.h>
static int warnings;
int Sarvari=0;
state_s* State=NULL;
static void absolute_path(const char* path,char* out){
    if(path[0]=='/')snprintf(out,1024,"%s",path);
    else {char cwd[1024]={};getcwd(cwd,sizeof(cwd));snprintf(out,1024,"%s/%s",cwd,path);}
}
FILE* elma_fopen(const char* path,const char* mode){char out[1024];absolute_path(path,out);return fopen(out,mode);}
int elma_access(const char* path,int mode){char out[1024];absolute_path(path,out);return access(out,mode);}
int elma_remove(const char* path){char out[1024];absolute_path(path,out);return remove(out);}
int elma_rename(const char* from,const char* to){char source[1024],target[1024];absolute_path(from,source);absolute_path(to,target);if(access(target,0)==0){errno=EEXIST;return -1;}return rename(source,target);}
#define fopen elma_fopen
#define access elma_access
#define remove elma_remove
#define rename elma_rename
void hiba(char* text,char*,char*){fprintf(stderr,"%s\n",text);abort();}
void uzenet(char*,char*,char*){++warnings;}
void di_reset_state(state_s* state){memset(&state->opciok1,0,sizeof(state->opciok1));memset(&state->opciok2,0,sizeof(state->opciok2));state->billplussz=state->billminusz=state->billsnap=0;}
#define CHECK(x) do{if(!(x)){fprintf(stderr,"line%d: %s\n",__LINE__,#x);return 1;}}while(0)
int main(){
#ifdef ELMA_PS3_NATIVE_TEST
    const char* root="/dev_hdd0/game/ELMAC0001/USRDIR/state-file-test";mkdir(root,0777);CHECK(chdir(root)==0);
#else
    char root[]="/tmp/elma-state-XXXXXX";CHECK(mkdtemp(root));CHECK(chdir(root)==0);
#endif
    remove("state.dat");remove("state.dat.bak");remove("state.dat.tmp");
    state_s state;memset(state.jatekosa,0,sizeof(state.jatekosa));memset(state.jatekosb,0,sizeof(state.jatekosb));memset(state.editfilenev,0,sizeof(state.editfilenev));memset(state.playextfilenev,0,sizeof(state.playextfilenev));state.jatekosokszama=1;strcpy(state.jatekosok[0].nev,"Rider");strcpy(state.jatekosa,"Rider");strcpy(state.jatekosb,"Rider");
    state.palyakidejei[0].singleidok.idokszama=1;state.palyakidejei[0].singleidok.idok[0]=1652;strcpy(state.palyakidejei[0].singleidok.nevek1[0],"Rider");state.save();
    uint64_t hash=UINT64_C(14695981039346656037);FILE* golden=fopen("state.dat","rb");CHECK(golden);
    int byte;while((byte=fgetc(golden))!=EOF){hash^=static_cast<unsigned char>(byte);hash*=UINT64_C(1099511628211);}fclose(golden);
    printf("state-hash %016llx\n",static_cast<unsigned long long>(hash));
    CHECK(hash==UINT64_C(0x3acb3bea399218d1)); // Desktop LE encrypted file golden.
    state_s loaded;CHECK(loaded.jatekosokszama==1);CHECK(!strcmp(loaded.jatekosa,"Rider"));CHECK(loaded.palyakidejei[0].singleidok.idok[0]==1652);CHECK(warnings==0);
    CHECK(rename("state.dat","state.dat.bak")==0);state_s recovered;CHECK(recovered.jatekosokszama==1);CHECK(access("state.dat.bak",0)!=0);
    FILE*f=fopen("state.dat","wb");CHECK(f);fwrite("short",1,5,f);fclose(f);
    loaded.reloadidok();CHECK(loaded.palyakidejei[0].singleidok.idok[0]==1652);
    state_s truncated;CHECK(truncated.jatekosokszama==0);CHECK(truncated.single==1);CHECK(warnings>0);
    state.jatekosokszama=INT32_MAX;state.save();state_s invalid_count;CHECK(invalid_count.jatekosokszama==0);
    state.jatekosokszama=1;state.palyakidejei[0].singleidok.idokszama=INT32_MAX;state.save();state_s invalid_times;CHECK(invalid_times.jatekosokszama==0);
    remove("state.dat");chdir("..");rmdir(root);puts("PASS: encrypted state roundtrip, replacement, backup recovery and corruption rejection");return 0;
}
