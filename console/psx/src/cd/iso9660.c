/* Minimal read-only ISO9660 reader, see iso9660.h. */
#include "iso9660.h"

#include <string.h>

#define PVD_SECTOR 16u
#define DIR_REC_MIN 34u /* 33 fixed bytes + 1 identifier byte */

static uint32_t rd_le32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

static uint32_t sectors_of(uint32_t bytes)
{
    return (bytes >> 11) + ((bytes & (ISO_SECTOR_SIZE - 1)) ? 1u : 0u);
}

/* True when [lba, lba + ceil(size / 2048)) lies inside the volume. */
static int extent_ok(const iso_vol *v, uint32_t lba, uint32_t size)
{
    uint32_t n = sectors_of(size);
    if (lba >= v->volume_size)
        return n == 0;
    return n <= v->volume_size - lba;
}

/* Makes the sector at an absolute LBA available and returns a pointer to
 * it (valid until the next load), or NULL on a read error. With a window
 * larger than one sector an aligned group of sectors is read at once. */
static const uint8_t *load(iso_vol *v, uint32_t abs_lba)
{
    if (v->buf_lba != ISO_NO_LBA && abs_lba >= v->buf_lba && abs_lba - v->buf_lba < v->buf_count)
        return v->buf + (size_t)(abs_lba - v->buf_lba) * ISO_SECTOR_SIZE;
    v->buf_lba = ISO_NO_LBA;
    v->buf_count = 0;
    if (v->window > 1 && abs_lba >= v->base && abs_lba - v->base < v->volume_size) {
        uint32_t rel = abs_lba - v->base;
        uint32_t start = rel & ~(v->window - 1);
        uint32_t n = v->volume_size - start;
        if (n > v->window)
            n = v->window;
        if (v->read(v->ctx, v->base + start, n, v->buf) == 0) {
            v->buf_lba = v->base + start;
            v->buf_count = n;
            return v->buf + (size_t)(rel - start) * ISO_SECTOR_SIZE;
        }
    }
    if (v->read(v->ctx, abs_lba, 1, v->buf) != 0)
        return 0;
    v->buf_lba = abs_lba;
    v->buf_count = 1;
    return v->buf;
}

int iso_set_window(iso_vol *v, void *buf, uint32_t sectors)
{
    if (!v || !buf || sectors == 0 || (sectors & (sectors - 1)) != 0)
        return ISO_ERR_BADARG;
    v->buf = (uint8_t *)buf;
    v->window = sectors;
    v->buf_lba = ISO_NO_LBA;
    v->buf_count = 0;
    return ISO_OK;
}

uint32_t iso_abs_lba(const iso_vol *v, uint32_t lba)
{
    return v->base + lba;
}

/* Checks a primary volume descriptor in sector buffer b and fills the
 * volume fields. Returns ISO_OK or ISO_ERR_CORRUPT. */
static int parse_pvd(iso_vol *v, const uint8_t *b)
{
    uint32_t vol_size = rd_le32(b + 80);
    uint32_t root_lba = rd_le32(b + 156 + 2);
    uint32_t root_size = rd_le32(b + 156 + 10);

    if (b[128] != 0x00 || b[129] != 0x08) /* logical block size 2048 */
        return ISO_ERR_CORRUPT;
    if (b[156] < DIR_REC_MIN || !(b[156 + 25] & ISO_FLAG_DIR))
        return ISO_ERR_CORRUPT;
    if (vol_size <= PVD_SECTOR || root_size == 0)
        return ISO_ERR_CORRUPT;
    v->volume_size = vol_size;
    if (!extent_ok(v, root_lba, root_size)) /* uses v->volume_size */
        return ISO_ERR_CORRUPT;
    v->root_lba = root_lba;
    v->root_size = root_size;
    return ISO_OK;
}

