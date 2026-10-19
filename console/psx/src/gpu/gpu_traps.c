/* The sky of a level as trapezoids, see gpu_traps.h. */
#include <stdlib.h>
#include <string.h>

#include "gpu_traps.h"

typedef struct {
	int32_t x0, y0, x1, y1; /* y0 < y1 */
	uint8_t ground;         /* crossing it gives ground */
	uint8_t open;           /* a sky trapezoid is open to its right */
	int32_t open_y0;        /* ... from this height */
	int32_t open_right;     /* ... up to this edge (-1: right_x) */
	int seg;                /* its place in the segment list */
	int twin;               /* edges with the same ends have the same twin */
	int64_t slope;          /* dx/dy with 16 fraction bits (estimates) */
} edge;

typedef struct {
	edge* edges;
	gpu_trap* traps;
	int ntraps, cap;
	int32_t right_x;
	int failed;
} sweep;

/* x of the edge at height y (y0 <= y <= y1), rounded down. */
static int32_t edge_x(const edge* e, int32_t y) {
	const int64_t num = (int64_t)(y - e->y0) * (e->x1 - e->x0);
	const int32_t dy = e->y1 - e->y0;
	int64_t q = num / dy;
	if (num % dy != 0 && num < 0) q--;
	return e->x0 + (int32_t)q;
}

static void push_trap(sweep* s, int32_t y0, int32_t y1, int32_t xl0, int32_t xl1, int32_t xr0, int32_t xr1) {
	if (y1 <= y0 || s->failed) return;
	if (s->ntraps == s->cap) {
		const int cap = s->cap ? s->cap * 2 : 1024;
		gpu_trap* t = (gpu_trap*)malloc(cap * sizeof(gpu_trap));
		if (!t) {
			s->failed = 1;
			return;
		}
		if (s->ntraps) memcpy(t, s->traps, s->ntraps * sizeof(gpu_trap));
		free(s->traps);
		s->traps = t;
		s->cap = cap;
	}
	gpu_trap* t = &s->traps[s->ntraps++];
	t->y0 = y0;
	t->y1 = y1;
	t->xl0 = xl0;
	t->xl1 = xl1;
	t->xr0 = xr0;
	t->xr1 = xr1;
}

static void close_trap(sweep* s, edge* e, int32_t y) {
	if (!e->open) return;
	e->open = 0;
	int32_t xr0 = s->right_x, xr1 = s->right_x;
	if (e->open_right >= 0) {
		const edge* r = &s->edges[e->open_right];
		xr0 = edge_x(r, e->open_y0);
		xr1 = edge_x(r, y);
	}
	push_trap(s, e->open_y0, y, edge_x(e, e->open_y0), edge_x(e, y), xr0, xr1);
}

/* The same, estimated (within a few 1/16 pixels). */
static int32_t edge_x_fast(const edge* e, int32_t y) {
	return e->x0 + (int32_t)(((int64_t)(y - e->y0) * e->slope) >> 16);
}

/* Whether edge k goes on the right of edge a in a band where both are
 * active, compared in its middle (mid): edges do not cross, but next to a
 * vertex they may touch. Edges meeting there are ordered by slope. */
static int right_of(const edge* k, const edge* a, int32_t mid) {
	if (k->twin >= 0 && k->twin == a->twin) return 1;
	const int32_t d = edge_x(k, mid) - edge_x(a, mid);
	if (d > 1) return 1;
	if (d < -1) return 0;
	/* Compare the slopes dx/dy (the dy are positive): */
	const int64_t lhs = (int64_t)(k->x1 - k->x0) * (a->y1 - a->y0);
	const int64_t rhs = (int64_t)(a->x1 - a->x0) * (k->y1 - k->y0);
	if (lhs != rhs) return lhs > rhs;
	/* On each other: after it, so twins follow each other. */
	return 1;
}

/* The order of edges at the bottom of a band (xa, xbv: their x there),
 * edges meeting there by the direction they go up in. */
