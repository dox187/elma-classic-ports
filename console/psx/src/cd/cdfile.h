/*
 * Adapter that turns a mounted ISO9660 volume into a psx_file_backend (see
 * ../psx_file.h), so that psx_fopen/psx_file_list serve files from the disc.
 *
 *   static cdtrack_vol vol;
 *   static cdfile_ctx ctx;
 *   static psx_file_backend backend;
 *   cdtrack_mount_data2(&vol);
 *   cdfile_init(&ctx, &vol.iso, &backend);
 *   psx_file_add_backend(&backend);
 *
 * Plain C on top of iso9660.h only, so it also works on the host.
 */
#ifndef CDFILE_H
#define CDFILE_H

#include "../psx_file.h"
#include "iso9660.h"

#ifdef __cplusplus
extern "C" {
#endif

#define CDFILE_MAX_OPEN 8
#define CDFILE_DIR_MAX 48

typedef struct cdfile_ctx {
    iso_vol *vol;
    iso_entry files[CDFILE_MAX_OPEN];
    unsigned char used[CDFILE_MAX_OPEN];
    /* Cursor of the last directory listing so that listing a directory
     * index by index does not rescan it from the start every time. */
    char cursor_dir[CDFILE_DIR_MAX];
    iso_dir cursor;
    int cursor_next; /* index the cursor delivers next, -1 = no cursor */
} cdfile_ctx;

/* Fills *backend (name "cd"); ctx and vol must outlive it. */
void cdfile_init(cdfile_ctx *ctx, iso_vol *vol, psx_file_backend *backend);

#ifdef __cplusplus
}
#endif

#endif
