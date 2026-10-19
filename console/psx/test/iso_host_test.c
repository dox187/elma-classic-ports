/*
 * Host test for src/cd/iso9660.c.
 *
 *   iso_host_test FILE SECSIZE DATAOFF FIRST_LBA BASE_LBA COMMAND [ARG]
 *
 * FILE holds consecutive sectors of SECSIZE bytes (2352 raw or 2048); the
 * user data of each starts DATAOFF bytes into the sector (16 for raw
 * MODE1, 0 for 2048). Sector 0 of FILE has the absolute LBA FIRST_LBA;
 * sectors outside the file cannot be read. BASE_LBA is the track start
 * handed to iso_mount (usually a deliberately misaligned guess).
 *
 * Commands:
 *   info              mount and print the result
 *   list PATH         list a directory ("name size flags lba")
 *   extract OUTDIR [WINDOW]
 *                     copy the whole tree to the host, reading each file
 *                     both in one piece and in odd-sized chunks
 *   selftest [WINDOW] mount, then run the error-case and fuzz tests
 *                     (WINDOW = sectors per buffer refill, power of two, default 1)
 */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include "../src/cd/iso9660.h"

static int g_fail;

#define CHECK(cond)                                                          \
    do {                                                                     \
        if (!(cond)) {                                                       \
            printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);           \
            g_fail++;                                                        \
        }                                                                    \
    } while (0)

/* ---- file-backed sector source ---------------------------------------- */

typedef struct {
    FILE *f;
    long secsize, dataoff;
    uint32_t first_lba, nsec;
    uint32_t reads;
} file_src;

static int file_read(void *ctx, uint32_t lba, uint32_t count, void *dst)
{
    file_src *s = (file_src *)ctx;
    uint32_t i;
    s->reads++;
    for (i = 0; i < count; i++) {
        uint32_t l = lba + i;
        if (l < s->first_lba || l - s->first_lba >= s->nsec)
            return -1;
        if (fseek(s->f, (long)(l - s->first_lba) * s->secsize + s->dataoff, SEEK_SET))
            return -1;
        if (fread((uint8_t *)dst + (size_t)i * 2048, 1, 2048, s->f) != 2048)
            return -1;
    }
    return 0;
}

/* ---- memory-backed sector source (ISO sector 0 = LBA `first`) ---------- */

typedef struct {
    uint8_t *data;
    uint32_t nsec, first;
    int fail_lba_from; /* reads at or above this LBA fail, -1 = never */
} mem_src;

static int mem_read(void *ctx, uint32_t lba, uint32_t count, void *dst)
{
    mem_src *m = (mem_src *)ctx;
    uint32_t i;
    for (i = 0; i < count; i++) {
        uint32_t l = lba + i;
        if (l < m->first || l - m->first >= m->nsec)
            return -1;
        if (m->fail_lba_from >= 0 && l >= (uint32_t)m->fail_lba_from)
            return -1;
        memcpy((uint8_t *)dst + (size_t)i * 2048, m->data + (size_t)(l - m->first) * 2048, 2048);
    }
    return 0;
}

/* ---- tree walking ------------------------------------------------------ */

static void make_dirs(const char *path)
{
    char tmp[1024];
    size_t i;
    snprintf(tmp, sizeof tmp, "%s", path);
    for (i = 1; tmp[i]; i++)
        if (tmp[i] == '/') {
            tmp[i] = 0;
            mkdir(tmp, 0755);
            tmp[i] = '/';
        }
    mkdir(tmp, 0755);
}