static int left_of(int32_t xa, const edge* a, int32_t xbv, const edge* b) {
	const int32_t d = xa - xbv;
	if (d < -3) return 1;
	if (d > 3) return 0;
	return a->slope < b->slope;
}

/* The original cancels crossings of the same pixel (ecset.cpp, rendez): of
 * the first two at the same place one goes if they set the same state,
 * both if not, again and again. Edges on each other do the same on every
 * row; states[] in the order of the segments, returns the state left (1
 * ground, 0 sky) or -1 if none. */
static int cancel(const uint8_t* states, int n) {
	uint8_t s[64];
	if (n > 64) n = 64;
	memcpy(s, states, n);
	while (n >= 2) {
		if (s[0] == s[1]) {
			memmove(&s[1], &s[2], n - 2);
			n--;
		} else {
			memmove(&s[0], &s[2], n - 2);
			n -= 2;
		}
	}
	return n ? s[0] : -1;
}

typedef int (*edge_less)(const edge* a, const edge* b);
static int less_y0(const edge* a, const edge* b) { return a->y0 < b->y0; }
static int less_y1(const edge* a, const edge* b) { return a->y1 < b->y1; }
static int less_ends(const edge* a, const edge* b) {
	if (a->x0 != b->x0) return a->x0 < b->x0;
	if (a->y0 != b->y0) return a->y0 < b->y0;
	if (a->x1 != b->x1) return a->x1 < b->x1;
	return a->y1 < b->y1;
}

/* Shell sort of edge indices. */
static void sort_by(const edge* edges, int* idx, int n, edge_less less) {
	for (int gap = n / 2; gap > 0; gap /= 2)
		for (int i = gap; i < n; ++i) {
			const int v = idx[i];
			int j = i;
			while (j >= gap && less(&edges[v], &edges[idx[j - gap]])) {
				idx[j] = idx[j - gap];
				j -= gap;
			}
			idx[j] = v;
		}
}

