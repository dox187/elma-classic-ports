// The game view on the GPU, in place of KIRAJ320.CPP (kirajzol320 and its
// helpers) and the brushes of ecset.cpp. The layout, the camera, the bike's
// geometry, the objects, the map and the timer are those of the original;
// only the pixels are made differently.
//
// The view is 320x240 for the original 640x480 (gpu_video.h): one pixel is
// a 2x2 block of the original's brush pixels, the same part of the world is
// seen. The camera moves by whole blocks.
//
// Every pixel of the original is ground or sky (gpu_level.h), and the
// pictures are clipped to one of them (ground, sky or none) and covered by
// distance. The GPU's mask bit (bit 15 of a VRAM pixel; a primitive can set
// it on what it writes, and can skip pixels where it is set) tells ground
// from sky while the picture is built:
//
//   1. the ground texture over the view, setting the mask;
//   2. the far pictures (distance 500 and more) clipped to ground or not
//      clipped, farthest first, setting the mask; also over what will be
//      sky, that comes next;
//   3. the sky trapezoids flat, clearing the mask: now the mask is set on
//      ground and clear on sky;
//   4. the sky texture over the view, skipping masked pixels: only the sky;
//   5. the far pictures clipped to sky or not clipped, skipping masked
//      pixels;
//   6. the objects and the bikes (they disturb the mask under them);
//   7. the near pictures (distance under 500, the original's top brush):
//      those clipped to sky or not, where the mask is marked again under
//      the bikes and objects (a black additive pass keeps the colors and
//      sets the bit), skipping masked pixels; then the mask is turned over
//      (ground clear, sky set) where the near ground pictures are, and
//      those clipped to ground or not are drawn;
//   8. the map (view window), and, when the frame is complete, the timer,
//      whose digits take the color by the pixel under them (read back).
#include <psxgpu.h>
#include <psxgte.h>

#include "all.h"
#include "gpu/gpu_level.h"
#include "gpu/gpu_lgr.h"
#include "gpu/gpu_video.h"

// Switched by the tests (gpu_compare_test.lua) in the comparison build:
extern "C" volatile int gpu_render_soft;
volatile int gpu_render_soft = 0;
// Statistics for the tests, see gpu_draw_stats.
extern "C" struct gpu_draw_stats_s {
	uint32_t frames;
	uint32_t prims_words;   // command words of the last frame
	uint32_t traps_drawn;   // trapezoids of the last frame
	uint32_t pictures_drawn;
	uint32_t near_drawn;
	uint32_t draw_lines;    // scan lines of the last frame's building
	int32_t view_x, view_y; // the first view's bottom left brush pixel
	int32_t cam_x, cam_y;   // ... taken to an even one (the GPU view's)
	// Pixels the GPU fills in the last frame (an estimate of its time):
	uint32_t fill_textured, fill_flat, fill_blend;
	// gv_clock ticks of the last frame's parts (without the sound): finding
	// the pictures of the view, ground, far ground pictures, sky, far sky
	// pictures, objects, bikes, near pictures, map:
	uint32_t part[9];
	uint32_t sound;          // ... in hang() (the sound mixer)
	uint32_t traps_seen, traps_clipped;  // trapezoids looked at, cut by clip_x
	uint32_t prims_max;      // command words of the longest frame so far

} gpu_draw_stats;
gpu_draw_stats_s gpu_draw_stats;

#ifdef ELMA_PSX_GPU_COMPARE
void soft_kirajzol320(double t, valtozok* pvalt1, valtozok* pvalt2, int viewki1, int timeki1, int viewki2,
                      int timeki2);
#else
// What the rest of the game uses of KIRAJ320.CPP:
int Kitoltestmegrak = 0;
int Kitoltestmegrakkezd = 10;
double Hatarx1, Hatarx2, Hatary1, Hatary2;
int Cxsize = 640, Cysize = 480;

// The picture size keys (billplussz, billminusz) have no button on the pad;
// the view is always the whole picture.
void novelkepmeret(void) { Kitoltestmegrak = Kitoltestmegrakkezd; }
void csokkentkepmeret(void) { Kitoltestmegrak = Kitoltestmegrakkezd; }

void forditkepet(pic8* ppic) {
	for (int y1 = 0; y1 < ppic->getysize() / 2; y1++) {
		int y2 = ppic->getysize() - 1 - y1;
		unsigned char* sora = ppic->getptr(y1);
		unsigned char* sorb = ppic->getptr(y2);
		int xsize = ppic->getxsize();
		for (int x = 0; x < xsize; x++) {
			unsigned char tmp = sora[x];
			sora[x] = sorb[x];
			sorb[x] = tmp;
		}
	}
}
#endif

