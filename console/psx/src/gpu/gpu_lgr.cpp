// The graphics of the LGR file in VRAM, see gpu_lgr.h.
//
// While lgrfile's constructor reads the LGR, gpu_lgr_step (called before
// each of its pictures, LGRFILE.CPP) takes what the previous one made: the
// picture is resampled to the resolution it is drawn at, converted to the
// texels of VRAM (4 or 8 bits) and kept until the end, and the full size
// copy is freed (it is only needed by the software renderer, so the
// comparison build keeps it). When the LGR is complete (gpu_lgr_loaded) the
// images are packed into the texture area and uploaded.
#include <psxgpu.h>

#include "all.h"
#include "gpu/gpu_lgr.h"
#include "gpu/gpu_video.h"

gpu_lgr_assets Glgr;

namespace {

#ifdef ELMA_PSX_GPU_COMPARE
const bool FREE_COPIES = false;
#else
const bool FREE_COPIES = true;
#endif

// --- CLUTs -------------------------------------------------------------------

// An 8-bit CLUT is the LGR palette with one entry transparent (or none); a
// 4-bit CLUT holds the 16 colors of one image. They are uploaded when the
// game mode starts (gpu_video.h: x 320..639 from row 240).
struct clut_def {
	uint8_t bits;
	int16_t transparent;  // the transparent entry, -1: none
	uint8_t map[16];      // 4 bits: the palette index of each entry
};
const int MAX_CLUT8 = 16, MAX_CLUTS = 255;
const int CLUT8_Y = GV_GAME_DATA_Y, CLUT4_Y = GV_GAME_DATA_Y + MAX_CLUT8;
clut_def cluts[MAX_CLUTS];
uint16_t clut_ids[MAX_CLUTS];
int nclut = 0, nclut8 = 0, nclut4 = 0;

int add_clut8(int transparent) {
	for (int i = 0; i < nclut; ++i)
		if (cluts[i].bits == 8 && cluts[i].transparent == transparent) return i;
	if (nclut == MAX_CLUTS || nclut8 == MAX_CLUT8) return -1;
	clut_def* c = &cluts[nclut];
	c->bits = 8;
	c->transparent = (int16_t)transparent;
	clut_ids[nclut] = getClut(GV_GAME_DATA_X, CLUT8_Y + nclut8);
	nclut8++;
	return nclut++;
}

int add_clut4(const uint8_t* map, int transparent) {
	for (int i = 0; i < nclut; ++i)
		if (cluts[i].bits == 4 && cluts[i].transparent == transparent && !memcmp(cluts[i].map, map, 16))
			return i;
	if (nclut == MAX_CLUTS) return -1;
	clut_def* c = &cluts[nclut];
	c->bits = 4;
	c->transparent = (int16_t)transparent;
	memcpy(c->map, map, 16);
	clut_ids[nclut] = getClut(GV_GAME_DATA_X + 16 * (nclut4 % 20), CLUT4_Y + nclut4 / 20);
	nclut4++;
	return nclut++;
}

void upload_cluts() {
	static uint32_t row_words[128];
	uint16_t* row = (uint16_t*)row_words;
	for (int i = 0; i < nclut; ++i) {
		const clut_def* c = &cluts[i];
		const int n = c->bits == 8 ? 256 : 16;
		for (int k = 0; k < n; ++k) row[k] = Glgr.palette[c->bits == 8 ? k : c->map[k]];
		if (c->transparent >= 0) row[c->transparent] = 0;
		const int id = clut_ids[i];
		RECT r = {(int16_t)((id & 0x3f) << 4), (int16_t)(id >> 6), (int16_t)n, 1};
		DrawSync(0);
		LoadImage(&r, row_words);
	}
	DrawSync(0);
}

uint16_t vram_color(const unsigned char* c) {
	const uint16_t v = (uint16_t)((c[0] >> 1) | (c[1] >> 1) << 5 | (c[2] >> 1) << 10);
	// 0 would be transparent; nearly black instead:
	return v ? v : 0x0400;
}

// --- Images ------------------------------------------------------------------------

enum Kind {
	K_PIC8,     // a pic8 seen from the top, sampled at every second pixel
	K_PIC8_UP,  // a pic8 that is upside down (anim frames), the same
	K_BIKE,     // a kiskep, every fourth pixel
	K_RLE,      // a picture of lgrfile::kepek (rows of empty/full runs)
	K_TEXTURE,  // an upside down texture, one period (gpu_lgr.h)
};
enum Group { G_PICTURE, G_TEXTURE, G_OTHER };

// An image taken from the LGR: its texels at the view's resolution in
// VRAM's format, tile after tile, until it is uploaded.
struct image {
	Group group;
	char name[10];   // pictures and textures (lgrfile sorts them later)
	gpu_pic pic;     // the description, copied to out at the end
	gpu_pic* out;
	int w, h, bits, clut, transparent;
	uint8_t* data;   // every tile's rows of cells
	int tile0;       // first tile slot
};

const int MAX_IMAGES = 512;
image* images = 0;
int nimage = 0;

int mod(int a, int m) {
	const int r = a % m;
	return r < 0 ? r + m : r;
}

// A source while it is sampled.
struct source {
	Kind kind;
	const void* p;
	int sw, sh;
	int transparent;
	// The place in an RLE picture between consecutive rows:
	const unsigned char* rle_pos;
	int rle_row;
};

void rle_skip_row(source* s) {
	const unsigned char* t = s->rle_pos;
	while (true) {
		const int empty = t[0] * 256 + t[1];
		t += 2;
		if (empty > 60000) break;
		const int full = t[0] * 256 + t[1];
		t += 2 + full;
	}
	s->rle_pos = t;
	s->rle_row++;
}

// Row j of the image at the view's resolution, w texels: palette indices,
// and 1 in trans[] where transparent.
void sample_row(source* s, int j, int w, unsigned char* idx, unsigned char* trans) {
	switch (s->kind) {
	case K_PIC8:
	case K_PIC8_UP: {
		pic8* pic = (pic8*)s->p;
		int y = s->kind == K_PIC8 ? 2 * j : s->sh - 1 - 2 * j;
		if (y < 0) y = 0;
		if (y > s->sh - 1) y = s->sh - 1;
		const unsigned char* row = pic->getptr(y);
		for (int i = 0; i < w; ++i) {
			idx[i] = row[2 * i < s->sw ? 2 * i : s->sw - 1];
			trans[i] = idx[i] == s->transparent;
		}
		break;
	}
	case K_BIKE: {
		const kiskep* k = (const kiskep*)s->p;
		int y = 4 * j + 1;
		if (y > k->ysize - 1) y = k->ysize - 1;
		const unsigned char* row = k->tomb + y * 256;
		for (int i = 0; i < w; ++i) {
			int x = 4 * i + 1;
			if (x > k->xsize - 1) x = k->xsize - 1;
			idx[i] = row[x];
			trans[i] = idx[i] == s->transparent;
		}
		break;
	}
	case K_TEXTURE: {
		pic8* pic = (pic8*)s->p;
		const unsigned char* row = pic->getptr(mod(-2 - 2 * j, s->sh));
		for (int i = 0; i < w; ++i) {
			idx[i] = row[(2 * i) % s->sw];
			trans[i] = 0;
		}
		break;
	}
	case K_RLE: {
		const kep* k = (const kep*)s->p;
		if (!s->rle_pos || s->rle_row > 2 * j) {
			s->rle_pos = k->adatok;
			s->rle_row = 0;
		}
		while (s->rle_row < 2 * j) rle_skip_row(s);
		static unsigned char full_idx[2048], full_trans[2048];
		const unsigned char* t = s->rle_pos;
		int x = 0;
		memset(full_trans, 1, s->sw < 2048 ? s->sw : 2048);
		while (true) {
			const int empty = t[0] * 256 + t[1];
			t += 2;
			if (empty > 60000) break;
			x += empty;
			const int full = t[0] * 256 + t[1];
			t += 2;
			for (int i = 0; i < full && x + i < 2048; ++i) {
				full_idx[x + i] = t[i];
				full_trans[x + i] = 0;
			}
			t += full;
			x += full;
		}
		s->rle_pos = t;
		s->rle_row++;
		for (int i = 0; i < w; ++i) {
			const int sx = 2 * i < 2048 ? 2 * i : 2047;
			trans[i] = full_trans[sx];
			idx[i] = trans[i] ? 0 : full_idx[sx];
		}
		break;
	}
	}
}

// A tile in VRAM is a whole number of cells wide, and an even number, as
// the SDK's LoadImage drops an odd halfword. It also sends whole blocks of
// 16 words: after a tile come zero words (GPU no-ops), not the next tile.
int tile_cells(int w, int bits) { return (((w * bits + 15) / 16) + 1) & ~1; }
int tile_bytes(int w, int h, int bits) { return ((tile_cells(w, bits) * 2 * h + 63) & ~63) + 64; }

// Takes an image: decides its color depth and CLUT from the sampled texels
// and converts them. Returns the image or NULL (nothing to take, too big).
image* take(Kind kind, const void* p, int sw, int sh, int transparent, Group group, const char* name,
            gpu_pic* out) {
	if (out) memset(out, 0, sizeof(*out));
	if (!p || sw <= 0 || sh <= 0 || sw > 2048 || nimage == MAX_IMAGES) {
		Glgr.missing++;
		return 0;
	}
	image* im = &images[nimage];
	memset(im, 0, sizeof(*im));
	im->group = group;
	if (name) strncpy(im->name, name, sizeof(im->name) - 1);
	im->out = out;
	switch (kind) {
	case K_BIKE:
		im->w = (sw + 3) / 4;
		im->h = (sh + 3) / 4;
		im->pic.scale = 4;
		break;
	case K_TEXTURE:
		im->w = sw % 2 ? sw : sw / 2;
		im->h = sh % 2 ? sh : sh / 2;
		im->pic.scale = 2;
		break;
	default:
		im->w = (sw + 1) / 2;
		im->h = (sh + 1) / 2;
		im->pic.scale = 2;
	}
	if (im->w > 512 || im->h > 512) {
		Glgr.missing++;
		return 0;
	}
	im->pic.w = (int16_t)im->w;
	im->pic.h = (int16_t)im->h;
	im->pic.tiles_x = (uint8_t)((im->w + 255) / 256);
	im->pic.tiles_y = (uint8_t)((im->h + 255) / 256);

	// The texels' colors (a first pass over the source, row by row):
	source s = {kind, p, sw, sh, transparent, 0, 0};
	static unsigned char idx[512], trans[512];
	uint32_t used[8] = {0};
	bool any_transparent = false;
	for (int j = 0; j < im->h; ++j) {
		sample_row(&s, j, im->w, idx, trans);
		for (int i = 0; i < im->w; ++i) {
			if (trans[i])
				any_transparent = true;
			else
				used[idx[i] >> 5] |= 1u << (idx[i] & 31);
		}
	}
	int count = 0;
	uint8_t map[16] = {0};
	for (int c = 0; c < 256; ++c)
		if (used[c >> 5] & (1u << (c & 31))) {
			if (count < 16) map[count] = (uint8_t)c;
			count++;
		}
	im->bits = 8;
	im->clut = -1;
	if (count + (any_transparent ? 1 : 0) <= 16) {
		im->transparent = any_transparent ? count : -1;
		im->clut = add_clut4(map, im->transparent);
		if (im->clut >= 0) im->bits = 4;
	}
	if (im->bits == 8) {
		int t = -1;
		if (any_transparent) {
			t = transparent;
			if (t < 0 || (used[t >> 5] & (1u << (t & 31)))) {
				// An RLE picture has no transparent color: an unused one,
				// one that already has a CLUT if possible.
				t = -1;
				for (int i = 0; i < nclut && t < 0; ++i)
					if (cluts[i].bits == 8 && cluts[i].transparent >= 0 &&
					    !(used[cluts[i].transparent >> 5] & (1u << (cluts[i].transparent & 31))))
						t = cluts[i].transparent;
				for (int c = 0; c < 256 && t < 0; ++c)
					if (!(used[c >> 5] & (1u << (c & 31)))) t = c;
			}
		}
		im->transparent = t;
		im->clut = add_clut8(t);
	}
	uint8_t to4[256] = {0};
	if (im->bits == 4)
		for (int k = 0; k < 16; ++k) to4[map[k]] = (uint8_t)k;

	// Tile after tile, rows of whole cells (tile_bytes), filled in a second
	// pass over the source:
	int bytes = 0;
	int tile_offset[4];
	for (int ty = 0; ty < im->pic.tiles_y; ++ty)
		for (int tx = 0; tx < im->pic.tiles_x; ++tx) {
			const int w = im->w - tx * 256 < 256 ? im->w - tx * 256 : 256;
			const int h = im->h - ty * 256 < 256 ? im->h - ty * 256 : 256;
			tile_offset[ty * im->pic.tiles_x + tx] = bytes;
			bytes += tile_bytes(w, h, im->bits);
		}
	im->data = new uint8_t[bytes];
	memset(im->data, 0, bytes);
	s.rle_pos = 0;
	s.rle_row = 0;
	for (int j = 0; j < im->h; ++j) {
		sample_row(&s, j, im->w, idx, trans);
		const int ty = j >> 8, jj = j & 255;
		for (int tx = 0; tx < im->pic.tiles_x; ++tx) {
			const int x0 = tx * 256;
			const int w = im->w - x0 < 256 ? im->w - x0 : 256;
			const int row_bytes = tile_cells(w, im->bits) * 2;
			uint8_t* o = im->data + tile_offset[ty * im->pic.tiles_x + tx] + jj * row_bytes;
			const unsigned char* in = idx + x0;
			const unsigned char* tr = trans + x0;
			for (int i = 0; i < w; ++i) {
				if (im->bits == 8)
					o[i] = tr[i] ? (unsigned char)im->transparent : in[i];
				else {
					const int v = tr[i] ? im->transparent : to4[in[i]];
					o[i >> 1] |= (unsigned char)(v << ((i & 1) * 4));
				}
			}
		}
	}
	nimage++;
	return im;
}

// --- The LGR's pictures --------------------------------------------------------

struct kiskep_entry {
	const kiskep* k;
	gpu_pic pic;
};
const int MAX_KISKEP = 32;
kiskep_entry kiskeps[MAX_KISKEP];
int nkiskep = 0;

struct anim_entry {
	const anim* a;
	gpu_anim pics;
};
const int MAX_ANIMS = 2 + MAXFOODSZAM;
anim_entry anims[MAX_ANIMS];
int nanim = 0;

// The LGR being taken, and how much of it is taken:
const lgrfile* taking = 0;
int taken_kep = 0, taken_tex = 0, taken_grass = 0;

void free_assets() {
	for (int i = 0; i < Glgr.npictures; ++i) delete[] Glgr.pictures[i].tiles;
	for (int i = 0; i < Glgr.ntextures; ++i) delete[] Glgr.textures[i].tiles;
	for (int i = 0; i < Glgr.nmasks; ++i) delete[] Glgr.masks[i].rects;
	if (Glgr.grass)
		for (int i = 0; i < MAXKOVETOKEPSZAM; ++i) {
			delete[] Glgr.grass[i].pic.tiles;
			delete[] Glgr.grass[i].tops;
		}
	delete[] Glgr.pictures;
	delete[] Glgr.textures;
	delete[] Glgr.masks;
	delete[] Glgr.grass;
	for (int i = 0; i < nkiskep; ++i) delete[] kiskeps[i].pic.tiles;
	for (int i = 0; i < nanim; ++i) {
		for (int f = 0; f < anims[i].pics.nframes; ++f) delete[] anims[i].pics.frames[f].tiles;
		delete[] anims[i].pics.frames;
	}
	memset(&Glgr, 0, sizeof(Glgr));
	nkiskep = nanim = 0;
	nclut = nclut8 = nclut4 = 0;
	if (images)
		for (int i = 0; i < nimage; ++i) delete[] images[i].data;
	delete[] images;
	images = 0;
	nimage = 0;
}

void start(const lgrfile* l) {
	free_assets();
	taking = l;
	taken_kep = taken_tex = taken_grass = 0;
	images = new image[MAX_IMAGES];
	Glgr.grass = new gpu_grass[MAXKOVETOKEPSZAM];
	memset(Glgr.grass, 0, MAXKOVETOKEPSZAM * sizeof(gpu_grass));
	// The opaque 8-bit CLUT first (index 0), flat colors and textures use it:
	add_clut8(-1);
}

void take_kiskep(kiskep* k) {
	if (!k || !k->tomb || nkiskep == MAX_KISKEP) return;
	for (int i = 0; i < nkiskep; ++i)
		if (kiskeps[i].k == k) return;
	kiskep_entry* e = &kiskeps[nkiskep++];
	e->k = k;
	take(K_BIKE, k, k->xsize, k->ysize, k->lyuk, G_OTHER, 0, &e->pic);
	if (FREE_COPIES) {
		delete[] k->tomb;
		k->tomb = 0;
	}
}

void take_bike(const motkepek* m) {
	take_kiskep(m->pkisa);
	take_kiskep(m->pkisb);
	take_kiskep(m->pkisc);
	take_kiskep(m->pkisd);
	take_kiskep(m->pkisvezeto);
	take_kiskep(m->pkiscomb);
	take_kiskep(m->pkislabszar);
	take_kiskep(m->pkiskerek);
	take_kiskep(m->pkiselsorud);
	take_kiskep(m->pkishatsorud);
	take_kiskep(m->pkisalkar);
	take_kiskep(m->pkisfelkar);
	take_kiskep(m->pkisfej);
}

void take_anim(anim* a) {
	if (!a || nanim == MAX_ANIMS || a->frameszam <= 0 || !a->ppictomb[0]) return;
	for (int i = 0; i < nanim; ++i)
		if (anims[i].a == a) return;
	anim_entry* e = &anims[nanim++];
	e->a = a;
	e->pics.nframes = a->frameszam;
	e->pics.frames = new gpu_pic[a->frameszam];
	// The frames are upside down; the transparent color is the top left
	// pixel of the original picture.
	const unsigned char t = a->ppictomb[0]->gpixel(0, a->ppictomb[0]->getysize() - 1);
	for (int f = 0; f < a->frameszam; ++f) {
		pic8* frame = a->ppictomb[f];
		take(K_PIC8_UP, frame, frame->getxsize(), frame->getysize(), t, G_OTHER, 0, &e->pics.frames[f]);
		if (FREE_COPIES) {
			delete frame;
			a->ppictomb[f] = 0;
		}
	}
}

void take_grass(koveto* k, int i) {
	pic8* pic = k->pkeptomb[i];
	gpu_grass* g = &Glgr.grass[i];
	if (!pic) return;
	const unsigned char t = k->atlatszotomb[i];
	take(K_PIC8, pic, pic->getxsize(), pic->getysize(), t, G_OTHER, 0, &g->pic);
	g->xsize = (int16_t)pic->getxsize();
	g->ysize = (int16_t)pic->getysize();
	g->tops = new uint8_t[g->xsize];
	for (int x = 0; x < g->xsize; ++x) {
		int y = 0;
		while (y < g->ysize && pic->getptr(y)[x] == t) y++;
		g->tops[x] = (uint8_t)(y < 255 ? y : 255);
	}
	if (FREE_COPIES) {
		delete pic;
		k->pkeptomb[i] = 0;
	}
}

// Masks as rectangles: rows with the same filled runs are merged.
void make_mask(const maszk* m, gpu_mask* out) {
	out->xsize = (int16_t)m->xsize;
	out->ysize = (int16_t)m->ysize;
	const int MAXRUN = 64, MAXRECT = 512;
	gpu_mask_rect* rects = new gpu_mask_rect[MAXRECT];
	int nrects = 0;
	int16_t prev_x1[MAXRUN], prev_x2[MAXRUN], open_rect[MAXRUN];
	int nprev = 0;
	int i = 0;
	for (int y = 0; y <= m->ysize; ++y) {
		int16_t x1[MAXRUN], x2[MAXRUN];
		int n = 0;
		if (y < m->ysize) {
			int x = 0;
			while (m->adatok[i].tipus != ME_SOREMELES) {
				if (m->adatok[i].tipus == ME_TELI && n < MAXRUN) {
					x1[n] = (int16_t)x;
					x2[n] = (int16_t)(x + m->adatok[i].hossz - 1);
					n++;
				}
				x += m->adatok[i].hossz;
				i++;
			}
			i++;
		}
		bool same = n == nprev;
		for (int k = 0; same && k < n; ++k) same = x1[k] == prev_x1[k] && x2[k] == prev_x2[k];
		if (same) {
			for (int k = 0; k < n; ++k)
				if (open_rect[k] >= 0) rects[open_rect[k]].y2 = (int16_t)y;
			continue;
		}
		for (int k = 0; k < n; ++k) {
			prev_x1[k] = x1[k];
			prev_x2[k] = x2[k];
			open_rect[k] = -1;
			if (nrects < MAXRECT) {
				gpu_mask_rect* r = &rects[nrects];
				r->x1 = x1[k];
				r->x2 = x2[k];
				r->y1 = r->y2 = (int16_t)y;
				open_rect[k] = (int16_t)nrects++;
			}
		}
		nprev = n;
	}
	out->nrects = (int16_t)nrects;
	out->rects = new gpu_mask_rect[nrects ? nrects : 1];
	memcpy(out->rects, rects, nrects * sizeof(gpu_mask_rect));
	delete[] rects;
}

// --- Packing ---------------------------------------------------------------------

// Free VRAM for textures, in cells (gpu_video.h): the right part of VRAM in
// two texture page rows (without the debug font's corner and the menu
// palette's row), and the strip under the menu picture (its first 128 cells
// hold the menu's staging rows).
struct region {
	int16_t x0, x1, y0, y1;
};
const region regions[] = {
	{GV_TEX_X, 1024, 0, 256},
	{GV_TEX_X, GV_FONT_X, 256, GV_MENU_CLUT_Y},
	{GV_FONT_X, 1024, 256, GV_FONT_Y},
	{128, GV_TEX_X, 480, 512},
};
const int NREGIONS = sizeof(regions) / sizeof(regions[0]);

struct tile_slot {
	int16_t image, tx, ty;
	int16_t cw, h;  // cells, rows
	int16_t x, y;   // placed at, x < 0: not placed
	int32_t offset; // its data in the image
};

// Skyline packing: for each region the height filled in every cell column;
// a tile goes where its top ends lowest (then leftmost).
const int MAX_REGION_W = 512;
int16_t* skyline[NREGIONS];

// A tile must lie within one texture page: 64 cells for 4 bits a texel, a
// page of 128 cells starting at a multiple of 64 for 8 bits.
bool fits_page(int x, int cw, int bits) {
	const int page = x & ~63;
	return bits == 4 ? x + cw <= page + 64 : x + cw <= page + 128;
}

bool place(tile_slot* s, int bits) {
	int best_r = -1, best_x = 0, best_y = 1 << 30;
	for (int r = 0; r < NREGIONS; ++r) {
		const region* g = &regions[r];
		const int width = g->x1 - g->x0;
		const int16_t* line = skyline[r];
		// Candidates: where the skyline steps, and the texture pages.
		for (int i = 0; i + s->cw <= width; ++i) {
			const int x = g->x0 + i;
			if (i > 0 && line[i] == line[i - 1] && (x & 63)) continue;
			if (!fits_page(x, s->cw, bits)) continue;
			int y = 0;
			for (int k = 0; k < s->cw && y < best_y; ++k)
				if (line[i + k] > y) y = line[i + k];
			if (y >= best_y || g->y0 + y + s->h > g->y1) continue;
			best_y = y;
			best_r = r;
			best_x = i;
		}
	}
	if (best_r < 0) return false;
	for (int k = 0; k < s->cw; ++k) skyline[best_r][best_x + k] = (int16_t)(best_y + s->h);
	s->x = (int16_t)(regions[best_r].x0 + best_x);
	s->y = (int16_t)(regions[best_r].y0 + best_y);
	return true;
}

void pack_and_upload() {
	int nslot = 0;
	for (int i = 0; i < nimage; ++i) nslot += images[i].pic.tiles_x * images[i].pic.tiles_y;
	tile_slot* slots = new tile_slot[nslot ? nslot : 1];
	nslot = 0;
	for (int i = 0; i < nimage; ++i) {
		image* im = &images[i];
		im->tile0 = nslot;
		int32_t offset = 0;
		for (int ty = 0; ty < im->pic.tiles_y; ++ty)
			for (int tx = 0; tx < im->pic.tiles_x; ++tx) {
				tile_slot* s = &slots[nslot++];
				const int w = im->w - tx * 256 < 256 ? im->w - tx * 256 : 256;
				const int h = im->h - ty * 256 < 256 ? im->h - ty * 256 : 256;
				s->image = (int16_t)i;
				s->tx = (int16_t)tx;
				s->ty = (int16_t)ty;
				s->cw = (int16_t)tile_cells(w, im->bits);
				s->h = (int16_t)h;
				s->x = -1;
				s->offset = offset;
				offset += tile_bytes(w, h, im->bits);
			}
	}
	// The tallest first (images not drawn take no room):
	int16_t* order = new int16_t[nslot ? nslot : 1];
	int norder = 0;
	for (int i = 0; i < nslot; ++i)
		if (images[slots[i].image].out) order[norder++] = (int16_t)i;
	for (int gap = norder / 2; gap > 0; gap /= 2)
		for (int i = gap; i < norder; ++i) {
			const int16_t v = order[i];
			int j = i;
			while (j >= gap && (slots[order[j - gap]].h < slots[v].h ||
			                    (slots[order[j - gap]].h == slots[v].h && slots[order[j - gap]].cw < slots[v].cw))) {
				order[j] = order[j - gap];
				j -= gap;
			}
			order[j] = v;
		}
	for (int r = 0; r < NREGIONS; ++r) {
		skyline[r] = new int16_t[MAX_REGION_W];
		memset(skyline[r], 0, MAX_REGION_W * sizeof(int16_t));
	}
	Glgr.vram_cells = 0;
	for (int i = 0; i < norder; ++i) {
		tile_slot* s = &slots[order[i]];
		if (place(s, images[s->image].bits)) Glgr.vram_cells += s->cw * s->h;
	}
	for (int r = 0; r < NREGIONS; ++r) delete[] skyline[r];
	delete[] order;

	// The tiles of every image, and the upload:
	for (int i = 0; i < nimage; ++i) {
		image* im = &images[i];
		gpu_pic* out = im->out;
		if (!out) {
			delete[] im->data;
			im->data = 0;
			continue;
		}
		*out = im->pic;
		const int n = im->pic.tiles_x * im->pic.tiles_y;
		gpu_tile* tiles = new gpu_tile[n];
		bool complete = true;
		for (int k = 0; k < n && complete; ++k) {
			const tile_slot* s = &slots[im->tile0 + k];
			if (s->x < 0) {
				complete = false;
				break;
			}
			gpu_tile* t = &tiles[k];
			const int page_x = s->x & ~63, page_y = s->y & 256;
			t->tpage = (uint16_t)getTPage(im->bits == 4 ? 0 : 1, 0, page_x, page_y);
			t->u = (uint8_t)((s->x - page_x) * (im->bits == 4 ? 4 : 2));
			t->v = (uint8_t)(s->y - page_y);
			const int w = im->w - s->tx * 256 < 256 ? im->w - s->tx * 256 : 256;
			const int h = im->h - s->ty * 256 < 256 ? im->h - s->ty * 256 : 256;
			t->w1 = (uint8_t)(w - 1);
			t->h1 = (uint8_t)(h - 1);
			t->clut = (uint8_t)im->clut;
			RECT r = {s->x, s->y, s->cw, s->h};
			LoadImage(&r, (const uint32_t*)(im->data + s->offset));
			DrawSync(0);
		}
		if (complete)
			out->tiles = tiles;
		else {
			// Not in VRAM: drawn as nothing.
			delete[] tiles;
			Glgr.missing++;
		}
		delete[] im->data;
		im->data = 0;
	}
	delete[] slots;
}

void game_mode_started() { upload_cluts(); }

} // namespace

