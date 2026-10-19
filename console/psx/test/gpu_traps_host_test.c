/* Host test of the sky trapezoids of the GPU renderer (src/gpu/gpu_traps.c).
 *
 * For every level file given (external levels, read only) the polygons are
 * read as the game reads them, and every pixel row of the level is compared:
 * the original renderer's rule (ecset.cpp addszakasz and rendez: the
 * crossings of a row, sorted, coincident ones cancelled, the state of the
 * nearest crossing on the left) against the trapezoids at the row's centre.
 * Pixels whose centre lies within 1/8 pixel of an edge are not counted (the
 * fixed point rounding of the trapezoids). Synthetic levels with polygons of
 * both directions (inverted holes, sky polygons inside ground ...) are
 * tested too.
 *
 * What remains are single rows next to vertices: where the original's
 * crossings of two edges fall on one pixel of a row it cancels them, and in
 * a level whose polygons are not consistently directed that turns the rest
 * of the row (the original draws a one pixel line there); the trapezoids
 * show such lines at other rows, or not at all.
 *
 *   cc -O2 -o build/gpu_traps_host_test test/gpu_traps_host_test.c \
 *       src/gpu/gpu_traps.c -Isrc/gpu -lm
 *   build/gpu_traps_host_test ../../build/Lev/ *.lev
 *
 * Prints the levels with more than 0.1% of their sky pixels wrong; exit
 * status 1 if all levels together have more than 0.05% wrong, or one has
 * more than 10% (a real error in the trapezoids, not single rows). */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "gpu_traps.h"

typedef struct {
	double x, y;
} vec;

typedef struct {
	int npoly;
	int* count;
	vec** pts;
} level;

static int read_level(const char* path, level* lev) {
	FILE* f = fopen(path, "rb");
	if (!f) return 0;
	unsigned char* d = malloc(4 << 20);
	const size_t len = fread(d, 1, 4 << 20, f);
	fclose(f);
	if (len < 140 || memcmp(d, "POT", 3) != 0) {
		free(d);
		return 0;
	}
	const int version = (d[3] - '0') * 10 + (d[4] - '0');
	size_t p;
	if (version >= 14)
		p = 5 + 2 + 4 + 8 + 24 + 51 + 16 + 10 + 10;
	else
		p = 100;
	double dn;
	memcpy(&dn, d + p, 8);
	p += 8;
	const int n = (int)dn;
	lev->npoly = 0;
	lev->count = malloc(sizeof(int) * (n > 0 ? n : 1));
	lev->pts = malloc(sizeof(vec*) * (n > 0 ? n : 1));
	for (int i = 0; i < n; ++i) {
		int32_t grass = 0, points;
		if (version >= 8) {
			memcpy(&grass, d + p, 4);
			p += 4;
			if (version < 12 && grass) p += 34;
		}
		memcpy(&points, d + p, 4);
		p += 4;
		if (points < 3 || points > 1000 || p + 16 * (size_t)points > len) break;
		if (!grass) {
			lev->count[lev->npoly] = points;
			lev->pts[lev->npoly] = malloc(sizeof(vec) * points);
			memcpy(lev->pts[lev->npoly], d + p, 16 * points);
			lev->npoly++;
		}
		p += 16 * (size_t)points;
	}
	free(d);
	return lev->npoly > 0;
}

/* --- The original's rows (ecset.cpp) --------------------------------------- */

typedef struct {
	int x;
	int ground;
} crossing;

typedef struct {
	crossing* c;
	int n, cap;
} row;

static void push(row* r, int x, int ground) {
	if (r->n == r->cap) {
		r->cap = r->cap ? r->cap * 2 : 8;
		r->c = realloc(r->c, r->cap * sizeof(crossing));
	}
	r->c[r->n].x = x;
	r->c[r->n].ground = ground;
	r->n++;
}

/* rendez(): bubble sort (the first element stays), coincident crossings
 * removed (the same state once, different ones both), then neighbours of
 * the same state merged. */
