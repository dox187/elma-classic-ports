// The picture of the level in the two nametables (vertical mirroring), a
// window of 33 columns and 30 rows around the camera, loaded as it moves.
#ifndef MAP_H
#define MAP_H

#include <stdint.h>
#include "levels.h"

// The camera: the map pixel at the top left corner of the screen.
extern int16_t Cam_x, Cam_y;
// Size of the map in pixels:
extern uint16_t Map_w, Map_h;

// Selects a level and draws the window around the camera (rendering off).
void map_start( const level_t* lev );
// Loads what the camera's move needs into the update buffer of the next
// frame (at most 8 pixels in each direction).
void map_scroll( void );

// Updates of the nametables for the next frame, for set_vram_update:
extern uint8_t Vram_buf[];
// Starts a new list of updates; map_scroll adds to it.
void vram_begin( void );
void vram_end( void );
// Adds a run of len tiles from adr (with NT_UPD_HORZ or NT_UPD_VERT) and
// returns where the tiles go.
uint8_t* vram_run( uint16_t adr, uint8_t flags, uint8_t len );

#endif