namespace {

// The statistics of the frame being built, copied to gpu_draw_stats when
// it is complete (the tests read whole frames).
gpu_draw_stats_s frame_stats;
uint32_t frame_part[9];

// hang() mixes the sound; its time is counted apart.
void hang_timed() {
	const uint32_t t0 = gv_clock();
	hang();
	frame_stats.sound += gv_clock() - t0;
}

// --- The picture's layout (KIRAJ320.CPP beallitmereteket) -------------------

const int Kepxsize = 640, Kepysize = 480;
#define SPLITKOZ (12)

int Cx1 = 0, Cy1 = 0, Cx2 = 639, Cy2 = 479, Cy1Bplayer = 0, Cy2Bplayer = 0;
int CxsizeV = 640, CysizeV = 480;
double Mo_y = 0.0, Mo_bal = 0.0, Mo_dx = 0.0;
int Viewxsize, Viewysize, Viewxorig, Viewxtolas;

void beallitmereteket(int splitscreen) {
	Cy1Bplayer = 100, Cy2Bplayer = 200;
	CxsizeV = Kepxsize;
	CysizeV = Kepysize;
	Cx1 = 0;
	Cy1 = 0;
	Cx2 = Cx1 + CxsizeV - 1;
	Cy2 = Cy1 + CysizeV - 1;
	if (splitscreen) {
		CysizeV = (Kepysize - SPLITKOZ) / 2;
		Cy1 = Kepysize - CysizeV;
		Cy2 = Kepysize - 1;
		Cy1Bplayer = 0;
		Cy2Bplayer = CysizeV - 1;
	}
	Hatarx1 = 2.0;
	Hatary1 = 2.0;
	Hatarx2 = CxsizeV - 3.0;
	Hatary2 = CysizeV - 3.0;
	Mo_bal = (Kepxsize / Arany) * 0.15 * Motornagyitas;
	if (Mo_bal > CxsizeV / Arany / 2.0) Mo_bal = CxsizeV / Arany / 2.0;
	Mo_dx = CxsizeV / Arany - 2.0 * Mo_bal;
	Mo_y = CysizeV / Arany / 2.0;
	const double illesztes = 1.0;
	Viewxsize = 140 * illesztes * sqrt(double(CysizeV) / (480.0 * illesztes));
	Viewysize = 70 * illesztes * sqrt(double(CysizeV) / (480.0 * illesztes));
	Viewxorig = 40 * illesztes * (1.0 - 0.6) / 0.4;
	Viewxtolas = CxsizeV - 2 * Viewxorig - Viewxsize;
	if (Viewxtolas < 0) {
		Viewxsize += Viewxtolas;
		Viewxtolas = 0;
	}
	if (Viewysize > CysizeV - 2) Viewysize = CysizeV - 2;
	Cxsize = CxsizeV;
	Cysize = CysizeV;
}

// --- Primitives --------------------------------------------------------------

uint16_t cur_tpage = 0xffff;
int cur_set = -1, cur_check = -1;

void stp(int set, int check) {
	if (set == cur_set && check == cur_check) return;
	DR_STP* p = gv_prim<DR_STP>();
	setDrawStp(p, set, check);
	cur_set = set;
	cur_check = check;
}

void tpage(uint16_t tp) {
	if (tp == cur_tpage) return;
	DR_TPAGE* p = gv_prim<DR_TPAGE>();
	setDrawTPage(p, 0, 0, tp);
	cur_tpage = tp;
}

// Untextured semi-transparent primitives blend by the current page's mode:
// 1 is B+F, so black keeps the picture and only the mask bit is written.
const uint16_t TPAGE_ADD = getTPage(0, 1, 0, 0);

void sprite(int x, int y, int w, int h, int u, int v, uint16_t tp, uint16_t clut) {
	frame_stats.fill_textured += w * h;
	tpage(tp);
	SPRT* s = gv_prim<SPRT>();
	setSprt(s);
	setShadeTex(s, 1);
	setRGB0(s, 128, 128, 128);
	setXY0(s, x, y);
	setUV0(s, u, v);
	setWH(s, w, h);
	s->clut = clut;
}

void tile(int x, int y, int w, int h, uint16_t color, bool mark) {
	if (w <= 0 || h <= 0) return;
	if (mark)
		frame_stats.fill_blend += w * h;
	else
		frame_stats.fill_flat += w * h;
	if (mark) tpage(TPAGE_ADD);
	TILE* t = gv_prim<TILE>();
	setTile(t);
	if (mark) {
		setRGB0(t, 0, 0, 0);
		setSemiTrans(t, 1);
	} else
		setRGB0(t, (color & 31) << 3, ((color >> 5) & 31) << 3, ((color >> 10) & 31) << 3);
	setXY0(t, x, y);
	setWH(t, w, h);
}

// --- The view being drawn ------------------------------------------------------

struct view_ctx {
	int w, h;           // display pixels (the drawing offset is its corner)
	int kx, ky;         // brush pixel of the bottom left (even)
	int cam_x, cam_top; // half-resolution brush column at x 0, row at y 0
	int cysize;         // its height in original pixels
	double fx, fy;      // (sarok - origo)*Arany - (kx, ky)
	// Brush pixels in view (with a margin):
	int bx0, by0, bx1, by1;
};
view_ctx V;

int mod(int a, int m) {
	const int r = a % m;
	return r < 0 ? r + m : r;
}

// floor(a/2) also for negative a:
inline int half(int a) { return a >> 1; }

// A tiled texture over a display rectangle; texel (u, v) at display (x, y)
// is ((x + ub) mod w, (y + vb) mod h).
void fill_texture(int x0, int y0, int x1, int y1, const gpu_pic* tex, int ub, int vb) {
	if (!tex || !tex->tiles || x0 >= x1 || y0 >= y1) return;
	const int Q = tex->w, P = tex->h;
	for (int y = y0; y < y1;) {
		const int v = mod(y + vb, P);
		int rows = P - v;
		if (rows > 256 - (v & 255)) rows = 256 - (v & 255);
		if (rows > y1 - y) rows = y1 - y;
		for (int x = x0; x < x1;) {
			const int u = mod(x + ub, Q);
			int cols = Q - u;
			if (cols > 256 - (u & 255)) cols = 256 - (u & 255);
			if (cols > x1 - x) cols = x1 - x;
			const gpu_tile* t = gpu_pic_tile(tex, u >> 8, v >> 8);
			sprite(x, y, cols, rows, t->u + (u & 255), t->v + (v & 255), t->tpage, gpu_clut_id(t->clut));
			x += cols;
		}
		y += rows;
	}
}

// A world-anchored texture over a display rectangle (gpu_lgr.h).
void fill_world(int x0, int y0, int x1, int y1, const gpu_pic* tex) {
	if (x0 < 0) x0 = 0;
	if (y0 < 0) y0 = 0;
	if (x1 > V.w) x1 = V.w;
	if (y1 > V.h) y1 = V.h;
	fill_texture(x0, y0, x1, y1, tex, V.cam_x, -1 - V.cam_top);
}

// An image with its top left corner at display (x, y).
void picture(const gpu_pic* p, int x, int y) {
	if (!p || !p->tiles) return;
	if (x >= V.w || y >= V.h || x + p->w <= 0 || y + p->h <= 0) return;
	for (int ty = 0; ty < p->tiles_y; ++ty)
		for (int tx = 0; tx < p->tiles_x; ++tx) {
			const gpu_tile* t = gpu_pic_tile(p, tx, ty);
			sprite(x + 256 * tx, y + 256 * ty, t->w1 + 1, t->h1 + 1, t->u, t->v, t->tpage, gpu_clut_id(t->clut));
		}
}

// Display position of a brush pixel's top left (half resolution):
inline int disp_x(int bx) { return half(bx) - V.cam_x; }
inline int disp_y(int by) { return V.cam_top - half(by); }

// --- The sky trapezoids ------------------------------------------------------------

uint16_t* trap_stamp = 0;
int trap_stamp_n = 0;
uint16_t stamp = 0;

struct fvec {
	int32_t x, y;  // display, 4 fraction bits
};

void emit_polygon(const fvec* v, int n, uint16_t color, bool mark) {
	if (n < 3) return;
	// (In whole pixels: the vertices are near the display, the products fit.)
	int32_t area2 = 0;
	for (int i = 0, j = n - 1; i < n; j = i++) {
		const fvec a = v[j], b = v[i];
		area2 += (a.x >> 4) * (b.y >> 4) - (b.x >> 4) * (a.y >> 4);
	}
	if (area2 < 0) area2 = -area2;
	const uint32_t area = (uint32_t)area2 >> 1;
	if (mark)
		frame_stats.fill_blend += area;
	else
		frame_stats.fill_flat += area;
	if (mark) tpage(TPAGE_ADD);
	// A fan of quads (and a triangle for an odd count):
	for (int i = 1; i + 1 < n; i += 2) {
		if (i + 2 < n) {
			POLY_F4* p = gv_prim<POLY_F4>();
			setPolyF4(p);
			// 0, i, i+2, i+1: the quad's two triangles (0,i,i+2), (i,i+2,i+1)
			setXY4(p, (v[0].x + 8) >> 4, (v[0].y + 8) >> 4, (v[i].x + 8) >> 4, (v[i].y + 8) >> 4, (v[i + 2].x + 8) >> 4,
			       (v[i + 2].y + 8) >> 4, (v[i + 1].x + 8) >> 4, (v[i + 1].y + 8) >> 4);
			if (mark) {
				setRGB0(p, 0, 0, 0);
				setSemiTrans(p, 1);
			} else
				setRGB0(p, (color & 31) << 3, ((color >> 5) & 31) << 3, ((color >> 10) & 31) << 3);
		} else {
			POLY_F3* p = gv_prim<POLY_F3>();
			setPolyF3(p);
			setXY3(p, (v[0].x + 8) >> 4, (v[0].y + 8) >> 4, (v[i].x + 8) >> 4, (v[i].y + 8) >> 4, (v[i + 1].x + 8) >> 4,
			       (v[i + 1].y + 8) >> 4);
			if (mark) {
				setRGB0(p, 0, 0, 0);
				setSemiTrans(p, 1);
			} else
				setRGB0(p, (color & 31) << 3, ((color >> 5) & 31) << 3, ((color >> 10) & 31) << 3);
		}
	}
}

// Clips a convex polygon to x0 <= x <= x1 (fixed point).
int clip_x(const fvec* in, int n, fvec* out, int32_t x0, int32_t x1) {
	fvec tmp[12];
	int m = 0;
	for (int i = 0; i < n; ++i) {
		const fvec a = in[i], b = in[i + 1 < n ? i + 1 : 0];
		const bool ain = a.x >= x0, bin = b.x >= x0;
		if (ain) tmp[m++] = a;
		if (ain != bin) {
			fvec c;
			c.x = x0;
			c.y = a.y + (int32_t)((int64_t)(b.y - a.y) * (x0 - a.x) / (b.x - a.x));
			tmp[m++] = c;
		}
	}
	int k = 0;
	for (int i = 0; i < m; ++i) {
		const fvec a = tmp[i], b = tmp[i + 1 < m ? i + 1 : 0];
		const bool ain = a.x <= x1, bin = b.x <= x1;
		if (ain) out[k++] = a;
		if (ain != bin) {
			fvec c;
			c.x = x1;
			c.y = a.y + (int32_t)((int64_t)(b.y - a.y) * (x1 - a.x) / (b.x - a.x));
			out[k++] = c;
		}
	}
	return k;
}

// (num << 16) / den for 0 <= num <= den, in 32 bits (64-bit divisions are
// library calls):
inline int32_t frac16(int32_t num, int32_t den) {
	if (den <= 0) return 0;
	while (den >= (1 << 15)) {
		num >>= 1;
		den >>= 1;
	}
	return (num << 16) / den;
}
inline int32_t lerp16(int32_t a, int32_t b, int32_t f) { return a + (int32_t)(((int64_t)(b - a) * f) >> 16); }

// A trapezoid of the view (display coordinates, 4 fraction bits) as a quad.
void emit_trap(int32_t xlt, int32_t xrt, int32_t yt, int32_t xlb, int32_t xrb, int32_t yb, uint16_t color,
               bool mark) {
	const uint32_t area = (uint32_t)(((xrt - xlt) + (xrb - xlb)) * ((yb - yt) >> 4)) >> 5;
	if (mark) {
		frame_stats.fill_blend += area;
		tpage(TPAGE_ADD);
	} else
		frame_stats.fill_flat += area;
	POLY_F4* p = gv_prim<POLY_F4>();
	setPolyF4(p);
	setXY4(p, (xlt + 8) >> 4, (yt + 8) >> 4, (xrt + 8) >> 4, (yt + 8) >> 4, (xlb + 8) >> 4, (yb + 8) >> 4,
	       (xrb + 8) >> 4, (yb + 8) >> 4);
	if (mark) {
		setRGB0(p, 0, 0, 0);
		setSemiTrans(p, 1);
	} else
		setRGB0(p, (color & 31) << 3, ((color >> 5) & 31) << 3, ((color >> 10) & 31) << 3);
}

// The sky trapezoids in the brush rectangle bx0..bx1, by0..by1 (pixels), in
// the main view: display x = brush x / 2 - kx / 2, y from the top.
void draw_traps(int bx0, int by0, int bx1, int by1, uint16_t color, bool mark, uint32_t* count) {
	if (!Glevel.ntraps || !Glevel.grid_start) return;
	if (trap_stamp_n != Glevel.ntraps) {
		delete[] trap_stamp;
		trap_stamp = new uint16_t[Glevel.ntraps];
		memset(trap_stamp, 0, Glevel.ntraps * sizeof(uint16_t));
		trap_stamp_n = Glevel.ntraps;
		stamp = 0;
	}
	if (++stamp == 0) {
		memset(trap_stamp, 0, Glevel.ntraps * sizeof(uint16_t));
		stamp = 1;
	}
	int cx0 = bx0 / GPU_TRAP_CELL, cx1 = bx1 / GPU_TRAP_CELL;
	int cy0 = by0 / GPU_TRAP_CELL, cy1 = by1 / GPU_TRAP_CELL;
	if (cx0 < 0) cx0 = 0;
	if (cy0 < 0) cy0 = 0;
	if (cx1 > Glevel.tgrid_w - 1) cx1 = Glevel.tgrid_w - 1;
	if (cy1 > Glevel.tgrid_h - 1) cy1 = Glevel.tgrid_h - 1;
	// Brush (4 fraction bits) to display (4 fraction bits): x / 2 + ox,
	// oy - y / 2.
	const int32_t ox = -V.kx * 8, oy = (V.ky + V.cysize) * 8;
	const int32_t bx0q = bx0 << 4, bx1q = bx1 << 4, by0q = by0 << 4, by1q = by1 << 4;
	const int dw = V.w, dh = V.h;
	const int32_t yclip1 = dh * 16;
	// Beyond these the GPU could not take the coordinates; nearer it clips:
	const int32_t far_lo = -256 * 16, far_hi_x = (dw + 256) * 16, far_hi_y = (dh + 256) * 16;
	for (int cy = cy0; cy <= cy1; ++cy)
		for (int cx = cx0; cx <= cx1; ++cx) {
			const int c = cy * Glevel.tgrid_w + cx;
			for (uint32_t k = Glevel.grid_start[c]; k < Glevel.grid_start[c + 1]; ++k) {
				const int ti = Glevel.grid_items[k];
				if (trap_stamp[ti] == stamp) continue;
				trap_stamp[ti] = stamp;
				frame_stats.traps_seen++;
				const gpu_trap* t = &Glevel.traps[ti];
				if (t->y1 < by0q || t->y0 > by1q) continue;
				const int32_t xmin = t->xl0 < t->xl1 ? t->xl0 : t->xl1;
				const int32_t xmax = t->xr0 > t->xr1 ? t->xr0 : t->xr1;
				if (xmax < bx0q || xmin > bx1q) continue;
				// Display y of the bottom and the top (the top is smaller):
				int32_t yb = oy - (t->y0 >> 1), yt = oy - (t->y1 >> 1);
				// No row of pixels in the view (the GPU draws rows from the
				// rounded top to the rounded bottom, exclusive):
				if (((yt < 0 ? 0 : yt) + 8) >> 4 >= ((yb > yclip1 ? yclip1 : yb) + 8) >> 4) continue;
				int32_t xlt = t->xl1, xrt = t->xr1, xlb = t->xl0, xrb = t->xr0;
				if (yt < far_lo || yb > far_hi_y) {
					// Cut to the view's rows:
					const int32_t ya = yt < 0 ? 0 : yt, yz = yb > yclip1 ? yclip1 : yb;
					if (ya != yt) {
						const int32_t f = frac16(yb - ya, yb - yt);
						xlt = lerp16(t->xl0, t->xl1, f);
						xrt = lerp16(t->xr0, t->xr1, f);
					}
					if (yz != yb) {
						const int32_t f = frac16(yb - yz, yb - yt);
						xlb = lerp16(t->xl0, t->xl1, f);
						xrb = lerp16(t->xr0, t->xr1, f);
					}
					yt = ya;
					yb = yz;
				}
				xlt = ox + (xlt >> 1);
				xrt = ox + (xrt >> 1);
				xlb = ox + (xlb >> 1);
				xrb = ox + (xrb >> 1);
				const int32_t lo = xlt < xlb ? xlt : xlb, hi = xrt > xrb ? xrt : xrb;
				if (hi < 0 || lo > dw * 16) continue;
				if (lo < far_lo || hi > far_hi_x) {
					fvec q[4] = {{xlt, yt}, {xrt, yt}, {xrb, yb}, {xlb, yb}};
					fvec out[12];
					const int n = clip_x(q, 4, out, 0, dw * 16);
					frame_stats.traps_clipped++;
					emit_polygon(out, n, color, mark);
				} else
					emit_trap(xlt, xrt, yt, xlb, xrb, yb, color, mark);
				if (count) (*count)++;
			}
		}
}

// The sky trapezoids under a display rectangle of the main view.
void draw_sky_traps(int x0, int y0, int x1, int y1, uint16_t color, bool mark) {
	// Brush rectangle of the display rectangle:
	const int bx0 = V.kx + 2 * x0 - 2, bx1 = V.kx + 2 * x1 + 2;
	const int by0 = V.ky + V.cysize - 2 * y1 - 2, by1 = V.ky + V.cysize - 2 * y0 + 2;
	draw_traps(bx0, by0, bx1, by1, color, mark, mark ? 0 : &frame_stats.traps_drawn);
}

// --- Pictures, masks, grass ----------------------------------------------------------

struct bbox {
	int x0, y0, x1, y1;  // display, exclusive end; empty if x0 >= x1
};

void bbox_add(bbox* b, int x0, int y0, int x1, int y1) {
	if (x0 < 0) x0 = 0;
	if (y0 < 0) y0 = 0;
	if (x1 > V.w) x1 = V.w;
	if (y1 > V.h) y1 = V.h;
	if (x0 >= x1 || y0 >= y1) return;
	if (b->x0 >= b->x1) {
		b->x0 = x0, b->y0 = y0, b->x1 = x1, b->y1 = y1;
		return;
	}
	if (x0 < b->x0) b->x0 = x0;
	if (y0 < b->y0) b->y0 = y0;
	if (x1 > b->x1) b->x1 = x1;
	if (y1 > b->y1) b->y1 = y1;
}

// The display rectangle of an instance (a little larger).
void inst_rect(const gpu_inst* in, int* x, int* y, int* w, int* h) {
	*x = disp_x(in->x);
	*y = disp_y(in->y);
	*w = (in->w + 1) / 2 + 1;
	*h = (in->h + 1) / 2 + 1;
}

// The instances of the view, for each drawing list in its order:
const int MAX_VISIBLE = 1024;
uint16_t vis[4][MAX_VISIBLE];
int nvis[4];
// A bit for every instance (they are in drawing order), set for those in
// the view:
uint32_t* inst_bits = 0;
int inst_words = 0;

void collect_visible() {
	for (int l = 0; l < 4; ++l) nvis[l] = 0;
	if (!Glevel.ninst || !Glevel.inst_start) return;
	const int words = (Glevel.ninst + 31) >> 5;
	if (inst_words != words) {
		delete[] inst_bits;
		inst_bits = new uint32_t[words];
		inst_words = words;
	}
	memset(inst_bits, 0, words * sizeof(uint32_t));
	int cx0 = V.bx0 / GPU_GRID_CELL, cx1 = V.bx1 / GPU_GRID_CELL;
	int cy0 = V.by0 / GPU_GRID_CELL, cy1 = V.by1 / GPU_GRID_CELL;
	if (cx0 < 0) cx0 = 0;
	if (cy0 < 0) cy0 = 0;
	if (cx1 > Glevel.grid_w - 1) cx1 = Glevel.grid_w - 1;
	if (cy1 > Glevel.grid_h - 1) cy1 = Glevel.grid_h - 1;
	int wmin = words, wmax = -1;
	for (int cy = cy0; cy <= cy1; ++cy)
		for (int cx = cx0; cx <= cx1; ++cx) {
			const int c = cy * Glevel.grid_w + cx;
			for (uint32_t k = Glevel.inst_start[c]; k < Glevel.inst_start[c + 1]; ++k) {
				const int i = Glevel.inst_items[k];
				const gpu_inst* in = gpu_instance(i);
				// Brush rectangle: columns x..x+w-1, rows y-h+1..y.
				if (in->x > V.bx1 || in->x + in->w < V.bx0 || in->y < V.by0 || in->y - in->h > V.by1) continue;
				inst_bits[i >> 5] |= 1u << (i & 31);
				if ((i >> 5) < wmin) wmin = i >> 5;
				if ((i >> 5) > wmax) wmax = i >> 5;
			}
		}
	// In drawing order; the ground lists take those not clipped to the sky,
	// the sky lists those not clipped to the ground:
	for (int w = wmin; w <= wmax; ++w) {
		uint32_t bits = inst_bits[w];
		while (bits) {
			const int b = __builtin_ctz(bits);
			bits &= bits - 1;
			const int i = (w << 5) + b;
			const gpu_inst* in = gpu_instance(i);
			const int near = in->distance < 500 ? 2 : 0;
			if (in->clip != GI_CLIP_SKY && nvis[GL_FAR_GROUND + near] < MAX_VISIBLE)
				vis[GL_FAR_GROUND + near][nvis[GL_FAR_GROUND + near]++] = (uint16_t)i;
			if (in->clip != GI_CLIP_GROUND && nvis[GL_FAR_SKY + near] < MAX_VISIBLE)
				vis[GL_FAR_SKY + near][nvis[GL_FAR_SKY + near]++] = (uint16_t)i;
		}
	}
}

void draw_list(int l, bbox* used, uint32_t* count) {
	for (int i = 0; i < nvis[l]; ++i) {
		const gpu_inst* in = gpu_instance(vis[l][i]);
		const int bx = (in->x >> 1) - V.cam_x, by = V.cam_top - (in->y >> 1);
		int s = in->sprite0;
		const gpu_wsprite* sp = gpu_sprite(s);
		int left = GPU_SPRITE_CHUNK - (s & (GPU_SPRITE_CHUNK - 1));
		for (int k = 0; k < in->nsprites; ++k, ++s, ++sp, --left) {
			if (!left) {
				sp = gpu_sprite(s);
				left = GPU_SPRITE_CHUNK;
			}
			const int x = bx + sp->dx, y = by - sp->dy;
			const int w = sp->w1 + 1, h = sp->h1 + 1;
			if (x >= V.w || y >= V.h || x + w <= 0 || y + h <= 0) continue;
			sprite(x, y, w, h, sp->u, sp->v, sp->tpage, sp->clut);
		}
		if (used) {
			int x, y, w, h;
			inst_rect(in, &x, &y, &w, &h);
			bbox_add(used, x, y, x + w, y + h);
		}
		if (count) (*count)++;
	}
}

// --- The bike (kibike, dobozki) --------------------------------------------------
//
// The geometry of KIRAJ320.CPP, computed in fixed point: in software floating
// point the original's doubles took about 20 ms a frame. Points and vectors
// are original picture pixels (Arany a meter) from the view's bottom left,
// y upwards, with 12 fraction bits; directions are vectors of length 4096;
// angles are in the units of isin/icos: 4096 a turn (the SDK's header says
// 131072, but its code takes the angle modulo 4096).

struct fv {
	int32_t x, y;
};
inline fv mkfv(int32_t x, int32_t y) {
	fv r;
	r.x = x;
	r.y = y;
	return r;
}
inline fv operator+(fv a, fv b) { return mkfv(a.x + b.x, a.y + b.y); }
inline fv operator-(fv a, fv b) { return mkfv(a.x - b.x, a.y - b.y); }
// a * k / 4096:
inline int32_t mul12(int32_t a, int32_t k) { return (int32_t)(((int64_t)a * k) >> 12); }
inline fv operator*(fv a, int32_t k) { return mkfv(mul12(a.x, k), mul12(a.y, k)); }
inline int32_t dot12(fv a, fv b) { return (int32_t)(((int64_t)a.x * b.x + (int64_t)a.y * b.y) >> 12); }
inline fv rot90(fv a) { return mkfv(-a.y, a.x); }   // forgatas90fokkal
inline fv rotm90(fv a) { return mkfv(a.y, -a.x); }  // forgatasminusz90fokkal

uint32_t isqrt32(uint32_t v) {
	uint32_t r = 0, bit = 1u << 30;
	while (bit > v) bit >>= 2;
	while (bit) {
		if (v >= r + bit) {
			v -= r + bit;
			r = (r >> 1) + bit;
		} else
			r >>= 1;
		bit >>= 2;
	}
	return r;
}

uint32_t isqrt64(uint64_t v) {
	if (!(v >> 32)) return isqrt32((uint32_t)v);
	uint64_t r = 0, bit = (uint64_t)1 << 62;
	while (bit > v) bit >>= 2;
	while (bit) {
		if (v >= r + bit) {
			v -= r + bit;
			r = (r >> 1) + bit;
		} else
			r >>= 1;
		bit >>= 2;
	}
	return (uint32_t)r;
}

int32_t len12(fv a) { return (int32_t)isqrt64((uint64_t)((int64_t)a.x * a.x + (int64_t)a.y * a.y)); }

// a * 4096 / l (l > 0), in 32 bits:
fv div12(fv a, int32_t l) {
	int s = 0;
	while ((l >> s) >= (1 << 18)) ++s;
	const int32_t ls = l >> s;
	if (ls <= 0) return mkfv(4096, 0);
	return mkfv(((a.x >> s) << 12) / ls, ((a.y >> s) << 12) / ls);
}

// egys:
fv unit12(fv a) {
	const int32_t l = len12(a);
	return l > 0 ? div12(a, l) : mkfv(4096, 0);
}

// A vector turned by an angle (vekt2::forgatas):
fv turned(fv a, int32_t angle) {
	const int32_t s = isin(angle), c = icos(angle);
	return mkfv(mul12(a.x, c) - mul12(a.y, s), mul12(a.x, s) + mul12(a.y, c));
}

// Radians to isin/icos units:
int32_t angle_units(double a) {
	return (int32_t)((int64_t)(a * (4096.0 / (2.0 * 3.14159265358979323846))) & 4095);
}

// The lengths of the bike's drawing in pixels, made again when Arany (or
// the radii) change.
struct bike_consts {
	double arany, kerek, fej;
	double a12;   // Arany * 4096
	int32_t kerekrajz, fejsugar;
	int32_t m03, m05, m06, m076, m08, m10, m11, m14, m20, m21;
	int32_t comb, labszar, alkar, felkar;
	int32_t mi_c, mi_s;  // mmeret*cos(malfa), mmeret*sin(malfa) in pixels, 20 fraction bits
};
bike_consts BK = {-1, -1, -1};

int32_t bk_px(double m) { return (int32_t)floor(m * Arany * 4096.0 + 0.5); }

void bike_consts_update() {
	if (BK.arany == Arany && BK.kerek == Kerekrajzsugar && BK.fej == Fejsugar) return;
	BK.arany = Arany;
	BK.kerek = Kerekrajzsugar;
	BK.fej = Fejsugar;
	BK.a12 = Arany * 4096.0;
	BK.kerekrajz = bk_px(Kerekrajzsugar);
	BK.fejsugar = bk_px(Fejsugar);
	BK.m03 = bk_px(0.03);
	BK.m05 = bk_px(0.05);
	BK.m06 = bk_px(0.06);
	BK.m076 = bk_px(0.076);
	BK.m08 = bk_px(0.08);
	BK.m10 = bk_px(0.1);
	BK.m11 = bk_px(0.11);
	BK.m14 = bk_px(0.14);
	BK.m20 = bk_px(0.2);
	BK.m21 = bk_px(0.21);
	BK.comb = BK.labszar = bk_px(0.51);
	BK.alkar = bk_px(0.308 * 1.05);
	BK.felkar = bk_px(0.328 * 1.05);
	const double malfa = 0.62, mmeret = 0.0045;
	BK.mi_c = (int32_t)floor(mmeret * cos(malfa) * Arany * 1048576.0 + 0.5);
	BK.mi_s = (int32_t)floor(mmeret * sin(malfa) * Arany * 1048576.0 + 0.5);
}

// A point relative to the view's corner:
inline fv rel(const vekt2& p, const vekt2& sarok) {
	return mkfv((int32_t)((p.x - sarok.x) * BK.a12), (int32_t)((p.y - sarok.y) * BK.a12));
}

// Affinitas of doboz.cpp (the bike squeezed while it turns):
int Affin = 0;
int32_t Affin_k = 0;  // (1 - Affinnagysag) * 4096
fv Affinkozep, Affinirany;

// The display rectangle of the bike and objects drawn (the near pictures'
// mask is restored under it), and where the view is: the point (x, y) of
// the bike's coordinates is at display x (x + Fx12) / 8192, y (Cy12 - y) / 8192.
bbox drawn_bbox;
int32_t Fx12, Cy12;

// dobozki: the parallelogram r, r+u, r+v, r+u+v textured with the bike part.
void box(const kiskep* pk, fv u, fv v, fv r) {
	const gpu_pic* pic = gpu_kiskep_pic(pk);
	if (!pic || !pic->tiles) return;
	if (Affin) {
		r = r - Affinirany * mul12(dot12(r - Affinkozep, Affinirany), Affin_k);
		u = u - Affinirany * mul12(dot12(u, Affinirany), Affin_k);
		v = v - Affinirany * mul12(dot12(v, Affinirany), Affin_k);
	}
	const fv p[4] = {r, r + u, r + v, r + u + v};
	int16_t xs[4], ys[4];
	int x0 = 10000, y0 = 10000, x1 = -10000, y1 = -10000;
	for (int i = 0; i < 4; ++i) {
		// floor(X/2 + 0.5) of the original pixel X:
		const int xi = (p[i].x + Fx12 + 4096) >> 13;
		const int yi = (Cy12 - p[i].y + 4096) >> 13;
		if (xi < -1000 || xi > 1000 || yi < -1000 || yi > 1000) return;
		xs[i] = (int16_t)xi;
		ys[i] = (int16_t)yi;
		if (xi < x0) x0 = xi;
		if (xi > x1) x1 = xi;
		if (yi < y0) y0 = yi;
		if (yi > y1) y1 = yi;
	}
	if (x1 < 0 || y1 < 0 || x0 >= V.w || y0 >= V.h) return;
	bbox_add(&drawn_bbox, x0, y0, x1 + 1, y1 + 1);
	{
		const int64_t area = ((int64_t)u.x * v.y - (int64_t)u.y * v.x) >> 26;
		frame_stats.fill_textured += (uint32_t)(area < 0 ? -area : area);
	}
	const gpu_tile* t = gpu_pic_tile(pic, 0, 0);
	const int uw = t->w1 + 1, vh = t->h1 + 1;
	POLY_FT4* q = gv_prim<POLY_FT4>();
	setPolyFT4(q);
	setShadeTex(q, 1);
	setRGB0(q, 128, 128, 128);
	setXY4(q, xs[0], ys[0], xs[1], ys[1], xs[2], ys[2], xs[3], ys[3]);
	setUV4(q, t->u, t->v, t->u + uw - 1, t->v, t->u, t->v + vh - 1, t->u + uw - 1, t->v + vh - 1);
	q->tpage = t->tpage;
	q->clut = gpu_clut_id(t->clut);
	cur_tpage = 0xffff;  // a textured polygon sets the page too
}

void kidoboz(fv a, fv b, int32_t szelesseg, const kiskep* pk, int32_t tulloga, int32_t tullogb, int tukor = 0) {
	const fv vegys = unit12(b - a);
	b = b + vegys * tullogb;
	a = a - vegys * tulloga;
	const fv v = b - a;
	const fv v2fel = (tukor ? rot90(vegys) : rotm90(vegys)) * szelesseg;
	a = a - v2fel;
	box(pk, v, mkfv(v2fel.x * 2, v2fel.y * 2), a);
}

void kidobozkerek(fv r, int32_t sugar, int32_t alfa, const kiskep* pk, int tukor = 0) {
	const fv vfel = mkfv(mul12(icos(alfa), sugar), mul12(isin(alfa), sugar));
	if (tukor)
		kidoboz(r + vfel, r - vfel, sugar, pk, 0, 0, tukor);
	else
		kidoboz(r - vfel, r + vfel, sugar, pk, 0, 0, tukor);
}

// ketkormetszete (VEKT2.CPP): where two circles meet.
fv ketkormetszete(fv r1, fv r2, int32_t l1, int32_t l2) {
	const fv v = r2 - r1;
	int32_t l = len12(v);
	if (l >= l1 + l2) l = l1 + l2 - 1;
	if (l1 >= l + l2) l1 = l + l2 - 2;
	if (l2 >= l + l1) l2 = l + l1 - 2;
	if (l < 16) l = 16;
	const fv vegys = div12(v, l);
	const fv normal = rot90(vegys);
	// In pixels with 8 fraction bits, so that the squares fit in 32 bits:
	const int32_t a = l1 >> 4, b = l2 >> 4, c = l >> 4;
	const int32_t x = (a * a - b * b + c * c) / (2 * c);
	const int32_t mm = a * a - x * x;
	const int32_t m = mm > 0 ? (int32_t)isqrt32((uint32_t)mm) : 0;
	return r1 + vegys * (x << 4) + normal * (m << 4);
}

// The bike's picture units (KIRAJ320.CPP: Mi, Mj with Mx, My), pixels with
// 20 fraction bits a unit, and the bike's center:
fv Mi, Mj, Mr;
const int Mx = 390, My = 420;

// Mi * n + Mj * m + Mr:
fv mpoint(int n, int m) {
	return mkfv((int32_t)(((int64_t)Mi.x * n + (int64_t)Mj.x * m) >> 8) + Mr.x,
	            (int32_t)(((int64_t)Mi.y * n + (int64_t)Mj.y * m) >> 8) + Mr.y);
}
fv mvec(fv m, int n) { return mkfv((int32_t)(((int64_t)m.x * n) >> 8), (int32_t)(((int64_t)m.y * n) >> 8)); }

void kitag(const kiskep* pk, kisbox* pb) {
	const fv r = mpoint(pb->x1 + 260 - Mx, My - (pb->y1 + 260));
	box(pk, mvec(Mi, pb->x2 - pb->x1), mvec(Mj, pb->y1 - pb->y2), r);
}

void kibike(int ajatekos, double t, vekt2 sarok, motorst* pmot, valtozok* pvalt, motkepek* pmk) {
	bike_consts_update();
	double ugrasnagysag = pvalt->ugrasnagysag;
	const double forgas_d = pvalt->baljobbv_f.forgas;
	int vanforgas = 0;
	int32_t forgas = 4096;
	Affin = 0;
	if (forgas_d < 0.999) {
		vanforgas = 1;
		// -cos(forgas * pi):
		forgas = -icos((int32_t)(forgas_d * 2048.0));
	}
	fv p_k1 = rel(pmot->kor2.r, sarok);
	fv p_k2 = rel(pmot->kor4.r, sarok);
	int elsokerekrogton = 1;
	int hatsokerekrogton = 1;
	if (vanforgas) {
		if ((forgas > 0 && !pmot->hatra_f) || (forgas <= 0 && pmot->hatra_f))
			elsokerekrogton = 0;
		else
			hatsokerekrogton = 0;
	}
	if (elsokerekrogton) kidobozkerek(p_k1, BK.kerekrajz, angle_units(pmot->kor2.alfa), pmk->pkiskerek);
	if (hatsokerekrogton) kidobozkerek(p_k2, BK.kerekrajz, angle_units(pmot->kor4.alfa), pmk->pkiskerek);

	const fv kozep = rel(pmot->kor1.r, sarok);
	const int32_t alfa1 = angle_units(pmot->kor1.alfa);
	fv jobbra = mkfv(icos(alfa1), isin(alfa1));
	const fv fel = rot90(jobbra);
	if (vanforgas) {
		// setaffinitas( kozep, jobbra, forgas, Arany, Arany ):
		Affin = 1;
		Affinkozep = kozep;
		Affinirany = jobbra;
		Affin_k = 4096 - forgas;
	}
	if (pmot->hatra_f) {
		jobbra = mkfv(-jobbra.x, -jobbra.y);
		const fv tmpv = p_k1;
		p_k1 = p_k2;
		p_k2 = tmpv;
	}
	// Mi = jobbra*(mmeret*cos(malfa)) + fel*(mmeret*sin(malfa)):
	Mi = mkfv((int32_t)(((int64_t)jobbra.x * BK.mi_c + (int64_t)fel.x * BK.mi_s) >> 12),
	          (int32_t)(((int64_t)jobbra.y * BK.mi_c + (int64_t)fel.y * BK.mi_s) >> 12));
	Mj = rot90(Mi);
	if (pmot->hatra_f) Mj = mkfv(-Mj.x, -Mj.y);
	Mr = kozep;

	const fv p_fogantyu = mpoint(365 - Mx, My - 292);
	kidoboz(p_k1, p_fogantyu, BK.m06, pmk->pkiselsorud, BK.m05, BK.m03);
	const fv p_darab2 = mpoint(370 - Mx, My - 520);
	kidoboz(p_darab2, p_k2, BK.m06, pmk->pkishatsorud, 0, BK.m10);

	int flages = 0;
	if (!Single && Tag) {
		if ((ajatekos && Aafogo) || (!ajatekos && !Aafogo)) flages = 1;
		if (!flages && Kozelvannak) {
			int egeszido = t * 30.0;
			if (egeszido % 2) flages = 1;
		}
	}
	if (flages) {
		const fv zaszlotalp = mpoint(500 + 107 - Mx, My + 114 - 600);
		// + (Mi*356 + Mj*500)*0.2:
		const fv mi712 = mvec(Mi, 712);
		const fv zaszloteto = zaszlotalp + mkfv(mi712.x / 10, mi712.y / 10) + mvec(Mj, 100);
		kidoboz(zaszlotalp, zaszloteto, BK.m20, Plgr->pkiszaszlo, 0, 0, pmot->hatra_f);
	}

	kitag(pmk->pkisa, &KisboxA);
	kitag(pmk->pkisb, &KisboxB);
	kitag(pmk->pkisc, &KisboxC);
	kitag(pmk->pkisd, &KisboxD);

	const fv p_vezeto = rel(pmot->vezetor, sarok);
	const fv p_csipo = p_vezeto + mvec(Mi, 75) + mvec(Mj, -47);
	const fv p_vall = p_vezeto + mvec(Mi, 47) + mvec(Mj, 65);
	const fv p_valltest = p_vezeto + mvec(Mi, 41) + mvec(Mj, 70);
	const fv p_labfej = mpoint(346 - Mx, My - 514);
	fv p_terd;
	if (pmot->hatra_f)
		p_terd = ketkormetszete(p_csipo, p_labfej, BK.comb, BK.labszar);
	else
		p_terd = ketkormetszete(p_labfej, p_csipo, BK.labszar, BK.comb);

	kidobozkerek(rel(pmot->fejr, sarok), BK.fejsugar, alfa1, pmk->pkisfej, pmot->hatra_f);

	fv p_kezfej = p_fogantyu;
	if (ugrasnagysag > 0.0001) {
		ugrasnagysag = 1.0 - ugrasnagysag;
		int fellendit = 1;
		if ((pvalt->ugras1volt && !pmot->hatra_f) || (!pvalt->ugras1volt && pmot->hatra_f)) fellendit = 0;
		double alfa = 0.0;
		double hosszit = 0.1;
		if (fellendit) {
			double hatar = 0.25;
			double maxalfa = 2.7;
			double maxhosszit = -0.3;
			if (ugrasnagysag < hatar) {
				alfa = maxalfa * ugrasnagysag / hatar;
				hosszit = maxhosszit * ugrasnagysag / hatar + 1.0;
			} else {
				double mertek = 1.0 - (ugrasnagysag - hatar) / (1.0 - hatar);
				alfa = maxalfa * mertek;
				hosszit = maxhosszit * mertek + 1.0;
			}
		} else {
			double hatar = 0.2;
			double maxalfa = -1.6;
			double maxhosszit = 0.15;
			if (ugrasnagysag < hatar) {
				alfa = maxalfa * ugrasnagysag / hatar;
				hosszit = maxhosszit * ugrasnagysag / hatar + 1.0;
			} else {
				double mertek = 1.0 - (ugrasnagysag - hatar) / (1.0 - hatar);
				alfa = maxalfa * mertek;
				hosszit = maxhosszit * mertek + 1.0;
			}
		}
		fv kar = p_kezfej - p_vall;
		kar = turned(kar, angle_units(pmot->hatra_f ? alfa : -alfa));
		kar = kar * (int32_t)(hosszit * 4096.0);
		p_kezfej = p_vall + kar;
	}

	fv p_konyok;
	if (pmot->hatra_f)
		p_konyok = ketkormetszete(p_kezfej, p_vall, BK.alkar, BK.felkar);
	else
		p_konyok = ketkormetszete(p_vall, p_kezfej, BK.felkar, BK.alkar);

	kidoboz(p_terd, p_csipo, BK.m14, pmk->pkiscomb, BK.m03, BK.m10, pmot->hatra_f);
	kidoboz(p_labfej, p_terd, BK.m21, pmk->pkislabszar, BK.m03, BK.m03, pmot->hatra_f);
	kidoboz(p_csipo, p_valltest, BK.m20, pmk->pkisvezeto, BK.m10, BK.m05, pmot->hatra_f);
	kidoboz(p_konyok, p_vall, BK.m11, pmk->pkisfelkar, BK.m08, BK.m10, !pmot->hatra_f);
	kidoboz(p_kezfej, p_konyok, BK.m076, pmk->pkisalkar, BK.m08, BK.m10, pmot->hatra_f);
	Affin = 0;

	if (!elsokerekrogton || !hatsokerekrogton) {
		if (pmot->hatra_f) {
			const fv tmpv = p_k1;
			p_k1 = p_k2;
			p_k2 = tmpv;
		}
		if (!elsokerekrogton) kidobozkerek(p_k1, bk_px(pmot->kor2.sugar), angle_units(pmot->kor2.alfa), pmk->pkiskerek);
		if (!hatsokerekrogton) kidobozkerek(p_k2, bk_px(pmot->kor4.sugar), angle_units(pmot->kor4.alfa), pmk->pkiskerek);
	}
}

// --- Objects -----------------------------------------------------------------------

void draw_objects(double t, int balalsox, int balalsoy) {
	const int objminx = balalsox - 2 * Plgr->objektumsugar - 2;
	const int objminy = balalsoy - 2 * Plgr->objektumsugar - 2;
	const int objmaxx = balalsox + Kepxsize;
	const int objmaxy = balalsoy + Kepysize;
	for (int i = 0; i < MAXKEREK; i++) {
		kerek* pker = Ptop->kerektomb[i];
		if (!pker) break;
		if (pker->tipus == T_KEZDO || (pker->tipus == T_KAJA && !pker->aktiv) || (!Single && Tag && pker->tipus == T_CEL))
			continue;
		if (pker->rxint < objminx || pker->ryint < objminy || pker->rxint > objmaxx || pker->ryint > objmaxy) continue;
		const anim* a = 0;
		int dy = 0;
		switch (pker->tipus) {
		case T_KAJA:
			a = Plgr->foodtomb[pker->foodsorszam % Plgr->foodszam];
			if (State->animatedobjects) dy = Plgr->objektumlebeges * sin(t * 15.5 + pker->sinfazis);
			break;
		case T_CEL:
			a = Plgr->pexit;
			if (State->animatedobjects) dy = Plgr->objektumlebeges * sin(t * 15.5 + pker->sinfazis);
			break;
		case T_HALALOS:
			a = Plgr->pkiller;
			break;
		default:
			continue;
		}
		const gpu_anim* g = gpu_anim_pics(a);
		if (!g || g->nframes <= 0) continue;
		int frame = 0;
		if (State->animatedobjects) frame = (int)(t / 0.014) % g->nframes;
		const gpu_pic* p = &g->frames[frame];
		// Bottom left at brush (rxint, ryint + dy), the frame is objektummeret high:
		const int top = pker->ryint + dy + Plgr->objektummeret - 1;
		const int x = disp_x(pker->rxint), y = disp_y(top);
		picture(p, x, y);
		bbox_add(&drawn_bbox, x, y, x + p->w, y + p->h);
	}
}

// --- The map (kiview) -------------------------------------------------------------

uint16_t pal(int index) { return Glgr.palette[index & 255]; }

// A ring of kigyuru (3x3 pixels of the original) at original picture
// coordinates (x, y from the bottom of the view).
void ring(int x, int y, uint16_t color) {
	const int dx0 = half(x - 1), dx1 = half(x + 1);
	const int dy0 = half(V.cysize - 1 - (y + 1)), dy1 = half(V.cysize - 1 - (y - 1));
	tile(dx0, dy0, dx1 - dx0 + 1, dy1 - dy0 + 1, color, false);
}

DR_AREA* push_area(int x0, int y0, int x1, int y1, int fb_x, int fb_y) {
	DR_AREA* a = gv_prim<DR_AREA>();
	setDrawAreaXY(a, fb_x + x0, fb_y + y0, fb_x + x1, fb_y + y1);
	return a;
}

int Fb_x = 0, Fb_y = 0;
int View_x = 0, View_y = 0;  // the view's corner in the frame buffer

void kiview(int ajatekos, double baljobb, vekt2 motorkozep, motorst* pmot2) {
	double Viewxsize_d = Viewxsize * Viewzoom * Aranyalaprec;
	double Viewysize_d = Viewysize * Viewzoom * Aranyalaprec;
	double szeltoltav = 0.2;
	double atfuthossz = 1.0 - 2.0 * szeltoltav;
	vekt2 sarokbolkozepre(Viewxsize_d * (szeltoltav + baljobb * atfuthossz), Viewysize_d / 2);
	vekt2 sarok = motorkozep - sarokbolkozepre;
	int vx1 = Viewxorig + baljobb * Viewxtolas;
	int vx2 = vx1 + Viewxsize - 1;
	int vy1 = 1;
	int vy2 = vy1 + Viewysize - 1;
	const double k = Aranyalap / Viewzoom;  // map pixels a meter

	// The map's rectangle in display pixels:
	const int dx0 = half(vx1), dx1 = half(vx2 + 1);
	const int dy0 = half(V.cysize - 1 - vy2), dy1 = half(V.cysize - 1 - vy1);
	DR_AREA* a = push_area(View_x + dx0, View_y + dy0, View_x + dx1, View_y + dy1, Fb_x, Fb_y);
	(void)a;
	stp(0, 0);
	tile(dx0, dy0, dx1 - dx0 + 1, dy1 - dy0 + 1, pal(Plgr->viewfoldsor[0]), false);
	// The sky, from the runs of the map's display pixels (gpu_level.h): the
	// center of column i, row j is at map pixel (mx + 2i + 1, my + 2j + 1).
	const double mx = (Glevel.origo_x - sarok.x) * k + vx1;  // map x of brush x 0
	const double my = (Glevel.origo_y - sarok.y) * k + vy1;
	if (Glevel.map_rows) {
		const int ox = (int)floor(mx * 0.5 + 0.5), oy = (int)floor((V.cysize - my) * 0.5 - 0.5);
		const uint16_t sky = pal(Plgr->viewegsor[0]);
		int j0 = oy - dy1, j1 = oy - dy0;
		if (j0 < 0) j0 = 0;
		if (j1 > Glevel.map_rows - 1) j1 = Glevel.map_rows - 1;
		const int c0 = dx0 - ox, c1 = dx1 - ox;  // the columns shown
		const int16_t* runs = Glevel.map_runs;
		for (int j = j0; j <= j1; ++j) {
			// The first run that ends after c0:
			uint32_t lo = Glevel.map_row_start[j], hi = Glevel.map_row_start[j + 1];
			while (lo < hi) {
				const uint32_t mid = (lo + hi) >> 1;
				if (runs[2 * mid + 1] <= c0)
					lo = mid + 1;
				else
					hi = mid;
			}
			const uint32_t end = Glevel.map_row_start[j + 1];
			for (uint32_t r = lo; r < end && runs[2 * r] <= c1; ++r) {
				const int x0 = runs[2 * r] > c0 ? runs[2 * r] : c0;
				const int x1 = runs[2 * r + 1] < c1 + 1 ? runs[2 * r + 1] : c1 + 1;
				tile(x0 + ox, oy - j, x1 - x0, 1, sky, false);
			}
		}
	}

	// Objects: killers (in the original's map brush), food and the exit:
	for (int i = 0; i < MAXKEREK; i++) {
		kerek* pker = Ptop->kerektomb[i];
		if (!pker) break;
		unsigned char color;
		if (pker->tipus == T_HALALOS)
			color = Plgr->viewkiller[0];
		else if (pker->tipus == T_KAJA && pker->aktiv)
			color = Plgr->viewfood;
		else if ((Single || !Tag) && pker->tipus == T_CEL)
			color = Plgr->viewexit[0];
		else
			continue;
		// (The wheels are upside down while playing.)
		const double py = Ptop->kerekekfejjellefele ? pker->r.y : -pker->r.y;
		const int qx = (int)((pker->r.x - sarok.x) * k) + vx1;
		const int qy = (int)((py - sarok.y) * k) + vy1;
		if (qx < vx1 || qx > vx2 || qy < vy1 || qy > vy2) continue;
		ring(qx, qy, pal(color));
	}

	unsigned char viewindex1 = Plgr->viewmotorindex1;
	unsigned char viewindex2 = Plgr->viewmotorindex2;
	if ((State->aplayerabike && !ajatekos) || (!State->aplayerabike && ajatekos)) {
		viewindex1 = Plgr->viewmotorindex2;
		viewindex2 = Plgr->viewmotorindex1;
	}
	if (pmot2) {
		vekt2 sarokrel = pmot2->kor1.r - sarok;
		int mxp = sarokrel.x * Aranyalap / Viewzoom + vx1;
		int myp = sarokrel.y * Aranyalap / Viewzoom + vy1;
		if (mxp >= vx1 && mxp <= vx2 && myp >= vy1 && myp <= vy2) ring(mxp, myp, pal(viewindex2));
	}
	int mxp = sarokbolkozepre.x * Aranyalap / Viewzoom;
	int myp = sarokbolkozepre.y * Aranyalap / Viewzoom;
	ring(vx1 + mxp, vy1 + myp, pal(viewindex1));

	// Back to the view, then the frame around the map:
	push_area(View_x, View_y, View_x + V.w - 1, View_y + V.h - 1, Fb_x, Fb_y);
	const uint16_t frame = pal(Plgr->keretindex);
	const int fx0 = half(vx1 - 1), fx1 = half(vx2 + 1);
	const int fy0 = half(V.cysize - 1 - (vy2 + 1)), fy1 = half(V.cysize - 1 - (vy1 - 1));
	tile(fx0, fy0, fx1 - fx0 + 1, 1, frame, false);
	tile(fx0, fy1, fx1 - fx0 + 1, 1, frame, false);
	tile(fx0, fy0, 1, fy1 - fy0 + 1, frame, false);
	tile(fx1, fy0, 1, fy1 - fy0 + 1, frame, false);
}

// --- The timer (kidigit), drawn when the frame is complete --------------------------

struct hud_view {
	int view_x, view_y, w, h;  // display rectangle in the frame buffer
	int cxsize, cysize;
	char time1[24], time2[24], fogo[24];
	int show;
};
struct hud_frame {
	int nviews;
	hud_view v[2];
};
hud_frame huds[2];
int hud_index = 0;

// The digits as runs of pixels in original picture coordinates (y from the
// bottom), as kiszegmens / kikettospont draw them.
struct seg_run {
	int16_t x, y, len;
	uint8_t vertical;
};
const int MAX_RUNS = 256;
seg_run runs[MAX_RUNS];
int nruns = 0;

int Vvh, Vfh, Digdx, Kozdx, Ketpx, Ketpy1, Ketpy2;

void add_run(int x, int y, int len, int vertical) {
	if (nruns == MAX_RUNS || len <= 0) return;
	runs[nruns].x = (int16_t)x;
	runs[nruns].y = (int16_t)y;
	runs[nruns].len = (int16_t)len;
	runs[nruns].vertical = (uint8_t)vertical;
	nruns++;
}

void kiszegmens(int szam, int x, int y) {
	switch (szam) {
	case 0: add_run(x, y + 1, Vfh, 1); break;
	case 1: add_run(x + Vvh + 1, y + 1, Vfh, 1); break;
	case 2: add_run(x, y + Vfh + 2, Vfh, 1); break;
	case 3: add_run(x + Vvh + 1, y + Vfh + 2, Vfh, 1); break;
	case 4: add_run(x + 1, y, Vvh, 0); break;
	case 5: add_run(x + 1, y + Vfh + 1, Vvh, 0); break;
	case 6: add_run(x + 1, y + Vfh + Vfh + 2, Vvh, 0); break;
	}
}

void kiegydigit(int c, int x, int y) {
	static const char* const segs[10] = {"401236", "13", "40536", "41536", "1523", "41526", "401526", "136", "4015236", "415236"};
	if (c < '0' || c > '9') return;
	for (const char* s = segs[c - '0']; *s; ++s) kiszegmens(*s - '0', x, y);
}

void kikettospont(int x, int y) {
	add_run(x + Ketpx, y + Ketpy1, 2, 0);
	add_run(x + Ketpx, y + Ketpy1 + 1, 2, 0);
	add_run(x + Ketpx, y + Ketpy2, 2, 0);
	add_run(x + Ketpx, y + Ketpy2 + 1, 2, 0);
}

void kiegyszam(const char* time, int x, int y) {
	kiegydigit(time[0], x, y);
	x += Digdx;
	kiegydigit(time[1], x, y);
	kikettospont(x, y);
	x += Kozdx;
	kiegydigit(time[3], x, y);
	x += Digdx;
	kiegydigit(time[4], x, y);
	kikettospont(x, y);
	x += Kozdx;
	kiegydigit(time[6], x, y);
	x += Digdx;
	kiegydigit(time[7], x, y);
}

void make_runs(const hud_view* hv) {
	nruns = 0;
	const double kepmeretx = double(hv->cxsize) / Kepxsize;
	const double kepmerety = hv->cysize / 480.0;
	const int xtav = 28 * kepmeretx;
	int x = xtav;
	const int y = 420 * kepmerety;
	Vvh = 10 * kepmerety;
	Vfh = 16 * kepmerety;
	Digdx = 16 * kepmerety;
	Kozdx = 24 * kepmerety;
	Ketpx = 17 * kepmerety;
	Ketpy1 = 9 * kepmerety;
	Ketpy2 = 23 * kepmerety;
	const int xelso = x;
	if (hv->time1[0] != 0) kiegyszam(hv->time1, xelso, y);
	x = hv->cxsize - (xtav + Digdx * 3 + Kozdx * 3);
	kiegyszam(hv->time2, x, y);
	if (hv->fogo[0]) kiegyszam(hv->fogo, (xelso + x) >> 1, y);
}

uint16_t readback[4096];
// The darkest and lightest palette colors (makenegalttomb).
uint16_t dark_color = 0, light_color = 0x7fff;

void timer_colors() {
	int light = -1, dark = 1000, li = 0, di = 0;
	const unsigned char* p = Plgr->paltomb;
	for (int i = 0; i < 256; ++i) {
		const int v = p[i * 3] + p[i * 3 + 1] + p[i * 3 + 2];
		if (light < v) light = v, li = i;
		if (dark > v) dark = v, di = i;
	}
	light_color = Glgr.palette[li];
	dark_color = Glgr.palette[di];
}

const int MAX_TIMER_TILES = 384;
struct timer_prims {
	DR_AREA area;
	DR_OFFSET offset;
	DR_STP stp;
	TILE tiles[MAX_TIMER_TILES];
};
timer_prims tprims;

// The pixels of the digits, joined into rectangles of one color while they
// follow each other in a row or a column.
struct tile_joiner {
	int n;
	void* last;
	int x, y, w, h;
	uint16_t col;
	void flush() {
		if (!w || n >= MAX_TIMER_TILES) return;
		TILE* t = &tprims.tiles[n++];
		setTile(t);
		setRGB0(t, (col & 31) << 3, ((col >> 5) & 31) << 3, ((col >> 10) & 31) << 3);
		setXY0(t, x, y);
		setWH(t, w, h);
		catPrim(last, t);
		last = t;
		w = 0;
	}
	void add(int px, int py, uint16_t c) {
		if (w && c == col) {
			if (h == 1 && py == y && px == x + w) {
				w++;
				return;
			}
			if (w == 1 && px == x && py == y - 1) {
				y--;
				h++;
				return;
			}
			if (w == 1 && px == x && py == y + h) {
				h++;
				return;
			}
		}
		flush();
		x = px, y = py, w = 1, h = 1, col = c;
	}
};

// Draws the timers into the finished frame: every pixel of a digit takes
// the lightest color where the picture under it is dark (all components
// under 20 of 63), the darkest elsewhere, as the original's lookup.
void finish_frame(int fb_x, int fb_y, void* data) {
	const hud_frame* hf = (const hud_frame*)data;
	if (!Plgr) return;
	timer_colors();
	setDrawAreaXY(&tprims.area, fb_x, fb_y, fb_x + GV_GAME_W - 1, fb_y + GV_GAME_H - 1);
	setDrawOffset(&tprims.offset, fb_x, fb_y);
	setDrawStp(&tprims.stp, 0, 0);
	catPrim(&tprims.area, &tprims.offset);
	catPrim(&tprims.offset, &tprims.stp);
	tile_joiner tj;
	tj.n = 0;
	tj.last = &tprims.stp;
	tj.w = 0;
	for (int vi = 0; vi < hf->nviews; ++vi) {
		const hud_view* hv = &hf->v[vi];
		if (!hv->show) continue;
		make_runs(hv);
		if (!nruns) continue;
		// The rectangle of the digits in display pixels:
		int x0 = 10000, y0 = 10000, x1 = -1, y1 = -1;
		for (int i = 0; i < nruns; ++i) {
			const seg_run* r = &runs[i];
			const int ax = half(r->x), bx = half(r->x + (r->vertical ? 0 : r->len - 1));
			const int ay = half(hv->cysize - 1 - (r->y + (r->vertical ? r->len - 1 : 0)));
			const int by = half(hv->cysize - 1 - r->y);
			if (ax < x0) x0 = ax;
			if (bx > x1) x1 = bx;
			if (ay < y0) y0 = ay;
			if (by > y1) y1 = by;
		}
		if (x0 < 0) x0 = 0;
		if (y0 < 0) y0 = 0;
		if (x1 > hv->w - 1) x1 = hv->w - 1;
		if (y1 > hv->h - 1) y1 = hv->h - 1;
		if (x0 > x1 || y0 > y1) continue;
		// Whole words: an even width.
		x0 &= ~1;
		if (((x1 - x0 + 1) & 1)) x1++;
		const int rw = x1 - x0 + 1;
		// Read back a band of rows at a time (StoreImage writes whole blocks
		// of 16 words):
		const int band = ((int)(sizeof(readback) / 2) - 32) / rw;
		if (band < 1) continue;
		for (int b0 = y0; b0 <= y1; b0 += band) {
			const int b1 = b0 + band - 1 < y1 ? b0 + band - 1 : y1;
			RECT rect = {(int16_t)(fb_x + hv->view_x + x0), (int16_t)(fb_y + hv->view_y + b0), (int16_t)rw,
			             (int16_t)(b1 - b0 + 1)};
			DrawSync(0);
			StoreImage(&rect, (uint32_t*)readback);
			DrawSync(0);
			// Pixel by pixel (the display pixel of an original pixel):
			for (int i = 0; i < nruns; ++i) {
				const seg_run* r = &runs[i];
				int prev_x = -1, prev_y = -1;
				for (int k = 0; k < r->len; ++k) {
					const int ox = r->x + (r->vertical ? 0 : k);
					const int oy = r->y + (r->vertical ? k : 0);
					const int dx = half(ox), dy = half(hv->cysize - 1 - oy);
					if (dx == prev_x && dy == prev_y) continue;
					prev_x = dx, prev_y = dy;
					if (dx < x0 || dx > x1 || dy < b0 || dy > b1) continue;
					const uint16_t c = readback[(dy - b0) * rw + (dx - x0)];
					const bool dark = (c & 31) < 10 && ((c >> 5) & 31) < 10 && ((c >> 10) & 31) < 10;
					tj.add(hv->view_x + dx, hv->view_y + dy, dark ? light_color : dark_color);
				}
			}
			tj.flush();
		}
	}
	termPrim(tj.last);
	DrawOTag((const uint32_t*)&tprims.area);
}

// --- One player's picture (kirakegyjatekost) --------------------------------------

void kirakegyjatekost(int ajatekos, double t, motorst* pmot, valtozok* pvalt, int viewki, int timeki, motorst* pmot2,
                      valtozok* pvalt2, int view_x, int view_y, hud_view* hv) {
	vekt2 motorkozep = pmot->kor1.r;
	const double motor_x = dd_center_bike() ? CxsizeV / Arany / 2.0 : Mo_bal + pvalt->baljobbv_h.baljobb * Mo_dx;
	vekt2 sarok(motorkozep.x - motor_x, motorkozep.y - Mo_y);

	// The brush pixel of the view's bottom left (getbalalso_int), taken to an
	// even one: a display pixel is 2x2 brush pixels.
	const double bxd = (sarok.x - Glevel.origo_x) * Arany, byd = (sarok.y - Glevel.origo_y) * Arany;
	const int balalsox = (int)bxd, balalsoy = (int)byd;
	V.w = CxsizeV / 2;
	V.h = CysizeV / 2;
	V.kx = balalsox & ~1;
	V.ky = balalsoy & ~1;
	V.cysize = CysizeV;
	V.cam_x = V.kx / 2;
	V.cam_top = V.ky / 2 + CysizeV / 2 - 1;
	V.fx = bxd - V.kx;
	V.fy = byd - V.ky;
	Fx12 = (int32_t)(V.fx * 4096.0);
	Cy12 = (int32_t)((V.cysize - V.fy) * 4096.0);
	V.bx0 = V.kx - 4;
	V.bx1 = V.kx + CxsizeV + 4;
	V.by0 = V.ky - 4;
	V.by1 = V.ky + CysizeV + 4;
	View_x = view_x;
	View_y = view_y;
	if (view_y == 0) {
		frame_stats.view_x = balalsox;
		frame_stats.view_y = balalsoy;
		frame_stats.cam_x = V.kx;
		frame_stats.cam_y = V.ky;
	}

	// Drawing relative to the view:
	push_area(view_x, view_y, view_x + V.w - 1, view_y + V.h - 1, Fb_x, Fb_y);
	DR_OFFSET* off = gv_prim<DR_OFFSET>();
	setDrawOffset(off, Fb_x + view_x, Fb_y + view_y);

	const gpu_pic* ground = Glevel.ground_texture >= 0 ? &Glgr.textures[Glevel.ground_texture] : 0;
	const gpu_pic* sky = Glevel.sky_texture >= 0 ? &Glgr.textures[Glevel.sky_texture] : 0;

	uint32_t* part = frame_part;
	uint32_t tp = gv_clock(), tq, ts = frame_stats.sound;
#define PART(i) (tq = gv_clock(), part[i] += tq - tp - (frame_stats.sound - ts), tp = tq, ts = frame_stats.sound)
	collect_visible();
	PART(0);
	// 1-2: ground and the far pictures on it, setting the mask.
	stp(1, 0);
	fill_world(0, 0, V.w, V.h, ground);
	PART(1);
	draw_list(GL_FAR_GROUND, 0, &frame_stats.pictures_drawn);
	hang_timed();
	PART(2);
	// 3: the sky, clearing the mask.
	stp(0, 0);
	draw_sky_traps(0, 0, V.w, V.h, 0, false);
	// 4-5: the sky texture and the far pictures on the sky.
	stp(0, 1);
	if (sky && sky->tiles) {
		// Screen-anchored: half the speed horizontally, not vertically
		// (ecset.cpp kitesz, egkepsor).
		const int W = Plgr->texturak[Glevel.sky_texture].origxsize;
		int u0;
		if (W % 2)
			u0 = (int)(((int64_t)V.cam_x * ((W + 1) / 2)) % W);
		else
			u0 = (V.cam_x >> 1) % sky->w;
		fill_texture(0, 0, V.w, V.h, sky, u0, -(CysizeV / 2));
	}
	PART(3);
	draw_list(GL_FAR_SKY, 0, &frame_stats.pictures_drawn);
	PART(4);

	// 6: objects and bikes.
	stp(0, 0);
	drawn_bbox.x0 = drawn_bbox.x1 = 0;
	draw_objects(t, balalsox, balalsoy);
	PART(5);
	motkepek* pmkepek1 = &Plgr->mkepek1;
	motkepek* pmkepek2 = &Plgr->mkepek2;
	if ((State->aplayerabike && !ajatekos) || (!State->aplayerabike && ajatekos)) {
		pmkepek1 = &Plgr->mkepek2;
		pmkepek2 = &Plgr->mkepek1;
	}
	if (!Single) {
		double felx = Kepxsize / 2.0;
		double fely = Kepysize / 2.0;
		vekt2 kozep(sarok.x + felx * Aranyrec, sarok.y + fely * Aranyrec);
		double tav = abs(pmot2->kor1.r - kozep);
		if (tav < (sqrt(felx * felx + fely * fely) + 140.0 * kepnagyitas()) * Aranyrec)
			kibike(!ajatekos, t, sarok, pmot2, pvalt2, pmkepek2);
	}
	kibike(ajatekos, t, sarok, pmot, pvalt, pmkepek1);
	hang_timed();
	PART(6);

	// 7: the near pictures.
	if (nvis[GL_NEAR_SKY]) {
		// The mask under the bikes and objects again: all set, then
		// clear on the sky.
		if (drawn_bbox.x0 < drawn_bbox.x1) {
			stp(1, 0);
			tile(drawn_bbox.x0, drawn_bbox.y0, drawn_bbox.x1 - drawn_bbox.x0, drawn_bbox.y1 - drawn_bbox.y0, 0, true);
			stp(0, 0);
			push_area(view_x + drawn_bbox.x0, view_y + drawn_bbox.y0, view_x + drawn_bbox.x1 - 1,
			          view_y + drawn_bbox.y1 - 1, Fb_x, Fb_y);
			draw_sky_traps(drawn_bbox.x0, drawn_bbox.y0, drawn_bbox.x1, drawn_bbox.y1, 0, true);
			push_area(view_x, view_y, view_x + V.w - 1, view_y + V.h - 1, Fb_x, Fb_y);
		}
		stp(0, 1);
		draw_list(GL_NEAR_SKY, 0, &frame_stats.near_drawn);
	}
	if (nvis[GL_NEAR_GROUND]) {
		// Where they are: the mask clear on ground, set on sky.
		bbox nb = {0, 0, 0, 0};
		for (int i = 0; i < nvis[GL_NEAR_GROUND]; ++i) {
			int x, y, w, h;
			inst_rect(gpu_instance(vis[GL_NEAR_GROUND][i]), &x, &y, &w, &h);
			bbox_add(&nb, x, y, x + w, y + h);
		}
		if (nb.x0 < nb.x1) {
			stp(0, 0);
			tile(nb.x0, nb.y0, nb.x1 - nb.x0, nb.y1 - nb.y0, 0, true);
			stp(1, 0);
			push_area(view_x + nb.x0, view_y + nb.y0, view_x + nb.x1 - 1, view_y + nb.y1 - 1, Fb_x, Fb_y);
			draw_sky_traps(nb.x0, nb.y0, nb.x1, nb.y1, 0, true);
			push_area(view_x, view_y, view_x + V.w - 1, view_y + V.h - 1, Fb_x, Fb_y);
			stp(0, 1);
			draw_list(GL_NEAR_GROUND, 0, &frame_stats.near_drawn);
		}
	}
	stp(0, 0);
	PART(7);

	// 8: the map.
	if (viewki) {
		if (Single)
			kiview(ajatekos, pvalt->baljobbv_h.baljobb, motorkozep, NULL);
		else
			kiview(ajatekos, pvalt->baljobbv_h.baljobb, motorkozep, pmot2);
	}
	PART(8);
#undef PART

	// The timer, for finish_frame:
	hv->view_x = view_x;
	hv->view_y = view_y;
	hv->w = V.w;
	hv->h = V.h;
	hv->cxsize = CxsizeV;
	hv->cysize = CysizeV;
	hv->show = timeki;
	hv->time1[0] = hv->time2[0] = hv->fogo[0] = 0;
	if (timeki) {
		double fogoido = -1.0;
		if (!Single) fogoido = ajatekos ? Afogoido : Bfogoido;
		strncpy(hv->time1, Ezenlegjobbido, sizeof(hv->time1) - 1);
		hv->time1[sizeof(hv->time1) - 1] = 0;
		ido2string((long)(t * Idod2lszorzo), hv->time2);
		if (Tag && fogoido >= 0) ido2string((long)(fogoido * Idod2lszorzo), hv->fogo);
	}
}

} // namespace

