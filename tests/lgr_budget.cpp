#include "LGR_BUDGET.H"
static int errors;
#define CHECK(x) do { if(!(x)){fprintf(stderr,"line %d: %s\n",__LINE__,#x);++errors;} }while(0)
static void fixture(FILE* f,bool hd,bool oversized=false) {
    fwrite(hd?"LGR13":"LGR12",1,5,f);int32_t n=10,version=1002;
    elma_write(&n,4,1,f);elma_write(&version,4,1,f);elma_write(&n,4,1,f);
    for(int i=0;i<10;++i){char name[10]={};snprintf(name,sizeof(name),"image%d",i);fwrite(name,10,1,f);}
    int32_t type=101,zero=0;
    for(int i=0;i<10;++i)elma_write(&type,4,1,f);
    for(int i=0;i<30;++i)elma_write(&zero,4,1,f);
    for(int i=0;i<10;++i) {
        char name[20]={};snprintf(name,sizeof(name),"IMAGE%d.PCX",i);fwrite(name,20,1,f);
        if(hd){int16_t x=8,y=6;elma_write(&x,2,1,f);elma_write(&y,2,1,f);}
        int32_t length=128;elma_write(&length,4,1,f);
        unsigned char header[128]={};header[0]=10;header[1]=5;header[2]=1;header[3]=8;header[8]=31;header[10]=23;header[65]=1;header[66]=32;
        if(oversized){header[8]=255;header[9]=255;}
        fwrite(header,128,1,f);
    }
    int32_t check=187565543;elma_write(&check,4,1,f);fflush(f);rewind(f);
}
int main(int argc,char**argv) {
#ifdef ELMA_PS3
    const char* temporary="/dev_hdd0/game/ELMAC0001/USRDIR/lgr-budget-test.tmp";
    FILE* f=fopen(temporary,"w+b");
#else
    FILE* f=tmpfile();
#endif
    CHECK(f);if(!f)return 1;
    elma_lgr_budget normal={},hd={},large={};
    fixture(f,false);CHECK(elma_estimate_lgr(f,1,&normal));
    CHECK(normal.persistent==4u*1024*1024+10u*(608u*24u+24u*64u));
    rewind(f);fixture(f,true);CHECK(elma_estimate_lgr(f,1,&hd));CHECK(hd.persistent==4u*1024*1024+10u*(600u*6u+6u*64u));
    rewind(f);CHECK(elma_estimate_lgr(f,4,&large));CHECK(large.persistent==normal.persistent);
    rewind(f);CHECK(!elma_estimate_lgr(f,500,&large));
    // Live replacement admission credits the old library once, before free.
    rewind(f);fixture(f,true);elma_lgr_budget needed={};CHECK(elma_estimate_lgr(f,1,&needed));
    const uint64_t reserve=24u*1024u*1024u,old=2u*1024u*1024u;
    const uint64_t exact=reserve+needed.persistent+needed.temporary-old;
    rewind(f);CHECK(elma_admit_lgr(f,1,1,1,exact,old)==ELMA_LGR_ACCEPT);
    rewind(f);CHECK(elma_admit_lgr(f,1,1,1,exact-1,old)==ELMA_LGR_TOO_LARGE);
    rewind(f);CHECK(elma_admit_lgr(f,1,1,1,exact,0)==ELMA_LGR_TOO_LARGE);
    CHECK(elma_admit_lgr(NULL,1,1,1,UINT64_MAX,0)==ELMA_LGR_INVALID);
    rewind(f);fwrite("BAD!!",1,5,f);fflush(f);rewind(f);
    CHECK(elma_admit_lgr(f,1,1,1,256u*1024u*1024u,old)==ELMA_LGR_INVALID);
    // Neither fixed-width list names nor image filenames may run into the
    // adjacent field when the real loader treats them as C strings.
    char unterminated[20];memset(unterminated,'A',sizeof(unterminated));
    rewind(f);fixture(f,true);fseek(f,17,SEEK_SET);fwrite(unterminated,1,10,f);fflush(f);rewind(f);
    CHECK(elma_admit_lgr(f,1,1,1,256u*1024u*1024u,old)==ELMA_LGR_INVALID);
    rewind(f);fixture(f,true);fseek(f,17+10*26,SEEK_SET);fwrite(unterminated,1,20,f);fflush(f);rewind(f);
    CHECK(elma_admit_lgr(f,1,1,1,256u*1024u*1024u,old)==ELMA_LGR_INVALID);
    rewind(f);fixture(f,true,true);CHECK(!elma_estimate_lgr(f,1,&large));
    rewind(f);fixture(f,false);fseek(f,13,SEEK_SET);int32_t bad_count=INT32_MAX;
    elma_write(&bad_count,4,1,f);fflush(f);rewind(f);CHECK(!elma_estimate_lgr(f,1,&large));fclose(f);
#ifdef ELMA_PS3
    remove(temporary);
    const char* real="/dev_hdd0/game/ELMAC0001/USRDIR/lgr/default.lgr";
#else
    const char* real=argc>1?argv[1]:NULL;
#endif
    if(real) {
        f=fopen(real,"rb");CHECK(f);
        if(f){CHECK(elma_estimate_lgr(f,1,&normal));rewind(f);CHECK(elma_estimate_lgr(f,4,&hd));fclose(f);}
        printf("LGR metadata: 1x %llu/%llu, 4x %llu/%llu bytes\n",(unsigned long long)normal.persistent,
          (unsigned long long)normal.temporary,(unsigned long long)hd.persistent,(unsigned long long)hd.temporary);
    }
#ifdef ELMA_PS3
    FILE* result=fopen("/dev_hdd0/game/ELMAC0001/USRDIR/lgr-budget-result.txt","w");
    if(result){fprintf(result,"%s\n",errors?"FAIL":"PASS");fclose(result);}
#endif
    return errors?1:0;
}
