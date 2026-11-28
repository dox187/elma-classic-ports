/* Rotated original LGR parts; wheel/head positions follow physics directly.
 * Limb articulation is represented by three precomputed rider-compression poses.
 */
/* The scheduled cartridge places sprite positioning in bank 13. The upload
 * routines execute in fixed ROM while selecting the bank containing a tile. */
#ifdef RIDING_BANKED_DRAW
#pragma bank 13
#define BIKE_FIXED NONBANKED
#else
#define BIKE_FIXED
#endif
#include <gb/gb.h>
#include <gb/cgb.h>
#include <stddef.h>
#include <string.h>
#include "bike_render16.h"
#include "riding_assets.h"

/* Eight 8x16 body pairs, shadow X/Y only; tile/properties remain cached.
 * At most four body columns, four wheel columns and one head intersect any
 * scanline, keeping the complete motor below the ten-OBJ hardware limit. */
static void body16(uint8_t x,uint8_t y,uint8_t mask) __sdcccall(0) __naked {
    __asm
    ldhl sp,#2
    ld d,(hl)
    inc hl
    ld e,(hl)
    inc hl
    ld b,(hl)
_body16_registers:
    .macro body_position
    srl b
    sbc a,a
    and e
    ld (hl+),a
    ld (hl),d
    inc l
    inc l
    inc l
    .endm
    .macro body_row
    .rept 3
    body_position
    ld a,d
    add a,#8
    ld d,a
    .endm
    body_position
    .endm
    ld hl,#_shadow_OAM
    body_row
    ld a,d
    sub a,#24
    ld d,a
    ld a,e
    add a,#16
    ld e,a
    body_row
    ret
    __endasm;
}

static uint8_t last_body,last_wheel[2];
static uint16_t last_head;
#ifdef RIDING_BODY_TRANSFERS
uint16_t bike_streamed_heads[2];
#else
static uint16_t previous_head;
#endif
static uint16_t head_upload_frame;
static uint8_t head_tile;
static uint8_t positions_valid,center_x,center_y,center_mask;
static uint8_t prepared,prepared_changed;
static bike_screen_t last_screen;

void bike_render16_init_sprites(void) BANKED;

void bike_render_init(void) BIKE_DRAW_CALL {
    last_body=last_wheel[0]=last_wheel[1]=255;
    last_head=256;
#ifdef RIDING_BODY_TRANSFERS
    bike_streamed_heads[0]=bike_streamed_heads[1]=256;
#else
    previous_head=256;
#endif
    head_tile=BIKE_HEAD_TILE;
    head_upload_frame=0;
    positions_valid=0;
    center_y=0;
    prepared=0;
    bike_render16_init_sprites();
}

void bike_render_hide(void) BIKE_FIXED {
    uint8_t i;
    for(i=0;i<BIKE_OBJECT_OAM_BASE;++i)move_sprite(i,0,0);
    positions_valid=0;
    center_y=0;
    prepared=0;
}

/* A fresh HBlank plus the following OAM scan provides at least
 * (87+80)*2 = 334 double-speed CPU T-cycles before VRAM closes again.
 * Allow 36 T between STAT reads, 40 T for the successful test and launch, and
 * transfer at most three tiles (192 T), leaving 66 T of margin.
 * https://gbdev.io/pandocs/Rendering.html
 * https://gbdev.io/pandocs/VRAM_DMA_Transfers.html */
