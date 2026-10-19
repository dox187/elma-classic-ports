/* The FILE layer of the PS1 build, see psx_file.h. */
#include "psx_file.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "memcard/mclz.h"

/* Built with the <stdio.h> shim of src/include (the game) or with the
 * SDK's own <stdio.h> (tests that do not need the FILE names): */
#ifndef EOF
#define EOF (-1)
#endif
#ifndef SEEK_SET
#define SEEK_SET 0
#define SEEK_CUR 1
#define SEEK_END 2
#endif

#define MAX_BACKENDS 4
#define MAX_DISCARDS 8
#define MAX_RAM_FILES 32
#define PATH_SIZE 64
/* Whole CD sectors (2048 bytes), several at a time: on the disc every
 * separate read costs a seek. */
#define BUFFER_SIZE (8 * 2048)

typedef struct ram_file {
	char path[PATH_SIZE];
	unsigned char* data;
	long size, capacity;
	int open_count;
	/* A copy of the bytes packed with mclz (packed_size bytes). While no
	 * file is open on it, a big file keeps only this (data is NULL); it is
	 * unpacked when it is opened and dropped when it is written. */
	unsigned char* packed;
	long packed_size;
} ram_file;

/* The packer of the memory card part (mclz.c). Programs without it (the
 * tests) keep their RAM files unpacked. */
size_t mclz_compress(const uint8_t* src, size_t n, uint8_t* dst) __attribute__((weak));
int mclz_expand(const uint8_t* src, size_t in_n, uint8_t* dst, size_t out_n) __attribute__((weak));
/* Smaller files are not worth it: */
#define PACK_MIN 4096

enum { KIND_BACKEND, KIND_RAM, KIND_DISCARD };

struct psx_file {
	int kind;
	int writing;
	/* KIND_BACKEND: */
	const psx_file_backend* backend;
	int handle;
	/* buffer holds the bytes from buffer_start on: */
	unsigned char* buffer;
	long buffer_start;
	int buffer_length;
	/* KIND_RAM: */
	ram_file* ram;
	long position, size;
	int eof, error;
};

static psx_file_backend backends[MAX_BACKENDS];
static int backend_count = 0;
static char discards[MAX_DISCARDS][PATH_SIZE];
static int discard_count = 0;
static ram_file ram_files[MAX_RAM_FILES];
static long ram_limit = 512 * 1024;
static long ram_used = 0;

void psx_file_add_backend(const psx_file_backend* backend) {
	if (backend_count < MAX_BACKENDS) backends[backend_count++] = *backend;
}

void psx_file_set_ram_limit(long bytes) { ram_limit = bytes; }

long psx_file_ram_used(void) { return ram_used; }

void psx_file_normalize(const char* path, char* out, int size) {
	int n = 0;
	while (path[0] == '.' && (path[1] == '\\' || path[1] == '/')) path += 2;
	while (*path == '\\' || *path == '/') path++;
	for (; *path && n < size - 1; path++) {
		char c = *path;
		if (c == '\\') c = '/';
		if (c >= 'a' && c <= 'z') c = (char)(c - 'a' + 'A');
		out[n++] = c;
	}
	out[n] = 0;
}

void psx_file_discard(const char* path) {
	if (discard_count < MAX_DISCARDS)
		psx_file_normalize(path, discards[discard_count++], PATH_SIZE);
}

static int discarded(const char* path) {
	for (int i = 0; i < discard_count; i++)
		if (strcmp(discards[i], path) == 0) return 1;
	return 0;
}

static ram_file* find_ram(const char* path) {
	for (int i = 0; i < MAX_RAM_FILES; i++)
		if (ram_files[i].path[0] && strcmp(ram_files[i].path, path) == 0) return &ram_files[i];
	return NULL;
}

static ram_file* new_ram(const char* path) {
	for (int i = 0; i < MAX_RAM_FILES; i++) {
		if (!ram_files[i].path[0]) {
			memset(&ram_files[i], 0, sizeof(ram_files[i]));
			snprintf(ram_files[i].path, PATH_SIZE, "%s", path);
			return &ram_files[i];
		}
	}
	return NULL;
}

static void drop_packed(ram_file* r) {
	if (!r->packed) return;
	ram_used -= r->packed_size;
	free(r->packed);
	r->packed = NULL;
	r->packed_size = 0;
}

static void truncate_ram(ram_file* r) {
	drop_packed(r);
	ram_used -= r->capacity;
	free(r->data);
	r->data = NULL;
	r->size = r->capacity = 0;
}

