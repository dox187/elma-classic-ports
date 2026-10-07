#ifndef ELMA_CLI_HOOK_H
#define ELMA_CLI_HOOK_H

// The terminal version draws texts as real terminal text instead of the
// game's pixel font. The core registers them here while it builds a frame;
// the platform layer places them over the picture when the frame is shown.

enum { CLI_ALIGN_LEFT = -1, CLI_ALIGN_CENTER = 0, CLI_ALIGN_RIGHT = 1 };
enum { CLI_COLOR_MENU = 0, CLI_COLOR_TIME };

// x, y: position in the 640x480 screen, y is the middle of the text line.
void cli_text( const char* text, int x, int y, int align, int color );
// Same, but the position is a pointer into the locked frame buffer, since
// the core draws the timers into sub-pictures of the screen:
void cli_text_at_pixel( const unsigned char* pixel, const char* text,
						int align, int color );
// Menu cursor, in place of the rotating helmet of the original:
void cli_cursor( int x, int y );

// Terminal graphics setting, shown in the Options menu:
const char* cli_graphics_name( void );
void cli_next_graphics( void );

#endif
