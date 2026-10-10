#pragma once
// Host feasibility arithmetic. The solver's only numeric storage is signed
// int64 Q(WIDE_BITS); intermediates are checked signed __int128 integers.
// Floating conversion is restricted to JSON output, never solver equations.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <type_traits>
#ifndef WIDE_BITS
#define WIDE_BITS 32
#endif

struct wide_stats_t {
    uint64_t add=0, sub=0, mul=0, div=0, compare=0, square_root=0, trig=0;
    uint64_t integer_multiply=0, power_two_divide=0, overflow=0;
    uint64_t trig_q48_multiply=0, maximum_trig_abs_raw=0;
    uint64_t mul_operand_bits[65]={}, div_operand_bits[65]={};
    uint64_t maximum_abs_raw=0, minimum_divisor_raw=UINT64_MAX;
    unsigned maximum_product_bits=0, maximum_dividend_bits=0;
};
inline wide_stats_t wide_stats;
inline uint64_t wide_magnitude(int64_t x) {return x<0 ? uint64_t(-(__int128)x) : uint64_t(x);}
inline unsigned wide_bits(unsigned __int128 x) {unsigned n=0;while(x){++n;x>>=1;}return n;}
[[noreturn]] inline void wide_fail(const char* op) {
    ++wide_stats.overflow;
    std::fprintf(stderr,"WIDE_OVERFLOW_OR_DOMAIN %s Q%d\n",op,WIDE_BITS);
    std::abort();
}
inline int64_t wide_checked(__int128 x,const char* op) {
    if(x<INT64_MIN || x>INT64_MAX)wide_fail(op);
    auto raw=(int64_t)x;auto m=wide_magnitude(raw);
    if(m>wide_stats.maximum_abs_raw)wide_stats.maximum_abs_raw=m;
    return raw;
}
inline int64_t wide_trig_checked(__int128 x,const char* op) {
    if(x<INT64_MIN || x>INT64_MAX)wide_fail(op);
    auto raw=(int64_t)x;auto m=wide_magnitude(raw);
    if(m>wide_stats.maximum_trig_abs_raw)wide_stats.maximum_trig_abs_raw=m;
    return raw;
}
inline __int128 wide_round_div(__int128 n,__int128 d) {
    if(!d)wide_fail("divide by zero");
    bool negative=(n<0)!=(d<0);if(n<0)n=-n;if(d<0)d=-d;
    __int128 q=n/d,r=n%d;if(r>=d-r)++q;return negative ? -q:q;
}

