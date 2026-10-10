/* Host arithmetic backend for the flat C step. Every solver operation is
 * integer; this file deliberately uses __int128 for a correctness reference.
 * The 65816 control object calls the same named API with an assembly backend. */
#include "wide_port.h"
#include "wide_math_config.h"
#if WIDE_HAS_ACCEL
#include "wide_accel_core.h"
#endif
#include "wide_trig_table_c.h"
#include <stdio.h>
#include <stdlib.h>
#include <limits.h>
#include <string.h>

#ifndef WIDE_PORT_BITS
#define WIDE_PORT_BITS 40
#endif
#ifndef WP_STATE_BITS
#define WP_STATE_BITS 32
#endif
#ifndef WP_STATE_WIDTH
#define WP_STATE_WIDTH 48
#endif
#define SCALE (INT64_C(1)<<WIDE_PORT_BITS)
#define STATE_SHIFT (INT64_C(1)<<(WIDE_PORT_BITS-WP_STATE_BITS))
static struct {uint64_t add,sub,mul,div,compare,sqrt,trig,trig_internal_mul,force,compact,overflow;} stats;
static uint64_t magnitude(int64_t x){return x<0?(uint64_t)-(__int128)x:(uint64_t)x;}
void wp_wide_fail(char* text){++stats.overflow;fprintf(stderr,"WIDE_C_DOMAIN %s\n",text);abort();}
static int64_t checked(__int128 x){if(x<INT64_MIN||x>INT64_MAX)wp_wide_fail("signed64 overflow");return (int64_t)x;}
static __int128 rounded(__int128 n,__int128 d){
 int negative=(n<0)!=(d<0);__int128 q,r;
 if(!d)wp_wide_fail("divide by zero");if(n<0)n=-n;if(d<0)d=-d;
 q=n/d;r=n%d;if(r>=d-r)++q;return negative?-q:q;
}
wp_scalar wp_int(int x){return checked((__int128)x*SCALE);}
int wp_to_int(wp_scalar x){return (int)(x/SCALE);}
wp_scalar wp_add(wp_scalar a,wp_scalar b){++stats.add;return checked((__int128)a+b);}
wp_scalar wp_sub(wp_scalar a,wp_scalar b){++stats.sub;return checked((__int128)a-b);}
wp_scalar wp_neg(wp_scalar a){return checked(-(__int128)a);}
wp_scalar wp_fabs(wp_scalar a){return a<0?wp_neg(a):a;}
wp_scalar wp_mul(wp_scalar a,wp_scalar b){++stats.mul;return checked(rounded((__int128)a*b,SCALE));}
wp_scalar wp_div(wp_scalar a,wp_scalar b){++stats.div;return checked(rounded((__int128)a*SCALE,b));}
#define CMP(name,op) int name(wp_scalar a,wp_scalar b){++stats.compare;return a op b;}
CMP(wp_eq,==) CMP(wp_ne,!=) CMP(wp_lt,<) CMP(wp_gt,>) CMP(wp_le,<=) CMP(wp_ge,>=)
#undef CMP
wp_vec wp_vec_make(wp_scalar x,wp_scalar y){wp_vec r={x,y};return r;}
wp_vec wp_add_v(wp_vec a,wp_vec b){return wp_vec_make(wp_add(a.x,b.x),wp_add(a.y,b.y));}
wp_vec wp_sub_v(wp_vec a,wp_vec b){return wp_vec_make(wp_sub(a.x,b.x),wp_sub(a.y,b.y));}
wp_scalar wp_dot(wp_vec a,wp_vec b){return wp_add(wp_mul(a.x,b.x),wp_mul(a.y,b.y));}
wp_scalar wp_cross(wp_vec a,wp_vec b){return wp_sub(wp_mul(a.x,b.y),wp_mul(a.y,b.x));}
wp_vec wp_scale(wp_vec a,wp_scalar b){return wp_vec_make(wp_mul(a.x,b),wp_mul(a.y,b));}
wp_vec wp_scale_left(wp_scalar a,wp_vec b){return wp_scale(b,a);}
wp_vec wp_forgatas90fokkal(wp_vec a){return wp_vec_make(wp_neg(a.y),a.x);}
wp_scalar wp_sqrt(wp_scalar a){
 unsigned __int128 n,rem,root=0,bit=(unsigned __int128)1<<126;
 ++stats.sqrt;if(a<0)wp_wide_fail("negative sqrt");n=(unsigned __int128)a*SCALE;rem=n;
 while(bit>rem)bit>>=2;
 while(bit){if(rem>=root+bit){rem-=root+bit;root=(root>>1)+bit;}else root>>=1;bit>>=2;}
 if(n-root*root>root)++root;return checked(root);
}
wp_scalar wp_absnegyzet(wp_vec a){return wp_add(wp_mul(a.x,a.x),wp_mul(a.y,a.y));}
wp_scalar wp_abs(wp_vec a){
 wp_scalar n=wp_absnegyzet(a),r=wp_sqrt(n);unsigned __int128 target,square;
 if(!r)return 0;target=(unsigned __int128)n<<WIDE_PORT_BITS;square=(unsigned __int128)r*r;
 if(target>=square&&2*(target-square)>=(uint64_t)r)return r+1;return r;
}
wp_vec wp_egys(wp_vec a){return wp_scale(a,wp_div(SCALE,wp_abs(a)));}
wp_scalar wp_floor(wp_scalar a){int64_t q=a/SCALE;if(a<0&&a%SCALE)--q;return checked((__int128)q*SCALE);}
static int64_t q48mul(int64_t a,int64_t b){++stats.trig_internal_mul;return checked(rounded((__int128)a*b,(__int128)1<<48));}
static wp_scalar trig_uncached(wp_scalar x,int cosine){
 int64_t pi=WIDE_PI_Q48,a,quarter=pi/2,anchor,d,d2,d3,s,c,result;unsigned i;__int128 phase=(__int128)x*(INT64_C(1)<<(48-WIDE_PORT_BITS));
 ++stats.trig;if(cosine)phase+=pi/2;a=(int64_t)(phase%(2*pi));if(a<0)a+=2*pi;
 int negative=a>pi;if(negative)a-=pi;if(a>pi/2)a=pi-a;
 i=(unsigned)((__int128)a*WIDE_TRIG_INTERVALS/quarter);if(i>WIDE_TRIG_INTERVALS)i=WIDE_TRIG_INTERVALS;
 anchor=(int64_t)((__int128)i*quarter/WIDE_TRIG_INTERVALS);d=a-anchor;d2=q48mul(d,d);d3=q48mul(d2,d);
 s=wide_sin_q48[i];c=wide_cos_q48[i];
 result=checked((__int128)s+q48mul(c,d-rounded(d3,6))-q48mul(s,rounded(d2,2)));
 result=checked(rounded(result,(__int128)1<<(48-WIDE_PORT_BITS)));return negative?-result:result;
}
static wp_scalar trig(wp_scalar x,int cosine){
 static struct {int64_t angle,value[2];unsigned valid;} entry[2];static unsigned next;unsigned i;
 for(i=0;i<2;++i)if(entry[i].valid&&entry[i].angle==x)break;
 if(i==2){i=next;next^=1;entry[i].angle=x;entry[i].valid=0;}
 if(!(entry[i].valid&(1u<<cosine))){entry[i].value[cosine]=trig_uncached(x,cosine);entry[i].valid|=1u<<cosine;}
 return entry[i].value[cosine];
}
wp_scalar wp_sin(wp_scalar x){return trig(x,0);}
wp_scalar wp_cos(wp_scalar x){return trig(x,1);}
bool wp_wide_safe_axle_distance(wp_vec a){uint64_t x=magnitude(a.x),y=magnitude(a.y);return x<4*SCALE&&y<4*SCALE&&(x>=SCALE/4||y>=SCALE/4);}
#if WIDE_HAS_ACCEL
wp_vec wp_wa_force(wp_vec g,wp_vec rate,int active){
 int64_t x=checked(rounded(g.x,(__int128)1<<(WIDE_PORT_BITS-GUMI_BITS))),y=checked(rounded(g.y,(__int128)1<<(WIDE_PORT_BITS-GUMI_BITS)));stats.force+=2;
 if(x<-(INT64_C(1)<<47)||x>=(INT64_C(1)<<47)||y<-(INT64_C(1)<<47)||y>=(INT64_C(1)<<47))wp_wide_fail("force position48 range");
 if(rate.x<-(INT64_C(1)<<47)||rate.x>=(INT64_C(1)<<47)||rate.y<-(INT64_C(1)<<47)||rate.y>=(INT64_C(1)<<47))wp_wide_fail("force rate48 range");
 return wp_vec_make(wa_spring_damper(x,rate.x,active),wa_spring_damper(y,rate.y,active));
}
#endif
wp_vec wp_wa_opposite_body(wp_vec a){return wp_vec_make(checked(rounded(-(__int128)a.x,20)),checked(rounded(-(__int128)a.y,20)));}
wp_scalar wp_wide_constant_reciprocal(wp_scalar a){
 static struct{int valid;int64_t key,result;} cache[8];static unsigned next;unsigned i;
 for(i=0;i<8;++i)if(cache[i].valid&&cache[i].key==a)return cache[i].result;
 int64_t result=wp_div(SCALE,a);cache[next].valid=1;cache[next].key=a;cache[next].result=result;next=(next+1)%8;return result;
}
wp_scalar wp_wide_constant_divide(wp_scalar a,wp_scalar b){
 static struct{int valid;int64_t key;uint64_t reciprocal;} cache[8];static unsigned next;
 uint64_t d=magnitude(b),reciprocal=0;unsigned i;unsigned __int128 n,q,remainder;
 if(!d)wp_wide_fail("constant divisor zero");
 for(i=0;i<8;++i)if(cache[i].valid&&cache[i].key==b){reciprocal=cache[i].reciprocal;break;}
 if(i==8){unsigned __int128 r=((unsigned __int128)SCALE<<60)/d;if(r>UINT64_MAX)return wp_div(a,b);reciprocal=(uint64_t)r;cache[next].valid=1;cache[next].key=b;cache[next].reciprocal=reciprocal;next=(next+1)%8;}
 n=(unsigned __int128)magnitude(a)*SCALE;q=((unsigned __int128)magnitude(a)*reciprocal)>>60;remainder=n-q*d;
 while(remainder>=d){remainder-=d;++q;}if(remainder>=d-remainder)++q;
 return checked((a<0)!=(b<0)?-(__int128)q:(__int128)q);
}
wp_vec wp_wide_contact_normal(wp_kor* circle,wp_vec point,wp_scalar* length){
 static struct{int valid;wp_vec r,point,n;wp_scalar h;} cache[16];static unsigned next;unsigned i;
 for(i=0;i<16;++i)if(cache[i].valid&&cache[i].r.x==circle->r.x&&cache[i].r.y==circle->r.y&&cache[i].point.x==point.x&&cache[i].point.y==point.y){*length=cache[i].h;return cache[i].n;}
 wp_vec d=wp_sub_v(circle->r,point);wp_scalar h=wp_abs(d);wp_vec normal=wp_scale(wp_sub_v(circle->r,point),wp_div(SCALE,h));
 cache[next].valid=1;cache[next].r=circle->r;cache[next].point=point;cache[next].n=normal;cache[next].h=h;next=(next+1)%16;*length=h;return normal;
}
wp_vec wp_wide_gravity_force(wp_vec direction,wp_scalar mass){
 static struct{int valid;wp_vec direction,result;wp_scalar mass,g;} cache[16];static unsigned next;unsigned i;wp_scalar gravity=G;
 for(i=0;i<16;++i)if(cache[i].valid&&cache[i].direction.x==direction.x&&cache[i].direction.y==direction.y&&cache[i].mass==mass&&cache[i].g==gravity)return cache[i].result;
 wp_vec result;
#if WIDE_GRAVITY_MASS_FOLDED
 result=wp_scale(direction,gravity);
#else
 result=wp_scale(wp_scale(direction,mass),gravity);
#endif
 cache[next].valid=1;cache[next].direction=direction;cache[next].mass=mass;cache[next].g=gravity;cache[next].result=result;next=(next+1)%16;return result;
}
wp_scalar wp_compact_integrate(wp_scalar state,wp_scalar rate,wp_scalar dt,bool angle){
 int64_t p=checked(rounded(state,STATE_SHIFT)),d=checked(rounded(rate,STATE_SHIFT)),r; (void)dt;(void)angle;++stats.compact;
 __int128 limit=(__int128)1<<(WP_STATE_WIDTH-1);
 if((__int128)p< -limit||(__int128)p>=limit||rate<-(INT64_C(1)<<47)||rate>=(INT64_C(1)<<47))wp_wide_fail("compact input range");
 r=checked((__int128)p+d);if((__int128)r< -limit||(__int128)r>=limit)wp_wide_fail("compact output range");return checked((__int128)r*STATE_SHIFT);
}
wp_scalar wp_quantize32(wp_scalar a){return checked(rounded(a,(__int128)1<<(WIDE_PORT_BITS-32))*((__int128)1<<(WIDE_PORT_BITS-32)));}
#if WIDE_PROFILE_MATH
static struct norm_range {const char *kind,*caller;uint64_t count,computed;int64_t xmin,xmax,ymin,ymax,lmin,lmax;uint64_t normalmax;} ranges[64];
static unsigned range_count;
static void record_norm(const char* kind,const char* caller,wp_vec a,wp_scalar length,wp_vec normal,uint64_t computed){
 unsigned i;struct norm_range* r;uint64_t nm=magnitude(normal.x)>magnitude(normal.y)?magnitude(normal.x):magnitude(normal.y);
 for(i=0;i<range_count;++i)if(!strcmp(ranges[i].kind,kind)&&!strcmp(ranges[i].caller,caller))break;
 if(i==range_count){if(range_count==64)wp_wide_fail("norm profile capacity");++range_count;r=&ranges[i];r->kind=kind;r->caller=caller;r->xmin=r->xmax=a.x;r->ymin=r->ymax=a.y;r->lmin=r->lmax=length;}
 r=&ranges[i];++r->count;r->computed+=computed;if(a.x<r->xmin)r->xmin=a.x;if(a.x>r->xmax)r->xmax=a.x;if(a.y<r->ymin)r->ymin=a.y;if(a.y>r->ymax)r->ymax=a.y;
 if(length<r->lmin)r->lmin=length;if(length>r->lmax)r->lmax=length;if(nm>r->normalmax)r->normalmax=nm;
}
wp_scalar wp_profile_abs(wp_vec a,const char* caller){wp_scalar r=wp_abs(a);record_norm("abs",caller,a,r,(wp_vec){0,0},1);return r;}
wp_scalar wp_profile_absnegyzet(wp_vec a,const char* caller){wp_scalar r=wp_absnegyzet(a);record_norm("squared",caller,a,r,(wp_vec){0,0},1);return r;}
wp_vec wp_profile_egys(wp_vec a,const char* caller){wp_vec r=wp_egys(a);record_norm("unit",caller,a,0,r,1);return r;}
wp_vec wp_profile_wide_contact_normal(wp_kor* a,wp_vec point,wp_scalar* length,const char* caller){
 uint64_t before=stats.sqrt;wp_vec r=wp_wide_contact_normal(a,point,length);
 /* Plain subtraction avoids adding profiling work to solver operation counts. */
 wp_vec d={a->r.x-point.x,a->r.y-point.y};record_norm("contact",caller,d,*length,r,stats.sqrt-before);return r;
}
#endif
void wp_math_reset_stats(void){memset(&stats,0,sizeof(stats));
#if WIDE_PROFILE_MATH
 memset(ranges,0,sizeof(ranges));range_count=0;
#endif
}
void wp_math_print_stats(void){fprintf(stderr,"WIDE_C_STATS {\"add\":%llu,\"sub\":%llu,\"mul\":%llu,\"div\":%llu,\"compare\":%llu,\"sqrt\":%llu,\"trig\":%llu,\"trig_internal_mul\":%llu,\"force_component\":%llu,\"compact\":%llu,\"overflow\":%llu}\n",stats.add,stats.sub,stats.mul,stats.div,stats.compare,stats.sqrt,stats.trig,stats.trig_internal_mul,stats.force,stats.compact,stats.overflow);
#if WIDE_PROFILE_MATH
 unsigned i;for(i=0;i<range_count;++i){struct norm_range* r=&ranges[i];fprintf(stderr,"WIDE_NORM_RANGE {\"bits\":%d,\"kind\":\"%s\",\"caller\":\"%s\",\"count\":%llu,\"computed\":%llu,\"xmin\":%lld,\"xmax\":%lld,\"ymin\":%lld,\"ymax\":%lld,\"lmin\":%lld,\"lmax\":%lld,\"normalmax\":%llu}\n",WIDE_PORT_BITS,r->kind,r->caller,r->count,r->computed,r->xmin,r->xmax,r->ymin,r->ymax,r->lmin,r->lmax,r->normalmax);}
#endif
}
