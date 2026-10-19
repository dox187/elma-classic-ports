/*
 * PSn00bSDK glue: finds the data tracks of the disc and mounts them with
 * the ISO9660 reader (iso9660.h).
 *
 * Disc layout: track 1 is the bootable program (SYSTEM.CNF + PS-EXE); the
 * game data is a plain ISO9660 image on the second data track. The TOC
 * (GetTN/GetTD) gives the track start only rounded down to whole seconds,
 * so the descriptor is searched a few sectors forward (see iso_mount).
 * The drive is read in the 2048-byte data mode, which works for MODE2 Form 1
 * (track 1) and MODE1 sectors (track 2) alike.
 *
 * Usage (after ResetGraph, interrupts enabled):
 *
 *   static cdtrack_vol vol;
 *   cdtrack_init();
 *   if (cdtrack_mount_data2(&vol) != ISO_OK)    // track 2, else:
 *       cdtrack_mount(&vol, 1);                 // files on track 1
 *   iso_find(&vol.iso, "LEV/WARMUP.LEV", &e);
 *   iso_read(&vol.iso, &e, 0, e.size, buffer);
 *
 * Everything is blocking. Only one cdtrack_vol may read at a time; the
 * drive is not shared with CD audio or XA streaming while a read runs.
 */
#ifndef CDTRACK_H
#define CDTRACK_H

#include <stdint.h>

#include "iso9660.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Sectors per CdRead request. Bigger requests mean fewer re-seeks; a read
 * error repeats the whole request. */
#define CDTRACK_CHUNK_SECTORS 64
/* Attempts per request before the read fails (each one retried by the BIOS
 * library as well). */
#define CDTRACK_RETRIES 3
/* Tracks 2..(1 + CDTRACK_MAX_DATA_SEARCH) are tried by cdtrack_mount_data2. */
#define CDTRACK_MAX_DATA_SEARCH 3
/* Sectors the reader fetches per request for directories and partial
 * sectors (see iso_set_window); 8 sectors = 16 KB per volume. */
#define CDTRACK_WINDOW 8

typedef struct cdtrack_vol {
    iso_vol iso;                                       /* pass &vol.iso to the iso_* functions */
    uint32_t sector[CDTRACK_WINDOW * ISO_SECTOR_SIZE / 4]; /* the reader's buffer, word aligned */
    int track;                                         /* mounted track number, 0 if none */
    int track_base;                                    /* LBA the TOC gave (rounded down) */
} cdtrack_vol;

/* Initializes the CD library (idempotent). 0 when the drive is ready,
 * -1 on error. Call ResetGraph first. */
int cdtrack_init(void);

/* First and last track from the TOC. 0 or -1. */
int cdtrack_tracks(int *first, int *last);

/* Start of a track as an LBA (LBA 0 = 00:02:00), rounded down to a whole
 * second as the drive reports it, or -1. */
int cdtrack_track_base(int track);

/* Mounts the ISO9660 volume that starts on the given track (1 = the boot
 * track). Returns ISO_OK or a negative ISO_ERR_*; on success vol->iso is
 * ready and vol->iso.base is the exact start of the volume. */
int cdtrack_mount(cdtrack_vol *vol, int track);

/* Mounts the first of the tracks after track 1 that holds an ISO9660
 * volume (the game data). ISO_ERR_NOT_FOUND when the disc has only one
 * track or none of them has a descriptor. */
int cdtrack_mount_data2(cdtrack_vol *vol);

/* Reads `count` 2048-byte sectors at an absolute LBA. This is the callback
 * given to iso_mount; it can also be used directly. Returns 0 or -1.
 * A destination that is not word aligned is read one sector at a time
 * through a bounce buffer, which is slower. */
int cdtrack_read(void *ctx, uint32_t lba, uint32_t count, void *dst);

#ifdef __cplusplus
}
#endif

#endif
