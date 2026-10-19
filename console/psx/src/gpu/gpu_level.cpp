// The level prepared for the GPU renderer, see gpu_level.h. In place of the
// brushes of ecset.cpp (which are kept, next to this, in the comparison
// build ELMA_PSX_GPU_COMPARE).
#include "all.h"
#include "gpu/gpu_level.h"
#include "gpu/gpu_lgr.h"
#include "gpu/gpu_video.h"

gpu_level Glevel;

namespace {

// The original game's Arany (initadatok, 100.0*0.48), as in ecset.cpp:
const double EREDETIARANY = 48.0;

void meghelyez(double* pd, double arany) {
	int pixel = *pd * arany;
	*pd = (pixel + 0.5) / arany;
}

// The level's bounding box from Pszak (ecset::getorigoandsize).
void level_box(double* minx, double* miny, double* maxx, double* maxy) {
	Pszak->felsorolasresetszak();
	vonal* psz = Pszak->getnextszak();
	if (!psz) hiba((char*)"Nincs egyetlen szakasz sem definialva!");
	*minx = *maxx = psz->r.x;
	*miny = *maxy = psz->r.y;
	while (psz) {
		const double xs[2] = {psz->r.x, psz->r.x + psz->v.x};
		const double ys[2] = {psz->r.y, psz->r.y + psz->v.y};
		for (int i = 0; i < 2; ++i) {
			if (xs[i] < *minx) *minx = xs[i];
			if (xs[i] > *maxx) *maxx = xs[i];
			if (ys[i] < *miny) *miny = ys[i];
			if (ys[i] > *maxy) *maxy = ys[i];
		}
		psz = Pszak->getnextszak();
	}
}

} // namespace

#ifndef ELMA_PSX_GPU_COMPARE
// What the rest of the game uses of ecset.cpp. The brush itself is not
// made; Pecsetalso only knows its origin and size, for kilogna and the
// physics (console/psx/src/phys).
ecset* Pecsetalso = NULL;
ecset* Pecsetfelso = NULL;
ecset* Pecsetview = NULL;
int Kisordarabszam = 0;
int Osszegszam = 0;

int uresszam(int x, int xsize, unsigned char* sor, unsigned char lyuk) {
	int szam = 0;
	while (x < xsize && sor[x] == lyuk) {
		x++;
		szam++;
	}
	return szam;
}

int teliszam(int x, int xsize, unsigned char* sor, unsigned char lyuk) {
	int szam = 0;
	while (x < xsize && sor[x] != lyuk) {
		x++;
		szam++;
	}
	return szam;
}

ecset::ecset(int view_p) {
	elsotomb = kurtomb = NULL;
	tombbenkov = 0;
	nagydarabtomb = NULL;
	sortombmeret = 0;
	msorok = NULL;
	sorok = NULL;
	kurxposok_A = kurxposok_B = NULL;
	curdarabok_A = curdarabok_B = NULL;
	view = view_p;
	xsizedb = ysizedb = 0.0;
	maxx = sorszam = 0;
	eredetimaxx = eredetisorszam = 0;
	getorigoandsize();
	maxx = xsizedb * Arany;
	sorszam = ysizedb * Arany;
}

ecset::~ecset(void) {}

void ecset::getorigoandsize(void) {
	double minx, miny, maxx_m, maxy;
	level_box(&minx, &miny, &maxx_m, &maxy);
	origo = vekt2(minx - 10000 / Aranyalap, miny - 1000 / Aranyalap);
	meghelyez(&origo.x, Arany);
	meghelyez(&origo.y, Arany);
	xsizedb = (maxx_m + 10000 / Aranyalap) - origo.x;
	ysizedb = (maxy + 1000 / Aranyalap) - origo.y;
	eredetiorigo = vekt2(minx - 10000 / EREDETIARANY, miny - 1000 / EREDETIARANY);
	meghelyez(&eredetiorigo.x, EREDETIARANY);
	meghelyez(&eredetiorigo.y, EREDETIARANY);
	eredetimaxx = ((maxx_m + 10000 / EREDETIARANY) - eredetiorigo.x) * EREDETIARANY;
	eredetisorszam = ((maxy + 1000 / EREDETIARANY) - eredetiorigo.y) * EREDETIARANY;
}

