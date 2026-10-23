#include "all.h"
#undef fopen
#undef access
#undef remove
#undef rename
#include <cerrno>
#include <string>
#include <vector>
#include <sys/stat.h>
#ifndef ELMA_PS3_NATIVE_TEST
#include <sys/resource.h>
#include <csignal>
#endif
double K_pi=3.141592,K_pip2=1.570796,K_2pi=6.283184;
int Volttopsave=0,Sarvari=0;
static int warnings,fail_open,fail_install;
#ifndef ELMA_PS3_NATIVE_TEST
static long fail_after=-1;
struct WriteFault {FILE* backing;long written;};
static ssize_t fault_write(void* object,const char* data,size_t n){WriteFault* f=(WriteFault*)object;
    if(f->written>=fail_after){errno=ENOSPC;return -1;}
    size_t count=n;if(count>size_t(fail_after-f->written))count=size_t(fail_after-f->written);
    size_t result=fwrite(data,1,count,f->backing);f->written+=result;return ssize_t(result);
}
static int fault_seek(void* object,off64_t* offset,int whence){WriteFault* f=(WriteFault*)object;
    if(fseeko(f->backing,*offset,whence)!=0)return -1;*offset=ftello(f->backing);return 0;}
static int fault_close(void* object){WriteFault* f=(WriteFault*)object;int status=fclose(f->backing);delete f;return status;}
#endif
static std::string path(const char* name){std::string p(name);for(size_t i=0;i<p.size();++i)if(p[i]=='\\')p[i]='/';if(p[0]!='/'){char cwd[1024];getcwd(cwd,sizeof(cwd));p=std::string(cwd)+"/"+p;}return p;}
FILE* elma_fopen(const char* name,const char* mode){if(fail_open && strstr(name,".tmp")){errno=ENOSPC;return NULL;}FILE*f=fopen(path(name).c_str(),mode);
#ifndef ELMA_PS3_NATIVE_TEST
 if(f && fail_after>=0 && strstr(name,".tmp")){WriteFault* fault=new WriteFault{f,0};cookie_io_functions_t operations={};operations.write=fault_write;operations.seek=fault_seek;operations.close=fault_close;f=fopencookie(fault,"w",operations);}
#endif
 if(f && strchr(mode,'w'))setvbuf(f,NULL,_IONBF,0);return f;}
int elma_access(const char* name,int mode){return access(path(name).c_str(),mode);}
int elma_remove(const char* name){return remove(path(name).c_str());}
int elma_rename(const char* from,const char* to){if(fail_install && strstr(from,".tmp")){--fail_install;errno=EIO;return -1;}if(elma_access(to,0)==0){errno=EEXIST;return -1;}return rename(path(from).c_str(),path(to).c_str());}
void hiba(char* a,char*,char*){fprintf(stderr,"fatal:%s\n",a);abort();}
void uzenet(char*,char*,char*){++warnings;}
int dialog(char*,char*,char*,char*,char*,char*,char*,char*,char*,char*,char*,char*,char*,char*,char*,char*,char*,char*,char*,char*,char*,char*,char*,char*){return 0;}
int s_random(int){return 0;}
int gyujtemenypalya(char*){return 0;}
void mentgyujtemenyidok(char*,long,palyaidok*){abort();}
int check_topology(int){return 0;}
static topol* fixture_level;
int floadlevel_e(char*,int){fixture_level=new topol;return 1;}
int menu_exit(){delete fixture_level;return 1;}
static std::vector<unsigned char> bytes(const char* name){FILE*f=elma_fopen(name,"rb");std::vector<unsigned char> v;if(!f)return v;int c;while((c=fgetc(f))!=EOF)v.push_back(c);fclose(f);return v;}
#define CHECK(x) do{if(!(x)){fprintf(stderr,"line%d:%s\n",__LINE__,#x);return 1;}}while(0)
int main(){
#ifdef ELMA_PS3_NATIVE_TEST
 const char* root="/dev_hdd0/game/ELMAC0001/USRDIR/level-file-test";mkdir(root,0777);CHECK(chdir(root)==0);
#else
 char root[]="/tmp/elma-level-XXXXXX";CHECK(mkdtemp(root));CHECK(chdir(root)==0);
#endif
 mkdir(path("lev").c_str(),0777);floadlevel_e(NULL,1);topol& level=*fixture_level;
 CHECK(level.save((char*)"TEST.lev",1));std::vector<unsigned char> original=bytes("lev/TEST.lev");CHECK(original.size()>700);
 level.idok.singleidok.idokszama=1;level.idok.singleidok.idok[0]=1652;const palyaidok saved=level.idok;
 fail_open=1;CHECK(!level.save((char*)"TEST.lev",1));fail_open=0;CHECK(bytes("lev/TEST.lev")==original);CHECK(!memcmp(&saved,&level.idok,sizeof(saved)));
 fail_install=2;CHECK(!level.save((char*)"TEST.lev",1));CHECK(bytes("lev/TEST.lev")==original);CHECK(!memcmp(&saved,&level.idok,sizeof(saved)));
#ifndef ELMA_PS3_NATIVE_TEST
 struct rlimit old_limit,limited;CHECK(getrlimit(RLIMIT_FSIZE,&old_limit)==0);limited=old_limit;limited.rlim_cur=64;signal(SIGXFSZ,SIG_IGN);CHECK(setrlimit(RLIMIT_FSIZE,&limited)==0);
 int success=level.save((char*)"TEST.lev",1);CHECK(setrlimit(RLIMIT_FSIZE,&old_limit)==0);CHECK(!success);CHECK(bytes("lev/TEST.lev")==original);CHECK(!memcmp(&saved,&level.idok,sizeof(saved)));
#endif
 // Update only the trailing records while preserving every geometry byte.
 level.idokhelye=long(original.size()-sizeof(palyaidok)-8);level.saveidok((char*)"TEST.lev");std::vector<unsigned char> updated=bytes("lev/TEST.lev");CHECK(updated.size()==original.size());CHECK(!memcmp(updated.data(),original.data(),size_t(level.idokhelye)));CHECK(!memcmp(&saved,&level.idok,sizeof(saved)));
#ifndef ELMA_PS3_NATIVE_TEST
 // Fail inside the encrypted time payload after successfully copying the
 // whole level and writing its first marker. The live table must be restored.
 int old_warnings=warnings;fail_after=long(updated.size())+4+10;level.saveidok((char*)"TEST.lev");fail_after=-1;CHECK(warnings==old_warnings+1);
 CHECK(bytes("lev/TEST.lev")==updated);CHECK(!memcmp(&saved,&level.idok,sizeof(saved)));
#endif
 fail_open=1;level.saveidok((char*)"TEST.lev");fail_open=0;CHECK(bytes("lev/TEST.lev")==updated);CHECK(!memcmp(&saved,&level.idok,sizeof(saved)));
 menu_exit();remove(path("lev/TEST.lev").c_str());rmdir(path("lev").c_str());chdir("..");rmdir(root);puts("PASS: actual level save, failed write/install, retained times and atomic record update");return 0;
}