struct wide_scalar {
    int64_t raw=0;
    static constexpr int fractional_bits=WIDE_BITS;
    static constexpr int64_t scale=int64_t(1)<<WIDE_BITS;
    wide_scalar()=default;
    template<class T,typename std::enable_if<std::is_integral<T>::value,int>::type=0>
    wide_scalar(T x):raw(wide_checked((__int128)x*scale,"integer conversion")){}
    static wide_scalar from_raw(int64_t x) {wide_scalar w;w.raw=x;return w;}
    static wide_scalar literal(const char* s) {
        bool neg=false;if(*s=='-'||*s=='+'){neg=*s=='-';++s;}
        __int128 value=0,denominator=1;int fractional=0;bool point=false;
        while((*s>='0'&&*s<='9')||*s=='.'){
            if(*s=='.')point=true;
            else {value=value*10+(*s-'0');if(point)++fractional;}
            ++s;
        }
        int exponent=0;if(*s=='e'||*s=='E'){++s;exponent=std::atoi(s);}
        exponent-=fractional;
        if(exponent>=0){while(exponent--)value*=10;}
        else {if(exponent < -30)return from_raw(0);while(exponent++)denominator*=10;}
        return from_raw(wide_checked(wide_round_div((neg?-value:value)*scale,denominator),"decimal conversion"));
    }
    // Original grid code truncates scalar coordinates to integer cell indices.
    operator int()const {return int(raw/scale);}
    double output_double()const {return double(raw)/double(scale);}
    wide_scalar operator-()const {return from_raw(wide_checked(-(__int128)raw,"negate"));}
    wide_scalar& operator+=(wide_scalar b);
    wide_scalar& operator-=(wide_scalar b);
    wide_scalar& operator*=(wide_scalar b);
    wide_scalar& operator/=(wide_scalar b);
};
inline wide_scalar operator+(wide_scalar a,wide_scalar b){++wide_stats.add;return wide_scalar::from_raw(wide_checked((__int128)a.raw+b.raw,"add"));}
inline wide_scalar operator-(wide_scalar a,wide_scalar b){++wide_stats.sub;return wide_scalar::from_raw(wide_checked((__int128)a.raw-b.raw,"subtract"));}
inline wide_scalar operator*(wide_scalar a,wide_scalar b){
    ++wide_stats.mul;auto am=wide_magnitude(a.raw),bm=wide_magnitude(b.raw);
    ++wide_stats.mul_operand_bits[wide_bits(am)];++wide_stats.mul_operand_bits[wide_bits(bm)];
    if(a.raw%wide_scalar::scale==0 || b.raw%wide_scalar::scale==0)++wide_stats.integer_multiply;
    __int128 p=(__int128)a.raw*b.raw;unsigned bits=wide_bits(p<0?-p:p);
    if(bits>wide_stats.maximum_product_bits)wide_stats.maximum_product_bits=bits;
    return wide_scalar::from_raw(wide_checked(wide_round_div(p,wide_scalar::scale),"multiply"));
}
inline wide_scalar operator/(wide_scalar a,wide_scalar b){
    ++wide_stats.div;auto m=wide_magnitude(b.raw);
    ++wide_stats.div_operand_bits[wide_bits(wide_magnitude(a.raw))];++wide_stats.div_operand_bits[wide_bits(m)];
    if(m<wide_stats.minimum_divisor_raw)wide_stats.minimum_divisor_raw=m;
    if(m && !(m&(m-1)))++wide_stats.power_two_divide;
    __int128 p=(__int128)a.raw*wide_scalar::scale;unsigned bits=wide_bits(p<0?-p:p);
    if(bits>wide_stats.maximum_dividend_bits)wide_stats.maximum_dividend_bits=bits;
    return wide_scalar::from_raw(wide_checked(wide_round_div(p,b.raw),"divide"));
}
#define WIDE_COMPARE(OP) inline bool operator OP(wide_scalar a,wide_scalar b){++wide_stats.compare;return a.raw OP b.raw;}
WIDE_COMPARE(<) WIDE_COMPARE(>) WIDE_COMPARE(<=) WIDE_COMPARE(>=) WIDE_COMPARE(==) WIDE_COMPARE(!=)
#undef WIDE_COMPARE
#define WIDE_INTEGER(OP) \
template<class T,typename std::enable_if<std::is_integral<T>::value,int>::type=0> \
inline auto operator OP(wide_scalar a,T b)->decltype(a OP wide_scalar(b)){return a OP wide_scalar(b);} \
template<class T,typename std::enable_if<std::is_integral<T>::value,int>::type=0> \
inline auto operator OP(T a,wide_scalar b)->decltype(wide_scalar(a) OP b){return wide_scalar(a) OP b;}
WIDE_INTEGER(+) WIDE_INTEGER(-) WIDE_INTEGER(*) WIDE_INTEGER(/)
WIDE_INTEGER(<) WIDE_INTEGER(>) WIDE_INTEGER(<=) WIDE_INTEGER(>=) WIDE_INTEGER(==) WIDE_INTEGER(!=)
#undef WIDE_INTEGER
inline wide_scalar& wide_scalar::operator+=(wide_scalar b){return *this=*this+b;}
inline wide_scalar& wide_scalar::operator-=(wide_scalar b){return *this=*this-b;}
inline wide_scalar& wide_scalar::operator*=(wide_scalar b){return *this=*this*b;}
inline wide_scalar& wide_scalar::operator/=(wide_scalar b){return *this=*this/b;}
inline wide_scalar fabs(wide_scalar x){return x.raw<0?-x:x;}
inline wide_scalar floor(wide_scalar x){__int128 q=x.raw/wide_scalar::scale;if(x.raw<0 && x.raw%wide_scalar::scale)--q;return wide_scalar::from_raw(wide_checked(q*wide_scalar::scale,"floor"));}
inline wide_scalar sqrt(wide_scalar x){
    ++wide_stats.square_root;if(x.raw<0)wide_fail("negative square root");
    unsigned __int128 n=(unsigned __int128)x.raw*wide_scalar::scale,rem=n,root=0,bit=(unsigned __int128)1<<126;
    while(bit>rem)bit>>=2;
    while(bit){if(rem>=root+bit){rem-=root+bit;root=(root>>1)+bit;}else root>>=1;bit>>=2;}
    if(n-root*root > root)++root;
    return wide_scalar::from_raw(wide_checked(root,"square root"));
}

