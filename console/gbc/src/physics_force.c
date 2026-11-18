#include "physics_force.h"
#ifdef __SDCC
#pragma bank 8
int32_t riding_floor_div20(int32_t x) __sdcccall(0);
#else
static int32_t riding_floor_div20(int32_t x) {
    return x>=0 ? x/20 : -(int32_t)(((uint32_t)(-(int64_t)x)+19)/20);
}
#endif

extern int64_t force_residual[2];
typedef struct {
    int32_t fraction;
    uint32_t units;
    int8_t upper;
} force_sum_t;
/* Native assembly uses the packed SDCC layout: fraction[4], units[4],
 * upper[1]. The persistent residual retains its original signed Q24 format. */
static force_sum_t forces[2];
#ifdef __SDCC
typedef char force_sum_layout[sizeof(force_sum_t)==9 ? 1 : -1];
#endif

#ifndef __SDCC
void riding_force_begin(void) {
    for(uint8_t axis=0;axis<2;++axis) {
        force_sum_t *p=&forces[axis];
        uint64_t raw=(uint64_t)force_residual[axis];
        p->fraction=(int32_t)(raw&0xffffff);
        p->units=(uint32_t)(raw>>24);p->upper=(int8_t)(raw>>56);
    }
}

void riding_force_sub(uint8_t axis,int32_t units,int32_t fraction) {
    force_sum_t *p=&forces[axis];
    uint32_t previous=p->units;
    p->units=previous-(uint32_t)units;
    p->upper+=(units<0)-(previous<(uint32_t)units);
    p->fraction-=fraction;
}

#endif

static int32_t divide40(const force_sum_t *p)
#ifdef __SDCC
__sdcccall(0)
#endif
{
    uint32_t low=p->units,result=0;
    uint8_t high=(uint8_t)p->upper,negative=p->upper<0;
    uint16_t remainder=0;
    if(p->upper==((int32_t)low<0 ? -1 : 0))
        return riding_floor_div20((int32_t)low);
    if(negative) { high=(uint8_t)(0-high-(low!=0));low=0-low; }
    /* Rare full-width sums: base-256 long division, remainder always <20.
     * The four physical spring/damper terms and two torque terms fit40 bits. */
    for(uint8_t i=0;i<5;++i) {
        uint16_t word=(remainder<<8)|high;
        uint8_t digit=(uint8_t)(word/20U);
        remainder=word-(uint16_t)digit*20U;
        result=(result<<8)|digit;
        high=(uint8_t)(low>>24);low<<=8;
    }
    return (int32_t)(negative ? 0-result-(remainder!=0) : result);
}

#ifndef __SDCC
int32_t riding_force_finish(uint8_t axis) {
    force_sum_t *p=&forces[axis];
    int32_t carry=(p->fraction>>24)+10;
    uint32_t previous=p->units;
    p->units+=(uint32_t)carry;
    p->upper+=(carry<0 ? -1 : 0)+(p->units<previous);
    int32_t result=divide40(p);
    int32_t remainder=(int32_t)(p->units-10U-(uint32_t)result*20U);
    force_residual[axis]=(int64_t)remainder*(1L<<24)+((uint32_t)p->fraction&0xffffff);
    return result;
}

#endif

#ifdef __SDCC
#pragma save
#pragma disable_warning 85
/* Copy the residual without shifting a 64-bit temporary. */
void riding_force_begin(void) __sdcccall(0) __naked {
 __asm
 ld hl,#(_force_residual+0)
 ld de,#(_forces+0)
 ld a,(hl+)
 ld (de),a
 inc de
 ld a,(hl+)
 ld (de),a
 inc de
 ld a,(hl+)
 ld (de),a
 inc de
 xor a,a
 ld (de),a
 inc de
 ld a,(hl+)
 ld (de),a
 inc de
 ld a,(hl+)
 ld (de),a
 inc de
 ld a,(hl+)
 ld (de),a
 inc de
 ld a,(hl+)
 ld (de),a
 inc de
 ld a,(hl+)
 ld (de),a
 inc de
 ld hl,#(_force_residual+8)
 ld de,#(_forces+9)
 ld a,(hl+)
 ld (de),a
 inc de
 ld a,(hl+)
 ld (de),a
 inc de
 ld a,(hl+)
 ld (de),a
 inc de
 xor a,a
 ld (de),a
 inc de
 ld a,(hl+)
 ld (de),a
 inc de
 ld a,(hl+)
 ld (de),a
 inc de
 ld a,(hl+)
 ld (de),a
 inc de
 ld a,(hl+)
 ld (de),a
 inc de
 ld a,(hl+)
 ld (de),a
 inc de
 ret
 __endasm;
}