static void upload_aligned(uint8_t tile,uint8_t count,const uint8_t *source) __sdcccall(0) BIKE_FIXED __naked {
    __asm
_bike_dma_begin::
    ldhl sp,#2
    ld a,(hl+)
    swap a
    ld e,a
    and a,#15
    or a,#0x80
    ld d,a
    ld a,e
    and a,#0xf0
    ld e,a
    ld a,(hl+)
    ld b,a
    ld a,(hl+)
    ld h,(hl)
    ld l,a
#ifdef RIDING_BODY_TRANSFERS
_bike_dma_regs::
#endif
010$:
    ld a,h
    ldh (#0x51),a
    ld a,l
    ldh (#0x52),a
    ld a,d
    ldh (#0x53),a
    ld a,e
    ldh (#0x54),a
    ldh a,(#0x40)
    bit 7,a
    jr nz,011$
    ld a,b
    dec a
    ldh (#0x55),a
    ret
011$:
    di
    ldh a,(#0x41)
    and a,#3
    cp a,#1
    jr nz,013$
    ; LY144..151 leave at least two complete lines for all 16 blocks.
    ldh a,(#0x44)
    sub a,#144
    cp a,#8
    jr nc,012$
    ld a,b
    dec a
    ldh (#0x55),a
    ei
    ret
012$:
    ; One tile fits even at the last dot of VBlank plus the next mode 2.
    ; LY can already be zero during line 153. Recheck STAT just before launch.
    ldh a,(#0x41)
    and a,#3
    cp a,#1
    jr nz,013$
    ld c,#0
    jr 017$
013$:
    cp a,#3
    jr z,014$
    ei
    jr 011$
014$:
    ld a,b
    cp a,#3
    jr c,015$
    ld a,#3
015$:
    dec a
    ld c,a
    ; We sampled mode 3 before computing the count. Recheck it to avoid
    ; treating the tail of that HBlank as its beginning.
    ldh a,(#0x41)
    and a,#3
    cp a,#3
    jr nz,013$
016$:
    ldh a,(#0x41)
    rra
    jr c,016$
017$:
    ld a,c
    ldh (#0x55),a
    ei
    inc c
    ld a,b
    sub a,c
    ret z
    ld b,a
    ; Reprogram both hardware addresses for every following chunk.
    ld a,c
    swap a
    ld c,a
    add a,l
    ld l,a
    jr nc,018$
    inc h
018$:
    ld a,c
    add a,e
    ld e,a
    jr nc,010$
    inc d
    jr 010$
_bike_dma_end::
    __endasm;
}

static void upload(uint8_t tile,uint8_t count,const uint8_t *data) BIKE_FIXED {
    if((uint16_t)data&15)set_sprite_data(tile,count,data);
    else upload_aligned(tile,count,data);
}

static void place(uint8_t sprite,int16_t x,int16_t y) {
    if(x < -7 || x >= 160 || y < -15 || y >= 136)move_sprite(sprite,0,0);
    else move_sprite(sprite,(uint8_t)(x+8),(uint8_t)(y+16));
}

/* Most riding frames fit the complete bike inside the playfield. Publish the
 * thirteen coordinate pairs directly from the projected signed words. The
 * edge renderer below also handles coordinates outside the byte range. */
typedef char screen_parts_layout[
    offsetof(bike_screen_t,body_y)==2 && offsetof(bike_screen_t,head_x)==8 &&
    offsetof(bike_screen_t,head_y)==10 && offsetof(bike_screen_t,wheel_x)==12 &&
    offsetof(bike_screen_t,wheel_y)==16 ? 1 : -1];
static uint8_t draw_centered(const bike_screen_t *s,uint8_t mask) __sdcccall(0) __naked {
    __asm
    ldhl sp,#4
    ld b,(hl)
    dec hl
    ld a,(hl-)
    ld l,(hl)
    ld h,a
    ld a,(hl+)
    sub a,#16
    cp a,#129
    jp nc,021$
    add a,#8
    ld d,a
    ld a,(hl+)
    or a
    jp nz,021$
    ld a,(hl+)
    sub a,#16
    cp a,#105
    jp nc,021$
    add a,#16
    ld e,a
    ld a,(hl+)
    or a
    jp nz,021$
    ; The camera often keeps the body on the same pixel while the head and
    ; wheels continue to move. Only these three bytes determine all eight
    ; coordinate pairs. Zero is outside the admitted centered Y range.
    ld a,(_center_y)
    cp e
    jr nz,023$
    ld a,(_center_x)
    cp d
    jr nz,023$
    ld a,(_center_mask)
    cp b
    jr z,024$
023$:
    ld a,e
    ld (_center_y),a
    ld a,d
    ld (_center_x),a
    ld a,b
    ld (_center_mask),a
    push hl
    call _body16_registers
    pop hl
024$:
    ld de,#4
    add hl,de
    ; Head origin is (center - 4,center - 4), hardware offsets (8,16).
    ld a,(hl+)
    cp a,#164
    jp nc,021$
    add a,#4
    ld d,a
    ld a,(hl+)
    or a
    jp nz,021$
    ld a,(hl+)
    cp a,#140
    jp nc,021$
    add a,#12
    ld e,a
    ld a,(hl+)
    or a
    jp nz,021$
    ld a,d
    ld (_shadow_OAM+49),a
    ld a,e
    ld (_shadow_OAM+48),a
    ; The contiguous wheel words are x0,x1,y0,y1.
    ld c,#145
    call 022$
    jp nc,021$
    ld d,a
    call 022$
    jp nc,021$
    ld e,a
    ld c,#121
    call 022$
    jp nc,021$
    add a,#8
    ld (_shadow_OAM+32),a
    ld (_shadow_OAM+36),a
    ld a,d
    ld (_shadow_OAM+33),a
    add a,#8
    ld (_shadow_OAM+37),a
    call 022$
    jp nc,021$
    add a,#8
    ld (_shadow_OAM+40),a
    ld (_shadow_OAM+44),a
    ld a,e
    ld (_shadow_OAM+41),a
    add a,#8
    ld (_shadow_OAM+45),a
    ld e,#1
    ret
021$:
    ld e,#0
    ret
022$:
    ld a,(hl+)
    ld b,a
    ld a,(hl+)
    or a
    ret nz
    ld a,b
    sub a,#8
    cp a,c
    ld a,b
    ret
    __endasm;
}

/* The cast after >>8 keeps only subtraction bytes 1 and 2. Byte 0 still
 * supplies their borrow; byte 3 cannot affect them. Keep these exact signed
 * displacements and the two separately rounded products out of SDCC's
 * 32-bit stack temporaries. No scratch RAM or interrupt masking is needed. */
typedef char rider_frame_layout[
    offsetof(gbc_bike_t,body)==0 && offsetof(gbc_bike_t,wheel)==10 &&
    offsetof(gbc_bike_t,rider)==30 && sizeof(gbc_pose_t)==10 &&
    offsetof(gbc_pose_t,y)==4 && offsetof(gbc_pose_t,angle)==8 ? 1 : -1];
static uint8_t rider_compression(const gbc_bike_t *bike,uint8_t angle) __sdcccall(0) BIKE_FIXED __naked {
    __asm
    ldhl sp,#2
    ld a,(hl+)
    ld d,(hl)
    ld e,a
    push de
    ld hl,#30
    add hl,de
    ld b,d
    ld c,e
    ld a,(bc)
    ld e,a
    ld a,(hl+)
    sub a,e
    inc bc
    ld a,(bc)
    ld e,a
    ld a,(hl+)
    sbc a,e
    ld e,a
    inc bc
    ld a,(bc)
    ld d,a
    ld a,(hl)
    sbc a,d
    ld d,a
    ; -256..255 have high byte FF or 00; +256 also requires low byte 00.
    inc a
    cp a,#2
    jr c,001$
    sub a,#2
    or a,e
    jr z,001$
    ld e,#2
    add sp,#2
    ret
001$:
    push de
    ldhl sp,#2
    ld a,(hl+)
    ld d,(hl)
    ld e,a
    ld hl,#4
    add hl,de
    ld b,h
    ld c,l
    ld de,#30
    add hl,de
    ld a,(bc)
    ld e,a
    ld a,(hl+)
    sub a,e
    inc bc
    ld a,(bc)
    ld e,a
    ld a,(hl+)
    sbc a,e
    ld e,a
    inc bc
    ld a,(bc)
    ld d,a
    ld a,(hl)
    sbc a,d
    ld d,a
    inc a
    cp a,#2
    jr c,002$
    sub a,#2
    or a,e
    jr z,002$
    ld e,#2
    add sp,#4
    ret
002$:
    push de
    ldhl sp,#10
    ld c,(hl)
    ld b,#0
    ld hl,#_riding_up_x
    add hl,bc
    ld c,(hl)
    ldhl sp,#2
    ld a,(hl+)
    ld d,(hl)
    ld e,a
    call 010$
    push hl
    ldhl sp,#12
    ld c,(hl)
    ld b,#0
    ld hl,#_riding_up_y
    add hl,bc
    ld c,(hl)
    ldhl sp,#2
    ld a,(hl+)
    ld d,(hl)
    ld e,a
    call 010$
    pop de
    ld a,e
    sub a,l
    ld e,a
    ld a,d
    sbc a,h
    ld d,a
    bit 7,a
    jr nz,003$
    ld a,e
    sub a,#0x2d
    ld a,d
    sbc a,#0x17
    jr c,003$
    ld a,e
    sub a,#0xb5
    ld a,d
    sbc a,#0x20
    ld e,#1
    jr c,004$
    inc e
    jr 004$
003$:
    ld e,#0
004$:
    add sp,#6
    ret
010$:
    ; Signed DE * signed C. Initialize from the sign bit, then append
    ; the remaining seven bits. The common cardinal coefficients use
    ; 127*d = 128*d - d. Both paths retain each product's own floor.
    ld a,c
    or a
    ld hl,#0
    ret z
    cp a,#127
    jr z,015$
    cp a,#-127
    jr nz,016$
    xor a
    sub e
    ld e,a
    sbc a,a
    sub d
    ld d,a
015$:
    ld h,e
    ld a,d
    rra
    rr h
    rr l
    ld a,l
    sub e
    ld l,a
    ld a,h
    sbc d
    ld h,a
    jr 018$
016$:
    sla c
    jr nc,013$
    xor a
    sub e
    ld l,a
    sbc a,a
    sub d
    ld h,a
013$:
    .rept 7
    add hl,hl
    sla c
    jr nc,.+3
    add hl,de
    .endm
018$:
    sra h
    rr l
    ret
    __endasm;
}

/* Moving the two factors of two out of 12*x reduces the half-pixel phase to
 * bit 13 of 3*x. Keep both words in registers and assemble the two bits
 * in screen order. */
static uint8_t head_phase(const gbc_pose_t *head) __sdcccall(0) BIKE_FIXED __naked {
    __asm
    ldhl sp,#2
    ld a,(hl+)
    ld h,(hl)
    ld l,a
    ld a,(hl+)
    ld e,a
    ld a,(hl+)
    ld d,a
    inc hl
    inc hl
    ld a,(hl+)
    ld h,(hl)
    ld l,a
    xor a
    sub l
    ld l,a
    sbc a,a
    sub h
    ld h,a
    ld b,h
    ld c,l
    add hl,hl
    add hl,bc
    ld a,h
    rlca
    rlca
    rlca
    rlca
    and a,#2
    ld c,a
    ld h,d
    ld l,e
    add hl,hl
    add hl,de
    ld a,h
    rlca
    rlca
    rlca
    and a,#1
    or c
    ld e,a
    ret
    __endasm;
}

#ifdef RIDING_PAIRED_MASKS
/* Each wheel has two adjacent OAM entries. A resident atlas never overwrites
 * pattern data, so these four tile attributes can be selected directly. */
static void resident_wheels(const gbc_bike_t *bike) __sdcccall(0) BIKE_FIXED __naked {
    __asm
    ldhl sp,#2
    ld a,(hl+)
    ld h,(hl)
    ld l,a
    ld de,#19
    add hl,de
    ld a,(hl)
    ld de,#10
    add hl,de
    ld b,(hl)
    ld hl,#_riding_wheel_tiles
    ld d,h
    ld e,l
    add a,#16
    swap a
    rrca
    and a,#7
    ld (_last_wheel),a
    add a,l
    ld l,a
    jr nc,001$
    inc h
001$:
    ld a,(hl)
    ld (_shadow_OAM+34),a
    add a,#2
    ld (_shadow_OAM+38),a
    ld a,b
    add a,#16
    swap a
    rrca
    and a,#7
    ld (_last_wheel+1),a
    add a,e
    ld e,a
    jr nc,002$
    inc d
002$:
    ld a,(de)
    ld (_shadow_OAM+42),a
    add a,#2
    ld (_shadow_OAM+46),a
    ret
    __endasm;
}
#endif

#ifdef RIDING_BODY_TRANSFERS
void bike_body_upload(uint8_t body, uint8_t previous) BANKED;
/* Register entry from bank 13. The source bank stays mapped during DMA. */
void bike_body_dma(void) BIKE_FIXED __naked {
    __asm
    ld (#0x2000),a
    ldh (#__current_bank),a
    call _bike_dma_regs
    ld a,#13
    ld (#0x2000),a
    ldh (#__current_bank),a
    ret
    __endasm;
}
#endif

void bike_render_prepare(const gbc_bike_t *bike) BIKE_FIXED {
    uint8_t angle,compression,body,head,wheel,oldbank,i,phase;
#ifndef RIDING_BODY_TRANSFERS
    uint8_t bank;
#endif
    uint16_t frame;
    angle=(uint8_t)((bike->body.angle+1024U)>>11)&31;
    /* Use subpixel physical displacement so the selected rider pose does not
     * flicker as the camera rounds positions to whole screen pixels. */
    compression=rider_compression(bike,angle);
    body=(bike->turned ? 96 : 0)+compression*32+angle;
    /* OAM uses floor(world pixels), while the atlas retains half-pixel phase.
     * The camera and level origin are whole pixels, so only world low words
     * contribute. Positive screen Y is the negative of physical world Y. */
    phase=head_phase(&bike->head);
    head=(((bike->turned ? 32 : 0)+angle)<<2)|phase;
    oldbank=CURRENT_BANK;
    prepared_changed=body!=last_body;
    VBK_REG=1;
    if(body!=last_body) {
#ifdef RIDING_BODY_TRANSFERS
        bike_body_upload(body,last_body);
#else
        bank=body>>6;
        SWITCH_ROM(10+bank);
        upload(BIKE_BODY_TILE,16,riding_bodies[bank]+((uint16_t)(body&63)<<8));
#endif
        last_body=body;
    }
    __critical {frame=sys_time;}
    if(head!=last_head && (last_head==256 || frame!=head_upload_frame)) {
        /* The VBlank OAM DMA precedes this code. Keep that displayed head
         * pattern intact until the next DMA publishes the matching new pose.
         * At most one publication per display frame prevents a second prepare
         * call from recycling the pattern that hardware OAM still references. */
#ifdef RIDING_BODY_TRANSFERS
        uint8_t resident=(head+4U)&127U;
        if(head<128 && resident<BIKE_HEAD_RESIDENT_COUNT) {
            shadow_OAM[12].tile=BIKE_HEAD_RESIDENT_TILE+2U*resident;
        } else {
            uint8_t slot=head_tile==BIKE_HEAD_TILE;
            head_tile=slot ? BIKE_HEAD_BACK_TILE : BIKE_HEAD_TILE;
            if(bike_streamed_heads[slot]!=head) {
                SWITCH_ROM(13);
                upload(head_tile,1,riding_heads+((uint16_t)head<<4));
                bike_streamed_heads[slot]=head;
            }
            shadow_OAM[12].tile=head_tile;
        }
#else
        head_tile=head_tile==BIKE_HEAD_TILE ? BIKE_HEAD_BACK_TILE : BIKE_HEAD_TILE;
        /* The other head buffer still holds the preceding publication, even
         * after a skipped display frame. Reuse its pixels when a half-pixel
         * phase returns. The same frame gate still controls the OAM change. */
        if(head!=previous_head) {
            SWITCH_ROM(13);
            upload(head_tile,1,riding_heads+((uint16_t)head<<5));
        }
        previous_head=last_head;
        shadow_OAM[12].tile=head_tile;
#endif
        head_upload_frame=frame;
        last_head=head;
    }
#ifdef RIDING_PAIRED_MASKS
    if(riding_wheel_tiles[0])resident_wheels(bike);
    else
#endif
    for(i=0;i<2;++i) {
        wheel=(uint8_t)((bike->wheel[i].angle+4096U)>>13)&7;
        if(wheel!=last_wheel[i]) {
            SWITCH_ROM(13);
            upload(BIKE_WHEEL_TILE+i*4,4,riding_wheels+((uint16_t)wheel<<6));
            last_wheel[i]=wheel;
        }
    }
    SWITCH_ROM(oldbank);
    VBK_REG=0;
    prepared=1;
}

void bike_render_draw(const gbc_bike_t *bike,const bike_screen_t *s) BIKE_DRAW_CALL {
    uint8_t i,row,col,x,y;
    volatile OAM_item_t *o;
#ifdef RIDING_PAIRED_MASKS
    extern const uint8_t riding_body_pair_masks[];
#else
    uint16_t original_mask;
#endif
    uint8_t mask;
    if(!prepared)bike_render_prepare(bike);
    prepared=0;
#ifdef RIDING_PAIRED_MASKS
    mask=riding_body_pair_masks[last_body];
#else
    original_mask=riding_masks[last_body];
    /* A vertical pair is visible when either original 8x8 tile was used. */
    mask=(uint8_t)((original_mask|(original_mask>>4))&15)
        |(uint8_t)(((original_mask>>4)|(original_mask>>8))&240);
#endif
    if(draw_centered(s,mask)) {positions_valid=0;return;}
    center_y=0;
    if(positions_valid && !prepared_changed && !memcmp(s,&last_screen,sizeof(last_screen)))return;
    memcpy(&last_screen,s,sizeof(last_screen));
    positions_valid=1;
    if(s->body_x>=16 && s->body_x<=144 && s->body_y>=16 && s->body_y<=120) {
        body16((uint8_t)s->body_x-8,(uint8_t)s->body_y,mask);
    } else {
        for(i=0,row=0;row<2;++row)
            for(col=0;col<4;++col,++i) {
                if(mask&1)place(i,s->body_x-16+col*8,s->body_y-16+row*16);
                else move_sprite(i,0,0);
                mask>>=1;
            }
    }
    for(i=0;i<2;++i) {
        if(s->wheel_x[i]>=8 && s->wheel_x[i]<=152 && s->wheel_y[i]>=8 && s->wheel_y[i]<=128) {
            x=(uint8_t)s->wheel_x[i];y=(uint8_t)s->wheel_y[i]+8;
            o=&shadow_OAM[8+i*2];
            o->y=y;o->x=x;++o;
            o->y=y;o->x=x+8;
        } else {
            for(col=0;col<2;++col)
                place(8+i*2+col,s->wheel_x[i]-8+col*8,s->wheel_y[i]-8);
        }
    }
    place(12,s->head_x-4,s->head_y-4);
}
