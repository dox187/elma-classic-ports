/* Rotated original LGR parts; wheel/head positions follow physics directly.
 * Limb articulation is represented by three precomputed rider-compression poses.
 */
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
    ld hl,#_shadow_OAM
    srl b
    ld a,#0
    jr nc,000$
    ld a,e
000$:
    ld (hl+),a
    ld (hl),d
    inc hl
    inc hl
    inc hl
    ld a,d
    add a,#8
    ld d,a
    srl b
    ld a,#0
    jr nc,001$
    ld a,e
001$:
    ld (hl+),a
    ld (hl),d
    inc hl
    inc hl
    inc hl
    ld a,d
    add a,#8
    ld d,a
    srl b
    ld a,#0
    jr nc,002$
    ld a,e
002$:
    ld (hl+),a
    ld (hl),d
    inc hl
    inc hl
    inc hl
    ld a,d
    add a,#8
    ld d,a
    srl b
    ld a,#0
    jr nc,003$
    ld a,e
003$:
    ld (hl+),a
    ld (hl),d
    inc hl
    inc hl
    inc hl
    ld a,d
    sub a,#24
    ld d,a
    ld a,e
    add a,#16
    ld e,a
    srl b
    ld a,#0
    jr nc,004$
    ld a,e
004$:
    ld (hl+),a
    ld (hl),d
    inc hl
    inc hl
    inc hl
    ld a,d
    add a,#8
    ld d,a
    srl b
    ld a,#0
    jr nc,005$
    ld a,e
005$:
    ld (hl+),a
    ld (hl),d
    inc hl
    inc hl
    inc hl
    ld a,d
    add a,#8
    ld d,a
    srl b
    ld a,#0
    jr nc,006$
    ld a,e
006$:
    ld (hl+),a
    ld (hl),d
    inc hl
    inc hl
    inc hl
    ld a,d
    add a,#8
    ld d,a
    srl b
    ld a,#0
    jr nc,007$
    ld a,e
007$:
    ld (hl+),a
    ld (hl),d
    inc hl
    inc hl
    inc hl

    ret
    __endasm;
}

static uint8_t last_body,last_wheel[2];
static uint16_t last_head;
static uint16_t head_upload_frame;
static uint8_t head_tile;
static uint8_t positions_valid;
static uint8_t prepared,prepared_changed;
static bike_screen_t last_screen;
static const uint8_t blank_head_half[16]={0};

void bike_render_init(void) {
    uint8_t i;
    last_body=last_wheel[0]=last_wheel[1]=255;
    last_head=256;
    head_tile=BIKE_HEAD_TILE;
    head_upload_frame=0;
    positions_valid=0;
    prepared=0;
    /* Every head frame has a transparent lower half. Initialize both buffers
     * once while the LCD is off; only their upper tile changes during play. */
    VBK_REG=1;
    set_sprite_data((uint8_t)(BIKE_HEAD_TILE+1),1,blank_head_half);
    set_sprite_data((uint8_t)(BIKE_HEAD_BACK_TILE+1),1,blank_head_half);
    VBK_REG=0;
    set_sprite_palette(0,1,riding_body_palette);
    set_sprite_palette(3,1,riding_wheel_palette);
    set_sprite_palette(4,1,riding_head_palette);
    for(i=0;i<8;++i) {
        shadow_OAM[i].tile=192+i*2;
        shadow_OAM[i].prop=S_BANK;
    }
    for(i=8;i<12;++i) {
        shadow_OAM[i].tile=208+(i-8)*2;
        shadow_OAM[i].prop=S_BANK|3;
    }
    shadow_OAM[12].tile=BIKE_HEAD_TILE;
    shadow_OAM[12].prop=S_BANK|4;
}

void bike_render_hide(void) {
    uint8_t i;
    for(i=0;i<BIKE_OBJECT_OAM_BASE;++i)move_sprite(i,0,0);
    positions_valid=0;
    prepared=0;
}

/* Atlas sources and pattern destinations are 16-byte aligned. Keep the source
 * ROM bank and VBK selected until completion. HBlank DMA is started in OAM
 * scan (mode 2), never in HBlank; interrupts stay enabled while it completes.
 * https://gbdev.io/pandocs/CGB_Registers.html#lcd-vram-dma-transfers
 */
static void upload(uint8_t tile,uint8_t count,const uint8_t *data) {
    uint16_t source=(uint16_t)data;
    uint16_t dest=0x8000U+((uint16_t)tile<<4);
    if(source&15) {set_sprite_data(tile,count,data);return;}
    /* At LY<=151 at least two complete VBlank scanlines remain even if this
     * line is about to end: enough for the largest 16-block (256-byte) copy.
     * General DMA is used there, otherwise HBlank DMA bounds VRAM access. */
    if((LCDC_REG&LCDCF_ON) && !(LY_REG>=144 && LY_REG<=151)) {
        __critical {
            while((STAT_REG&3)!=2) {}
            HDMA1_REG=source>>8;HDMA2_REG=(uint8_t)source;
            HDMA3_REG=dest>>8;HDMA4_REG=(uint8_t)dest;
            HDMA5_REG=0x80|(count-1);
        }
        while(!(HDMA5_REG&0x80)) {}
    } else {
        HDMA1_REG=source>>8;HDMA2_REG=(uint8_t)source;
        HDMA3_REG=dest>>8;HDMA4_REG=(uint8_t)dest;
        HDMA5_REG=count-1;
    }
}