void ecset::getbalalso_int(vekt2 balalso, int* px, int* py) {
	vekt2 relat = balalso - origo;
	*px = relat.x * Arany;
	*py = relat.y * Arany;
}

// ecset.cpp: the edge band of the brush the original never drew.
#define ECSETSZEL (20)

int ecset::kilogna(vekt2 r) {
	double x = (r.x - 320.0 / EREDETIARANY - eredetiorigo.x) * EREDETIARANY;
	double y = (r.y - 240.0 / EREDETIARANY - eredetiorigo.y) * EREDETIARANY;
	if (x < ECSETSZEL || y < ECSETSZEL) return 1;
	if (floor(x) + 639 > eredetimaxx - ECSETSZEL) return 1;
	if (floor(y) + 479 > eredetisorszam - ECSETSZEL) return 1;
	return 0;
}
#else
void soft_betoltecseteket(void);
#endif

int32_t gpu_brush_x16(double x) { return (int32_t)((x - Glevel.origo_x) * Arany * 16.0); }
int32_t gpu_brush_y16(double y) { return (int32_t)((y - Glevel.origo_y) * Arany * 16.0); }

namespace {

// --- The sky as trapezoids (gpu_traps.c) -----------------------------------

void build_traps() {
	// The edges of the polygons (Pszak, not the grass polygons) as
	// ecset::addszakasz sees them, in brush pixels:
	int n = 0;
	Pszak->felsorolasresetszak();
	while (Pszak->getnextszak()) n++;
	gpu_seg* segs = new gpu_seg[n ? n : 1];
	n = 0;
	Pszak->felsorolasresetszak();
	for (vonal* psz = Pszak->getnextszak(); psz; psz = Pszak->getnextszak()) {
		gpu_seg* g = &segs[n++];
		g->x0 = gpu_brush_x16(psz->r.x);
		g->y0 = gpu_brush_y16(psz->r.y);
		g->x1 = gpu_brush_x16(psz->r.x + psz->v.x);
		g->y1 = gpu_brush_y16(psz->r.y + psz->v.y);
	}
	free(Glevel.traps);
	Glevel.traps = 0;
	Glevel.ntraps = gpu_make_traps(segs, n, Glevel.maxx * 16, &Glevel.traps);
	delete[] segs;
}

void trap_cells(const gpu_trap* t, int* cx0, int* cy0, int* cx1, int* cy1) {
	int32_t xmin = t->xl0 < t->xl1 ? t->xl0 : t->xl1;
	int32_t xmax = t->xr0 > t->xr1 ? t->xr0 : t->xr1;
	*cx0 = (xmin >> 4) / GPU_TRAP_CELL;
	*cx1 = (xmax >> 4) / GPU_TRAP_CELL;
	*cy0 = (t->y0 >> 4) / GPU_TRAP_CELL;
	*cy1 = (t->y1 >> 4) / GPU_TRAP_CELL;
	if (*cx0 < 0) *cx0 = 0;
	if (*cy0 < 0) *cy0 = 0;
	if (*cx1 > Glevel.tgrid_w - 1) *cx1 = Glevel.tgrid_w - 1;
	if (*cy1 > Glevel.tgrid_h - 1) *cy1 = Glevel.tgrid_h - 1;
}

void build_grid() {
	delete[] Glevel.grid_start;
	delete[] Glevel.grid_items;
	Glevel.tgrid_w = Glevel.maxx / GPU_TRAP_CELL + 1;
	Glevel.tgrid_h = Glevel.sorszam / GPU_TRAP_CELL + 1;
	// (The pictures' grid, build_inst_grid:)
	Glevel.grid_w = Glevel.maxx / GPU_GRID_CELL + 1;
	Glevel.grid_h = Glevel.sorszam / GPU_GRID_CELL + 1;
	const int cells = Glevel.tgrid_w * Glevel.tgrid_h;
	Glevel.grid_start = new uint32_t[cells + 1];
	memset(Glevel.grid_start, 0, (cells + 1) * sizeof(uint32_t));
	for (int i = 0; i < Glevel.ntraps; ++i) {
		int cx0, cy0, cx1, cy1;
		trap_cells(&Glevel.traps[i], &cx0, &cy0, &cx1, &cy1);
		for (int cy = cy0; cy <= cy1; ++cy)
			for (int cx = cx0; cx <= cx1; ++cx) Glevel.grid_start[cy * Glevel.tgrid_w + cx + 1]++;
	}
	for (int c = 0; c < cells; ++c) Glevel.grid_start[c + 1] += Glevel.grid_start[c];
	const uint32_t total = Glevel.grid_start[cells];
	Glevel.grid_items = new uint16_t[total ? total : 1];
	uint32_t* fill = new uint32_t[cells];
	memcpy(fill, Glevel.grid_start, cells * sizeof(uint32_t));
	for (int i = 0; i < Glevel.ntraps && i < 65536; ++i) {
		int cx0, cy0, cx1, cy1;
		trap_cells(&Glevel.traps[i], &cx0, &cy0, &cx1, &cy1);
		for (int cy = cy0; cy <= cy1; ++cy)
			for (int cx = cx0; cx <= cx1; ++cx) Glevel.grid_items[fill[cy * Glevel.tgrid_w + cx]++] = (uint16_t)i;
	}
	delete[] fill;
}

// --- The map ---------------------------------------------------------------------

// The sky of the map as runs of display pixels (gpu_level.h). A pixel is sky
// if its center is in a trapezoid; a row's runs are found trapezoid by
// trapezoid (they do not overlap), then sorted and joined.
void build_map() {
	delete[] Glevel.map_row_start;
	delete[] Glevel.map_runs;
	Glevel.map_row_start = 0;
	Glevel.map_runs = 0;
	Glevel.map_rows = 0;
	const double step = 2.0 / Glevel.view_scale;  // brush pixels a display pixel
	Glevel.map_step = step;
	const int rows = (int)(Glevel.sorszam / step) + 2;
	// Brush pixels with 8 fraction bits:
	const int32_t step8 = (int32_t)(step * 256.0);
	if (step8 <= 0 || !Glevel.ntraps) return;
	uint32_t* start = new uint32_t[rows + 1];
	memset(start, 0, (rows + 1) * sizeof(uint32_t));
	int16_t* runs = 0;
	for (int pass = 0; pass < 2; ++pass) {
		uint32_t* fill = 0;
		if (pass) {
			for (int j = 0; j < rows; ++j) start[j + 1] += start[j];
			runs = new int16_t[2 * (start[rows] ? start[rows] : 1)];
			fill = new uint32_t[rows];
			memcpy(fill, start, rows * sizeof(uint32_t));
		}
		for (int i = 0; i < Glevel.ntraps; ++i) {
			const gpu_trap* t = &Glevel.traps[i];
			// Rows whose center (j + 1/2) * step is in [y0, y1):
			const int32_t y0 = t->y0 << 4, y1 = t->y1 << 4;  // 8 fraction bits
			if (y1 <= y0) continue;
			int j = (int)((2 * (int64_t)y0 / step8 - 1) / 2);
			if (j < 0) j = 0;
			while ((int32_t)((2 * j + 1) * (int64_t)step8 / 2) < y0) ++j;
			while (j > 0 && (int32_t)((2 * j - 1) * (int64_t)step8 / 2) >= y0) --j;
			const double dy = y1 - y0;
			const double dl = (t->xl1 - t->xl0) * 16 / dy, dr = (t->xr1 - t->xr0) * 16 / dy;
			for (; j < rows; ++j) {
				const int32_t yc = (int32_t)((2 * j + 1) * (int64_t)step8 / 2);
				if (yc >= y1) break;
				// The edges at yc, then the columns whose centers are in
				// [xl, xr): (i + 1/2) * step >= xl.
				const double f = yc - y0;
				const int32_t xl = (t->xl0 << 4) + (int32_t)(dl * f), xr = (t->xr0 << 4) + (int32_t)(dr * f);
				int c0 = (int)((2 * (int64_t)xl + step8 - 1) / (2 * step8));
				int c1 = (int)((2 * (int64_t)xr + step8 - 1) / (2 * step8));
				if (c0 < 0) c0 = 0;
				if (c1 > 32767) c1 = 32767;
				if (c0 >= c1) continue;
				if (!pass)
					start[j + 1]++;
				else {
					runs[2 * fill[j]] = (int16_t)c0;
					runs[2 * fill[j] + 1] = (int16_t)c1;
					fill[j]++;
				}
			}
		}
		delete[] fill;
	}
	// Sorted and joined, row by row (packed again):
	uint32_t out = 0;
	for (int j = 0; j < rows; ++j) {
		const uint32_t a = start[j], b = start[j + 1];
		for (uint32_t k = a + 1; k < b; ++k) {
			const int16_t x0 = runs[2 * k], x1 = runs[2 * k + 1];
			uint32_t m = k;
			while (m > a && runs[2 * (m - 1)] > x0) {
				runs[2 * m] = runs[2 * (m - 1)];
				runs[2 * m + 1] = runs[2 * (m - 1) + 1];
				--m;
			}
			runs[2 * m] = x0;
			runs[2 * m + 1] = x1;
		}
		start[j] = out;
		for (uint32_t k = a; k < b; ++k) {
			if (out > start[j] && runs[2 * (out - 1) + 1] >= runs[2 * k]) {
				if (runs[2 * k + 1] > runs[2 * (out - 1) + 1]) runs[2 * (out - 1) + 1] = runs[2 * k + 1];
				continue;
			}
			runs[2 * out] = runs[2 * k];
			runs[2 * out + 1] = runs[2 * k + 1];
			out++;
		}
	}
	start[rows] = out;
	Glevel.map_rows = rows;
	Glevel.map_row_start = start;
	Glevel.map_runs = runs;
}

// --- Pictures, masks and grass ---------------------------------------------------

gpu_inst* insts = 0;
int ninst = 0, inst_cap = 0;
int order = 0;

gpu_inst* new_inst() {
	if (ninst == inst_cap) {
		const int cap = inst_cap ? inst_cap * 2 : 256;
		gpu_inst* t = new gpu_inst[cap];
		if (ninst) memcpy(t, insts, ninst * sizeof(gpu_inst));
		delete[] insts;
		insts = t;
		inst_cap = cap;
	}
	gpu_inst* i = &insts[ninst++];
	memset(i, 0, sizeof(*i));
	i->order = order++;
	return i;
}

enum { FAZIS_FOLD, FAZIS_EG, FAZIS_NEMFOLDEG };

// ecset::addspriteok: the pictures and masks of one phase.
void add_sprites(int fazis) {
	const int kepszelbal = nagyitpixel(120, kepnagyitas());
	const int kepszeljobb = nagyitpixel(50, kepnagyitas());
	const double ox = Glevel.origo_x, oy = Glevel.origo_y;
	for (int j = 0; j < MAXSPRITE; j++) {
		sprite* psp = Ptop->spritetomb[j];
		if (!psp) return;
		if (fazis == FAZIS_FOLD && psp->hatarol != HATAROL_G) continue;
		if (fazis == FAZIS_EG && psp->hatarol != HATAROL_S) continue;
		if (fazis == FAZIS_NEMFOLDEG && psp->hatarol) continue;
		const int x1 = (psp->r.x - ox) * Arany;
		const int y1 = (-psp->r.y - oy) * Arany;
		const int clip = fazis == FAZIS_FOLD ? GI_CLIP_GROUND : fazis == FAZIS_EG ? GI_CLIP_SKY : GI_CLIP_NONE;
		if (psp->kepnev[0] == 0) {
			if (!psp->texturanev[0] || !psp->maszknev[0]) continue;
			const int index_t = Plgr->gettexturaindex(psp->texturanev);
			const int index_m = Plgr->getmaszkindex(psp->maszknev);
			if (index_t < 0 || index_m < 0) continue;
			const maszk* pm = &Plgr->maszkok[index_m];
			if (x1 < kepszelbal || x1 + pm->xsize >= Glevel.maxx - kepszeljobb) continue;
			gpu_inst* in = new_inst();
			in->type = GI_MASK;
			in->x = x1;
			in->y = y1;
			in->w = (int16_t)pm->xsize;
			in->h = (int16_t)pm->ysize;
			in->distance = (int16_t)psp->tavolsag;
			in->clip = (uint8_t)clip;
			in->index = (int16_t)index_m;
			in->texture = (int16_t)index_t;
			continue;
		}
		if (psp->texturanev[0] || psp->maszknev[0]) continue;
		const int index = Plgr->getkepindex(psp->kepnev);
		if (index < 0) continue;
		const kep* pkep = &Plgr->kepek[index];
		// From here on all further pictures are left out too (as originally):
		if (x1 < kepszelbal || x1 + pkep->xsize >= Glevel.maxx - kepszeljobb) return;
		gpu_inst* in = new_inst();
		in->type = GI_PICTURE;
		in->x = x1;
		in->y = y1;
		in->w = (int16_t)pkep->xsize;
		in->h = (int16_t)pkep->ysize;
		in->distance = (int16_t)psp->tavolsag;
		in->clip = (uint8_t)clip;
		in->index = (int16_t)index;
	}
}

// ecset::kiegykovetokep and kovetotextura: a grass picture and the qgrass
// above it, at distance 600 on the ground.
void add_grass_picture(int index, int xo, int yo) {
	koveto* pkov = Plgr->pkoveto;
	const gpu_grass* g = &Glgr.grass[index];
	if (pkov->feltomb[index])
		yo -= Plgr->keltolas;
	else
		yo -= Plgr->keltolas + pkov->lejtestomb[index];
	gpu_inst* in = new_inst();
	in->type = GI_GRASS;
	in->x = xo;
	in->y = yo + g->ysize - 1;
	in->w = g->xsize;
	in->h = g->ysize;
	in->distance = 600;
	in->clip = GI_CLIP_GROUND;
	in->index = (int16_t)index;
	if (g->xsize > Plgr->kovetomaxx || g->ysize > Plgr->kovetomaxy) return;
	if (Glevel.qgrass_texture < 0) return;
	in = new_inst();
	in->type = GI_QGRASS;
	in->x = xo;
	in->y = yo + g->ysize + Plgr->fuggtoldas - 1;  // top row of the strips
	in->w = g->xsize;
	in->h = (int16_t)(g->ysize + Plgr->fuggtoldas);  // at most, down to yo
	in->distance = 600;
	in->clip = GI_CLIP_GROUND;
	in->index = (int16_t)index;
	in->texture = (int16_t)Glevel.qgrass_texture;
}

// ecset::kikovetokepek
void add_grass_line(int* ytomb, int hossz, int x0) {
	if (hossz < 1) return;
	koveto* pkov = Plgr->pkoveto;
	int curx = x0;
	int cury = ytomb[0];
	while (curx < x0 + hossz) {
		int elteres = 10000, joindex = -1, jody = 0;
		for (int i = 0; i < pkov->kepszam; i++) {
			int dy = pkov->lejtestomb[i];
			if (!pkov->feltomb[i]) dy = -dy;
			const int ujx = curx + Glgr.grass[i].xsize;
			const int vonaly = ujx >= x0 + hossz ? ytomb[hossz - 1] : ytomb[ujx - x0];
			const int ujelteres = abs(cury + dy - vonaly);
			if (ujelteres < elteres) {
				elteres = ujelteres;
				joindex = i;
				jody = dy;
			}
		}
		if (joindex < 0) return;
		add_grass_picture(joindex, curx, cury);
		curx += Glgr.grass[joindex].xsize;
		cury += jody;
	}
}

// ecset::addkovetok (only the ground phase has grass)
void add_grass() {
	if (!Plgr->vanfu || Glgr.ngrass < 2) return;
	const int kovvonalhossz = nagyitpixel(10000, kepnagyitas());
	int* ytomb = new int[kovvonalhossz + 10];
	vekt2 origo(Glevel.origo_x, Glevel.origo_y);
	for (int i = 0; i < MAXGYURU; i++) {
		gyuru* pgy = Ptop->ptomb[i];
		if (!pgy) break;
		if (!pgy->koveto) continue;
		int vonalhossz = 0, x0 = 0;
		if (!makevonal(pgy, ytomb, &vonalhossz, &x0, kovvonalhossz, &origo)) continue;
		if (vonalhossz > kovvonalhossz) continue;
		add_grass_line(ytomb, vonalhossz, x0);
	}
	delete[] ytomb;
}

// The drawing order: the farthest first; at the same distance the one
// added later first.
inline bool drawn_before(const gpu_inst* a, const gpu_inst* b) {
	return a->distance > b->distance || (a->distance == b->distance && a->order > b->order);
}

void build_instances() {
	ninst = 0;
	order = 0;
	if (State->highquality) {
		add_sprites(FAZIS_FOLD);
		add_grass();
		add_sprites(FAZIS_EG);
		add_sprites(FAZIS_NEMFOLDEG);
	}
	if (ninst > 65535) ninst = 65535;
	// Sorted into the drawing order (shell sort of their indices):
	uint16_t* idx = new uint16_t[ninst ? ninst : 1];
	for (int i = 0; i < ninst; ++i) idx[i] = (uint16_t)i;
	for (int gap = ninst / 2; gap > 0; gap /= 2)
		for (int i = gap; i < ninst; ++i) {
			const uint16_t v = idx[i];
			int j = i;
			while (j >= gap && drawn_before(&insts[v], &insts[idx[j - gap]])) {
				idx[j] = idx[j - gap];
				j -= gap;
			}
			idx[j] = v;
		}
	delete[] Glevel.inst;
	Glevel.inst = new gpu_inst[ninst ? ninst : 1];
	for (int i = 0; i < ninst; ++i) Glevel.inst[i] = insts[idx[i]];
	Glevel.ninst = ninst;
	delete[] idx;
	delete[] insts;
	insts = 0;
	inst_cap = 0;
}

// --- The instances' sprites and their grid -------------------------------------

gpu_wsprite* sprs = 0;
int nspr = 0, spr_cap = 0;

// (Without sprs only counted: build_sprites runs twice.)
void push_sprite(int32_t hx, int32_t hy, int u, int v, int w, int h, uint16_t tpage, uint16_t clut) {
	if (!sprs || nspr >= spr_cap) {
		nspr++;
		return;
	}
	gpu_wsprite* p = &sprs[nspr++];
	p->hx = hx;
	p->hy = hy;
	p->u = (uint8_t)u;
	p->v = (uint8_t)v;
	p->w1 = (uint8_t)(w - 1);
	p->h1 = (uint8_t)(h - 1);
	p->tpage = tpage;
	p->clut = clut;
}

inline int32_t half(int32_t a) { return a >> 1; }

int mod(int a, int m) {
	const int r = a % m;
	return r < 0 ? r + m : r;
}

// An image with its top left at half-resolution brush pixel (hx, hy).
void sprites_pic(const gpu_pic* p, int32_t hx, int32_t hy) {
	if (!p || !p->tiles) return;
	for (int ty = 0; ty < p->tiles_y; ++ty)
		for (int tx = 0; tx < p->tiles_x; ++tx) {
			const gpu_tile* t = gpu_pic_tile(p, tx, ty);
			push_sprite(hx + 256 * tx, hy - 256 * ty, t->u, t->v, t->w1 + 1, t->h1 + 1, t->tpage, gpu_clut_id(t->clut));
		}
}

// A world-anchored texture over the half-resolution brush pixels
// hx0..hx1, hy_lo..hy_hi (gpu_lgr.h: texel (hx mod w, (-1-hy) mod h)).
void sprites_world(int32_t hx0, int32_t hx1, int32_t hy_lo, int32_t hy_hi, const gpu_pic* tex) {
	if (!tex || !tex->tiles || hx0 > hx1 || hy_lo > hy_hi) return;
	const int Q = tex->w, P = tex->h;
	for (int32_t hy = hy_hi; hy >= hy_lo;) {
		const int v = mod(-1 - hy, P);
		int rows = P - v;
		if (rows > 256 - (v & 255)) rows = 256 - (v & 255);
		if (rows > hy - hy_lo + 1) rows = hy - hy_lo + 1;
		for (int32_t hx = hx0; hx <= hx1;) {
			const int u = mod(hx, Q);
			int cols = Q - u;
			if (cols > 256 - (u & 255)) cols = 256 - (u & 255);
			if (cols > hx1 - hx + 1) cols = hx1 - hx + 1;
			const gpu_tile* t = gpu_pic_tile(tex, u >> 8, v >> 8);
			push_sprite(hx, hy, t->u + (u & 255), t->v + (v & 255), cols, rows, t->tpage, gpu_clut_id(t->clut));
			hx += cols;
		}
		hy -= rows;
	}
}

// A display pixel samples the even brush column and row of its 2x2 block:
// the half-resolution pixels whose sample lies in brush pixels a..b:
inline int32_t first_half(int32_t a) { return half(a + 1); }
inline int32_t last_half(int32_t b) { return half(b); }

void build_sprites() {
	delete[] Glevel.sprites;
	Glevel.sprites = 0;
	sprs = 0;
	spr_cap = 0;
	for (int pass = 0; pass < 2; ++pass) {
		if (pass) {
			spr_cap = nspr;
			sprs = new gpu_wsprite[nspr ? nspr : 1];
		}
		nspr = 0;
		for (int i = 0; i < Glevel.ninst; ++i) {
			gpu_inst* in = &Glevel.inst[i];
			in->sprite0 = nspr;
			switch (in->type) {
			case GI_PICTURE:
				if (in->index >= 0 && in->index < Glgr.npictures)
					sprites_pic(&Glgr.pictures[in->index], half(in->x), half(in->y));
				break;
			case GI_GRASS:
				if (in->index >= 0 && in->index < Glgr.ngrass) sprites_pic(&Glgr.grass[in->index].pic, half(in->x), half(in->y));
				break;
			case GI_MASK: {
				if (in->index < 0 || in->index >= Glgr.nmasks || in->texture < 0 || in->texture >= Glgr.ntextures) break;
				const gpu_mask* m = &Glgr.masks[in->index];
				// Mask row r is brush row y - r:
				for (int k = 0; k < m->nrects; ++k) {
					const gpu_mask_rect* r = &m->rects[k];
					sprites_world(first_half(in->x + r->x1), last_half(in->x + r->x2), first_half(in->y - r->y2),
					              last_half(in->y - r->y1), &Glgr.textures[in->texture]);
				}
				break;
			}
			case GI_QGRASS: {
				// in->y is the top row; a column's strip goes down to the grass
				// picture's first opaque pixel (yo + ysize - tops[x], yo the
				// bottom of the picture: top - ysize - fuggtoldas + 1).
				if (in->index < 0 || in->index >= Glgr.ngrass || in->texture < 0) break;
				const gpu_grass* g = &Glgr.grass[in->index];
				const gpu_pic* tex = &Glgr.textures[in->texture];
				const int yo = in->y - in->h + 1;
				const int32_t hy_hi = last_half(in->y);
				const int32_t hx_first = first_half(in->x), hx_last = last_half(in->x + g->xsize - 1);
				int32_t run_x0 = 0, run_lo = 0;
				bool run = false;
				for (int32_t hx = hx_first; hx <= hx_last + 1; ++hx) {
					int32_t lo = 0x7fffffff;
					if (hx <= hx_last) lo = first_half(yo + g->ysize - g->tops[2 * hx - in->x]);
					if (run && (lo != run_lo || hx > hx_last)) {
						sprites_world(run_x0, hx - 1, run_lo, hy_hi, tex);
						run = false;
					}
					if (!run && hx <= hx_last) {
						run = true;
						run_x0 = hx;
						run_lo = lo;
					}
				}
				break;
			}
			}
			in->nsprites = (int16_t)(nspr - in->sprite0);
		}
	}
	Glevel.sprites = sprs;
	Glevel.nsprites = nspr;
	sprs = 0;
	spr_cap = 0;
}

void inst_cells(const gpu_inst* in, int* cx0, int* cy0, int* cx1, int* cy1) {
	*cx0 = in->x / GPU_GRID_CELL;
	*cx1 = (in->x + in->w) / GPU_GRID_CELL;
	*cy0 = (in->y - in->h) / GPU_GRID_CELL;
	*cy1 = in->y / GPU_GRID_CELL;
	if (*cx0 < 0) *cx0 = 0;
	if (*cy0 < 0) *cy0 = 0;
	if (*cx1 > Glevel.grid_w - 1) *cx1 = Glevel.grid_w - 1;
	if (*cy1 > Glevel.grid_h - 1) *cy1 = Glevel.grid_h - 1;
}

void build_inst_grid() {
	delete[] Glevel.inst_start;
	delete[] Glevel.inst_items;
	const int cells = Glevel.grid_w * Glevel.grid_h;
	Glevel.inst_start = new uint32_t[cells + 1];
	memset(Glevel.inst_start, 0, (cells + 1) * sizeof(uint32_t));
	const int n = Glevel.ninst < 65536 ? Glevel.ninst : 65536;
	for (int i = 0; i < n; ++i) {
		int cx0, cy0, cx1, cy1;
		inst_cells(&Glevel.inst[i], &cx0, &cy0, &cx1, &cy1);
		for (int cy = cy0; cy <= cy1; ++cy)
			for (int cx = cx0; cx <= cx1; ++cx) Glevel.inst_start[cy * Glevel.grid_w + cx + 1]++;
	}
	for (int c = 0; c < cells; ++c) Glevel.inst_start[c + 1] += Glevel.inst_start[c];
	const uint32_t total = Glevel.inst_start[cells];
	Glevel.inst_items = new uint16_t[total ? total : 1];
	uint32_t* fill = new uint32_t[cells];
	memcpy(fill, Glevel.inst_start, cells * sizeof(uint32_t));
	for (int i = 0; i < n; ++i) {
		int cx0, cy0, cx1, cy1;
		inst_cells(&Glevel.inst[i], &cx0, &cy0, &cx1, &cy1);
		for (int cy = cy0; cy <= cy1; ++cy)
			for (int cx = cx0; cx <= cx1; ++cx) Glevel.inst_items[fill[cy * Glevel.grid_w + cx]++] = (uint16_t)i;
	}
	delete[] fill;
}

// ecset::kitoltfoodkoordokat (the wheels stand upright now)
void object_positions() {
	for (int i = 0; i < MAXKEREK; i++) {
		kerek* pker = Ptop->kerektomb[i];
		if (!pker) continue;
		pker->rxint = (pker->r.x - Glevel.origo_x) * Arany - Plgr->objektumsugar;
		pker->ryint = (-pker->r.y - Glevel.origo_y) * Arany - Plgr->objektumsugar;
	}
}

} // namespace