static void rendez(row* r) {
	crossing* c = r->c;
	int n = r->n;
	for (int pass = 0; pass < n + 2; ++pass)
		for (int i = 1; i + 1 < n; ++i)
			if (c[i].x > c[i + 1].x) {
				crossing t = c[i];
				c[i] = c[i + 1];
				c[i + 1] = t;
			}
	int i = 1;
	while (i + 1 < n) {
		if (c[i].x == c[i + 1].x) {
			if (c[i].ground == c[i + 1].ground) {
				memmove(&c[i + 1], &c[i + 2], (n - i - 2) * sizeof(crossing));
				n--;
			} else {
				memmove(&c[i], &c[i + 2], (n - i - 2) * sizeof(crossing));
				n -= 2;
			}
			i = 1;
		} else
			i++;
	}
	i = 0;
	while (i + 1 < n) {
		if (c[i].ground == c[i + 1].ground) {
			memmove(&c[i + 1], &c[i + 2], (n - i - 2) * sizeof(crossing));
			n--;
			i = 0;
		} else
			i++;
	}
	r->n = n;
}

/* --- The test ----------------------------------------------------------------- */

static double ox, oy;
static const double ARANY = 48.0;

static void meghelyez(double* pd, double arany) {
	int pixel = *pd * arany;
	*pd = (pixel + 0.5) / arany;
}

static int32_t fx(double v) { return (int32_t)(v * 16.0); }

