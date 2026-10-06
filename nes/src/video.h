// The frame: sprites, nametable updates and the split under the bar at the
// top of the screen, handed to the NMI at the end of each frame.
#ifndef VIDEO_H
#define VIDEO_H

#include <stdint.h>

// Lines of the bar at the top of the game's screen, without background:
#define BAR_LINES 16

// Starts the picture of a frame: no sprites, no updates.
void frame_begin( void );
// Waits for the NMI, which shows the frame.
void frame_end( void );

// The game's screen: background below the bar, the bike's sprite bank
// switched in the NMI.
void video_game( uint8_t on );
void video_bike_bank( uint8_t bank );

// Sprite text at x, y (pixels), palette 3:
void spr_text( uint8_t x, uint8_t y, const char* s );
// Time in hundredths as mm:ss:hh into s (9 bytes):
void format_time( uint32_t t, char* s );

#endif
