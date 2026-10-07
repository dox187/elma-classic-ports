// The levels, as build.py places them in the data banks (levconv.py
// describes their data).
#ifndef LEVELS_H
#define LEVELS_H

#include <stdint.h>

typedef struct {
	const char* name;
	uint16_t w, h;          // the map in tiles
	uint32_t columns;       // where the columns start, from map
	uint32_t map;
	uint32_t segments;
	uint8_t gw, gh;         // the grid in cells of 4 m
	uint32_t grid_rows;     // where the rows of the grid start, from grid
	uint32_t grid;
	uint32_t objects;
	int32_t start_x, start_y;  // u
	uint8_t chr;            // 1 KB bank of its background tiles 128..255
} level_t;

// In the bank of the menus:
extern const level_t Levels[];
extern const uint8_t Level_count;
// Whether the levels are of the elma.res of the shareware game:
extern const uint8_t Shareware;

// The level played, copied from Levels by the menus:
extern level_t Level;

#endif