/* Returns the counted wrong pixels; *sky the sky pixels of the original. */
static long compare(level* lev, long* sky, long* near_edge) {
	double minx = 1e30, miny = 1e30, maxx = -1e30, maxy = -1e30;
	for (int i = 0; i < lev->npoly; ++i)
		for (int j = 0; j < lev->count[i]; ++j) {
			const double x = lev->pts[i][j].x, y = -lev->pts[i][j].y;
			if (x < minx) minx = x;
			if (x > maxx) maxx = x;
			if (y < miny) miny = y;
			if (y > maxy) maxy = y;
		}
	ox = minx - 10000 / ARANY;
	oy = miny - 1000 / ARANY;
	meghelyez(&ox, ARANY);
	meghelyez(&oy, ARANY);
	const int width = ((maxx + 10000 / ARANY) - ox) * ARANY;
	const int rows = ((maxy + 1000 / ARANY) - oy) * ARANY;

	int nseg = 0;
	for (int i = 0; i < lev->npoly; ++i) nseg += lev->count[i];
	gpu_seg* segs = malloc(sizeof(gpu_seg) * (nseg ? nseg : 1));
	row* ref = calloc(rows + 1, sizeof(row));
	for (int y = 0; y < rows; ++y) push(&ref[y], 1, 1);
	nseg = 0;
	for (int i = 0; i < lev->npoly; ++i)
		for (int j = 0; j < lev->count[i]; ++j) {
			const vec a = lev->pts[i][j], b = lev->pts[i][(j + 1) % lev->count[i]];
			/* Physics coordinates are upside down (szakasz.cpp): */
			const double ax = a.x, ay = -a.y, bx = b.x, by = -b.y;
			gpu_seg* g = &segs[nseg++];
			g->x0 = fx((ax - ox) * ARANY);
			g->y0 = fx((ay - oy) * ARANY);
			g->x1 = fx((bx - ox) * ARANY);
			g->y1 = fx((by - oy) * ARANY);
			/* ecset::addszakasz */
			double rx = (ax - ox) * ARANY - 0.5, ry = (ay - oy) * ARANY - 0.5;
			double vx = (bx - ax) * ARANY, vy = (by - ay) * ARANY;
			const int ground = vy < 0;
			if (vy < 0) {
				rx += vx;
				ry += vy;
				vx = -vx;
				vy = -vy;
			}
			if (vy < 0.001) continue;
			const int y1 = ry + 1, y2 = ry + vy;
			const double m = vx / vy, dy1 = ry, dy2 = ry + vy, dx1 = rx, dx2 = rx + vx;
			const double aa = (dx2 * dy1 - dx1 * dy2) / (dy1 - dy2);
			for (int y = y1; y <= y2; y++)
				if (y >= 0 && y < rows) push(&ref[y], (int)(m * y + aa + 1.0), ground);
		}
	gpu_trap* traps;
	const int ntraps = gpu_make_traps(segs, nseg, width * 16, &traps);

	long wrong = 0;
	*sky = 0;
	*near_edge = 0;
	unsigned char* state = malloc(width + 2);
	unsigned char* edge = malloc(width + 2);
	/* Every row of a small level, a sample of the rows of a big one: */
	long step = (long)width * rows / 20000000 + 1;
	const char* ppm = getenv("TRAPS_PPM");
	unsigned char* img = 0;
	const int iw = width / 4 + 1, ih = rows / 4 + 1;
	if (ppm) {
		step = 1;
		img = calloc((size_t)iw * ih, 3);
	}
	for (int y = 0; y < rows; ++y) {
		row* r = &ref[y];
		if (y % step) {
			free(r->c);
			continue;
		}
		rendez(r);
		for (int k = 0; k < r->n; ++k) {
			const int x0 = r->c[k].x < 0 ? 0 : r->c[k].x;
			const int x1 = k + 1 < r->n ? r->c[k + 1].x : width;
			for (int x = x0; x < x1 && x < width; ++x) state[x] = !r->c[k].ground;
		}
		if (r->c[0].x > 0) memset(state, 0, r->c[0].x < width ? r->c[0].x : width);
		memset(edge, 0, width);
		const int32_t yc = y * 16 + 8;
		for (int t = 0; t < ntraps; ++t) {
			const gpu_trap* tr = &traps[t];
			if (yc <= tr->y0 || yc > tr->y1) continue;
			const double f = (double)(yc - tr->y0) / (tr->y1 - tr->y0);
			const double xl = (tr->xl0 + (tr->xl1 - tr->xl0) * f) / 16.0;
			const double xr = (tr->xr0 + (tr->xr1 - tr->xr0) * f) / 16.0;
			for (int x = (int)floor(xl - 1); x <= (int)ceil(xr + 1); ++x) {
				if (x < 0 || x >= width) continue;
				const double c = x + 0.5;
				if (fabs(c - xl) < 0.125 || fabs(c - xr) < 0.125) edge[x] = 1;
				if (c > xl && c <= xr) state[x] ^= 2;
			}
		}
		if (getenv("TRAPS_MAP") && y % 48 == 0) {
			for (int x = 0; x < width; x += 24) {
				const int o = state[x] & 1, t = (state[x] >> 1) & 1;
				putchar(o == t ? (o ? ' ' : '.') : (o ? 'O' : 'X'));
			}
			putchar('\n');
		}
		if (img)
			for (int x = 0; x < width; ++x) {
				const int o = state[x] & 1, t = (state[x] >> 1) & 1;
				unsigned char* q = img + 3 * ((size_t)(ih - 1 - y / 4) * iw + x / 4);
				if (o != t && !edge[x]) {
					q[0] = o ? 255 : 0, q[1] = 0, q[2] = o ? 0 : 255;
				} else if (q[1] == 0 && q[0] == 0 && q[2] == 0)
					q[1] = o ? 200 : 60, q[0] = q[2] = o ? 200 : 60;
			}
		for (int x = 1; x < width; ++x) {
			const int original = state[x] & 1;
			const int traps_sky = (state[x] >> 1) & 1;
			*sky += original;
			if (original != traps_sky) {
				if (edge[x])
					(*near_edge)++;
				else {
					if (getenv("TRAPS_WHERE") && (wrong % atol(getenv("TRAPS_WHERE"))) == 0) {
						printf("row %d x %d original %d\n", y, x, original);
						for (int k = 0; k < r->n; ++k) printf("  crossing %d %s\n", r->c[k].x, r->c[k].ground ? "ground" : "sky");
						for (int t = 0; t < ntraps; ++t) {
							const gpu_trap* tr = &traps[t];
							if (yc <= tr->y0 || yc > tr->y1) continue;
							const double f = (double)(yc - tr->y0) / (tr->y1 - tr->y0);
							printf("  trap %d y %.2f..%.2f x %.2f..%.2f\n", t, tr->y0 / 16.0, tr->y1 / 16.0,
							       (tr->xl0 + (tr->xl1 - tr->xl0) * f) / 16.0, (tr->xr0 + (tr->xr1 - tr->xr0) * f) / 16.0);
						}
					}
					wrong++;
				}
			}
		}
		free(r->c);
	}
	if (img) {
		FILE* f = fopen(ppm, "wb");
		fprintf(f, "P6\n%d %d\n255\n", iw, ih);
		fwrite(img, 3, (size_t)iw * ih, f);
		fclose(f);
		free(img);
	}
	free(state);
	free(edge);
	free(ref);
	free(segs);
	free(traps);
	return wrong;
}

