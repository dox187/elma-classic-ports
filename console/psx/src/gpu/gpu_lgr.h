// The graphics of the LGR file in VRAM, for the GPU renderer (gpu_draw.cpp).
//
// When an LGR is loaded (loadlgrfile, LGRFILE.CPP), every picture, texture,
// object animation, grass picture and bike part is resampled to the
// resolution of the game view and uploaded once into the texture area of
// VRAM (gpu_video.h); the copies in RAM are then freed (gpu_lgr_loaded). The
// pictures of the level view are sampled at every second pixel in both
// directions (the view is 320x240 for the original 640x480), the bike parts
// at every fourth: they are drawn at a fifth of their size anyway. An image
// with at most 16 colors is stored with 4 bits a texel and its own 16-color
// CLUT, the others with 8 bits and the LGR palette.
#pragma once

#include <stdint.h>

class lgrfile;
class kiskep;
class anim;

// An image in VRAM is a grid of tiles of at most 256x256 texels (a texture
// page each).
struct gpu_tile {
	uint16_t tpage;  // color depth and page (getTPage bits, no blending)
	uint8_t u, v;    // top-left texel in the page
	uint8_t w1, h1;  // size - 1
	uint8_t clut;    // CLUT index (gpu_clut_id)
	uint8_t pad;
};

struct gpu_pic {
	int16_t w, h;             // texels
	uint8_t tiles_x, tiles_y; // tiles of 256 texels, the last ones smaller
	uint8_t scale;            // original pixels a texel (2 or 4)
	uint8_t pad;
	gpu_tile* tiles;          // NULL: not in VRAM (no room)
};

inline const gpu_tile* gpu_pic_tile(const gpu_pic* p, int tx, int ty) {
	return &p->tiles[ty * p->tiles_x + tx];
}

// A world-anchored texture (ground, sky, the texture of a mask, qgrass): the
// stored image is one period at the view's resolution, cols x rows texels.
// Texel column u is the original column (2u mod width); texel row v the
// original row (-2-2v mod height) of the bottom-up texture (lgrfile turns
// textures upside down), so drawn from the top it continues upwards in the
// world. A texture of odd width (height) is stored with two periods, so the
// period is still a whole number of texels.
// (Both the world-anchored use and the sky use this, see gpu_draw.cpp.)

// A mask as filled rectangles of its original pixels, (x1, y1)-(x2, y2)
// inclusive, y from the top.
struct gpu_mask_rect {
	int16_t x1, y1, x2, y2;
};
struct gpu_mask {
	int16_t xsize, ysize;
	int16_t nrects;
	gpu_mask_rect* rects;
};

// A grass picture (qup_*, qdown_*): its VRAM image, original size, and for
// every original column the number of transparent rows at its top (qgrass
// is drawn there, ecset.cpp kovetotextura).
struct gpu_grass {
	gpu_pic pic;
	int16_t xsize, ysize;
	uint8_t* tops;
};

struct gpu_anim {
	int nframes;
	gpu_pic* frames;
};

struct gpu_lgr_assets {
	const lgrfile* lgr;  // the LGR they were made from
	int npictures;
	gpu_pic* pictures;   // by the index of lgrfile::kepek
	int ntextures;
	gpu_pic* textures;   // by the index of lgrfile::texturak
	int nmasks;
	gpu_mask* masks;     // by the index of lgrfile::maszkok
	int ngrass;
	gpu_grass* grass;    // by the index of koveto::pkeptomb
	uint16_t palette[256]; // the LGR palette in VRAM format (bit 15 clear)
	uint32_t vram_cells;   // VRAM used
	uint32_t ram_freed;    // bytes of RAM given back
	int degraded;          // images that had to be stored at lower quality
	int missing;           // images that did not fit
};
extern gpu_lgr_assets Glgr;

// Called by loadlgrfile after a new lgrfile was made (LGRFILE.CPP).
void gpu_lgr_loaded();
// The VRAM image of a bike part or an object animation of Plgr, NULL if
// unknown.
const gpu_pic* gpu_kiskep_pic(const kiskep* k);
const gpu_anim* gpu_anim_pics(const anim* a);
// The getClut value of a CLUT index; valid in the game mode.
uint16_t gpu_clut_id(int index);
// Transparent-free CLUT of the LGR palette with 8 bits a texel (flat
// colors use Glgr.palette).
int gpu_opaque_clut8();
