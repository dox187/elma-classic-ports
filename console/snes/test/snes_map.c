// Test of the level background (map.asm), driven by test/map_check.py: the
// script sets the level and the camera of every frame in these variables.
#include <snes.h>
#include "core.h"
#include "map.h"

#define TEST_MAGIC 0x5A5A

u16 test_ready;          // TEST_MAGIC once the script set the first values
u16 test_level;          // level to show
u16 test_load;           // set by the script: load test_level again
s16 test_cam_x, test_cam_y;
u16 test_frame;          // frames shown since the load

static void load(void) {
	core_screen_off();
	map_set_camera(test_cam_x, test_cam_y);
	map_load(test_level);
	test_load = 0;
	test_frame = 0;
	core_screen_on(15);
}

int main(void) {
	consoleInit();
	core_init();
	while( test_ready != TEST_MAGIC )
		core_wait_frames(1);
	load();
	while( 1 ) {
		if( test_load )
			load();
		map_set_camera(test_cam_x, test_cam_y);
		core_frame_done();
		test_frame++;
	}
	return 0;
}