// Generated at build time using host trig; no runtime floating solver calls.
#include "wide_trig_table.h"
inline int64_t wide_q48_mul(int64_t a,int64_t b){++wide_stats.trig_q48_multiply;return wide_trig_checked(wide_round_div((__int128)a*b,(__int128)1<<48),"trig intermediate");}
inline wide_scalar wide_trig(wide_scalar x,bool cosine){
    ++wide_stats.trig;
    const int64_t pi=WIDE_PI_Q48;
    __int128 phase=(__int128)x.raw*(int64_t(1)<<(48-WIDE_BITS));
    if(cosine)phase+=pi/2;
    int64_t a=(int64_t)(phase%(2*pi));if(a<0)a+=2*pi;
    bool negative=a>pi;if(negative)a-=pi;if(a>pi/2)a=pi-a;
    int64_t quarter=pi/2;
    unsigned i=(unsigned)((__int128)a*WIDE_TRIG_INTERVALS/quarter);if(i>WIDE_TRIG_INTERVALS)i=WIDE_TRIG_INTERVALS;
    int64_t anchor=(int64_t)((__int128)i*quarter/WIDE_TRIG_INTERVALS);
    int64_t d=a-anchor;
    int64_t d2=wide_q48_mul(d,d),d3=wide_q48_mul(d2,d);
    int64_t s=wide_sin_q48[i],c=wide_cos_q48[i];
    int64_t result=wide_trig_checked((__int128)s+wide_q48_mul(c,d-wide_round_div(d3,6))-wide_q48_mul(s,wide_round_div(d2,2)),"trig expansion");
    auto raw=wide_checked(wide_round_div(result,(__int128)1<<(48-WIDE_BITS)),"trig result");
    return wide_scalar::from_raw(negative?-raw:raw);
}
inline wide_scalar sin(wide_scalar x){return wide_trig(x,false);}
inline wide_scalar cos(wide_scalar x){return wide_trig(x,true);}
inline int wide_scan_pair(FILE* f,wide_scalar* x,wide_scalar* y){char a[128],b[128];int n=fscanf(f,"%127s %127s",a,b);if(n==2){*x=wide_scalar::literal(a);*y=wide_scalar::literal(b);}return n;}
inline int wide_scan_object(FILE* f,int* t,wide_scalar* x,wide_scalar* y,int* k,int* o){char a[128],b[128];int n=fscanf(f,"%d %127s %127s %d %d",t,a,b,k,o);if(n==5){*x=wide_scalar::literal(a);*y=wide_scalar::literal(b);}return n;}
inline void wide_print_stats(const char* phase,const wide_stats_t& s){
    std::fprintf(stderr,"WIDE_STATS {\"phase\":\"%s\",\"bits\":%d,\"add\":%llu,\"sub\":%llu,\"mul\":%llu,\"div\":%llu,\"compare\":%llu,\"sqrt\":%llu,\"trig\":%llu,\"integer_multiply\":%llu,\"power_two_divide\":%llu,\"max_abs_raw\":%llu,\"min_divisor_raw\":%llu,\"max_product_bits\":%u,\"max_dividend_bits\":%u,\"overflow\":%llu,\"mul_operand_bits\":[",
      phase,WIDE_BITS,s.add,s.sub,s.mul,s.div,s.compare,s.square_root,s.trig,s.integer_multiply,s.power_two_divide,s.maximum_abs_raw,s.minimum_divisor_raw,s.maximum_product_bits,s.maximum_dividend_bits,s.overflow);
    for(unsigned i=0;i<=64;++i)std::fprintf(stderr,"%s%llu",i?",":"",s.mul_operand_bits[i]);
    std::fprintf(stderr,"],\"div_operand_bits\":[");for(unsigned i=0;i<=64;++i)std::fprintf(stderr,"%s%llu",i?",":"",s.div_operand_bits[i]);
    std::fprintf(stderr,"],\"trig_q48_multiply\":%llu,\"max_trig_abs_raw\":%llu}\n",s.trig_q48_multiply,s.maximum_trig_abs_raw);
}
