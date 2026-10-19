/* RAM-file writes must fit their actual bytes even when spare growth room
 * does not fit in the fragmented console heap. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static size_t allocation_limit = 70000;
static unsigned refused;
static void* limited_realloc(void* ptr, size_t size) {
	if (size > allocation_limit) {
		refused++;
		return NULL;
	}
	return realloc(ptr, size);
}

#define realloc limited_realloc
#include "../src/psx_file.c"
#undef realloc

static unsigned failures;
#define CHECK(condition) do { if (!(condition)) { \
	printf("FAIL line %d: %s\n", __LINE__, #condition); failures++; \
} } while (0)

int main(void) {
	/* Match the state serializer's version, level-times and player-array
	 * writes, followed by its small option fields. */
	static unsigned char state[4 + 90 * 688 + 50 * 116 + 256];
	static unsigned char back[sizeof(state)];
	for (size_t i = 0; i < sizeof(state); ++i) state[i] = (unsigned char)(i % 17);
	for (int pass = 0; pass < 4; ++pass) {
		state[sizeof(state)-1] = (unsigned char)pass;
		psx_file* f = psx_fopen("state.dat", "wb");
		CHECK(f != NULL);
		CHECK(psx_fwrite(state, 1, 4, f) == 4);
		CHECK(psx_fwrite(state + 4, 1, 90 * 688, f) == 90 * 688);
		CHECK(psx_fwrite(state + 4 + 90 * 688, 1, 50 * 116, f) == 50 * 116);
		CHECK(psx_fwrite(state + sizeof(state) - 256, 1, 256, f) == 256);
		CHECK(!psx_ferror(f));
		psx_fclose(f);
		CHECK(psx_file_ram_used() < 4096);
		f = psx_fopen("state.dat", "rb");
		CHECK(f != NULL);
		CHECK(psx_fread(back, 1, sizeof(back), f) == sizeof(back));
		CHECK(memcmp(state, back, sizeof(back)) == 0);
		psx_fclose(f);
	}
	CHECK(refused != 0);
	/* A genuine allocation failure must still report a short write. */
	allocation_limit = 1024;
	psx_file* f = psx_fopen("too-big.dat", "wb");
	CHECK(psx_fwrite(state, 1, 4096, f) < 4096);
	CHECK(psx_ferror(f));
	psx_fclose(f);
	printf("%s RAM-file allocation fallback (%u failures)\n", failures ? "FAIL" : "PASS", failures);
	return failures ? 1 : 0;
}
