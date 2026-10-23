#include "elma_x87.h"
#include "upstream/bochs/cpu/fpu/fpu_trans.h"
#include <cstring>
namespace {
double evaluate(double value, bool cosine) {
    static_assert(sizeof(double)==sizeof(uint64_t), "binary64 storage");
    uint64_t bits;
    std::memcpy(&bits,&value,sizeof(bits));
    softfloat_status_t status={};
    status.softfloat_roundingMode=softfloat_round_near_even;
    status.softfloat_exceptionMasks=0x3f;
    status.extF80_roundingPrecision=80;
    floatx80 operand=f64_to_extF80(bits,&status);
    if(cosine) fcos(operand,status);
    else fsin(operand,status);
    bits=extF80_to_f64(operand,&status);
    double result;
    std::memcpy(&result,&bits,sizeof(result));
    return result;
}
}
extern "C" double elma_x87_sin(double value) {return evaluate(value,false);}
extern "C" double elma_x87_cos(double value) {return evaluate(value,true);}
extern "C" void elma_x87_sincos(double value,double* sine,double* cosine) {
    *sine=elma_x87_sin(value);
    *cosine=elma_x87_cos(value);
}
