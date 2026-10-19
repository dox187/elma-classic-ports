/*
 * Minimal read-only ISO9660 reader for the PlayStation port.
 *
 * Portable C99: no malloc, no stdio, no global state. The caller supplies
 * a 2048-byte sector buffer (optionally larger, see iso_set_window) and a callback that reads 2048-byte user-data
 * sectors by absolute LBA. Plain ISO9660 level 1 (and anything compatible
 * with it) is supported; Rock Ridge, Joliet, multi-extent files and
 * extended attributes are ignored. Every length and extent that comes from
 * the disc is bounds-checked.
 *
 * Typical use:
 *
 *   iso_vol v;
 *   int r = iso_mount(&v, my_read, ctx, sector_buf, track2_base, ISO_SCAN_DEFAULT);
 *   iso_entry e;
 *   r = iso_find(&v, "LEV/WARMUP.LEV", &e);
 *   iso_read(&v, &e, 0, e.size, dst);
 *
 *   iso_dir d;
 *   iso_opendir(&v, "LEV", &d);
 *   while (iso_readdir(&v, &d, &e) > 0) { ... e.name ... }
 */
#ifndef ISO9660_H
#define ISO9660_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define ISO_SECTOR_SIZE 2048u

/* The PS1 drive reports a track start (GetTD) rounded down to whole
 * seconds, i.e. up to 74 sectors too early, so the descriptor is searched
 * this many sectors from base + 16. */
#define ISO_SCAN_DEFAULT 80u

#define ISO_NAME_MAX 32 /* longest stored name, with terminator */
#define ISO_NO_LBA 0xFFFFFFFFu

/* Return codes: >= 0 success, < 0 error. */
#define ISO_OK 0
#define ISO_ERR_READ (-1)      /* read callback failed */
#define ISO_ERR_NOT_FOUND (-2) /* no descriptor / no such file */
#define ISO_ERR_CORRUPT (-3)   /* inconsistent or out of range data */
#define ISO_ERR_BADARG (-4)    /* wrong argument, e.g. not a directory */
#define ISO_ERR_RANGE (-5)     /* read outside the file */

/* Reads `count` 2048-byte sectors starting at absolute LBA `lba` into
 * `dst`. Returns 0 on success. */
typedef int (*iso_read_fn)(void *ctx, uint32_t lba, uint32_t count, void *dst);

typedef struct iso_vol {
    iso_read_fn read;
    void *ctx;
    uint8_t *buf;          /* caller-owned sector buffer (window * 2048 bytes) */
    uint32_t window;       /* sectors per buffer refill, 1 unless iso_set_window */
    uint32_t buf_lba;      /* absolute LBA of the first sector in buf, or ISO_NO_LBA */
    uint32_t buf_count;    /* valid sectors in buf */
    uint32_t base;         /* absolute LBA of ISO sector 0 */
    uint32_t volume_size;  /* sectors, from the descriptor */
    uint32_t root_lba;     /* ISO-relative */
    uint32_t root_size;    /* bytes */
} iso_vol;

#define ISO_FLAG_DIR 0x02u

typedef struct iso_entry {
    char name[ISO_NAME_MAX]; /* identifier, ";version" and trailing '.' stripped */
    uint32_t lba;            /* ISO-relative extent */
    uint32_t size;           /* bytes */
    uint8_t flags;           /* ISO_FLAG_* (directory flag = 0x02) */
} iso_entry;

typedef struct iso_dir {
    uint32_t lba;  /* ISO-relative start of the directory */
    uint32_t size; /* bytes */
    uint32_t pos;  /* byte offset of the next record */
} iso_dir;

/* Mounts the volume whose track starts at (or up to `scan` sectors after)
 * the absolute LBA `base`: looks for the primary volume descriptor at
 * base+16 .. base+16+scan-1. Sectors that cannot be read are skipped. On
 * success v->base is the real start of the ISO image. */
int iso_mount(iso_vol *v, iso_read_fn read, void *ctx, void *sector_buf,
              uint32_t base, uint32_t scan);

/* Optional speed-up for slow media: after a successful mount, hands the
 * reader a bigger buffer of `sectors` * 2048 bytes (sectors a power of two,
 * e.g. 8). Directory and partial-sector reads then fetch aligned groups of
 * sectors in one request instead of one request per sector. The buffer
 * must stay valid as long as the volume is used. */
int iso_set_window(iso_vol *v, void *buf, uint32_t sectors);

/* Absolute LBA of an ISO-relative extent (what the CD driver needs). */
uint32_t iso_abs_lba(const iso_vol *v, uint32_t lba);

/* Finds a file or directory by path: '/' or '\' separated, case
 * insensitive, ";1" ignored, an empty path or "/" is the root. */
int iso_find(iso_vol *v, const char *path, iso_entry *out);

/* Opens a directory by path, or from an entry found earlier. */
int iso_opendir(iso_vol *v, const char *path, iso_dir *d);
int iso_opendir_entry(iso_vol *v, const iso_entry *e, iso_dir *d);

/* Returns 1 and fills *out with the next entry ("." and ".." are skipped),
 * 0 at the end of the directory, or a negative error. */
int iso_readdir(iso_vol *v, iso_dir *d, iso_entry *out);

/* Reads `len` bytes from byte `offset` of a file. Returns the number of
 * bytes read (clamped at the end of the file, so 0 at/after EOF) or a
 * negative error. `dst` receives whole sectors straight from the
 * callback, so the callback must cope with its alignment. */
int32_t iso_read(iso_vol *v, const iso_entry *e, uint32_t offset, uint32_t len,
                 void *dst);

#ifdef __cplusplus
}
#endif

#endif
