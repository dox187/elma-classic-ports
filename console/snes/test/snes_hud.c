// Test ROM of the time digits and the view box (src/hud.asm): a fake bike
// rides through a few levels (tools/gen_hud.py --test) while the time
// counts, with a best time or none, and both toggles switched off for a
// while. Every TEST_HOLD-th frame stays on the screen for a few frames with
// the same values; test_hold is its number + 1 while it is shown (for the
// screenshots of test/hud_check.py). Nothing but BG3 and the sprites is on,
// over a gray backdrop.
#include <snes.h>
#include "core.h"
#include "hud.h"
#include "levels.h"

#ifdef HAVE_PHYS
#include "phys.h"
#else
typedef struct {
	s32 body_x, body_y;
	u16 body_a;
	s32 wheel_x[2], wheel_y[2];
	u16 wheel_a[2];
	s32 rider_x, rider_y;
	s32 head_x, head_y;
	u8 turned;
	u8 gravity;
} bike_view_t;
typedef struct {
	u8 type, anim, gravity, active;
	s32 x, y;
} phys_obj_t;
extern bike_view_t phys_view;
extern phys_obj_t phys_objs[];
extern u16 phys_nobjs, phys_apples_left, phys_eaten;
#endif

typedef struct {
	u8 type, anim;
	s32 x, y;
} test_obj_t;

typedef struct {
	s32 x, y;
	u16 baljobb, cam_x, cam_y;
	u8 eaten;
} test_step_t;

extern const u16 hud_test_count, hud_test_frames;
extern const u16 hud_test_levels[], hud_test_nobjs[];
extern const test_obj_t* const hud_test_objs[];
extern const test_step_t* const hud_test_path[];

#define TEST_HOLD 100
#define TEST_HOLD_FRAMES 12

u16 test_level, test_frame, test_hold;

static const u16 Backdrop = 0x4210;     // gray

static void load(u16 k) {
	const test_obj_t* o = hud_test_objs[k];
	u16 i = 0, n = hud_test_nobjs[k];
	core_screen_off();
	phys_apples_left = 0;
	while( i < n ) {
		phys_objs[i].type = o[i].type;
		phys_objs[i].anim = o[i].anim;
		phys_objs[i].gravity = 0;
		phys_objs[i].active = 1;
		phys_objs[i].x = o[i].x;
		phys_objs[i].y = o[i].y;
		if( o[i].type == 2 )
			phys_apples_left++;
		i++;
	}
	phys_nobjs = n;
	hud_load(hud_test_levels[k]);
	core_cgram_now(0, &Backdrop, 2);
	*(vuint8*)0x212C = 0x14;            // TM: BG3 and sprites
	core_screen_on(15);
}

// The best time of a test level: none, ordinary ones, more than an hour.
static u32 best_of(u16 k) {
	if( k == 0 )
		return 0xFFFFFFFF;
	if( k == 3 )
		return 400000;
	if( k == 1 )
		return 1970;
	return 123456;
}

int main(void) {
	u16 k = 0, f, h;
	u32 best, t;
	const test_step_t* p;
	test_hold = 0;
	consoleInit();
	core_init();
	*(vuint8*)0x2105 = 0x09;            // mode 1, BG3 on top
	*(vuint8*)0x2101 = 0x63;            // sprites 16x16 and 32x32 at $6000
	while( k < hud_test_count ) {
		load(k);
		best = best_of(k);
		f = 0;
		while( f < hud_test_frames ) {
			p = &hud_test_path[k][f];
			if( p->eaten != 255 ) {
				phys_objs[p->eaten].active = 0;
				phys_apples_left--;
				phys_eaten = p->eaten;
			}
			phys_view.body_x = p->x;
			phys_view.body_y = p->y;
			// Level 1: no view box, then no time, then both for a while.
			hud_show_map = !(k == 1 && f >= 200 && f < 300) &&
				!(k == 1 && f >= 400 && f < 500);
			hud_show_time = !(k == 1 && f >= 300 && f < 500);
			t = (u32)f * 5 / 3;
			if( k == 2 )
				t += 359000;            // the hour: 59:59:99 from 360000
			test_level = k;
			test_frame = f;
			h = (f % TEST_HOLD == 0) ? TEST_HOLD_FRAMES : 1;
			while( h ) {
				hud_draw(p->cam_x, p->cam_y, p->baljobb, t, best);
				core_frame_done();
				if( h == TEST_HOLD_FRAMES - 1 )
					test_hold = f + 1;
				h--;
			}
			test_hold = 0;
			f++;
		}
		k++;
	}
	while( 1 )
		core_frame_done();
	return 0;
}
