// The saved state of the game in the battery-backed RAM of the cartridge
// (the state.dat of the original game, STATE.H): the players with their
// progress, the best ten times of each level and the options.
//
// The SRAM keeps two copies; a write goes to the older one and its header
// with the checksum is written last, so a write cut by a power loss leaves
// the other copy valid. A broken or empty SRAM is initialized at the start.
#ifndef SAVE_H
#define SAVE_H

#include <snes.h>
#include "core.h"

#define SAVE_PLAYERS  16        // players on the list (the original: 50)
#define SAVE_NAME_LEN 8         // letters of a name (JATEKOS.CPP)
#define SAVE_TIMES    10        // best times of a level (MAXIDOK)
#define SAVE_LEVELS   64        // room for levels; LEVEL_COUNT are used
#define SAVE_NO_TIME  0xFFFFFFFF

// The buttons of a level (Customize Controls, CUSTOM.CPP), indexes of
// save.keys; each holds one JOY_* bit, 0 for none. Start is always the
// original's Esc.
#define KEY_GAS   0             // Throttle
#define KEY_BRAKE 1             // Brake
#define KEY_LEFT  2             // Rotate left
#define KEY_RIGHT 3             // Rotate right
#define KEY_TURN  4             // Change direction
#define KEY_VIEW  5             // Toggle Navigator (the view box)
#define KEY_TIME  6             // Toggle Time
#define SAVE_KEYS 7
// The buttons that can be given to the controls (all but Start):
#define SAVE_KEYS_ALLOWED (JOY_B | JOY_Y | JOY_A | JOY_X | JOY_L | JOY_R | \
	JOY_SELECT | JOY_UP | JOY_DOWN | JOY_LEFT | JOY_RIGHT)

// What save_record did with a time (the messages of idoelintezes):
#define SAVE_REC_NONE  0        // not among the best ten
#define SAVE_REC_ADDED 1        // added at the end of the list
#define SAVE_REC_TOP10 2        // "You Made the Top Ten"
#define SAVE_REC_BEST  3        // "Best Time!"

typedef struct {
	char name[SAVE_NAME_LEN + 1];
	u8 done;                    // levels finished or skipped (sikerespalyakszama)
	u8 current;                 // the level chosen last (jelenlegipalya)
	u8 skipped[SAVE_LEVELS / 8];// bit per level: skipped
} save_player_t;

typedef struct {
	u8 count;
	u8 player[SAVE_TIMES];      // whose time (index of save.players)
	u8 time[SAVE_TIMES][3];     // hundredths of a second, 24 bits
} save_times_t;

typedef struct {
	u8 nplayers;                // players on the list
	u8 player;                  // the player playing (Player A)
	u8 sound;                   // options: sound on
	u8 anim_menus;              // the balls and the turning helmet of the menus
	u8 anim_objects;            // apples and the flower turn
	u8 detail;                  // Video Detail: High (1) draws the pictures of the levels
	u8 spare[2];
	save_player_t players[SAVE_PLAYERS];
	save_times_t times[SAVE_LEVELS];
	u16 keys[SAVE_KEYS];        // the buttons of a level
} save_t;

extern save_t save;             // the state; save_write stores it

// Reads the state from the SRAM, or initializes it if neither copy is
// valid (first start, garbage). ui_intro calls it.
void save_load(void);
// Writes the state into the SRAM.
void save_write(void);

// The best time of a level in hundredths, SAVE_NO_TIME if none.
u32 save_best(u16 level);
// Time i (0 = best) of the list of a level.
u32 save_time(u16 level, u16 i);
// Puts a finished time of the player into the list of the level as the
// original game does (idoelintezes); in RAM only, see save_write.
u8 save_record(u16 level, u32 time_hs, u16 player);
// Levels the player playing has finished or skipped: the list of the
// levels offers one more (the original's sikerespalyakszama).
u16 save_levels_done(void);
// The player playing.
save_player_t* save_player(void);
// Adds a player with the name, makes it the player playing; 0 if the list
// is full.
u8 save_add_player(const char* name);
u8 save_skipped(u16 level);
void save_set_skipped(u16 level, u8 on);
// The buttons of a level as they were at the start (Reset all controls to
// default).
void save_default_keys(void);

#endif