// Before every picture of an LGR (and at its end): takes what lgrfile made
// since the last call.
void gpu_lgr_step(lgrfile* l) {
	if (!l) return;
	if (l != taking || l->kepszam < taken_kep || l->texturaszam < taken_tex) start(l);
	for (; taken_kep < l->kepszam; ++taken_kep) {
		kep* k = &l->kepek[taken_kep];
		take(K_RLE, k, k->xsize, k->ysize, -1, G_PICTURE, k->nev, 0);
		if (FREE_COPIES) {
			delete[] k->adatok;
			k->adatok = new unsigned char[1];
		}
	}
	for (; taken_tex < l->texturaszam; ++taken_tex) {
		textura* t = &l->texturak[taken_tex];
		const int w = t->origxsize > 0 ? t->origxsize : t->ppic->getxsize();
		take(K_TEXTURE, t->ppic, w, t->ppic->getysize(), -1, G_TEXTURE, t->nev, 0);
		if (FREE_COPIES) {
			delete t->ppic;
			t->ppic = new pic8(4, 1);
		}
	}
	for (; taken_grass < l->pkoveto->kepszam && taken_grass < MAXKOVETOKEPSZAM; ++taken_grass)
		take_grass(l->pkoveto, taken_grass);
	take_bike(&l->mkepek1);
	take_bike(&l->mkepek2);
	take_kiskep(l->pkiszaszlo);
	take_anim(l->pkiller);
	take_anim(l->pexit);
	for (int i = 0; i < MAXFOODSZAM; ++i) take_anim(l->foodtomb[i]);
	if (FREE_COPIES && l->pkimarad && l->pkimarad->getxsize() > 4) {
		// (Only the shrunk picture of the original showed it.)
		delete l->pkimarad;
		l->pkimarad = new pic8(4, 1);
	}
}