/* Stack ABI: axis at +2, signed units at +3, fraction at +7.
 * Subtract the sign-extended units through all five bytes independently
 * of the four-byte fraction. INC, LD and POP preserve the borrow flag. */
void riding_force_sub(uint8_t axis,int32_t units,int32_t fraction) __sdcccall(0) __naked {
 __asm
 ldhl sp,#2
 ld a,(hl)
 or a,a
 ld de,#_forces
 jr z,force_sub_axis
 ld de,#(_forces+9)
force_sub_axis:
 push de
 inc de
 inc de
 inc de
 inc de
 ldhl sp,#8
 ld a,(hl)
 add a,a
 sbc a,a
 ld c,a
 ldhl sp,#5
 ld a,(de)
 sub a,(hl)
 ld (de),a
 inc hl
 inc de
 ld a,(de)
 sbc a,(hl)
 ld (de),a
 inc hl
 inc de
 ld a,(de)
 sbc a,(hl)
 ld (de),a
 inc hl
 inc de
 ld a,(de)
 sbc a,(hl)
 ld (de),a
 inc hl
 inc de
 ld a,(de)
 sbc a,c
 ld (de),a
 pop de
 ld a,(de)
 sub a,(hl)
 ld (de),a
 inc hl
 inc de
 ld a,(de)
 sbc a,(hl)
 ld (de),a
 inc hl
 inc de
 ld a,(de)
 sbc a,(hl)
 ld (de),a
 inc hl
 inc de
 ld a,(de)
 sbc a,(hl)
 ld (de),a
 inc hl
 inc de
 ret
 __endasm;
}

/* Four fractions in [-2^23,2^23), plus the residual's nonnegative low
 * 24 bits, give a normalization carry in [-2,2]. Adding the half-divisor
 * makes that carry positive (8..12). The resulting integer is signed40.
 * After division the remainder is in [-10,9], so its low byte determines
 * every high byte exactly; no force precision is discarded. */
int32_t riding_force_finish(uint8_t axis) __sdcccall(0) __naked {
 __asm
 ldhl sp,#2
 ld a,(hl)
 or a,a
 ld hl,#_forces
 ld de,#_force_residual
 jr z,force_finish_axis
 ld hl,#(_forces+9)
 ld de,#(_force_residual+8)
force_finish_axis:
 push de
 push hl
 inc hl
 inc hl
 inc hl
 ld a,(hl+)
 add a,#10
 ld b,a
 ld a,(hl)
 add a,b
 ld (hl+),a
 ld a,(hl)
 adc a,#0
 ld (hl+),a
 ld a,(hl)
 adc a,#0
 ld (hl+),a
 ld a,(hl)
 adc a,#0
 ld (hl+),a
 ld a,(hl)
 adc a,#0
 ld (hl-),a
 ld b,a
 ld a,(hl)
 add a,a
 sbc a,a
 cp a,b
 jr nz,force_finish_wide
 pop hl
 push hl
 inc hl
 inc hl
 inc hl
 inc hl
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld c,(hl)
 inc hl
 ld b,(hl)
 push bc
 push de
 call _riding_floor_div20
 add sp,#4
 jr force_finish_store
force_finish_wide:
 pop hl
 push hl
 push hl
 call _divide40
 add sp,#2
force_finish_store:
 push hl
 push de
 ld a,e
 add a,a
 add a,a
 ld b,a
 add a,a
 add a,a
 add a,b
 ld b,a
 ldhl sp,#4
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 inc hl
 inc hl
 inc hl
 inc hl
 ld a,(hl)
 sub a,b
 sub a,#10
 dec hl
 ld (hl),a
 ldhl sp,#6
 ld e,(hl)
 inc hl
 ld d,(hl)
 ldhl sp,#4
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,(hl+)
 ld (de),a
 inc de
 ld a,(hl+)
 ld (de),a
 inc de
 ld a,(hl+)
 ld (de),a
 inc de
 ld a,(hl)
 ld (de),a
 inc de
 add a,a
 sbc a,a
 ld (de),a
 inc de
 ld (de),a
 inc de
 ld (de),a
 inc de
 ld (de),a
 pop de
 pop hl
 add sp,#4
 ret
 __endasm;
}

#pragma restore
#endif