static int extract_dir(iso_vol *v, const iso_entry *dir, const char *iso_path, const char *out)
{
    iso_dir d;
    iso_entry e;
    int r;
    make_dirs(out);
    r = iso_opendir_entry(v, dir, &d);
    if (r != ISO_OK) {
        printf("FAIL opendir %s: %d\n", iso_path, r);
        return 1;
    }
    while ((r = iso_readdir(v, &d, &e)) > 0) {
        char ip[1024], op[1024];
        snprintf(ip, sizeof ip, "%s/%s", iso_path, e.name);
        snprintf(op, sizeof op, "%s/%s", out, e.name);
        if (e.flags & ISO_FLAG_DIR) {
            if (extract_dir(v, &e, ip, op))
                return 1;
        } else {
            uint8_t *whole = malloc(e.size ? e.size : 1), *chunked = malloc(e.size ? e.size : 1);
            uint32_t off = 0, step = 1;
            iso_entry again;
            FILE *f;
            int32_t n;
            if (iso_find(v, ip, &again) != ISO_OK || again.lba != e.lba || again.size != e.size) {
                printf("FAIL find %s\n", ip);
                return 1;
            }
            n = iso_read(v, &e, 0, e.size, whole);
            if (n != (int32_t)e.size) {
                printf("FAIL read %s: %d\n", ip, (int)n);
                return 1;
            }
            while (off < e.size) { /* chunk sizes 1, 2, 3, ... 3000, wrap */
                n = iso_read(v, &e, off, step, chunked + off);
                if (n <= 0 || (uint32_t)n != (step > e.size - off ? e.size - off : step)) {
                    printf("FAIL chunk read %s at %u: %d\n", ip, off, (int)n);
                    return 1;
                }
                off += (uint32_t)n;
                step = step % 3000 + 1 + step / 7;
            }
            if (memcmp(whole, chunked, e.size) != 0) {
                printf("FAIL chunked read differs: %s\n", ip);
                return 1;
            }
            f = fopen(op, "wb");
            if (!f || (e.size && fwrite(whole, 1, e.size, f) != e.size)) {
                printf("FAIL write %s\n", op);
                return 1;
            }
            fclose(f);
            free(whole);
            free(chunked);
        }
    }
    if (r < 0) {
        printf("FAIL readdir %s: %d\n", iso_path, r);
        return 1;
    }
    return 0;
}

/* Walks the whole tree, only counting; used by the fuzz test. Bounded so
 * a looping directory structure cannot hang. */
static int walk_count(iso_vol *v, const iso_entry *dir, int depth, unsigned *budget)
{
    iso_dir d;
    iso_entry e;
    int r = iso_opendir_entry(v, dir, &d);
    uint8_t tmp[64];
    if (r != ISO_OK)
        return r;
    while ((r = iso_readdir(v, &d, &e)) > 0) {
        if (*budget == 0)
            return 0;
        (*budget)--;
        if (e.flags & ISO_FLAG_DIR) {
            if (depth < 8)
                walk_count(v, &e, depth + 1, budget);
        } else {
            iso_read(v, &e, 0, sizeof tmp, tmp);
            iso_read(v, &e, e.size ? e.size - 1 : 0, 10, tmp);
        }
    }
    return r;
}

/* ---- self test --------------------------------------------------------- */

static uint32_t rnd_state = 12345;
static uint32_t rnd(void)
{
    rnd_state = rnd_state * 1664525u + 1013904223u;
    return rnd_state >> 8;
}


/* Sector-group buffers for the window variant of the tests (one per
 * volume that can be live at the same time). */
static unsigned g_window = 1;
static uint8_t g_wbuf[2][64 * 2048];

static int mnt(iso_vol *v, int which, iso_read_fn rd, void *ctx, void *sbuf, uint32_t base,
               uint32_t scan)
{
    int r = iso_mount(v, rd, ctx, sbuf, base, scan);
    if (r == ISO_OK && g_window > 1)
        CHECK(iso_set_window(v, g_wbuf[which], g_window) == ISO_OK);
    return r;
}
#define mntv(v, rd, ctx, sb, base, scan) mnt(v, 0, rd, ctx, sb, base, scan)
#define mntw(v, rd, ctx, sb, base, scan) mnt(v, 1, rd, ctx, sb, base, scan)

