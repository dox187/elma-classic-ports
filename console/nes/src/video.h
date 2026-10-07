// The frame: sprites, nametable updates and the split under the bar at the
// top of the screen, handed to the NMI when drawn. The NMI of neslib shows
// a frame only when one was handed over, so drawing may take longer than a
// frame: the screen keeps the last one meanwhile.
#ifndef VIDEO_H
#define VIDEO_H

#include <stdint.h>

// Lines of the bar at the top of the game's screen, without background:
#define BAR_LINES 16

// The sprites of the frame being drawn, from OAM_BUF up to Oam_n:
extern uint8_t OAM_BUF[256];
extern uint8_t Oam_n;

// The frames shown so far (counted by the NMI) and whether a frame handed
// over is still waiting for it, of neslib:
extern volatile uint8_t FRAME_CNT1;
extern volatile uint8_t VRAM_UPDATE;

static inline void spr( uint8_t x, uint8_t y, uint8_t tile, uint8_t attr ) {
	uint8_t i = Oam_n;
	OAM_BUF[i] = y;
	OAM_BUF[i+1] = tile;
	OAM_BUF[i+2] = attr;
	OAM_BUF[i+3] = x;
	Oam_n = i+4;
}

// Whether a new frame may be drawn: the last one went out.
static inline uint8_t frame_ready( void ) {
	return !VRAM_UPDATE;
}

// Hides all sprites, with rendering off.
void sprites_off( void );
// Starts drawing a frame: no sprites, no updates.
void frame_begin( void );
// Hands the frame to the NMI, which shows it in the next vblank.
void frame_show( void );
// frame_show, then waits until it went out.
void frame_end( void );

// The game's screen: background below the bar, the bike's sprite bank
// switched in the NMI with the frame that shows it.
void video_game( uint8_t on );
void video_bike_bank( uint8_t bank );

// Sprite text at x, y (pixels), palette 3:
void spr_text( uint8_t x, uint8_t y, const char* s );
// Time in hundredths as mm:ss:hh into s (9 bytes):
void format_time( uint32_t t, char* s );

#endif