/* Makes the bytes of a packed file readable; 0 if there is no memory. */
static int unpack_ram(ram_file* r) {
	if (r->data || !r->packed) return 1;
	unsigned char* data = (unsigned char*)malloc((size_t)r->size);
	if (!data) return 0;
	if (!mclz_expand || mclz_expand(r->packed, (size_t)r->packed_size, data, (size_t)r->size) != 0) {
		free(data);
		return 0;
	}
	r->data = data;
	r->capacity = r->size;
	ram_used += r->capacity;
	return 1;
}

/* No file is open on r any more: keeps only a packed copy if that is
 * clearly smaller. */
static void pack_ram(ram_file* r) {
	if (!mclz_compress || r->open_count || !r->data) return;
	if (!r->packed && r->size >= PACK_MIN) {
		unsigned char* buffer = (unsigned char*)malloc(MCLZ_BOUND((size_t)r->size));
		if (!buffer) return;
		const long n = (long)mclz_compress(r->data, (size_t)r->size, buffer);
		if (n > r->size - r->size / 4) {
			free(buffer);
			return;
		}
		unsigned char* packed = (unsigned char*)realloc(buffer, (size_t)n);
		r->packed = packed ? packed : buffer;
		r->packed_size = n;
		ram_used += n;
	}
	if (!r->packed) return;
	ram_used -= r->capacity;
	free(r->data);
	r->data = NULL;
	r->capacity = 0;
}

/* Makes room for size bytes; 0 if the RAM limit does not allow it. */
static int reserve_ram(ram_file* r, long size) {
	if (size <= r->capacity) return 1;
	long capacity = r->capacity ? r->capacity : 1024;
	while (capacity < size) capacity *= 2;
	if (ram_used - r->capacity + capacity > ram_limit) {
		capacity = size;
		if (ram_used - r->capacity + capacity > ram_limit) return 0;
	}
	unsigned char* data = (unsigned char*)realloc(r->data, (size_t)capacity);
	if (!data) return 0;
	ram_used += capacity - r->capacity;
	r->data = data;
	r->capacity = capacity;
	return 1;
}

psx_file* psx_fopen(const char* name, const char* mode) {
	char path[PATH_SIZE];
	psx_file_normalize(name, path, sizeof(path));
	if (!path[0] || !mode) return NULL;
	const int write = mode[0] == 'w' || mode[0] == 'a';
	const int append = mode[0] == 'a';
	const int update = strchr(mode, '+') != NULL;

	/* (PSn00bSDK's calloc does not clear reused memory) */
	psx_file* f = (psx_file*)malloc(sizeof(psx_file));
	if (!f) return NULL;
	memset(f, 0, sizeof(*f));
	f->writing = write || update;

	if (write && discarded(path)) {
		f->kind = KIND_DISCARD;
		return f;
	}
	ram_file* r = find_ram(path);
	if (write) {
		if (!r) r = new_ram(path);
		if (!r) {
			free(f);
			return NULL;
		}
		if (!append) truncate_ram(r);
	}
	if (r) {
		if (!unpack_ram(r)) {
			free(f);
			return NULL;
		}
		/* A file that may change is no longer the packed copy: */
		if (f->writing) drop_packed(r);
		f->kind = KIND_RAM;
		f->ram = r;
		f->position = append ? r->size : 0;
		r->open_count++;
		return f;
	}
	if (mode[0] != 'r') {
		free(f);
		return NULL;
	}
	/* Files from the backends cannot be changed. */
	if (update) {
		free(f);
		return NULL;
	}
	for (int i = 0; i < backend_count; i++) {
		long size = 0;
		int handle = backends[i].open(backends[i].context, path, &size);
		if (handle < 0) continue;
		f->kind = KIND_BACKEND;
		f->backend = &backends[i];
		f->handle = handle;
		f->size = size;
		f->buffer = (unsigned char*)malloc(BUFFER_SIZE);
		if (!f->buffer) {
			backends[i].close(backends[i].context, handle);
			free(f);
			return NULL;
		}
		return f;
	}
	free(f);
	return NULL;
}

int psx_fclose(psx_file* f) {
	if (!f) return -1;
	if (f->kind == KIND_BACKEND) {
		f->backend->close(f->backend->context, f->handle);
		free(f->buffer);
	}
	if (f->kind == KIND_RAM) {
		ram_file* r = f->ram;
		r->open_count--;
		/* The capacity doubles while a file is written; when it is closed,
		 * only its bytes keep their room. */
		if (f->writing && !r->open_count && r->capacity > r->size && r->size > 0) {
			unsigned char* data = (unsigned char*)realloc(r->data, (size_t)r->size);
			if (data) {
				ram_used -= r->capacity - r->size;
				r->data = data;
				r->capacity = r->size;
			}
		}
		pack_ram(r);
	}
	free(f);
	return 0;
}

static long file_size(psx_file* f) {
	return f->kind == KIND_RAM ? f->ram->size : f->kind == KIND_BACKEND ? f->size : 0;
}

