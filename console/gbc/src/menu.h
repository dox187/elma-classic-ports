#ifndef GBC_MENU_H
#define GBC_MENU_H
#include <gb/gb.h>
#include <stdint.h>

#define MENU_NO_ACTION 255
#define MENU_RESUME 254
#define MENU_RESTART 253

enum { MENU_MAIN=0, MENU_LEVELS=1, MENU_CONTROLS=2, MENU_PLAYERS=3, MENU_NAME=4 };
extern volatile uint8_t menu_screen,menu_selection;
extern volatile uint8_t menu_player_selection,menu_keyboard_selection;

/* All menu code/assets are in bank 7; the world name copier lives in ROM0.
 * menu_open shows the main menu; level selection survives its sub-screens.
 * The caller restores game tiles/palettes/OAM after start, restart or resume.
 */
void menu_open(uint8_t selected,uint8_t can_resume) BANKED;
uint8_t menu_tick(uint8_t keys,uint8_t pressed) BANKED;
#endif
