/* Private original-Q48 trig baseline. No production integration. */
#include <snes.h>
#include "core.h"
void wide_mul64(const u16*,const u16*,u16,u16*,u16*);
extern const u16 wq_table0[],wq_table1[],wq_table2[],wq_table3[],wq_table4[],wq_table5[],wq_table6[],wq_table7[],wq_table8[];
u16 wq_angle[4],wq_sin[4],wq_cos[4];
volatile u16 wq_go,wq_done,wq_status,wq_hit;
static u16 cache_angle[2][4],cache_sin[2][4],cache_cos[2][4],cache_valid[2],next;
static u16 pi[5];
static u16 period[5],quarter[5],phase[5],tmp[5],a[5],d[4],d2[4],d3[4],s[4],c[4],v[4],t[4],result[4];
static void copy(u16*o,const u16*i,u16 n){u16 j;for(j=0;j<n;j++)o[j]=i[j];}
static u16 cmp(const u16*x,const u16*y,u16 n){u16 j=n;while(j){--j;if(x[j]>y[j])return 2;if(x[j]<y[j])return 0;}return 1;}
static void sub(u16*x,const u16*y,u16 n){u16 j,b=0;u32 z;for(j=0;j<n;j++){z=(u32)x[j]-y[j]-b;x[j]=(u16)z;b=(u16)(z>>31);}}
static void add(u16*x,const u16*y,u16 n){u16 j;u32 z=0;for(j=0;j<n;j++){z=(u32)x[j]+y[j]+(z>>16);x[j]=(u16)z;}}
static void shl(u16*x,u16 n){u16 j,carry=0,t;for(j=0;j<n;j++){t=x[j]>>15;x[j]=(x[j]<<1)|carry;carry=t;}}
static void shr(u16*x,u16 n){u16 j=n,carry=0,t;while(j){--j;t=x[j]<<15;x[j]=(x[j]>>1)|carry;carry=t;}}
static void neg(u16*x,u16 n){u16 j,carry=1;u32 z;for(j=0;j<n;j++){z=(u32)(u16)~x[j]+carry;x[j]=(u16)z;carry=(u16)(z>>16);}}
static const u16* row(u16 i){const u16*p;switch(i>>9){case 0:p=wq_table0;break;case 1:p=wq_table1;break;case 2:p=wq_table2;break;case 3:p=wq_table3;break;case 4:p=wq_table4;break;case 5:p=wq_table5;break;case 6:p=wq_table6;break;case 7:p=wq_table7;break;default:p=wq_table8;break;}return p+(i&511)*12;}
static void multiply(const u16*x,const u16*y,u16*out){u16 status=0;wide_mul64(x,y,48,out,&status);wq_status|=status;}
static void evaluate(u16 cosine,u16*out){u16 i,j,lo=0,hi=4096,negative;const u16*p;copy(a,phase,5);if(cosine){add(a,quarter,5);if(cmp(a,period,5)!=0)sub(a,period,5);}negative=cmp(a,pi,5)==2;if(negative)sub(a,pi,5);if(cmp(a,quarter,5)==2){copy(tmp,pi,5);sub(tmp,a,5);copy(a,tmp,5);}while(lo<hi){i=lo+(hi-lo+1)/2;p=row(i);if(cmp(a,p,4)!=0)lo=i;else hi=i-1;}i=lo;p=row(i);copy(d,p,4);if(i!=0&&i!=4096){t[0]=1;t[1]=t[2]=t[3]=0;sub(d,t,4);}copy(v,a,4);sub(v,d,4);copy(d,v,4);copy(s,p+4,4);copy(c,p+8,4);multiply(d,d,d2);multiply(d2,d,d3);copy(v,d,4);t[0]=(d3[0]+3)/6;t[1]=t[2]=t[3]=0;sub(v,t,4);multiply(c,v,result);add(result,s,4);copy(t,d2,4);v[0]=1;v[1]=v[2]=v[3]=0;add(t,v,4);shr(t,4);multiply(s,t,v);sub(result,v,4);t[0]=8;t[1]=t[2]=t[3]=0;add(result,t,4);for(j=0;j<4;j++)shr(result,4);if(negative)neg(result,4);copy(out,result,4);}
void wide_q44_trig_pair(const u16*angle,u16*sinout,u16*cosout){u16 i,j,negative;wq_status=0;wq_hit=0;for(i=0;i<2;i++)if(cache_valid[i]&&cmp(angle,cache_angle[i],4)==1){copy(sinout,cache_sin[i],4);copy(cosout,cache_cos[i],4);wq_hit=1;return;}copy(phase,angle,4);phase[4]=0;negative=phase[3]&0x8000;if(negative)neg(phase,4);for(i=0;i<4;i++)shl(phase,5);copy(tmp,period,5);for(i=0;i<16;i++)shl(tmp,5);for(i=0;i<17;i++){if(cmp(phase,tmp,5)!=0)sub(phase,tmp,5);shr(tmp,5);}if(negative){/* tmp=period>>1 here; zero test explicitly */j=0;for(i=0;i<5;i++)j|=phase[i];if(j){copy(tmp,period,5);sub(tmp,phase,5);copy(phase,tmp,5);}}evaluate(0,sinout);evaluate(1,cosout);i=next;next^=1;copy(cache_angle[i],angle,4);copy(cache_sin[i],sinout,4);copy(cache_cos[i],cosout,4);cache_valid[i]=1;}
void wide_q44_trig_end(void){}
int main(void){consoleInit();core_init();core_screen_off();/* WQ_CONSTANTS */while(1){if(wq_go){wq_go=0;wide_q44_trig_pair(wq_angle,wq_sin,wq_cos);wide_q44_trig_end();wq_done=1;}core_frame_done();}return 0;}
