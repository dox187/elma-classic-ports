#ifndef GBC_WORLD_H
#define GBC_WORLD_H
#include <gb/gb.h>
#include <stdint.h>
#include "level_catalogue.h"

typedef struct {
 uint16_t x,y;uint8_t kind;int32_t world_x,world_y;uint8_t gravity;
} game_object_t;

extern world_level_t game_world;
extern game_object_t game_objects[LEVEL_OBJECT_MAX];
extern uint8_t world_level_index;
extern uint16_t world_uploads,world_cache_failures;

void world_level_name(uint8_t index,char *dest) NONBANKED;
uint8_t world_select(uint8_t index) BANKED;
void world_begin(uint16_t camera_x,uint16_t camera_y) BANKED;
/* Stage an adjacent tile target in spare time; fine camera moves preserve it.
 * world_scroll commits the matching coarse view, or cancels on another target. */
void world_prepare(uint16_t old_x,uint16_t old_y,uint16_t x,uint16_t y,uint16_t start) BANKED;
void world_scroll(uint16_t old_x,uint16_t old_y,uint16_t x,uint16_t y) BANKED;
void world_game_assets(void) BANKED;
#endif
