// Test of the bike and the objects: the poses of test/bike_poses.py, each
// for POSE_HOLD frames, on a plain backdrop, with the objects around the
// bike. test/bike_test.py compares what it draws with test/bikefix.py and
// measures the time of bike_draw and objects_draw.
#include <snes.h>
#include "core.h"
#include "bike.h"
#include "bike_poses.h"

// The physics' output (phys.h), here from the poses:
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

bike_view_t phys_view;
phys_obj_t phys_objs[POSE_OBJS];
u16 phys_nobjs;

u16 test_pose;               // the pose shown
u16 test_time;               // steps of the "physics"

static const u16 Sky = 0x7E8C;

static void set_pose(u16 n) {
	const pose_t* p = &Poses[n];
	phys_view.body_x = p->body_x;
	phys_view.body_y = p->body_y;
	phys_view.body_a = p->body_a;
	phys_view.wheel_x[0] = p->w0x;
	phys_view.wheel_y[0] = p->w0y;
	phys_view.wheel_x[1] = p->w1x;
	phys_view.wheel_y[1] = p->w1y;
	phys_view.wheel_a[0] = p->w0a;
	phys_view.wheel_a[1] = p->w1a;
	phys_view.rider_x = p->rx;
	phys_view.rider_y = p->ry;
	phys_view.head_x = p->hx;
	phys_view.head_y = p->hy;
	phys_view.turned = (u8)p->turned;
	phys_view.gravity = 1;
	bike_anim.turn = p->turn;
	bike_anim.volt = p->volt;
	bike_anim.volt1 = (u8)p->volt1;
}

int main(void) {
	u16 i, f;
	consoleInit();
	core_init();
	core_screen_off();
	REG_BGMODE = 0x09;
	REG_TM = 0x10;               // sprites only
	core_cgram_now(0, &Sky, 2);
	for( i = 0; i < POSE_OBJS; i++ ) {
		phys_objs[i].type = (u8)Objs[i][0];
		phys_objs[i].anim = (u8)Objs[i][1];
		phys_objs[i].gravity = (u8)Objs[i][2];
		phys_objs[i].active = (u8)Objs[i][3];
		phys_objs[i].x = Objs[i][4];
		phys_objs[i].y = Objs[i][5];
	}
	phys_nobjs = POSE_OBJS;
	bike_load();
	objects_load(POSE_LEVEL);
	core_screen_on(15);
	test_time = 0;
	while( 1 ) {
		for( test_pose = 0; test_pose < POSE_COUNT; test_pose++ ) {
			set_pose(test_pose);
			for( f = 0; f < POSE_HOLD; f++ ) {
				bike_draw(Poses[test_pose].cam_x, Poses[test_pose].cam_y);
				objects_draw(Poses[test_pose].cam_x, Poses[test_pose].cam_y, test_time);
				core_frame_done();
				test_time++;
			}
		}
	}
	return 0;
}