void gpu_lgr_loaded() {
	lgrfile* l = Plgr;
	if (!l) return;
	const uint32_t t0 = gv_clock();
	gpu_lgr_step(l);
	gv_game_mode_hook = game_mode_started;
	Glgr.lgr = l;
	for (int i = 0; i < 256; ++i) Glgr.palette[i] = vram_color(l->paltomb + 3 * i);

	// lgrfile has sorted its pictures and textures by name since:
	Glgr.npictures = l->kepszam;
	Glgr.pictures = new gpu_pic[l->kepszam ? l->kepszam : 1];
	memset(Glgr.pictures, 0, (l->kepszam ? l->kepszam : 1) * sizeof(gpu_pic));
	Glgr.ntextures = l->texturaszam;
	Glgr.textures = new gpu_pic[l->texturaszam ? l->texturaszam : 1];
	memset(Glgr.textures, 0, (l->texturaszam ? l->texturaszam : 1) * sizeof(gpu_pic));
	for (int i = 0; i < nimage; ++i) {
		image* im = &images[i];
		if (im->group == G_PICTURE) {
			const int k = l->getkepindex(im->name);
			if (k >= 0) im->out = &Glgr.pictures[k];
		} else if (im->group == G_TEXTURE) {
			const int k = l->gettexturaindex(im->name);
			if (k >= 0) im->out = &Glgr.textures[k];
		}
	}
	Glgr.nmasks = l->maszkszam;
	Glgr.masks = new gpu_mask[l->maszkszam ? l->maszkszam : 1];
	for (int i = 0; i < l->maszkszam; ++i) {
		make_mask(&l->maszkok[i], &Glgr.masks[i]);
		if (FREE_COPIES) {
			// (lgrfile's destructor wants an array there.)
			delete[] l->maszkok[i].adatok;
			l->maszkok[i].adatok = new maszkelem[1];
			l->maszkok[i].adatok[0].hossz = 0;
			l->maszkok[i].adatok[0].tipus = ME_SOREMELES;
		}
	}
	Glgr.ngrass = l->pkoveto->kepszam < MAXKOVETOKEPSZAM ? l->pkoveto->kepszam : MAXKOVETOKEPSZAM;

	const int taken = nimage;
	pack_and_upload();
	if (gv_in_game_mode()) upload_cluts();
	delete[] images;
	images = 0;
	nimage = 0;
	taking = 0;
	printf("elma: LGR in VRAM: %u cells (%d images, %d CLUTs, %d missing), %u ms\n", (unsigned)Glgr.vram_cells, taken,
	       nclut, Glgr.missing, (unsigned)((gv_clock() - t0) / (GV_CLOCK_HZ / 1000)));
}

const gpu_pic* gpu_kiskep_pic(const kiskep* k) {
	for (int i = 0; i < nkiskep; ++i)
		if (kiskeps[i].k == k) return &kiskeps[i].pic;
	return 0;
}

const gpu_anim* gpu_anim_pics(const anim* a) {
	for (int i = 0; i < nanim; ++i)
		if (anims[i].a == a) return &anims[i].pics;
	return 0;
}

uint16_t gpu_clut_id(int index) { return clut_ids[index]; }

int gpu_opaque_clut8() { return 0; }
