#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/process.h>
SYS_PROCESS_PARAM(1001, 0x100000);
FILE* elma_fopen(const char*, const char*);
int elma_access(const char*, int);
int elma_remove(const char*);
int elma_rename(const char*, const char*);
int fifirst(char*,char*);
int finext(char*);
void ficlose();
void hiba(char* text,char*,char*) { fprintf(stderr,"core error: %s\n",text); exit(3); }
static int failures=0;
static void check(bool ok,const char* label) { printf("%s %s\n",ok?"PASS":"FAIL",label); if(!ok) ++failures; }
static bool write(const char* path,const char* text) {
    FILE* f=elma_fopen(path,"wb"); if(!f)return false;
    bool ok=fwrite(text,1,strlen(text),f)==strlen(text); return fclose(f)==0&&ok;
}
static bool read(const char* path,const char* expected) {
    FILE* f=elma_fopen(path,"rb"); if(!f)return false;
    char data[128]={}; size_t n=fread(data,1,sizeof(data)-1,f);fclose(f);
    return n==strlen(expected)&&strcmp(data,expected)==0;
}
int main() {
    setvbuf(stdout,NULL,_IONBF,0);
    const char* base="/dev_hdd0/game/ELMAC0001/USRDIR";
    check(chdir(base)==0,"set game working directory");
    mkdir("/dev_hdd0/game/ELMAC0001/USRDIR/FsCase",0777);
    check(write("FsCase\\MiXeD.tmp","binary\nstate"),"write relative backslash path");
    check(elma_access("fScAsE/mIxEd.TMP",F_OK)==0,"case independent relative access");
    check(read("FSCASE\\MIXED.TMP","binary\nstate"),"read case independent backslash path");
    check(elma_access("fscase/missing.tmp",F_OK)!=0,"missing file reports absent");
    check(elma_rename("fscase/mixed.tmp","FSCASE/Rename.tmp")==0,"rename case independent source and directory");
    check(read("fscase/rename.TMP","binary\nstate"),"renamed data preserved");
    char pattern[]="fscase\\*.TMP",name[32]={};
    int first=fifirst(pattern,name);int found=0;
    if(first==0)do{if(strcasecmp(name,"Rename.tmp")==0)++found;}while(finext(name)==0);
    ficlose(); check(found==1,"case independent directory wildcard enumeration");
    check(write("FsCase/state.tmp","new settings"),"write settings temporary file");
    check(elma_rename("FSCASE/STATE.TMP","fscase/State.dat")==0,"atomic settings rename");
    check(read("FSCASE/state.DAT","new settings"),"read settings after rename");
    check(elma_remove("fscase/RENAME.tmp")==0,"remove case independent file");
    check(elma_remove("FSCASE/STATE.DAT")==0,"remove settings file");
    check(elma_access("fscase/rename.tmp",F_OK)!=0,"removed file absent");
    FILE* report=elma_fopen("files-result.txt","wb");
    if(report){fprintf(report,"%s %d failures\n",failures?"FAIL":"PASS",failures);fclose(report);}
    return failures?1:0;
}