void kirajzol320(double t, valtozok* pvalt1, valtozok* pvalt2, int viewki1, int timeki1, int viewki2, int timeki2) {
#ifdef ELMA_PSX_GPU_COMPARE
	if (gpu_render_soft) {
		soft_kirajzol320(t, pvalt1, pvalt2, viewki1, timeki1, viewki2, timeki2);
		return;
	}
#endif
	gpu_level_ensure();
	const uint32_t t0 = gv_clock();
	int splitscreen = 0;
	int fulljatekosA = 1;
	if (!Single) {
		if (!pvalt1->showkep && !pvalt2->showkep) hiba("g45jnuhbvfr");
		if (pvalt1->showkep && pvalt2->showkep)
			splitscreen = 1;
		else
			fulljatekosA = pvalt1->showkep ? 1 : 0;
	}
	beallitmereteket(splitscreen);
	frame_stats = gpu_draw_stats;
	frame_stats.traps_drawn = frame_stats.pictures_drawn = frame_stats.near_drawn = 0;
	frame_stats.fill_textured = frame_stats.fill_flat = frame_stats.fill_blend = 0;
	frame_stats.sound = 0;
	frame_stats.traps_seen = frame_stats.traps_clipped = 0;
	memset(frame_part, 0, sizeof(frame_part));
	hang_timed();

	gv_game_begin(&Fb_x, &Fb_y);
	cur_tpage = 0xffff;
	cur_set = cur_check = -1;
	hud_frame* hf = &huds[hud_index];
	hud_index ^= 1;
	if (splitscreen) {
		hf->nviews = 2;
		// Player A on top (the picture is bottom-up: Cy1..Cy2 is its top
		// part), the gap between them black:
		stp(0, 0);
		tile(0, 0, GV_GAME_W, GV_GAME_H, 0, false);
		kirakegyjatekost(1, t, Pmot1, pvalt1, viewki1, timeki1, Pmot2, pvalt2, 0, 0, &hf->v[0]);
		kirakegyjatekost(0, t, Pmot2, pvalt2, viewki2, timeki2, Pmot1, pvalt1, 0, (Kepysize - CysizeV) / 2,
		                 &hf->v[1]);
	} else {
		hf->nviews = 1;
		if (fulljatekosA)
			kirakegyjatekost(1, t, Pmot1, pvalt1, viewki1, timeki1, Pmot2, pvalt2, 0, 0, &hf->v[0]);
		else
			kirakegyjatekost(0, t, Pmot2, pvalt2, viewki2, timeki2, Pmot1, pvalt1, 0, 0, &hf->v[0]);
	}
	hang_timed();
	const uint32_t t1 = gv_clock();
	gv_prof[GV_PROF_DRAW] += t1 - t0;
	frame_stats.draw_lines = t1 - t0;
	memcpy(frame_stats.part, frame_part, sizeof(frame_part));
	uint32_t used, cap, over;
	gv_game_end(finish_frame, hf);
	gv_prim_stats(&used, &cap, &over);
	frame_stats.prims_words = used;
	if (used > frame_stats.prims_max) frame_stats.prims_max = used;
	frame_stats.frames++;
	gpu_draw_stats = frame_stats;
	static uint32_t last_frame_end = 0;
	if (last_frame_end) gv_prof[GV_PROF_FRAME] += t1 - last_frame_end;
	last_frame_end = gv_clock();
	gv_frame_done(true);
}
