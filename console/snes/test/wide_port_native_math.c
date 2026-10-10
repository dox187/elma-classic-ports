/* Correctness-first word arithmetic facade for the complete flat C solver.
 * No long-long expressions or floating arithmetic reach 816-TCC. Generic
 * multiply/divide/root are deliberately slow link-proof fallbacks. */
#define WIDE_PORT_BRIDGE
#include "wide_port.h"
#include "wide_math_config.h"
#include "wide_native_trig_words.h"

void wide_mul64(const uint16_t*,const uint16_t*,uint16_t,uint16_t*,uint16_t*);
void wide_div64(const uint16_t*,const uint16_t*,uint16_t,uint16_t*,uint16_t*);
void wide_sqrt64(const uint16_t*,uint16_t,uint16_t*,uint16_t*);
volatile uint16_t wp_native_error;
static wp_scalar zero={{0,0,0,0}};

void wp_wide_fail(char* text){(void)text;wp_native_error=1;
#ifdef WP_NATIVE_HOST
 extern void wp_native_host_abort(void);wp_native_host_abort();
#else
 while(1){}
#endif
}
static int negative(wp_scalar a){return (a.word[3]&0x8000)!=0;}
static int unsigned_cmp(wp_scalar a,wp_scalar b){int i;for(i=3;i>=0;--i){if(a.word[i]<b.word[i])return -1;if(a.word[i]>b.word[i])return 1;}return 0;}
static int cmp(wp_scalar a,wp_scalar b){if(negative(a)!=negative(b))return negative(a)?-1:1;return unsigned_cmp(a,b);}
int wp_eq(wp_scalar a,wp_scalar b){return unsigned_cmp(a,b)==0;}
int wp_ne(wp_scalar a,wp_scalar b){return unsigned_cmp(a,b)!=0;}
int wp_lt(wp_scalar a,wp_scalar b){return cmp(a,b)<0;}
int wp_gt(wp_scalar a,wp_scalar b){return cmp(a,b)>0;}
int wp_le(wp_scalar a,wp_scalar b){return cmp(a,b)<=0;}
int wp_ge(wp_scalar a,wp_scalar b){return cmp(a,b)>=0;}
static wp_scalar unsigned_add(wp_scalar a,wp_scalar b){uint32_t sum;unsigned i;uint16_t carry=0;wp_scalar r;for(i=0;i<4;++i){sum=(uint32_t)a.word[i]+b.word[i]+carry;r.word[i]=(uint16_t)sum;carry=(uint16_t)(sum>>16);}return r;}
static wp_scalar unsigned_sub(wp_scalar a,wp_scalar b){unsigned i;uint32_t term;uint16_t borrow=0;wp_scalar r;for(i=0;i<4;++i){term=(uint32_t)b.word[i]+borrow;r.word[i]=(uint16_t)((uint32_t)a.word[i]-term);borrow=(uint32_t)a.word[i]<term;}return r;}
wp_scalar wp_add(wp_scalar a,wp_scalar b){wp_scalar r=unsigned_add(a,b);if(negative(a)==negative(b)&&negative(r)!=negative(a))wp_wide_fail("add overflow");return r;}
wp_scalar wp_sub(wp_scalar a,wp_scalar b){wp_scalar r=unsigned_sub(a,b);if(negative(a)!=negative(b)&&negative(r)!=negative(a))wp_wide_fail("sub overflow");return r;}
wp_scalar wp_neg(wp_scalar a){wp_scalar r=unsigned_sub(zero,a);if(negative(a)&&wp_eq(r,a))wp_wide_fail("neg overflow");return r;}
wp_scalar wp_fabs(wp_scalar a){return negative(a)?wp_neg(a):a;}
static wp_scalar magnitude(wp_scalar a){return negative(a)?unsigned_sub(zero,a):a;}
static wp_scalar shift_left(wp_scalar a,unsigned count){unsigned i;uint16_t carry,next;while(count--){carry=0;for(i=0;i<4;++i){next=a.word[i]>>15;a.word[i]=(uint16_t)((a.word[i]<<1)|carry);carry=next;}}return a;}
static wp_scalar shift_right(wp_scalar a,unsigned count){int i;uint16_t carry,next;while(count--){carry=0;for(i=3;i>=0;--i){next=a.word[i]&1;a.word[i]=(uint16_t)((a.word[i]>>1)|(carry<<15));carry=next;}}return a;}
static wp_scalar rounded_shift(wp_scalar a,unsigned count){int neg=negative(a);wp_scalar r=magnitude(a),half=zero;half.word[0]=1;half=shift_left(half,count-1);r=shift_right(unsigned_add(r,half),count);return neg?unsigned_sub(zero,r):r;}
wp_scalar wp_int(int x){wp_scalar r;unsigned i;r.word[0]=(uint16_t)x;for(i=1;i<4;++i)r.word[i]=x<0?0xffff:0;return shift_left(r,WIDE_PORT_BITS);}
int wp_to_int(wp_scalar a){wp_scalar r=shift_right(magnitude(a),WIDE_PORT_BITS);return negative(a)?-(int)r.word[0]:(int)r.word[0];}
wp_scalar wp_floor(wp_scalar a){unsigned i;for(i=0;i<WIDE_PORT_BITS/16;++i)a.word[i]=0;if(WIDE_PORT_BITS%16)a.word[WIDE_PORT_BITS/16]&=(uint16_t)(0xffffU<<(WIDE_PORT_BITS%16));return a;}
static wp_scalar product(wp_scalar a,wp_scalar b,unsigned fraction){wp_scalar r;uint16_t status;wide_mul64(a.word,b.word,fraction,r.word,&status);if(status)wp_wide_fail("mul backend");return r;}
wp_scalar wp_mul(wp_scalar a,wp_scalar b){return product(a,b,WIDE_PORT_BITS);}
wp_scalar wp_div(wp_scalar a,wp_scalar b){wp_scalar r;uint16_t status;wide_div64(a.word,b.word,WIDE_PORT_BITS,r.word,&status);if(status)wp_wide_fail("div backend");return r;}
wp_scalar wp_sqrt(wp_scalar a){wp_scalar r;uint16_t status;wide_sqrt64(a.word,WIDE_PORT_BITS,r.word,&status);if(status)wp_wide_fail("sqrt backend");return r;}
wp_vec wp_vec_make(wp_scalar x,wp_scalar y){wp_vec r;r.x=x;r.y=y;return r;}
wp_vec wp_add_v(wp_vec a,wp_vec b){return wp_vec_make(wp_add(a.x,b.x),wp_add(a.y,b.y));}
wp_vec wp_sub_v(wp_vec a,wp_vec b){return wp_vec_make(wp_sub(a.x,b.x),wp_sub(a.y,b.y));}
wp_scalar wp_dot(wp_vec a,wp_vec b){return wp_add(wp_mul(a.x,b.x),wp_mul(a.y,b.y));}
wp_scalar wp_cross(wp_vec a,wp_vec b){return wp_sub(wp_mul(a.x,b.y),wp_mul(a.y,b.x));}
wp_vec wp_scale(wp_vec a,wp_scalar b){return wp_vec_make(wp_mul(a.x,b),wp_mul(a.y,b));}
wp_vec wp_scale_left(wp_scalar a,wp_vec b){return wp_scale(b,a);}
wp_vec wp_forgatas90fokkal(wp_vec a){return wp_vec_make(wp_neg(a.y),a.x);}
wp_scalar wp_absnegyzet(wp_vec a){return wp_add(wp_mul(a.x,a.x),wp_mul(a.y,a.y));}
wp_scalar wp_abs(wp_vec a){wp_scalar n=wp_absnegyzet(a),r=wp_sqrt(n);if(wp_eq(r,zero))return zero;return rounded_shift(wp_add(r,wp_div(n,r)),1);}
wp_vec wp_egys(wp_vec a){return wp_scale(a,wp_div(wp_int(1),wp_abs(a)));}
bool wp_wide_safe_axle_distance(wp_vec a){wp_scalar x=magnitude(a.x),y=magnitude(a.y),quarter=shift_right(wp_int(1),2);return wp_lt(x,wp_int(4))&&wp_lt(y,wp_int(4))&&(wp_ge(x,quarter)||wp_ge(y,quarter));}
wp_scalar wp_wide_constant_divide(wp_scalar a,wp_scalar b){return wp_div(a,b);}
wp_scalar wp_wide_constant_reciprocal(wp_scalar a){return wp_div(wp_int(1),a);}
wp_vec wp_wide_contact_normal(wp_kor* circle,wp_vec point,wp_scalar* length){wp_vec d=wp_sub_v(circle->r,point);*length=wp_abs(d);return wp_scale(wp_sub_v(circle->r,point),wp_div(wp_int(1),*length));}
wp_vec wp_wide_gravity_force(wp_vec direction,wp_scalar mass){
#if WIDE_GRAVITY_MASS_FOLDED
 return wp_scale(direction,*wp_ptr_G());
#else
 return wp_scale(wp_scale(direction,mass),*wp_ptr_G());
#endif
}

