// The background of a level (map.asm): BG1 the ground, grass and pictures,
// streamed as the camera moves, BG2 the sky.
#ifndef MAP_H
#define MAP_H

#include <snes.h>

// In forced blank: palettes 1-7 of the BG, the tiles and maps of BG1 and
// BG2 for the camera set last, and the BG mode, bases and TM bits of BG1
// and BG2. Takes a few frames' time.
void map_load(u16 level);
// The top left pixel of the screen in level pixels; call it before
// map_load and every frame: sets the scroll of BG1 and BG2 and queues what
// BG1 needs (at most about 2.2 KB of DMA a frame).
void map_set_camera(s16 cam_x, s16 cam_y);

#endif
