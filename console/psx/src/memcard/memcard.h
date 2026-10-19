/* Memory card saves for the PS1 port (slot 1, "bu00:").
 *
 * The game keeps the files it writes (state.dat, ...) in the RAM file layer
 * (psx_file.h). This module stores them in ONE standard memory card save
 * file (BIOS browser header, title, 16x16 icon) in compressed form, and puts
 * them back into the RAM layer at boot.
 *
 * Calls block: memcard_save() takes about a second on real hardware (BIOS
 * sector writes, 1-3 blocks), memcard_load() a fraction of that. Call them
 * from menus or at boot, never in a level. Status codes are returned by
 * every call; memcard_message() gives a short on-screen text.
 *
 * The code that needs the card assumes a PSn00bSDK BIOS environment; the
 * compression (mclz.h) is plain C. */
#ifndef ELMA_PSX_MEMCARD_H
#define ELMA_PSX_MEMCARD_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum {
	MC_OK = 0,
	MC_NO_CARD,      /* no card in slot 1 */
	MC_UNFORMATTED,  /* card present but not formatted (never formatted by us) */
	MC_FULL,         /* not enough free blocks */
	MC_WRITE_ERROR,  /* the BIOS failed to create or write the file */
	MC_NO_SAVE,      /* card fine, but no save of this game on it yet */
	MC_CORRUPT,      /* save found but damaged (CRC or format); ignored */
	MC_NOT_FOUND,    /* load: the save does not contain this file */
	MC_NO_MEMORY,
	MC_BAD_ARG,      /* save: the file is not in the RAM layer, or too many files */
	MC_NOT_INIT
};

/* Sets up the BIOS card driver. Call AFTER InitPAD() and BEFORE StartPAD()
 * (it runs InitCARD(1), StartCARD(), _bu_init()). Returns the probe status
 * (MC_OK, MC_NO_CARD or MC_UNFORMATTED); a missing card is not fatal and can
 * appear later, every other call probes again. */
int memcard_init(void);

/* Reads the save once (the contents stay cached in compressed form) and
 * writes the file `path` into the RAM layer with psx_fopen/psx_fwrite.
 * MC_OK, or MC_NO_SAVE / MC_NOT_FOUND (nothing restored, not an error),
 * MC_NO_CARD, MC_UNFORMATTED, MC_CORRUPT. */
int memcard_load(const char* path);

/* Takes the current contents of the RAM file `path`, updates its entry and
 * rewrites the save file. MC_OK or an error code. */
int memcard_save(const char* path);

/* Last status of any call, a short English message for a status, and
 * statistics of the last save (card blocks used, vblanks it blocked). */
int memcard_status(void);
const char* memcard_message(int status);
int memcard_last_blocks(void);
int memcard_last_frames(void);

#ifdef __cplusplus
}
#endif

#endif
