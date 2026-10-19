/* psx_file backend on top of the ISO9660 reader, see cdfile.h. */
#include "cdfile.h"

#include <string.h>

static int cd_open(void *context, const char *path, long *size)
{
    cdfile_ctx *c = (cdfile_ctx *)context;
    iso_entry e;
    int i;
    if (iso_find(c->vol, path, &e) != ISO_OK || (e.flags & ISO_FLAG_DIR))
        return -1;
    for (i = 0; i < CDFILE_MAX_OPEN; i++) {
        if (!c->used[i]) {
            c->used[i] = 1;
            c->files[i] = e;
            *size = (long)e.size;
            return i;
        }
    }
    return -1;
}

static int cd_read(void *context, int handle, long offset, void *buffer, int n)
{
    cdfile_ctx *c = (cdfile_ctx *)context;
    if (handle < 0 || handle >= CDFILE_MAX_OPEN || !c->used[handle] || offset < 0 || n < 0)
        return -1;
    return (int)iso_read(c->vol, &c->files[handle], (uint32_t)offset, (uint32_t)n, buffer);
}

static void cd_close(void *context, int handle)
{
    cdfile_ctx *c = (cdfile_ctx *)context;
    if (handle >= 0 && handle < CDFILE_MAX_OPEN)
        c->used[handle] = 0;
}

/* The index-th file (directories are not counted) of directory dir. */
static int cd_list(void *context, const char *dir, int index, char *name, int size)
{
    cdfile_ctx *c = (cdfile_ctx *)context;
    char norm[CDFILE_DIR_MAX];
    iso_entry e;
    int r;

    if (index < 0 || size <= 0)
        return 1;
    psx_file_normalize(dir, norm, (int)sizeof norm);
    if (c->cursor_next != index || strcmp(norm, c->cursor_dir) != 0) {
        c->cursor_next = -1;
        if (iso_opendir(c->vol, norm, &c->cursor) != ISO_OK)
            return 1;
        memcpy(c->cursor_dir, norm, sizeof norm);
        c->cursor_next = 0;
    }
    for (;;) {
        r = iso_readdir(c->vol, &c->cursor, &e);
        if (r <= 0) {
            c->cursor_next = -1;
            return 1;
        }
        if (e.flags & ISO_FLAG_DIR)
            continue;
        if (c->cursor_next++ == index)
            break;
    }
    {
        int n = 0;
        while (e.name[n] && n < size - 1) {
            name[n] = e.name[n];
            n++;
        }
        name[n] = 0;
    }
    return 0;
}

void cdfile_init(cdfile_ctx *ctx, iso_vol *vol, psx_file_backend *backend)
{
    memset(ctx, 0, sizeof *ctx);
    ctx->vol = vol;
    ctx->cursor_next = -1;
    backend->name = "cd";
    backend->open = cd_open;
    backend->read = cd_read;
    backend->close = cd_close;
    backend->list = cd_list;
    backend->context = ctx;
}
