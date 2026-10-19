/* The part of <unistd.h> the game core uses: access() to see whether a file
 * exists (psx_file.c). */
#ifndef ELMA_PSX_UNISTD_H
#define ELMA_PSX_UNISTD_H

#ifdef __cplusplus
extern "C" {
#endif

#define F_OK 0
#define X_OK 1
#define W_OK 2
#define R_OK 4

int access(const char* path, int mode);

#ifdef __cplusplus
}
#endif

#endif
