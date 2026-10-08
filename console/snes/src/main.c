// Elasto Mania for the SNES.
#include <snes.h>
#include "core.h"
#include "version.h"

static const u8 Pal[4] = { 0x00, 0x7C, 0xFF, 0x03 };  // blue, yellow

int main(void) {
	consoleInit();
	core_init();
	core_cgram_now(0, Pal, 4);
	core_screen_on(15);
	while( 1 )
		core_frame_done();
	return 0;
}
