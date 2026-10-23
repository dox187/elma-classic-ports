#include <cstdio>
#include <cstring>
#include <cerrno>
#include <unistd.h>
static int fail_install;
static int fail_restore;
static bool reject_replace;
static int test_rename(const char* from,const char* to){
    if(fail_restore && strstr(from,".bak")){--fail_restore;errno=EIO;return -1;}
    if(fail_install && strstr(from,".tmp")){--fail_install;errno=EIO;return -1;}
    if(reject_replace && access(to,0)==0){errno=EEXIST;return -1;}
    return rename(from,to);
}
#define ELMA_ATOMIC_RENAME test_rename
#define ELMA_ATOMIC_TEST_NO_REPLACE 1
#include "ATOMIC_FILE.H"
#include <sys/stat.h>
#include <unistd.h>
#include <cstdlib>
static int errors;
#define CHECK(x) do{if(!(x)){fprintf(stderr,"line %d: %s\n",__LINE__,#x);++errors;}}while(0)
static bool contents(const char* path,const char* expected){char data[64]={};FILE*f=fopen(path,"rb");if(!f)return false;size_t n=fread(data,1,sizeof(data)-1,f);fclose(f);return n==strlen(expected)&&!strcmp(data,expected);}
int main(){
#ifdef ELMA_PS3
    const char* root="/dev_hdd0/game/ELMAC0001/USRDIR/atomic-test";mkdir(root,0777);
#else
    char directory[]="/tmp/elma-atomic-XXXXXX";const char* root=mkdtemp(directory);
#endif
    CHECK(root);if(!root)return 1;
    char file[1024],temp[1024],backup[1024],blocked[1024],missing[1024];
    snprintf(file,sizeof(file),"%s/state.dat",root);snprintf(temp,sizeof(temp),"%s.tmp",file);
    snprintf(backup,sizeof(backup),"%s.bak",file);
    snprintf(blocked,sizeof(blocked),"%s/directory",root);snprintf(missing,sizeof(missing),"%s/missing/state.dat",root);
    FILE*f=fopen(file,"wb");CHECK(f);if(!f)return 1;CHECK(fwrite("old",1,3,f)==3);CHECK(fclose(f)==0);
    {elma_atomic_file out(file);CHECK(out.file());CHECK(fwrite("bad",1,3,out.file())==3);CHECK(!out.commit(false));}
    CHECK(contents(file,"old"));CHECK(access(temp,0)!=0);
    {elma_atomic_file out(file);CHECK(out.file());CHECK(fwrite("abandoned",1,9,out.file())==9);}
    CHECK(contents(file,"old"));CHECK(access(temp,0)!=0);
    reject_replace=true;
    {elma_atomic_file out(file);CHECK(out.file());bool written=fwrite("new",1,3,out.file())==3;bool committed=out.commit(written);
        if(!committed)fprintf(stderr,"existing-target replacement errno=%d\n",out.error());CHECK(committed);}
    CHECK(contents(file,"new"));CHECK(access(temp,0)!=0);
    // Both installation attempts fail; rollback must preserve the primary.
    fail_install=2;
    {elma_atomic_file out(file);CHECK(out.file());CHECK(fwrite("lost",1,4,out.file())==4);CHECK(!out.commit());}
    CHECK(contents(file,"new"));CHECK(access(backup,0)!=0);
    // Failed rollback leaves the last complete save recoverable at next read.
    fail_install=2;fail_restore=1;
    {elma_atomic_file out(file);CHECK(out.file());CHECK(fwrite("lost",1,4,out.file())==4);CHECK(!out.commit());}
    CHECK(access(file,0)!=0);CHECK(contents(backup,"new"));CHECK(elma_restore_save(file));
    CHECK(contents(file,"new"));CHECK(access(backup,0)!=0);
    // Simulate interruption after primary -> backup, before temp installation.
    CHECK(rename(file,backup)==0);CHECK(elma_restore_save(file));
    CHECK(contents(file,"new"));CHECK(access(backup,0)!=0);
    // A complete installed primary takes priority over a stale backup.
    f=fopen(backup,"wb");CHECK(f);if(f){fwrite("stale",1,5,f);fclose(f);}
    CHECK(elma_restore_save(file));CHECK(contents(file,"new"));remove(backup);
    mkdir(blocked,0777);
    {elma_atomic_file out(blocked);CHECK(out.file());CHECK(fwrite("data",1,4,out.file())==4);CHECK(!out.commit());}
    struct stat st;CHECK(stat(blocked,&st)==0 && S_ISDIR(st.st_mode));
    {elma_atomic_file out(missing);CHECK(!out.file());CHECK(!out.commit());}
    remove(file);rmdir(blocked);rmdir(root);
#ifdef ELMA_PS3
    f=fopen("/dev_hdd0/game/ELMAC0001/USRDIR/atomic-result.txt","w");if(f){fprintf(f,"%s\n",errors?"FAIL":"PASS");fclose(f);}
#endif
    return errors?1:0;
}
