#include "physics_math32.h"

#ifndef __SDCC
/* Independent host oracle. Native code below does not rely on int64 support. */
static int32_t clamp32(int64_t x) {
    if(x>INT32_MAX)return INT32_MAX;
    if(x<INT32_MIN)return INT32_MIN;
    return (int32_t)x;
}

int32_t riding_kmul32(int32_t x,uint8_t m,uint8_t e) {
    return clamp32(((int64_t)x*m+((int64_t)1<<(e-1)))>>e);
}

int32_t riding_mulq32(int32_t x,int16_t y,uint8_t shift) {
    return clamp32(((int64_t)x*y+((int64_t)1<<(shift-1)))>>shift);
}

int32_t riding_mulshift32(int32_t x,int16_t y,uint8_t shift) {
    return clamp32(((int64_t)x*y)>>shift);
}

int32_t riding_dotq32(int32_t a,int32_t b,int16_t c,int16_t d,uint8_t shift) {
    return clamp32(((int64_t)a*c+(int64_t)b*d+((int64_t)1<<(shift-1)))>>shift);
}

int16_t riding_torque_input32(const riding_torque32_t *t) {
    int64_t sum=0;
    uint8_t i;
    for(i=0;i<2;++i)sum+=(int64_t)t->kx[i]*t->rely[i]-(int64_t)t->ky[i]*t->relx[i];
    sum>>=10;
    if(sum>INT16_MAX)return INT16_MAX;
    if(sum<INT16_MIN)return INT16_MIN;
    return (int16_t)sum;
}
#else
/* A signed56 container holds every full product and the four-term torque sum.
 * Low16 + middle32 + signed upper8 avoid SDCC's lack of native int64 support.
 * Only the final shifted output is clamped. No shared scratch RAM is used.
 */
typedef struct { uint16_t lo;uint32_t mid;int8_t top; } wide_t;
extern const uint32_t riding_math32_positive_limit[17];
int32_t riding_mul16(int16_t a,int16_t b) __sdcccall(0);
int16_t kmul(int16_t x,uint8_t m,uint8_t e) __sdcccall(0);

static void product(wide_t *out,int32_t x,int16_t y) {
    int16_t lower=(int16_t)x,upper=(int16_t)(x>>16);
    int32_t p=riding_mul16(lower,y),hi;
    out->lo=(uint16_t)p;
    /* The common signed16 input still retains the complete signed32 product. */
    if((upper==0 && lower>=0)||(upper==-1 && lower<0))hi=p>>16;
    else {
        hi=p>>16;
        if(lower<0)hi+=y; /* unsigned low-half correction */
        if(upper)hi+=riding_mul16(upper,y);
    }
    out->mid=(uint32_t)hi;
    out->top=hi<0 ? -1 : 0;
}

static void add(wide_t *a,const wide_t *b) {
    uint16_t lo=a->lo;
    uint32_t mid=a->mid,sum;
    uint8_t carry;
    a->lo+=b->lo;
    carry=a->lo<lo;
    sum=mid+b->mid;
    a->top=(int8_t)((int16_t)a->top+b->top+(sum<mid));
    a->mid=sum+carry;
    if(a->mid<sum)++a->top;
}

static void subtract(wide_t *a,const wide_t *b) {
    uint16_t lo=a->lo;
    uint32_t mid=a->mid,difference;
    uint8_t borrow=lo<b->lo;
    a->lo-=b->lo;
    difference=mid-b->mid;
    a->top=(int8_t)((int16_t)a->top-b->top-(mid<b->mid));
    a->mid=difference-borrow;
    if(difference<borrow)--a->top;
}

static int32_t finish(wide_t *v,uint8_t shift,uint8_t rounded) {
    uint16_t previous;
    uint32_t limit;
    if(rounded) {
        previous=v->lo;
        v->lo+=(uint16_t)1U<<(shift-1);
        if(v->lo<previous) {
            if(++v->mid==0)++v->top;
        }
    }
    limit=riding_math32_positive_limit[shift];
    if(v->top>=0) {
        if(v->top || v->mid>limit)return 2147483647L;
    } else if(v->top!=-1 || v->mid<~limit)return (-2147483647L-1L);
    if(shift==16)return (int32_t)v->mid;
    return (int32_t)(((uint32_t)v->lo>>shift)|(v->mid<<(16-shift)));
}

int32_t riding_kmul32_wide(int32_t x,uint8_t m,uint8_t e) __sdcccall(0) {
    wide_t value;
    if(x==(int32_t)(int16_t)x) {
        return (riding_mul16((int16_t)x,(int16_t)m)+(1L<<(e-1)))>>e;
    }
    product(&value,x,(int16_t)m);
    return finish(&value,e,1);
}

int32_t riding_mulq32_wide(int32_t x,int16_t y,uint8_t shift) __sdcccall(0) {
    wide_t value;
    if(x==(int32_t)(int16_t)x)
        return (riding_mul16((int16_t)x,y)+(1L<<(shift-1)))>>shift;
    product(&value,x,y);
    return finish(&value,shift,1);
}

int32_t riding_mulshift32(int32_t x,int16_t y,uint8_t shift) __sdcccall(0) {
    wide_t value;
    if(x==(int32_t)(int16_t)x)return riding_mul16((int16_t)x,y)>>shift;
    product(&value,x,y);
    return finish(&value,shift,0);
}

int32_t riding_dotq32_wide(int32_t a,int32_t b,int16_t c,int16_t d,uint8_t shift) __sdcccall(0) {
    wide_t value,other;
    int32_t p,q,sum,half;
    if(a==(int32_t)(int16_t)a && b==(int32_t)(int16_t)b) {
        p=riding_mul16((int16_t)a,c);q=riding_mul16((int16_t)b,d);
        sum=(int32_t)((uint32_t)p+(uint32_t)q);
        half=1L<<(shift-1);
        /* Unsigned addition avoids UB. Detect the rare signed overflow before
         * the rounding addition; neither product nor output is clamped16. */
        if(((p<0)!=(q<0) || (sum<0)==(p<0)) && sum<=2147483647L-half)
            return (sum+half)>>shift;
    }
    product(&value,a,c);product(&other,b,d);add(&value,&other);
    return finish(&value,shift,1);
}

int16_t riding_torque_narrow32(const riding_torque32_t *t) __sdcccall(0);

int16_t riding_torque_input32(const riding_torque32_t *t) __sdcccall(0) {
    wide_t value,other;
    uint8_t i;
    int32_t result;
    if(t->relx[0]==(int32_t)(int16_t)t->relx[0]
       && t->relx[1]==(int32_t)(int16_t)t->relx[1]
       && t->rely[0]==(int32_t)(int16_t)t->rely[0]
       && t->rely[1]==(int32_t)(int16_t)t->rely[1])return riding_torque_narrow32(t);
    value.lo=0;value.mid=0;value.top=0;
    for(i=0;i<2;++i) {
        product(&other,t->rely[i],t->kx[i]);add(&value,&other);
        product(&other,t->relx[i],t->ky[i]);subtract(&value,&other);
    }
    result=finish(&value,10,0);
    if(result>32767L)return 32767;
    if(result< -32768L)return -32768;
    return (int16_t)result;
}
#endif
