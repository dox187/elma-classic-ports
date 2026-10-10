// The bike, the rider and the objects of the level as sprites (bike.asm,
// objects.asm, bike.c): OBJ palettes 0-3, OBJ tiles 0-255, OAM 32-127, all
// at priority 2 (behind the front pictures of BG1).
//
// Per level: phys_level, then objects_load (it also takes the origin of the
// level pixels that bike_draw uses). Every frame: bike_draw and
// objects_draw, before core_frame_done.
#ifndef BIKE_H
#define BIKE_H

#include <snes.h>

// Forced blank: sprite palettes, the wheels' tiles, OBSEL.
void bike_load(void);
// From phys_view and bike_anim: OAM 32-63, loads the pictures of the parts
// that changed (at most 1600 bytes a frame, through the queue of the NMI).
void bike_draw(s16 cam_x, s16 cam_y);
// Forced blank or not: the objects of phys_objs (after phys_level).
void objects_load(u16 level);
// OAM 64-127; time = game time in steps of the physics, for the animation.
void objects_draw(s16 cam_x, s16 cam_y, u16 time);

typedef struct {
	u16 turn;      // PC forgas 0..65535 (1.0): the turn animation progress
	u16 volt;      // PC ugrasnagysag 0..65535
	u8 volt1;      // PC ugras1volt
} bike_anim_t;
extern bike_anim_t bike_anim;          // set by the game every frame

#endif