/* Raw unsigned division for phase reduction and table-index arithmetic.
 * Divisor is below 2^51; therefore a one-bit remainder shift cannot overflow. */
static wp_scalar unsigned_div(wp_scalar a,wp_scalar b,wp_scalar* remainder){wp_scalar q=zero,r=zero;int bit;for(bit=63;bit>=0;--bit){r=shift_left(r,1);r.word[0]|=(a.word[bit/16]>>(bit%16))&1;if(unsigned_cmp(r,b)>=0){r=unsigned_sub(r,b);q.word[bit/16]|=(uint16_t)(1U<<(bit%16));}}*remainder=r;return q;}
static wp_scalar divided_small(wp_scalar a,unsigned divisor){wp_scalar r;uint32_t n,rem=0;int i,neg=negative(a);a=magnitude(a);for(i=3;i>=0;--i){n=(rem<<16)|a.word[i];r.word[i]=(uint16_t)(n/divisor);rem=n%divisor;}if(2*rem>=divisor){wp_scalar one=zero;one.word[0]=1;r=unsigned_add(r,one);}return neg?unsigned_sub(zero,r):r;}
static wp_scalar raw_words(const uint16_t* words){wp_scalar r;r.word[0]=words[0];r.word[1]=words[1];r.word[2]=words[2];r.word[3]=words[3];return r;}
static wp_scalar trig_uncached(wp_scalar x,int cosine){
 wp_scalar pi=raw_words(wp_native_pi),quarter=shift_right(pi,1),period=shift_left(pi,1),phase,a,remainder,anchor,d,d2,d3,s,c,result,indexraw;
 unsigned index;int neg;
 /* Checked Q44->Q48 phase conversion; full signed48Q32 angle narrowing is
  * deliberately not used by this correctness-first reference. */
 phase=shift_left(x,48-WIDE_PORT_BITS);
 if(wp_ne(rounded_shift(phase,48-WIDE_PORT_BITS),x))wp_wide_fail("trig phase range");
 if(cosine)phase=wp_add(phase,quarter);
 unsigned_div(magnitude(phase),period,&a);if(negative(phase)&&wp_ne(a,zero))a=unsigned_sub(period,a);
 neg=wp_gt(a,pi);if(neg)a=wp_sub(a,pi);if(wp_gt(a,quarter))a=wp_sub(pi,a);
 indexraw=unsigned_div(shift_left(a,12),quarter,&remainder);index=indexraw.word[0];
 if(index>4096)index=4096;
 /* quarter*index fits signed64; multiplication with fraction0 is not needed. */
 anchor=zero;{wp_scalar part=quarter;unsigned multiplier=index;while(multiplier){if(multiplier&1)anchor=unsigned_add(anchor,part);part=shift_left(part,1);multiplier>>=1;}}anchor=shift_right(anchor,12);
 d=wp_sub(a,anchor);d2=product(d,d,48);d3=product(d2,d,48);
 if(index==4096){s=zero;s.word[3]=1;c=zero;}else{s=raw_words(wp_native_trig_row(index,0));c=raw_words(wp_native_trig_row(index,1));}
 result=wp_sub(wp_add(s,product(c,wp_sub(d,divided_small(d3,6)),48)),product(s,divided_small(d2,2),48));
 result=rounded_shift(result,48-WIDE_PORT_BITS);return neg?wp_neg(result):result;
}
static wp_scalar trig(wp_scalar x,int cosine){static struct{wp_scalar angle,value[2];unsigned valid;} cache[2];static unsigned next;unsigned i;for(i=0;i<2;++i)if(cache[i].valid&&wp_eq(cache[i].angle,x))break;if(i==2){i=next;next^=1;cache[i].angle=x;cache[i].valid=0;}if(!(cache[i].valid&(1U<<cosine))){cache[i].value[cosine]=trig_uncached(x,cosine);cache[i].valid|=1U<<cosine;}return cache[i].value[cosine];}
wp_scalar wp_sin(wp_scalar x){return trig(x,0);}
wp_scalar wp_cos(wp_scalar x){return trig(x,1);}
void wp_math_reset_stats(void){wp_native_error=0;}
void wp_math_print_stats(void){}