static void selftest(iso_vol *v0, file_src *fs)
{
    uint32_t nsec = v0->volume_size, i;
    uint8_t *img = malloc((size_t)nsec * 2048);
    uint8_t *copy = malloc((size_t)nsec * 2048);
    uint8_t sbuf[2048];
    iso_vol v;
    iso_entry e, e2;
    iso_dir d;
    mem_src m;
    int r;
    uint32_t real_first = v0->base, lev_lba;

    if (!img || !copy)
        abort();
    CHECK(file_read(fs, real_first, nsec, img) == 0);
    m.data = img;
    m.nsec = nsec;
    m.first = 5000; /* arbitrary absolute position of the memory image */
    m.fail_lba_from = -1;

    /* mount with every misalignment 0..74 sectors early, and exact */
    for (i = 0; i <= 74; i++) {
        r = mntv(&v, mem_read, &m, sbuf, m.first - i, ISO_SCAN_DEFAULT);
        CHECK(r == ISO_OK && v.base == m.first);
    }
    /* base 0 reads below the image fail; scan skips them and still finds
     * the descriptor when it is within the window */
    r = mntv(&v, mem_read, &m, sbuf, m.first - 3, 20);
    CHECK(r == ISO_OK);
    r = mntv(&v, mem_read, &m, sbuf, m.first - 40, 20); /* window too short */
    CHECK(r == ISO_ERR_NOT_FOUND || r == ISO_ERR_READ);
    r = mntv(&v, mem_read, &m, sbuf, m.first + 1, ISO_SCAN_DEFAULT); /* past the start */
    CHECK(r != ISO_OK);
    r = mntv(&v, mem_read, &m, sbuf, 0, ISO_SCAN_DEFAULT); /* nothing readable */
    CHECK(r == ISO_ERR_READ);
    CHECK(iso_mount(NULL, mem_read, &m, sbuf, 0, 1) == ISO_ERR_BADARG);
    CHECK(mntv(&v, NULL, &m, sbuf, 0, 1) == ISO_ERR_BADARG);

    CHECK(mntv(&v, mem_read, &m, sbuf, m.first, ISO_SCAN_DEFAULT) == ISO_OK);

    /* lookups */
    CHECK(iso_find(&v, "", &e) == ISO_OK && (e.flags & ISO_FLAG_DIR));
    CHECK(iso_find(&v, "/", &e) == ISO_OK && (e.flags & ISO_FLAG_DIR));
    CHECK(iso_find(&v, "ELMA.RES", &e) == ISO_OK && !(e.flags & ISO_FLAG_DIR));
    CHECK(iso_find(&v, "elma.res;1", &e2) == ISO_OK && e2.lba == e.lba && e2.size == e.size);
    CHECK(iso_find(&v, "/Elma.Res", &e2) == ISO_OK && e2.lba == e.lba);
    CHECK(iso_find(&v, "ELMA.RES;7", &e2) == ISO_OK && e2.lba == e.lba);
    CHECK(strcmp(e.name, "ELMA.RES") == 0);
    CHECK(iso_find(&v, "LEV", &e2) == ISO_OK && (e2.flags & ISO_FLAG_DIR));
    CHECK(iso_find(&v, "lev/", &e2) == ISO_OK && (e2.flags & ISO_FLAG_DIR));
    CHECK(iso_find(&v, "\\LEV\\", &e2) == ISO_OK && (e2.flags & ISO_FLAG_DIR));
    CHECK(iso_find(&v, "//LEV//", &e2) == ISO_OK);
    CHECK(iso_find(&v, "NOPE.TXT", &e2) == ISO_ERR_NOT_FOUND);
    CHECK(iso_find(&v, "LEV/NOPE.LEV", &e2) == ISO_ERR_NOT_FOUND);
    CHECK(iso_find(&v, "ELMA.RES/X", &e2) == ISO_ERR_NOT_FOUND);
    CHECK(iso_find(&v, "ELMA", &e2) == ISO_ERR_NOT_FOUND);
    CHECK(iso_find(&v, "ELMA.RESX", &e2) == ISO_ERR_NOT_FOUND);
    CHECK(iso_find(&v, "ELMA.RE", &e2) == ISO_ERR_NOT_FOUND);
    CHECK(iso_find(&v, NULL, &e2) == ISO_ERR_BADARG);
    CHECK(iso_opendir(&v, "ELMA.RES", &d) == ISO_ERR_BADARG); /* a file */
    CHECK(iso_opendir(&v, "NOPE", &d) == ISO_ERR_NOT_FOUND);
    CHECK(iso_read(&v, &e2, 0, 1, sbuf) == ISO_ERR_BADARG);   /* a directory */

    /* ranges */
    {
        iso_entry f;
        uint8_t *whole, *part;
        CHECK(iso_find(&v, "ELMA.RES", &f) == ISO_OK && f.size > 5000);
        whole = malloc(f.size);
        part = malloc(f.size);
        CHECK(iso_read(&v, &f, 0, f.size, whole) == (int32_t)f.size);
        CHECK(iso_read(&v, &f, f.size, 10, part) == 0);
        CHECK(iso_read(&v, &f, f.size + 100, 10, part) == 0);
        CHECK(iso_read(&v, &f, f.size - 5, 100, part) == 5 && !memcmp(part, whole + f.size - 5, 5));
        CHECK(iso_read(&v, &f, 2047, 2, part) == 2 && !memcmp(part, whole + 2047, 2));
        CHECK(iso_read(&v, &f, 2048, 4096, part) == 4096 && !memcmp(part, whole + 2048, 4096));
        CHECK(iso_read(&v, &f, 1000, 5000, part) == 5000 && !memcmp(part, whole + 1000, 5000));
        CHECK(iso_read(&v, &f, 0, 0, NULL) == 0);
        CHECK(iso_read(&v, &f, 0, 1, NULL) == ISO_ERR_BADARG);
        free(whole);
        free(part);
    }

    /* read callback failure in the middle of a file */
    {
        iso_entry f;
        uint8_t big[8192];
        CHECK(iso_find(&v, "ELMA.RES", &f) == ISO_OK);
        m.fail_lba_from = (int)(m.first + f.lba + 1);
        CHECK(iso_read(&v, &f, 0, 4096, big) == ISO_ERR_READ);
        CHECK(iso_read(&v, &f, 100, 100, big) == 100);
        /* with a window the sector may already be cached from a good read */
        r = iso_read(&v, &f, 2048 + 5, 10, big);
        CHECK(r == ISO_ERR_READ || (g_window > 1 && r == 10));
        m.fail_lba_from = -1;
    }

    /* corrupt descriptors / directories (work on a copy) */
    CHECK(iso_find(&v, "LEV", &e) == ISO_OK);
    lev_lba = e.lba;
    m.data = copy;
#define MUT(setup, expect)                                                     \
    do {                                                                       \
        memcpy(copy, img, (size_t)nsec * 2048);                                \
        setup;                                                                 \
        expect;                                                                \
    } while (0)
    {
        uint32_t root = v.root_lba;
        uint8_t *pvd = copy + 16 * 2048;
        uint8_t *rootdir = copy + (size_t)root * 2048;
        iso_vol w;

        MUT(memset(pvd, 0, 2048), CHECK(mntw(&w, mem_read, &m, sbuf, m.first, 80) == ISO_ERR_NOT_FOUND));
        MUT(pvd[1] = 'X', CHECK(mntw(&w, mem_read, &m, sbuf, m.first, 80) == ISO_ERR_NOT_FOUND));
        MUT(pvd[129] = 0x10, CHECK(mntw(&w, mem_read, &m, sbuf, m.first, 80) == ISO_ERR_CORRUPT));
        MUT(memset(pvd + 80, 0, 4), CHECK(mntw(&w, mem_read, &m, sbuf, m.first, 80) == ISO_ERR_CORRUPT));
        MUT(pvd[156 + 2] = 0xFF; pvd[156 + 3] = 0xFF, CHECK(mntw(&w, mem_read, &m, sbuf, m.first, 80) == ISO_ERR_CORRUPT));
        MUT(pvd[156] = 10, CHECK(mntw(&w, mem_read, &m, sbuf, m.first, 80) == ISO_ERR_CORRUPT));
        MUT(pvd[156 + 25] = 0, CHECK(mntw(&w, mem_read, &m, sbuf, m.first, 80) == ISO_ERR_CORRUPT));
        MUT(memset(pvd + 156 + 10, 0, 4), CHECK(mntw(&w, mem_read, &m, sbuf, m.first, 80) == ISO_ERR_CORRUPT));

        /* last record of a LEV sector: length that crosses the sector end */
        {
            uint8_t *sec = copy + (size_t)lev_lba * 2048;
            uint32_t pos = 0, last = 0;
            memcpy(copy, img, (size_t)nsec * 2048);
            while (pos < 2048 && sec[pos]) {
                last = pos;
                pos += sec[pos];
            }
            sec[last] = 0xFE;
            CHECK(last + 0xFE > 2048);
            CHECK(mntw(&w, mem_read, &m, sbuf, m.first, 80) == ISO_OK);
            CHECK(iso_opendir(&w, "LEV", &d) == ISO_OK);
            r = 1;
            while (r > 0)
                r = iso_readdir(&w, &d, &e);
            CHECK(r == ISO_ERR_CORRUPT);
        }
        MUT(rootdir[68] = 20, { /* shorter than the minimum */
            mntw(&w, mem_read, &m, sbuf, m.first, 80);
            iso_opendir(&w, "/", &d);
            CHECK(iso_readdir(&w, &d, &e) == ISO_ERR_CORRUPT);
        });
        MUT(rootdir[68 + 32] = 200, { /* identifier longer than the record */
            mntw(&w, mem_read, &m, sbuf, m.first, 80);
            iso_opendir(&w, "/", &d);
            CHECK(iso_readdir(&w, &d, &e) == ISO_ERR_CORRUPT);
        });
        MUT(rootdir[68 + 32] = 0, { /* empty identifier */
            mntw(&w, mem_read, &m, sbuf, m.first, 80);
            iso_opendir(&w, "/", &d);
            CHECK(iso_readdir(&w, &d, &e) == ISO_ERR_CORRUPT);
        });
        MUT(rootdir[68 + 10 + 3] = 0x7F, { /* file size far beyond the volume */
            mntw(&w, mem_read, &m, sbuf, m.first, 80);
            iso_opendir(&w, "/", &d);
            CHECK(iso_readdir(&w, &d, &e) == ISO_ERR_CORRUPT);
        });
        MUT(rootdir[68 + 2 + 3] = 0x7F, { /* extent beyond the volume */
            mntw(&w, mem_read, &m, sbuf, m.first, 80);
            iso_opendir(&w, "/", &d);
            CHECK(iso_readdir(&w, &d, &e) == ISO_ERR_CORRUPT);
        });
        /* a directory entry with size zero cannot be opened */
        {
            /* patch the LEV entry in the root directory: size 0 */
            uint32_t pos = 68;
            while (rootdir[pos]) {
                uint8_t *rec = rootdir + pos;
                if (rec[32] == 3 && memcmp(rec + 33, "LEV", 3) == 0) {
                    uint32_t k;
                    memcpy(copy, img, (size_t)nsec * 2048);
                    for (k = 0; k < 4; k++)
                        rec[10 + k] = 0;
                    mntw(&w, mem_read, &m, sbuf, m.first, 80);
                    CHECK(iso_find(&w, "LEV", &e) == ISO_OK);
                    CHECK(iso_opendir(&w, "LEV", &d) == ISO_ERR_CORRUPT);
                    CHECK(iso_find(&w, "LEV/X", &e) == ISO_ERR_CORRUPT);
                    break;
                }
                pos += rec[0];
            }
        }
        /* volume claims more sectors than exist: reads fail cleanly */
        MUT({ uint32_t big = nsec + 100000; memcpy(pvd + 80, &big, 4); }, {
            iso_entry f;
            CHECK(mntw(&w, mem_read, &m, sbuf, m.first, 80) == ISO_OK);
            CHECK(iso_find(&w, "ELMA.RES", &f) == ISO_OK);
            f.lba = nsec + 50;
            CHECK(iso_read(&w, &f, 0, 10, sbuf) == ISO_ERR_READ);
        });
    }

    /* fuzz: random corruption of the descriptor and directory sectors */
    {
        uint32_t dir_end = 0, k;
        iso_entry f;
        /* directories live between the path tables and the first file */
        iso_find(&v, "ELMA.RES", &f);
        dir_end = f.lba;
        iso_find(&v, "LEV", &f);
        if (f.lba + 20 > dir_end)
            dir_end = f.lba + 20;
        if (dir_end > nsec)
            dir_end = nsec;
        alarm(60);
        for (k = 0; k < 6000; k++) {
            iso_vol w;
            iso_entry root;
            unsigned budget = 2000;
            uint32_t n = 1 + rnd() % 6, j;
            memcpy(copy, img, (size_t)dir_end * 2048);
            for (j = 0; j < n; j++) {
                uint32_t sec = 16 + rnd() % (dir_end - 16);
                uint32_t off = rnd() % 2048;
                if (rnd() & 1)
                    off = rnd() % 200; /* favour the start of the sector */
                copy[(size_t)sec * 2048 + off] = (uint8_t)rnd();
            }
            if (mntw(&w, mem_read, &m, sbuf, m.first - rnd() % 75, 80) == ISO_OK) {
                if (iso_find(&w, "", &root) == ISO_OK)
                    walk_count(&w, &root, 0, &budget);
                iso_find(&w, "LEV/PA26LE01.LEV", &root);
            }
        }
        alarm(0);
    }
    free(img);
    free(copy);
}

