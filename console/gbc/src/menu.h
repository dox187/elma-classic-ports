#ifndef GBC_MENU_H
#define GBC_MENU_H
#include <gb/gb.h>
#include <stdint.h>

#define MENU_NO_ACTION 255
#define MENU_RESUME 254
#define MENU_RESTART 253

enum { MENU_MAIN=0, MENU_LEVELS=1, MENU_CONTROLS=2, MENU_PLAYERS=3, MENU_NAME=4, MENU_RESULT=5 };
extern volatile uint8_t menu_screen,menu_selection;
extern volatile uint8_t menu_player_selection,menu_keyboard_selection;

/* All menu code/assets are in bank 7; the world name copier lives in ROM0.
 * menu_open shows the main menu; level selection survives its sub-screens.
 * menu_result shows the completed run; the caller handles its controls.
 * The caller restores game tiles/palettes/OAM after start, restart or resume.
 */
void menu_open(uint8_t selected,uint8_t can_resume) BANKED;
void menu_result(uint8_t level,uint32_t frames,uint32_t previous_best) BANKED;
/* Bank 7 callers only. Write eight clock characters without a terminator. */
void menu_format_time(char *out,uint32_t frames);
uint8_t menu_tick(uint8_t keys,uint8_t pressed) BANKED;
#endif
