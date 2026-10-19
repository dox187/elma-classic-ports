/* PSn00bSDK glue for the ISO9660 reader, see cdtrack.h. */
#include "cdtrack.h"

#include <psxcd.h>
#include <string.h>

static int g_inited;
/* Word-aligned bounce buffer for destinations that are not. */
static uint32_t g_bounce[ISO_SECTOR_SIZE / 4];

int cdtrack_init(void)
{
    if (g_inited)
        return 0;
    if (!CdInit())
        return -1;
    g_inited = 1;
    return 0;
}

int cdtrack_tracks(int *first, int *last)
{
    uint8_t res[8];
    memset(res, 0, sizeof res);
    if (CdControlB(CdlGetTN, 0, res) != 1)
        return -1;
    if (!first || !last)
        return -1;
    *first = btoi(res[1]);
    *last = btoi(res[2]);
    return (*first >= 1 && *last >= *first) ? 0 : -1;
}

int cdtrack_track_base(int track)
{
    uint8_t res[8];
    uint8_t param = (uint8_t)itob(track);
    int minute, second;
    memset(res, 0, sizeof res);
    if (track < 1 || track > 99 || CdControlB(CdlGetTD, &param, res) != 1)
        return -1;
    if (res[0] & CdlStatError)
        return -1;
    minute = btoi(res[1]);
    second = btoi(res[2]);
    return (minute * 60 + second) * 75 - 150;
}

/* One CdRead request of n sectors into a word-aligned buffer. */
static int read_request(uint32_t lba, int n, uint32_t *buf)
{
    int attempt;
    for (attempt = 0; attempt < CDTRACK_RETRIES; attempt++) {
        CdlLOC loc;
        uint8_t res[8];
        CdIntToPos((int)lba, &loc);
        if (CdControlB(CdlSetloc, &loc, res) != 1)
            continue;
        if (!CdReadRetry(n, buf, CdlModeSpeed, CDTRACK_RETRIES))
            continue;
        if (CdReadSync(0, res) == 0)
            return 0;
        CdReadBreak();
        CdReadSync(0, res);
    }
    return -1;
}

int cdtrack_read(void *ctx, uint32_t lba, uint32_t count, void *dst)
{
    uint8_t *out = (uint8_t *)dst;
    (void)ctx;
    while (count) {
        uint32_t n = count;
        if (((uintptr_t)out & 3u) != 0) {
            if (read_request(lba, 1, g_bounce) != 0)
                return -1;
            memcpy(out, g_bounce, ISO_SECTOR_SIZE);
            n = 1;
        } else {
            if (n > CDTRACK_CHUNK_SECTORS)
                n = CDTRACK_CHUNK_SECTORS;
            if (read_request(lba, (int)n, (uint32_t *)out) != 0)
                return -1;
        }
        lba += n;
        out += (size_t)n * ISO_SECTOR_SIZE;
        count -= n;
    }
    return 0;
}

int cdtrack_mount(cdtrack_vol *vol, int track)
{
    int base, r;
    if (!vol)
        return ISO_ERR_BADARG;
    vol->track = 0;
    vol->track_base = 0;
    if (cdtrack_init() != 0)
        return ISO_ERR_READ;
    base = cdtrack_track_base(track);
    if (base < 0)
        return ISO_ERR_NOT_FOUND;
    r = iso_mount(&vol->iso, cdtrack_read, 0, vol->sector, (uint32_t)base, ISO_SCAN_DEFAULT);
    if (r == ISO_OK) {
        iso_set_window(&vol->iso, vol->sector, CDTRACK_WINDOW);
        vol->track = track;
        vol->track_base = base;
    }
    return r;
}

int cdtrack_mount_data2(cdtrack_vol *vol)
{
    int first, last, t, r = ISO_ERR_NOT_FOUND;
    if (!vol)
        return ISO_ERR_BADARG;
    if (cdtrack_init() != 0)
        return ISO_ERR_READ;
    if (cdtrack_tracks(&first, &last) != 0)
        return ISO_ERR_READ;
    if (last > 1 + CDTRACK_MAX_DATA_SEARCH)
        last = 1 + CDTRACK_MAX_DATA_SEARCH;
    for (t = (first > 2 ? first : 2); t <= last; t++) {
        r = cdtrack_mount(vol, t);
        if (r == ISO_OK)
            return r;
    }
    return r;
}
