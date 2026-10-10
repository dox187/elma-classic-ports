// The balls of the animated menus (GOLYOK.CPP, GOLYUTK.CPP): nine balls of
// three sizes bounce on the walls of the menu picture and on each other and
// turn when they rub. The original steps them from collision to collision;
// here they move a frame at a time and bounce when they overlap
// (ui_balls_asm.asm). A ball shows the darker background (szoveg2.pcx) with two small
// circles of the normal one: a sprite of color math (half the sum with the
// background) with two holes.
//
// Positions are in 1/64 of a pixel of the screen.
#include "ui_int.h"

#define NBALLS 9
// The speed of the first ball: one pixel of the original a unit of its
// time, 182 * 3.6 units a second (szoveglista::kirajzol): 10.92 pixels of
// the original a frame of 60, 0.4 of it on the screen, times 64.
#define SPEED 280

extern s16 ui_bx[NBALLS], ui_by[NBALLS], ui_bvx[NBALLS], ui_bvy[NBALLS];
extern u16 ui_ba[NBALLS];
extern s16 ui_bw[NBALLS], ui_br[NBALLS], ui_bhalf[NBALLS];
extern u16 ui_btile[NBALLS], ui_bbig[NBALLS], ui_bsz[NBALLS];
void ui_balls_move(void);
void ui_balls_sprites(s16 dy);
void ui_balls_energy(u16 set);

static u8 size[NBALLS];
static u8 loaded[NBALLS];       // the angle frame in the VRAM (0xFF: none)
static u8 balls_ready;
static u16 balls_last;
static u16 balls_acc;           // PAL: 6 steps in 5 frames
// Radius of the sizes (24, 30, 50 of the original, times 0.4 * 64):
static const s16 radius[3] = { 614, 768, 1280 };
static const u8 side[3] = { UI_BALL0_SIDE, UI_BALL1_SIDE, UI_BALL2_SIDE };
static const u16 slot_tile[NBALLS] = {
	0x004, 0x008, 0x080, 0x00C, 0x040, 0x088, 0x044, 0x048, 0x100
};
// sin of 64 angles of a turn, times 256:
static const s16 sin64[64] = {
	0, 25, 50, 74, 98, 121, 142, 162, 181, 198, 213, 226, 237, 245, 251, 255,
	256, 255, 251, 245, 237, 226, 213, 198, 181, 162, 142, 121, 98, 74, 50, 25,
	0, -25, -50, -74, -98, -121, -142, -162, -181, -198, -213, -226, -237, -245, -251, -255,
	-256, -255, -251, -245, -237, -226, -213, -198, -181, -162, -142, -121, -98, -74, -50, -25
};

// kitoltgolyokat: a grid of 3x3 around the middle of the picture of 640x480
// (not of the taller one), the first ball starts in a direction of seed.
void ui_balls_init(u16 seed) {
	u16 i;
	for( i = 0; i < NBALLS; i++ ) {
		u16 gx = i % 3, gy = i / 3;
		size[i] = gx;
		ui_bx[i] = (128 + ((s16)gx - 1) * 48) * 64;
		ui_by[i] = (96 + ((s16)gy - 1) * 48) * 64;
		ui_bvx[i] = 0;
		ui_bvy[i] = 0;
		ui_ba[i] = 0;
		ui_bw[i] = 0;
		ui_br[i] = radius[gx];
		ui_bhalf[i] = side[gx] * 4;
		ui_btile[i] = slot_tile[i];
		ui_bbig[i] = gx == 2 ? 2 : 0;
		ui_bsz[i] = gx;
		loaded[i] = 0xFF;
	}
	seed &= 63;
	ui_bvx[0] = -(s16)(((s32)sin64[seed] * SPEED) >> 8);
	ui_bvy[0] = -(s16)(((s32)sin64[(seed + 16) & 63] * SPEED) >> 8);
	ui_balls_energy(1);
	balls_ready = 1;
	balls_last = core_frame_count;
	balls_acc = 0;
}

// Steps the balls to the frame now (a few steps behind at most; on PAL six
// steps in five frames).
void ui_balls_step(u16 now) {
	u16 n;
	if( !balls_ready )
		ui_balls_init(now);
	n = now - balls_last;
	if( n > 4 ) {
		n = 4;
		balls_last = now - 4;
	}
	while( n-- ) {
		if( !(balls_last & 63) )
			ui_balls_energy(0);
		balls_last++;
		ui_balls_move();
		if( ui_pal ) {
			balls_acc += 13107;     // 1/5
			if( balls_acc < 13107 )
				ui_balls_move();
		}
	}
}

// The sprites of the balls, moved down by dy lines.
void ui_balls_draw(s16 dy) {
	if( !balls_ready )
		ui_balls_init(core_frame_count);
	ui_balls_sprites(dy);
}

void ui_balls_hide(void) {
	u16 i;
	for( i = 1; i <= NBALLS; i++ ) {
		core_oam[i * 4] = 0;
		core_oam[i * 4 + 1] = 224;
	}
	core_oam[512] = (core_oam[512] & 0x03) | 0x54;   // x bit 8: off the screen
	core_oam[513] = 0x55;
	core_oam[514] = (core_oam[514] & 0xF0) | 0x05;
}

// The tiles of the balls whose angle changed.
void ui_balls_upload(void) {
	u16 i, r;
	if( !balls_ready )
		return;
	for( i = 0; i < NBALLS; i++ ) {
		u16 f = (ui_ba[i] >> 11) & (UI_BALL_ANGLES - 1);
		u16 sd = side[size[i]];
		const u8* chr;
		if( f == loaded[i] )
			continue;
		if( core_dmaq_bytes + sd * sd * 32 > 4600 )
			break;
		chr = size[i] == 0 ? ui_ball0_chr : size[i] == 1 ? ui_ball1_chr : ui_ball2_chr;
		chr += f * sd * sd * 32;
		for( r = 0; r < sd; r++ )
			core_queue_vram(UIV_OBJ + (ui_btile[i] + r * 16) * 16, chr + r * sd * 32, sd * 32);
		loaded[i] = f;
	}
}

// The VRAM of the menus was loaded again: every ball uploads its tiles.
void ui_balls_vram_reset(void) {
	u16 i;
	for( i = 0; i < NBALLS; i++ )
		loaded[i] = 0xFF;
}