int gpu_make_traps(const gpu_seg* segs, int n, int32_t right_x, gpu_trap** out) {
	sweep s;
	memset(&s, 0, sizeof(s));
	s.right_x = right_x;
	*out = NULL;
	const int m = n ? n : 1;
	s.edges = (edge*)malloc(m * sizeof(edge));
	int* by_y0 = (int*)malloc(m * sizeof(int));
	int* by_y1 = (int*)malloc(m * sizeof(int));
	int* active = (int*)malloc(m * sizeof(int));
	int* eff = (int*)malloc(m * sizeof(int));
	uint8_t* eff_ground = (uint8_t*)malloc(m);
	int32_t* xb = (int32_t*)malloc(m * sizeof(int32_t)); /* x of the active edges at y */
	int32_t* xt = (int32_t*)malloc(m * sizeof(int32_t)); /* ... at the top of the band */
	if (!s.edges || !by_y0 || !by_y1 || !active || !eff || !eff_ground || !xb || !xt) {
		free(xb);
		free(xt);
		free(s.edges);
		free(by_y0);
		free(by_y1);
		free(active);
		free(eff);
		free(eff_ground);
		return 0;
	}
	int nedges = 0;
	for (int i = 0; i < n; ++i) {
		const gpu_seg* g = &segs[i];
		if (g->y0 == g->y1) continue; /* horizontal: crosses no row */
		edge* e = &s.edges[nedges++];
		e->ground = g->y1 < g->y0;
		if (g->y0 < g->y1) {
			e->x0 = g->x0, e->y0 = g->y0, e->x1 = g->x1, e->y1 = g->y1;
		} else {
			e->x0 = g->x1, e->y0 = g->y1, e->x1 = g->x0, e->y1 = g->y0;
		}
		e->open = 0;
		e->seg = i;
		e->twin = -1;
		e->slope = ((int64_t)(e->x1 - e->x0) * 65536) / (e->y1 - e->y0);
	}
	/* Edges that lie on each other (ends less than a pixel apart, e.g. a
	 * polygon drawn twice): their crossings of a row fall on the same pixel
	 * in the original and cancel there (see cancel), so they are handled
	 * together. */
	for (int i = 0; i < nedges; ++i) by_y0[i] = i;
	sort_by(s.edges, by_y0, nedges, less_ends);
	for (int i = 0; i < nedges; ++i) {
		edge* a = &s.edges[by_y0[i]];
		for (int j = i + 1; j < nedges; ++j) {
			edge* b = &s.edges[by_y0[j]];
			if (b->x0 - a->x0 >= 16) break;
			if (abs(b->y0 - a->y0) < 16 && abs(b->x1 - a->x1) < 16 && abs(b->y1 - a->y1) < 16) {
				if (a->twin < 0) a->twin = by_y0[i];
				if (b->twin < 0) b->twin = a->twin;
			}
		}
	}
	for (int i = 0; i < nedges; ++i) by_y0[i] = by_y1[i] = i;
	sort_by(s.edges, by_y0, nedges, less_y0);
	sort_by(s.edges, by_y1, nedges, less_y1);

	int nactive = 0, ia = 0, ib = 0;
	int32_t y = nedges ? s.edges[by_y0[0]].y0 : 0;
	while (ia < nedges || nactive > 0) {
		/* The edges ending here: */
		while (ib < nedges && s.edges[by_y1[ib]].y1 <= y) {
			const int k = by_y1[ib++];
			for (int i = 0; i < nactive; ++i)
				if (active[i] == k) {
					close_trap(&s, &s.edges[k], y);
					memmove(&active[i], &active[i + 1], (nactive - 1 - i) * sizeof(int));
					nactive--;
					break;
				}
		}
		/* The next event: the next end or start (an edge not started yet
		 * ends after it starts). */
		int ia_end = ia;
		while (ia_end < nedges && s.edges[by_y0[ia_end]].y0 <= y) ia_end++;
		int32_t next = INT32_MAX;
		if (ib < nedges) next = s.edges[by_y1[ib]].y1;
		if (ia_end < nedges && s.edges[by_y0[ia_end]].y0 < next) next = s.edges[by_y0[ia_end]].y0;
		int32_t top = next == INT32_MAX ? y : next;
		const int32_t middle = y + (top - y) / 2;
		/* The edges starting here, in their place (binary search; the
		 * active edges are ordered by x, and keep the order as they do
		 * not cross): */
		while (ia < ia_end) {
			const int k = by_y0[ia++];
			int lo = 0, hi = nactive;
			while (lo < hi) {
				const int m = (lo + hi) / 2;
				if (right_of(&s.edges[k], &s.edges[active[m]], middle))
					lo = m + 1;
				else
					hi = m;
			}
			memmove(&active[lo + 1], &active[lo], (nactive - lo) * sizeof(int));
			active[lo] = k;
			nactive++;
		}
		/* Polygons of a faulty level may cross: the order is checked again
		 * from the bottom of the band, and the band ends where two
		 * neighbours change places (the original sorts every row). */
		for (int i = 0; i < nactive; ++i) xb[i] = edge_x_fast(&s.edges[active[i]], y);
		for (int i = 1; i < nactive; ++i) {
			const int v = active[i];
			const int32_t xv = xb[i];
			int j = i;
			while (j > 0 && left_of(xv, &s.edges[v], xb[j - 1], &s.edges[active[j - 1]])) {
				active[j] = active[j - 1];
				xb[j] = xb[j - 1];
				j--;
			}
			active[j] = v;
			xb[j] = xv;
		}
		if (next != INT32_MAX) {
			for (int i = 0; i < nactive; ++i) xt[i] = edge_x_fast(&s.edges[active[i]], next);
			int32_t first = next;
			for (int i = 0; i + 1 < nactive; ++i) {
				const edge* a = &s.edges[active[i]];
				const edge* b = &s.edges[active[i + 1]];
				if (xt[i + 1] - xt[i] < -2 && a->slope > b->slope) {
					const int32_t gap = xb[i + 1] - xb[i];
					const int64_t dy = ((int64_t)(gap < 0 ? 0 : gap) << 16) / (a->slope - b->slope);
					const int32_t cross = y + (int32_t)(dy > 0 ? dy : 1);
					if (cross < first) first = cross;
				}
			}
			if (first < next) {
				next = first;
				for (int i = 0; i < nactive; ++i) xt[i] = edge_x_fast(&s.edges[active[i]], next);
			}
		} else
			for (int i = 0; i < nactive; ++i) xt[i] = xb[i];
		top = next == INT32_MAX ? y : next;
		/* The edges that count: neighbours less than a pixel apart all the
		 * way up the band (an edge drawn twice, a frame on a frame) cancel
		 * as the original's crossings of one pixel (by segment order). */
		int ne = 0;
		for (int i = 0; i < nactive;) {
			int j = i + 1;
			while (j < nactive) {
				const edge* a = &s.edges[active[j - 1]];
				const edge* b = &s.edges[active[j]];
				/* A pixel apart across the edges: for flat edges that is
				 * more than a pixel along the row. */
				int64_t steep = a->slope < 0 ? -a->slope : a->slope;
				const int64_t sb = b->slope < 0 ? -b->slope : b->slope;
				if (sb > steep) steep = sb;
				const int64_t limit = steep > 65536 ? (16 * steep) >> 16 : 16;
				const int32_t d0 = xb[j] - xb[j - 1];
				const int32_t d1 = xt[j] - xt[j - 1];
				/* ... and parallel: edges meeting at a vertex do not cancel
				 * on the rows next to it. */
				if ((d0 < 0 ? -(int64_t)d0 : d0) >= limit || (d1 < 0 ? -(int64_t)d1 : d1) >= limit || abs(d1 - d0) > 16) break;
				j++;
			}
			if (j - i == 1) {
				eff[ne] = active[i];
				eff_ground[ne++] = s.edges[active[i]].ground;
			} else {
				int members[64];
				uint8_t states[64];
				int count = 0;
				for (int k = i; k < j && count < 64; ++k) {
					const int v = active[k];
					int q = count++;
					while (q > 0 && s.edges[members[q - 1]].seg > s.edges[v].seg) {
						members[q] = members[q - 1];
						q--;
					}
					members[q] = v;
				}
				for (int k = 0; k < count; ++k) states[k] = s.edges[members[k]].ground;
				const int state = cancel(states, count);
				for (int k = i + 1; k < j; ++k) close_trap(&s, &s.edges[active[k]], y);
				if (state >= 0) {
					eff[ne] = active[i];
					eff_ground[ne++] = (uint8_t)state;
				} else
					close_trap(&s, &s.edges[active[i]], y);
			}
			i = j;
		}
		/* Sky right of an edge that gives sky, up to the next edge: */
		for (int i = 0; i < ne; ++i) {
			edge* l = &s.edges[eff[i]];
			const int r = i + 1 < ne ? eff[i + 1] : -1;
			const int ground = eff_ground[i];
			if (l->open && (ground || l->open_right != r)) close_trap(&s, l, y);
			if (!ground && !l->open) {
				l->open = 1;
				l->open_y0 = y;
				l->open_right = r;
			}
		}
		if (next == INT32_MAX) break;
		y = next;
	}
	for (int i = 0; i < nactive; ++i) close_trap(&s, &s.edges[active[i]], y);
	free(s.edges);
	free(by_y0);
	free(by_y1);
	free(active);
	free(eff);
	free(eff_ground);
	free(xb);
	free(xt);
	if (s.failed) {
		free(s.traps);
		return 0;
	}
	*out = s.traps;
	return s.ntraps;
}