int main(int argc, char **argv)
{
    file_src fs;
    iso_vol v;
    uint8_t sbuf[2048];
    long size;
    uint32_t base;
    int r;

    if (argc < 7) {
        fprintf(stderr, "usage: %s FILE SECSIZE DATAOFF FIRST_LBA BASE_LBA info|list P|extract D|selftest\n", argv[0]);
        return 2;
    }
    fs.f = fopen(argv[1], "rb");
    if (!fs.f) {
        perror(argv[1]);
        return 2;
    }
    fs.secsize = atol(argv[2]);
    fs.dataoff = atol(argv[3]);
    fs.first_lba = (uint32_t)strtoul(argv[4], NULL, 10);
    base = (uint32_t)strtoul(argv[5], NULL, 10);
    fseek(fs.f, 0, SEEK_END);
    size = ftell(fs.f);
    fs.nsec = (uint32_t)(size / fs.secsize);
    fs.reads = 0;

    r = iso_mount(&v, file_read, &fs, sbuf, base, ISO_SCAN_DEFAULT);
    if (!strcmp(argv[6], "info")) {
        printf("mount %d base %u volume %u root %u size %u\n", r, v.base, v.volume_size,
               v.root_lba, v.root_size);
        return r != ISO_OK;
    }
    if (r != ISO_OK) {
        printf("FAIL mount: %d\n", r);
        return 1;
    }
    if (!strcmp(argv[6], "list") && argc >= 8) {
        iso_dir d;
        iso_entry e;
        r = iso_opendir(&v, argv[7], &d);
        if (r != ISO_OK) {
            printf("FAIL opendir: %d\n", r);
            return 1;
        }
        while ((r = iso_readdir(&v, &d, &e)) > 0)
            printf("%s %u %u %u\n", e.name, e.size, e.flags, e.lba);
        return r < 0;
    }
    if (!strcmp(argv[6], "extract") && argc >= 8) {
        iso_entry root;
        if (argc >= 9) {
            g_window = (unsigned)atoi(argv[8]);
            if (iso_set_window(&v, g_wbuf[0], g_window) != ISO_OK)
                return 2;
        }
        iso_find(&v, "/", &root);
        return extract_dir(&v, &root, "", argv[7]);
    }
    if (!strcmp(argv[6], "selftest")) {
        if (argc >= 8)
            g_window = (unsigned)atoi(argv[7]);
        selftest(&v, &fs);
        printf(g_fail ? "selftest FAILED (%d)\n" : "selftest OK\n", g_fail);
        return g_fail != 0;
    }
    fprintf(stderr, "unknown command\n");
    return 2;
}