/* Reads into dest from the current position, n <= the bytes left. */
static long read_backend(psx_file* f, unsigned char* dest, long n) {
	long done = 0;
	while (done < n) {
		const long position = f->position + done;
		if (position >= f->buffer_start && position < f->buffer_start + f->buffer_length) {
			long count = f->buffer_start + f->buffer_length - position;
			if (count > n - done) count = n - done;
			memcpy(dest + done, f->buffer + (position - f->buffer_start), (size_t)count);
			done += count;
			continue;
		}
		/* Large reads go straight to the destination, whole buffers at a
		 * time, from a buffer-aligned position: */
		const long left = n - done;
		if (position % BUFFER_SIZE == 0 && left >= BUFFER_SIZE) {
			const long count = left - left % BUFFER_SIZE;
			const int got = f->backend->read(f->backend->context, f->handle, position,
			                                 dest + done, (int)count);
			if (got <= 0) break;
			done += got;
			if (got < count) break;
			continue;
		}
		const long start = position - position % BUFFER_SIZE;
		const int got =
		    f->backend->read(f->backend->context, f->handle, start, f->buffer, BUFFER_SIZE);
		if (got <= position - start) {
			f->buffer_length = 0;
			break;
		}
		f->buffer_start = start;
		f->buffer_length = got;
	}
	return done;
}

size_t psx_fread(void* buffer, size_t size, size_t count, psx_file* f) {
	if (!f || size == 0 || count == 0) return 0;
	/* The game reads pictures a byte at a time: */
	if (f->kind == KIND_BACKEND && size * count <= 8) {
		const long offset = f->position - f->buffer_start;
		const long n = (long)(size * count);
		if (offset >= 0 && offset + n <= f->buffer_length) {
			const unsigned char* from = f->buffer + offset;
			unsigned char* to = (unsigned char*)buffer;
			for (long i = 0; i < n; i++) to[i] = from[i];
			f->position += n;
			return count;
		}
	}
	if (f->kind == KIND_DISCARD) return 0;
	long want = (long)(size * count);
	const long left = file_size(f) - f->position;
	if (want > left) {
		want = left > 0 ? left : 0;
		f->eof = 1;
	}
	long got;
	if (f->kind == KIND_RAM) {
		memcpy(buffer, f->ram->data + f->position, (size_t)want);
		got = want;
	} else {
		got = read_backend(f, (unsigned char*)buffer, want);
		if (got < want) f->error = 1;
	}
	f->position += got;
	return (size_t)got / size;
}

size_t psx_fwrite(const void* buffer, size_t size, size_t count, psx_file* f) {
	if (!f || !f->writing || size == 0 || count == 0) return 0;
	if (f->kind == KIND_DISCARD) return count;
	if (f->kind != KIND_RAM) return 0;
	ram_file* r = f->ram;
	long n = (long)(size * count);
	if (!reserve_ram(r, f->position + n)) {
		f->error = 1;
		n = r->capacity - f->position;
		if (n <= 0) return 0;
	}
	if (f->position > r->size) memset(r->data + r->size, 0, (size_t)(f->position - r->size));
	memcpy(r->data + f->position, buffer, (size_t)n);
	f->position += n;
	if (f->position > r->size) r->size = f->position;
	return (size_t)n / size;
}

int psx_fseek(psx_file* f, long offset, int whence) {
	if (!f) return -1;
	long base = whence == SEEK_SET ? 0 : whence == SEEK_CUR ? f->position : file_size(f);
	if (base + offset < 0) return -1;
	f->position = base + offset;
	f->eof = 0;
	return 0;
}

long psx_ftell(psx_file* f) { return f ? f->position : -1; }

int psx_fgetc(psx_file* f) {
	unsigned char c;
	return psx_fread(&c, 1, 1, f) == 1 ? c : EOF;
}

char* psx_fgets(char* line, int size, psx_file* f) {
	if (!f || size <= 0) return NULL;
	int n = 0;
	while (n < size - 1) {
		const int c = psx_fgetc(f);
		if (c == EOF) break;
		line[n++] = (char)c;
		if (c == '\n') break;
	}
	line[n] = 0;
	return n ? line : NULL;
}

int psx_fputc(int c, psx_file* f) {
	const unsigned char b = (unsigned char)c;
	return psx_fwrite(&b, 1, 1, f) == 1 ? b : EOF;
}

int psx_fputs(const char* text, psx_file* f) {
	const size_t n = strlen(text);
	return psx_fwrite(text, 1, n, f) == n ? 0 : EOF;
}

int psx_vfprintf(psx_file* f, const char* format, va_list args) {
	char text[512];
	const int n = vsnprintf(text, sizeof(text), format, args);
	if (n < 0) return n;
	const size_t length = strlen(text);
	return psx_fwrite(text, 1, length, f) == length ? n : -1;
}