static void synthetic(level* lev, int seed) {
	/* Groups side by side of nested polygons (radius 40, 29, 18, 7 m, 6
	 * to 9 vertices, so they never cross), each of random direction: holes
	 * of the wrong direction, sky inside ground ... */
	srand(seed);
	lev->npoly = 0;
	lev->count = malloc(sizeof(int) * 16);
	lev->pts = malloc(sizeof(vec*) * 16);
	const int groups = 1 + rand() % 3;
	for (int g = 0; g < groups; ++g) {
		const int depth = 1 + rand() % 4;
		for (int i = 0; i < depth; ++i) {
			const double rr = 40.0 - 11.0 * i, cx = g * 100.0, cy = (rand() % 3) * 0.5;
			const int k = 6 + rand() % 4;
			const double turn = (rand() % 100) / 100.0;
			vec* p = malloc(sizeof(vec) * k);
			for (int j = 0; j < k; ++j) {
				const double a = 6.2831853 * (j + turn) / k;
				p[j].x = cx + rr * cos(a);
				p[j].y = cy + rr * sin(a);
			}
			if (rand() % 2)
				for (int j = 0; j < k / 2; ++j) {
					vec t = p[j];
					p[j] = p[k - 1 - j];
					p[k - 1 - j] = t;
				}
			lev->count[lev->npoly] = k;
			lev->pts[lev->npoly++] = p;
		}
	}
}

int main(int argc, char** argv) {
	int failed = 0, tested = 0;
	for (int i = 0; i < 40; ++i) {
		level lev;
		synthetic(&lev, i + 1);
		long sky, near_edge;
		const long wrong = compare(&lev, &sky, &near_edge);
		tested++;
		if (wrong * 1000 > sky) printf("diff synthetic %d: %ld of %ld sky pixels wrong (%ld at edges)\n", i, wrong, sky, near_edge);
		if (wrong * 10 > sky) failed++;
	}
	long all_wrong = 0, all_sky = 0, all_near = 0;
	for (int a = 1; a < argc; ++a) {
		level lev;
		if (!read_level(argv[a], &lev)) {
			printf("skip %s\n", argv[a]);
			continue;
		}
		long sky, near_edge;
		const long wrong = compare(&lev, &sky, &near_edge);
		tested++;
		all_wrong += wrong;
		all_sky += sky;
		all_near += near_edge;
		if (wrong * 1000 > sky) printf("diff %s: %ld of %ld sky pixels wrong (%ld at edges)\n", argv[a], wrong, sky, near_edge);
		if (wrong * 10 > sky) failed++;
	}
	if (all_wrong * 2000 > all_sky) failed++;
	printf("%s: %d levels, %ld of %ld sky pixels wrong away from edges, %ld within 1/8 pixel of an edge\n",
	       failed ? "FAIL" : "PASS", tested, all_wrong, all_sky, all_near);
	return failed ? 1 : 0;
}
