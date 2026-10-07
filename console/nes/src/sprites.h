// The sprites made by gfx.py.
#ifndef SPRITES_H
#define SPRITES_H

#include <stdint.h>

// Metasprites of the bike's frame (around the body) and the rider (around
// the rider's point) at 64 angles, facing left, in the data banks: a table
// of 64 pairs of offsets (frame, rider) from Bike_meta, each to the number
// of sprites, then x, y and the tile of each, in the bank of the angle.
extern const uint32_t Bike_meta;

// 16x16 objects, four tiles each: top left, top right, bottom left, bottom
// right.
extern const uint8_t Wheel_tiles[8*4];
extern const uint8_t Apple_tiles[4];
extern const uint8_t Flower_tiles[4];
extern const uint8_t Killer_tiles[4*4];

// Sprite tiles of the characters from 32 (space) to 127:
extern const uint8_t Hud_font[96];
// Lines of hints set closer than the font: their number of tiles, then
// the tiles from the left.
extern const uint8_t Hint_again[];  // A/B: AGAIN
extern const uint8_t Hint_menu[];   // START: MENU

#endif