int psx_fprintf(psx_file* f, const char* format, ...) {
	va_list args;
	va_start(args, format);
	const int n = psx_vfprintf(f, format, args);
	va_end(args);
	return n;
}

int psx_feof(psx_file* f) { return f ? f->eof : 1; }

int psx_ferror(psx_file* f) { return f ? f->error : 1; }

int psx_access(const char* name) {
	char path[PATH_SIZE];
	psx_file_normalize(name, path, sizeof(path));
	/* (Opening a packed file would unpack it.) */
	if (path[0] && find_ram(path)) return 0;
	psx_file* f = psx_fopen(name, "rb");
	if (!f) return -1;
	psx_fclose(f);
	return 0;
}

/* Matches "*", "*.EXT", "NAME.*" and exact names (both upper case). */
static int matches(const char* pattern, const char* name) {
	if (strcmp(pattern, "*") == 0 || strcmp(pattern, "*.*") == 0) return 1;
	const char* star = strchr(pattern, '*');
	if (!star) return strcmp(pattern, name) == 0;
	const size_t prefix = (size_t)(star - pattern);
	const size_t suffix = strlen(star + 1);
	const size_t length = strlen(name);
	return length >= prefix + suffix && strncmp(name, pattern, prefix) == 0 &&
	       strcmp(name + length - suffix, star + 1) == 0;
}

/* The name of a RAM file if it is directly in dir. */
static const char* ram_name_in(const ram_file* r, const char* dir) {
	const size_t n = strlen(dir);
	if (n == 0) return strchr(r->path, '/') ? NULL : r->path;
	if (strncmp(r->path, dir, n) != 0 || r->path[n] != '/') return NULL;
	const char* name = r->path + n + 1;
	return strchr(name, '/') ? NULL : name;
}

/* Where the last listing stopped, so that asking for the names one after
 * the other (fifirst/finext) does not scan the directory again for each one;
 * on the disc that would mean reading it again. */
static struct {
	char dir[PATH_SIZE], pattern[PATH_SIZE];
	int next_index; /* the index the saved place gives next, -1: none */
	int ram_i, backend, backend_i;
} list_cursor = {"", "", -1, 0, 0, 0};

static int deliver(const char* candidate, char* name, int size, int index, int ram_i, int backend,
                   int backend_i) {
	strncpy(name, candidate, (size_t)size - 1);
	name[size - 1] = 0;
	list_cursor.next_index = index + 1;
	list_cursor.ram_i = ram_i;
	list_cursor.backend = backend;
	list_cursor.backend_i = backend_i;
	return 0;
}

int psx_file_list(const char* dir_name, const char* pattern_name, int index, char* name, int size) {
	char dir[PATH_SIZE], pattern[PATH_SIZE];
	psx_file_normalize(dir_name, dir, sizeof(dir));
	psx_file_normalize(pattern_name, pattern, sizeof(pattern));
	const size_t dir_length = strlen(dir);
	if (dir_length && dir[dir_length - 1] == '/') dir[dir_length - 1] = 0;

	/* Go on from the last place, or start again: */
	int seen = 0, ram_start = 0, backend_start = 0, backend_i_start = 0;
	if (index == list_cursor.next_index && strcmp(dir, list_cursor.dir) == 0 &&
	    strcmp(pattern, list_cursor.pattern) == 0) {
		seen = index;
		ram_start = list_cursor.ram_i;
		backend_start = list_cursor.backend;
		backend_i_start = list_cursor.backend_i;
	} else {
		strcpy(list_cursor.dir, dir);
		strcpy(list_cursor.pattern, pattern);
	}
	list_cursor.next_index = -1;

	for (int i = ram_start; i < MAX_RAM_FILES; i++) {
		if (!ram_files[i].path[0]) continue;
		const char* candidate = ram_name_in(&ram_files[i], dir);
		if (!candidate || !matches(pattern, candidate)) continue;
		if (seen++ == index) return deliver(candidate, name, size, index, i + 1, 0, 0);
	}
	for (int b = backend_start; b < backend_count; b++) {
		if (!backends[b].list) continue;
		char candidate[PATH_SIZE];
		for (int i = b == backend_start ? backend_i_start : 0;
		     backends[b].list(backends[b].context, dir, i, candidate, sizeof(candidate)) == 0; i++) {
			if (!matches(pattern, candidate)) continue;
			/* A file written this session hides the one on the disc. */
			char full[PATH_SIZE * 2];
			snprintf(full, sizeof(full), "%s%s%s", dir, dir[0] ? "/" : "", candidate);
			if (find_ram(full)) continue;
			if (seen++ == index)
				return deliver(candidate, name, size, index, MAX_RAM_FILES, b, i + 1);
		}
	}
	name[0] = 0;
	return 1;
}
