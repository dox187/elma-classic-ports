// The level prepared for the GPU renderer at level load (betoltecseteket,
// in place of the brushes of ecset.cpp).
//
// Coordinates are those of the original's brush ("ecset"): pixels at the
// zoom of the game (Arany pixels a meter) from the brush's origin, y upwards.
// Fixed point values have 4 fraction bits.
#pragma once

#include <stdint.h>

#include "gpu/gpu_traps.h"

// A picture, a mask (texture), a grass picture or a strip of the qgrass
// texture above a grass picture, with the distance and clipping of the
// original. Drawn by distance, the farthest first; at equal distance the one
// the original added first wins, so it is drawn last. gpu_level::inst is in
// this drawing order.
enum { GI_PICTURE, GI_MASK, GI_GRASS, GI_QGRASS };
enum { GI_CLIP_NONE = 0, GI_CLIP_GROUND = 1, GI_CLIP_SKY = 2 };
struct gpu_inst {
	int32_t x, y;        // brush pixels: left column, top row
	int16_t w, h;        // pixels
	int16_t distance;
	uint8_t type, clip;
	int16_t index;       // picture, mask or grass picture of the LGR
	int16_t texture;     // the texture of a mask, qgrass
	int32_t sprite0;     // its sprites (gpu_level::sprites)
	int16_t nsprites;
};
const int GPU_INSTANCE_SHIFT = 9;
const int GPU_INSTANCE_CHUNK = 1 << GPU_INSTANCE_SHIFT;

// The sprites of the pictures are made at level load: an instance is drawn
// at a fixed place of the world, the texture of a mask or qgrass anchored
// to the world too. Top left at the half-resolution brush pixel (hx, hy),
// hy being its top row (y upwards).
// (hx, hy) is kept relative to the instance's (x >> 1, y >> 1), so a
// sprite takes 12 bytes; the sprites are kept in pieces of GPU_SPRITE_CHUNK
// (no single big block for a level with many pictures).
struct gpu_wsprite {
	int16_t dx, dy;
	uint8_t u, v, w1, h1;
	uint16_t tpage, clut;
};
const int GPU_SPRITE_SHIFT = 9;
const int GPU_SPRITE_CHUNK = 1 << GPU_SPRITE_SHIFT;

// Makes the level's pictures again if gv_level_release gave them back.
void gpu_level_ensure();

struct gpu_level {
	// The brush's origin (physics coordinates) and size (pixels):
	double origo_x, origo_y;
	int maxx, sorszam;
	// The sky (gpu_traps.h), malloc'd:
	int ntraps;
	gpu_trap* traps;
	// A grid over the brush for finding the trapezoids of a view:
	// (cells of GPU_TRAP_CELL brush pixels)
	int tgrid_w, tgrid_h;
	uint32_t* grid_start;  // tgrid_w*tgrid_h+1 offsets into grid_items
	uint16_t* grid_items;
	// The pictures, masks and grass, in drawing order. Those of the ground
	// (clipped to ground or not clipped) and those of the sky (clipped to sky
	// or not) are drawn apart, the far ones (distance 500 and more) and the
	// near ones apart (gpu_draw.cpp).
	int ninst;
	gpu_inst** inst;
	int nsprites;
	gpu_wsprite** sprite_chunks;
	// A grid over the brush for finding the instances of a view:
	// (cells of GPU_GRID_CELL brush pixels)
	int grid_w, grid_h;
	uint32_t* inst_start;  // grid_w*grid_h+1 offsets into inst_items
	uint16_t* inst_items;
	// The ground and sky textures (indices of lgrfile::texturak):
	int ground_texture, sky_texture, qgrass_texture;
	// For the map (view window): the same sky at its scale.
	double view_scale;     // map pixels a brush pixel
	// ... sampled at the centers of its display pixels (two map pixels
	// wide, map_step brush pixels): runs of sky, row by row from the bottom
	// of the brush (map_rows + 1 offsets into map_runs), a run being the
	// columns x0..x1-1 (from the brush's left), sorted by x.
	double map_step;
	int map_rows;
	uint32_t* map_row_start;
	int16_t* map_runs;     // x0, x1 pairs
};
// The drawing lists of a view (gpu_draw.cpp):
enum { GL_FAR_GROUND, GL_FAR_SKY, GL_NEAR_GROUND, GL_NEAR_SKY };
const int GPU_GRID_CELL = 512, GPU_TRAP_CELL = 256;

extern gpu_level Glevel;

inline gpu_inst* gpu_instance(int i) {
	return &Glevel.inst[i >> GPU_INSTANCE_SHIFT][i & (GPU_INSTANCE_CHUNK - 1)];
}

// Brush pixels of a point in physics coordinates (y up), fixed point.
int32_t gpu_brush_x16(double x);
int32_t gpu_brush_y16(double y);

// Sprite i of the level (gpu_inst::sprite0 and the next ones):
inline const gpu_wsprite* gpu_sprite(int i) {
	return &Glevel.sprite_chunks[i >> GPU_SPRITE_SHIFT][i & (GPU_SPRITE_CHUNK - 1)];
}