static void place(uint8_t sprite,int16_t x,int16_t y) {
    if(x < -7 || x >= 160 || y < -15 || y >= 136)move_sprite(sprite,0,0);
    else move_sprite(sprite,(uint8_t)(x+8),(uint8_t)(y+16));
}

/* The cast after >>8 keeps only subtraction bytes 1 and 2. Byte 0 still
 * supplies their borrow; byte 3 cannot affect them. Keep these exact signed
 * displacements and the two separately rounded products out of SDCC's
 * 32-bit stack temporaries. No scratch RAM or interrupt masking is needed. */
typedef char rider_frame_layout[
    offsetof(gbc_bike_t,body)==0 && offsetof(gbc_bike_t,rider)==30 &&
    offsetof(gbc_pose_t,y)==4 ? 1 : -1];
static uint8_t rider_compression(const gbc_bike_t *bike,uint8_t angle) __sdcccall(0) __naked {
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
    ; Signed DE * signed C, modulo 16 bits, then arithmetic >>1. Products
    ; fit int16_t for the accepted displacement and int8_t atlas vectors.
    ld a,c
    push af
    ld hl,#0
    ld b,#8
011$:
    add hl,hl
    sla c
    jr nc,012$
    add hl,de
012$:
    dec b
    jr nz,011$
    pop af
    bit 7,a
    jr z,013$
    ld a,h
    sub a,e
    ld h,a
013$:
    sra h
    rr l
    ret
    __endasm;
}

void bike_render_prepare(const gbc_bike_t *bike) {
    uint8_t angle,compression,body,head,wheel,bank,oldbank,i,phase;
    uint16_t fraction;
    uint16_t frame;
    angle=(uint8_t)((bike->body.angle+1024U)>>11)&31;
    /* Use subpixel physical displacement so the selected rider pose does not
     * flicker as the camera rounds positions to whole screen pixels. */
    compression=rider_compression(bike,angle);
    body=(bike->turned ? 96 : 0)+compression*32+angle;
    /* OAM uses floor(world pixels), while the atlas retains half-pixel phase.
     * The camera and level origin are whole pixels, so only world low words
     * contribute. Positive screen Y is the negative of physical world Y. */
    fraction=(uint16_t)bike->head.x;
    fraction=(fraction<<3)+(fraction<<2);
    phase=fraction>>15;
    fraction=0-(uint16_t)bike->head.y;
    fraction=(fraction<<3)+(fraction<<2);
    phase|=(fraction>>15)<<1;
    head=(((bike->turned ? 32 : 0)+angle)<<2)|phase;
    oldbank=CURRENT_BANK;
    prepared_changed=body!=last_body;
    VBK_REG=1;
    if(body!=last_body) {
        bank=body>>6;
        SWITCH_ROM(10+bank);
        upload(192,16,riding_bodies[bank]+((uint16_t)(body&63)<<8));
        last_body=body;
    }
    __critical {frame=sys_time;}
    if(head!=last_head && (last_head==256 || frame!=head_upload_frame)) {
        /* The VBlank OAM DMA precedes this code. Keep that displayed head
         * pattern intact until the next DMA publishes the matching new pose.
         * At most one publication per display frame prevents a second prepare
         * call from recycling the pattern that hardware OAM still references. */
        head_tile=head_tile==BIKE_HEAD_TILE ? BIKE_HEAD_BACK_TILE : BIKE_HEAD_TILE;
        SWITCH_ROM(13);
        upload(head_tile,1,riding_heads+((uint16_t)head<<5));
        shadow_OAM[12].tile=head_tile;
        head_upload_frame=frame;
        last_head=head;
    }
    for(i=0;i<2;++i) {
        wheel=(uint8_t)((bike->wheel[i].angle+4096U)>>13)&7;
        if(wheel!=last_wheel[i]) {
            SWITCH_ROM(13);
            upload(208+i*4,4,riding_wheels+((uint16_t)wheel<<6));
            last_wheel[i]=wheel;
        }
    }
    SWITCH_ROM(oldbank);
    VBK_REG=0;
    prepared=1;
}

void bike_render_draw(const gbc_bike_t *bike,const bike_screen_t *s) {
    uint8_t i,row,col,x,y;
    volatile OAM_item_t *o;
    uint16_t original_mask;
    uint8_t mask;
    if(!prepared)bike_render_prepare(bike);
    prepared=0;
    if(positions_valid && !prepared_changed && !memcmp(s,&last_screen,sizeof(last_screen)))return;
    memcpy(&last_screen,s,sizeof(last_screen));
    positions_valid=1;
    original_mask=riding_masks[last_body];
    /* A vertical pair is visible when either original 8x8 tile was used. */
    mask=(uint8_t)((original_mask|(original_mask>>4))&15)
        |(uint8_t)(((original_mask>>4)|(original_mask>>8))&240);
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