// The previous level's data, freed before the next one is built.
static void free_level() {
	free(Glevel.traps);
	Glevel.traps = 0;
	Glevel.ntraps = 0;
	delete[] Glevel.grid_start;
	delete[] Glevel.grid_items;
	Glevel.grid_start = 0;
	Glevel.grid_items = 0;
	delete[] Glevel.map_row_start;
	delete[] Glevel.map_runs;
	Glevel.map_row_start = 0;
	Glevel.map_runs = 0;
	Glevel.map_rows = 0;
	delete[] Glevel.inst;
	Glevel.inst = 0;
	Glevel.ninst = 0;
	delete[] Glevel.sprites;
	Glevel.sprites = 0;
	Glevel.nsprites = 0;
	delete[] Glevel.inst_start;
	delete[] Glevel.inst_items;
	Glevel.inst_start = 0;
	Glevel.inst_items = 0;
}

void betoltecseteket(void) {
	const uint32_t t0 = gv_clock();
	free_level();
#ifdef ELMA_PSX_GPU_COMPARE
	soft_betoltecseteket();
#else
	if (Pecsetalso) delete Pecsetalso;
	Pecsetalso = new ecset(0);
#endif
	// The brush's origin and size as ecset::getorigoandsize:
	double minx, miny, maxx, maxy;
	level_box(&minx, &miny, &maxx, &maxy);
	double ox = minx - 10000 / Aranyalap, oy = miny - 1000 / Aranyalap;
	meghelyez(&ox, Arany);
	meghelyez(&oy, Arany);
	Glevel.origo_x = ox;
	Glevel.origo_y = oy;
	Glevel.maxx = ((maxx + 10000 / Aranyalap) - ox) * Arany;
	Glevel.sorszam = ((maxy + 1000 / Aranyalap) - oy) * Arany;
	Glevel.view_scale = Aranyalap / Viewzoom / Arany;

	Glevel.ground_texture = Plgr->gettexturaindex(Ptop->fgnev);
	Glevel.sky_texture = Plgr->gettexturaindex(Ptop->bgnev);
	Glevel.qgrass_texture = Plgr->gettexturaindex((char*)"qgrass");

	build_traps();
	build_grid();
	build_map();
	build_instances();
	build_sprites();
	build_inst_grid();
	object_positions();
	printf("elma: level for the GPU: %d trapezoids, %u map runs, %d pictures in %d sprites, %u ms\n", Glevel.ntraps,
	       (unsigned)(Glevel.map_rows ? Glevel.map_row_start[Glevel.map_rows] : 0), Glevel.ninst, Glevel.nsprites,
	       (unsigned)((gv_clock() - t0) / (GV_CLOCK_HZ / 1000)));
}
