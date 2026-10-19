/* The sky of a level as trapezoids (used by gpu_level.cpp, tested on the
 * host by test/gpu_traps_host_test.c).
 *
 * The original renderer (ecset.cpp, addszakasz) fills every pixel row of
 * the level from the left with ground; each polygon edge the row crosses
 * sets the state from there on to ground if the edge points down (in the
 * level's y-up coordinates) and to sky if it points up. Between two edges
 * that follow each other on a row the state is that of the left one, so the
 * sky is made of trapezoids between consecutive edges of a horizontal band
 * in which no edge starts or ends; a sweep line from the bottom up finds
 * them, and a trapezoid goes on upwards as long as its two edges stay
 * neighbours. Coordinates are fixed point with 4 fraction bits. */
#ifndef GPU_TRAPS_H
#define GPU_TRAPS_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
	int32_t x0, y0, x1, y1; /* from (x0, y0) to (x1, y1) as in the polygon */
} gpu_seg;

typedef struct {
	int32_t y0, y1;   /* bottom and top */
	int32_t xl0, xl1; /* left edge at y0 and y1 */
	int32_t xr0, xr1; /* right edge at y0 and y1 */
} gpu_trap;

/* The sky trapezoids of the segments; right_x closes a sky band that has
 * no edge on its right. Returns their number and a malloc'd array in *out
 * (NULL on no memory). */
int gpu_make_traps(const gpu_seg* segs, int n, int32_t right_x, gpu_trap** out);

#ifdef __cplusplus
}
#endif

#endif
