#include <cstdio>
#include <cstring>
#include <cstdint>
#include "all.h"
#include "LE_STRUCT.H"
static int failures;
#define CHECK(c) do { if(!(c)) { fprintf(stderr,"line %d: %s\n",__LINE__,#c);++failures; } } while(0)
int main() {
    const unsigned char fixture[]={0x78,0x56,0x34,0x12,0xfe,0xff,0x00,0x00,0x80,0x3f,0,0,0,0,0,0,0xf0,0x3f};
#ifdef ELMA_PS3
    const char* temporary="/dev_hdd0/game/ELMAC0001/USRDIR/endian-test.tmp";
    FILE* f=fopen(temporary,"w+b");
#else
    FILE* f=tmpfile();
#endif
    CHECK(f);if(!f)return 1;
    fwrite(fixture,1,sizeof(fixture),f);rewind(f);
    long a=-1;short b=0;float c=0;double d=0;
    CHECK(elma_read(&a,1,4,f)==4 && a==0x12345678L);
    CHECK(elma_read(&b,2,1,f)==1 && b==-2);
    CHECK(elma_read(&c,1,4,f)==4 && c==1.0f);
    CHECK(elma_read(&d,1,8,f)==8 && d==1.0);
    rewind(f);CHECK(elma_write(&a,1,4,f)==4);CHECK(elma_write(&b,2,1,f)==1);
    CHECK(elma_write(&c,1,4,f)==4);CHECK(elma_write(&d,1,8,f)==8);
    rewind(f);unsigned char bytes[sizeof(fixture)];CHECK(fread(bytes,1,sizeof(bytes),f)==sizeof(bytes));CHECK(!memcmp(bytes,fixture,sizeof(bytes)));
    // A NaN payload, negative zero and subnormal must survive bit for bit.
    uint64_t patterns[]={UINT64_C(0x7ff8123456789abc),UINT64_C(0x8000000000000000),UINT64_C(1)};
    double values[3];memcpy(values,patterns,sizeof(values));rewind(f);
    CHECK(elma_write(values,8,3,f)==3);memset(values,0,sizeof(values));rewind(f);
    CHECK(elma_read(values,8,3,f)==3);CHECK(!memcmp(values,patterns,sizeof(values)));
    palyaidok times={};times.singleidok.idokszama=1;times.singleidok.idok[0]=12345;
    strcpy(times.singleidok.nevek1[0],"Rider");rewind(f);CHECK(elma_write(&times,1,sizeof(times),f)==sizeof(times));
    palyaidok loaded={};rewind(f);CHECK(elma_read(&loaded,1,sizeof(loaded),f)==sizeof(loaded));CHECK(!memcmp(&times,&loaded,sizeof(times)));
    CHECK(sizeof(palyaegyfeleidok)==344);CHECK(sizeof(palyaidok)==688);CHECK(sizeof(jatekos)==116);CHECK(sizeof(egyhang)==16);
    CHECK(elma_read(&a,SIZE_MAX,2,f)==0);
    CHECK(elma_write(&a,SIZE_MAX,2,f)==0);
    fclose(f);
#ifdef ELMA_PS3
    remove(temporary);
    FILE* result=fopen("/dev_hdd0/game/ELMAC0001/USRDIR/endian-result.txt","w");
    if(result) { fprintf(result,"%s\n",failures?"FAIL":"PASS");fclose(result); }
#endif
    return failures?1:0;
}
