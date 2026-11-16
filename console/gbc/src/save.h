#ifndef GBC_SAVE_H
#define GBC_SAVE_H
#include <gb/gb.h>
#include <stdint.h>

#define SAVE_PLAYER_COUNT 4
#define SAVE_NAME_MAX 10
#define SAVE_LEVEL_COUNT 54

extern volatile uint8_t save_player;
extern char save_names[SAVE_PLAYER_COUNT][SAVE_NAME_MAX+1];

/* Call init once before use. Main-loop calls only: interrupt handlers must
 * not switch cartridge RAM banks. Every call enables RAM and leaves bank 0.
 * Names accept A-Z, 0-9 and spaces, trim outer spaces, and reject blank or
 * invalid input. Read at most ten characters; pass a WRAM or ROM0 string.
 * Times use game_time_frames (nominal video frames), with zero = no record. */
void save_init(void) BANKED;
void save_select(uint8_t player) BANKED;
void save_name(uint8_t player,const char *name) BANKED;
uint32_t save_best(uint8_t player,uint8_t level) BANKED;
/* Return 1 only for a new nonzero best. Invalid player/level indices are
 * ignored by all APIs (best returns zero); renaming preserves all times. */
uint8_t save_record(uint8_t player,uint8_t level,uint32_t frames) BANKED;

#endif
