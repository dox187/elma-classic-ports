/* The game core only seeds rand() with time() and clock(); both count from
 * the start of the program (psx_platform). */
#ifndef ELMA_PSX_TIME_H
#define ELMA_PSX_TIME_H

#ifdef __cplusplus
extern "C" {
#endif

typedef long time_t;
typedef long clock_t;
#define CLOCKS_PER_SEC 1000

time_t time(time_t* t);
clock_t clock(void);

#ifdef __cplusplus
}
#endif

#endif
