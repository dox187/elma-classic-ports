#ifndef GBC_MENU_H
#define GBC_MENU_H
#include <gb/gb.h>
#include <stdint.h>

#define MENU_NO_ACTION 255
#define MENU_RESUME 254

/* All menu code/assets are in bank 7; the world name copier lives in ROM0.
 * The caller restores game tiles/palettes/OAM after a start or resume result.
 */
void menu_open(uint8_t selected,uint8_t can_resume) BANKED;
uint8_t menu_tick(uint8_t keys,uint8_t pressed) BANKED;
#endif