int iso_mount(iso_vol *v, iso_read_fn read, void *ctx, void *sector_buf,
              uint32_t base, uint32_t scan)
{
    uint32_t i;
    int err = ISO_ERR_READ; /* until some sector could be read */

    if (!v || !read || !sector_buf)
        return ISO_ERR_BADARG;
    v->read = read;
    v->ctx = ctx;
    v->buf = (uint8_t *)sector_buf;
    v->window = 1;
    v->buf_lba = ISO_NO_LBA;
    v->buf_count = 0;
    v->base = base;
    v->volume_size = 0;
    v->root_lba = 0;
    v->root_size = 0;

    for (i = 0; i < scan; i++) {
        uint32_t lba = base + PVD_SECTOR + i;
        const uint8_t *b;
        if (lba < base) /* wrapped around */
            break;
        b = load(v, lba);
        if (!b)
            continue;
        if (err == ISO_ERR_READ)
            err = ISO_ERR_NOT_FOUND;
        if (b[0] != 1 || memcmp(b + 1, "CD001", 5) != 0 || b[6] != 1)
            continue;
        if (parse_pvd(v, b) == ISO_OK) {
            v->base = base + i; /* ISO sector 0 = descriptor sector - 16 */
            return ISO_OK;
        }
        err = ISO_ERR_CORRUPT;
    }
    v->volume_size = 0;
    return err;
}

/* ---- directories ------------------------------------------------------- */

static int open_extent(iso_vol *v, uint32_t lba, uint32_t size, iso_dir *d)
{
    if (size == 0 || !extent_ok(v, lba, size))
        return ISO_ERR_CORRUPT;
    d->lba = lba;
    d->size = size;
    d->pos = 0;
    return ISO_OK;
}

int iso_opendir_entry(iso_vol *v, const iso_entry *e, iso_dir *d)
{
    if (!v || !e || !d || !(e->flags & ISO_FLAG_DIR))
        return ISO_ERR_BADARG;
    return open_extent(v, e->lba, e->size, d);
}

/* Parsed directory record; id points into the sector buffer and is only
 * valid until the next load. */
typedef struct rec {
    const uint8_t *id;
    uint32_t id_len;
    uint32_t lba, size;
    uint8_t flags;
} rec;

/* Returns 1 with *r set, 0 at the end, or an error. "." and ".." skipped. */
static int next_rec(iso_vol *v, iso_dir *d, rec *r)
{
    while (d->pos < d->size) {
        uint32_t off = d->pos & (ISO_SECTOR_SIZE - 1);
        uint32_t len, id_len;
        const uint8_t *p = load(v, v->base + d->lba + (d->pos >> 11));
        if (!p)
            return ISO_ERR_READ;
        p += off;
        len = p[0];
        if (len == 0) { /* padding up to the next sector */
            d->pos = (d->pos | (ISO_SECTOR_SIZE - 1)) + 1;
            continue;
        }
        if (len < DIR_REC_MIN || off + len > ISO_SECTOR_SIZE)
            return ISO_ERR_CORRUPT;
        id_len = p[32];
        if (id_len == 0 || 33 + id_len > len)
            return ISO_ERR_CORRUPT;
        d->pos += len;
        if (id_len == 1 && p[33] <= 1)
            continue; /* "." or ".." */
        r->id = p + 33;
        r->id_len = id_len;
        r->lba = rd_le32(p + 2);
        r->size = rd_le32(p + 10);
        r->flags = p[25];
        if (!extent_ok(v, r->lba, r->size))
            return ISO_ERR_CORRUPT;
        return 1;
    }
    return 0;
}

/* Length of an identifier without ";version" and a trailing '.'. */
static uint32_t visible_len(const uint8_t *id, uint32_t n)
{
    uint32_t i;
    for (i = 0; i < n; i++)
        if (id[i] == ';')
            break;
    n = i;
    if (n > 1 && id[n - 1] == '.')
        n--;
    return n;
}

static uint8_t upper(uint8_t c)
{
    return (c >= 'a' && c <= 'z') ? (uint8_t)(c - 'a' + 'A') : c;
}

int iso_readdir(iso_vol *v, iso_dir *d, iso_entry *out)
{
    rec r;
    if (!v || !d || !out)
        return ISO_ERR_BADARG;
    for (;;) {
        uint32_t n, i;
        int e = next_rec(v, d, &r);
        if (e <= 0)
            return e;
        n = visible_len(r.id, r.id_len);
        if (n >= ISO_NAME_MAX)
            continue; /* cannot be represented; not a level-1 name */
        for (i = 0; i < n; i++)
            out->name[i] = (char)r.id[i];
        out->name[n] = 0;
        out->lba = r.lba;
        out->size = r.size;
        out->flags = r.flags;
        return 1;
    }
}

/* ---- path lookup ------------------------------------------------------- */

static int is_sep(char c)
{
    return c == '/' || c == '\\';
}

int iso_find(iso_vol *v, const char *path, iso_entry *out)
{
    uint32_t cur_lba, cur_size;

    if (!v || !path || !out)
        return ISO_ERR_BADARG;
    if (v->volume_size == 0)
        return ISO_ERR_BADARG;
    cur_lba = v->root_lba;
    cur_size = v->root_size;
    out->name[0] = 0;
    out->lba = cur_lba;
    out->size = cur_size;
    out->flags = ISO_FLAG_DIR;

    for (;;) {
        const char *comp;
        uint32_t clen, n;
        iso_dir d;
        rec r;
        int e, found = 0;

        while (is_sep(*path))
            path++;
        if (*path == 0)
            return ISO_OK;
        if (!(out->flags & ISO_FLAG_DIR))
            return ISO_ERR_NOT_FOUND; /* a file in the middle of the path */
        comp = path;
        while (*path && !is_sep(*path))
            path++;
        clen = (uint32_t)(path - comp);
        for (n = 0; n < clen; n++)
            if (comp[n] == ';')
                break;
        clen = n;
        if (clen > 1 && comp[clen - 1] == '.')
            clen--;

        e = open_extent(v, cur_lba, cur_size, &d);
        if (e != ISO_OK)
            return e;
        while ((e = next_rec(v, &d, &r)) > 0) {
            uint32_t rn = visible_len(r.id, r.id_len), i;
            if (rn != clen)
                continue;
            for (i = 0; i < rn; i++)
                if (upper(r.id[i]) != upper((uint8_t)comp[i]))
                    break;
            if (i != rn)
                continue;
            if (rn >= ISO_NAME_MAX) { /* too long to store: report no name */
                out->name[0] = 0;
            } else {
                for (i = 0; i < rn; i++)
                    out->name[i] = (char)r.id[i];
                out->name[rn] = 0;
            }
            out->lba = r.lba;
            out->size = r.size;
            out->flags = r.flags;
            found = 1;
            break;
        }
        if (e < 0)
            return e;
        if (!found)
            return ISO_ERR_NOT_FOUND;
        cur_lba = out->lba;
        cur_size = out->size;
    }
}

int iso_opendir(iso_vol *v, const char *path, iso_dir *d)
{
    iso_entry e;
    int r = iso_find(v, path, &e);
    if (r != ISO_OK)
        return r;
    return iso_opendir_entry(v, &e, d);
}

/* ---- file data --------------------------------------------------------- */

int32_t iso_read(iso_vol *v, const iso_entry *e, uint32_t offset, uint32_t len,
                 void *dst)
{
    uint8_t *out = (uint8_t *)dst;
    uint32_t done = 0;

    if (!v || !e || (!dst && len) || (e->flags & ISO_FLAG_DIR))
        return ISO_ERR_BADARG;
    if (!extent_ok(v, e->lba, e->size))
        return ISO_ERR_CORRUPT;
    if (offset >= e->size)
        return 0;
    if (len > e->size - offset)
        len = e->size - offset;
    if (len > 0x7FFFFFFFu)
        len = 0x7FFFFFFFu;

    while (done < len) {
        uint32_t pos = offset + done;
        uint32_t sec = e->lba + (pos >> 11);
        uint32_t in = pos & (ISO_SECTOR_SIZE - 1);
        uint32_t left = len - done;

        if (in == 0 && left >= ISO_SECTOR_SIZE) {
            uint32_t count = left >> 11; /* whole sectors in one request */
            if (v->read(v->ctx, v->base + sec, count, out + done) != 0)
                return ISO_ERR_READ;
            done += count << 11;
        } else {
            uint32_t n = ISO_SECTOR_SIZE - in;
            const uint8_t *p = load(v, v->base + sec);
            if (!p)
                return ISO_ERR_READ;
            if (n > left)
                n = left;
            memcpy(out + done, p + in, n);
            done += n;
        }
    }
    return (int32_t)done;
}
