/* Host test of the memory card LZSS codec: round trips, corrupt input and
 * the sizes for the original state.dat (argv[1], optional). Build:
 *   cc -O2 -Wall -I../src/memcard mc_lz_test.c ../src/memcard/mclz.c -o mc_lz_test */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "mclz.h"

static int fails;
#define CHECK(c, m) do { if (!(c)) { printf("FAIL: %s\n", m); fails++; } } while (0)

static void round_trip(const uint8_t* d, size_t n, const char* what)
{
	uint8_t* c = malloc(MCLZ_BOUND(n));
	uint8_t* r = malloc(n + 1);
	size_t cn = mclz_compress(d, n, c);
	size_t c2n;
	uint8_t* c2 = malloc(MCLZ_BOUND(n));
	c2n = mclz_compress(d, n, c2);
	CHECK(cn == c2n && !memcmp(c, c2, cn), "deterministic");
	CHECK(mclz_expand(c, cn, r, n) == 0 && !memcmp(d, r, n), what);
	if (n > 8) CHECK(mclz_expand(c, cn - 1, r, n) != 0, "truncated input rejected");
	printf("%-22s %7zu -> %6zu\n", what, n, cn);
	free(c); free(r); free(c2);
}

int main(int argc, char** argv)
{
	uint8_t* z = calloc(1, 70000);
	size_t i;
	unsigned s = 12345;
	round_trip(z, 0, "empty");
	round_trip(z, 1, "one byte");
	round_trip(z, 70000, "zeros");
	for (i = 0; i < 70000; i++) { s = s * 1103515245u + 12345u; z[i] = (uint8_t)(s >> 16); }
	round_trip(z, 70000, "random");
	for (i = 0; i < 70000; i++) z[i] = (uint8_t)(i % 185 * 7);
	round_trip(z, 70000, "period 185");
	if (argc > 1) {
		FILE* f = fopen(argv[1], "rb");
		if (f) {
			uint8_t* d = malloc(1 << 20);
			size_t n = fread(d, 1, 1 << 20, f);
			fclose(f);
			round_trip(d, n, "state.dat");
			free(d);
		}
	}
	{ uint8_t bad[3] = { 1, 0xFF, 0xFF }, out[10]; CHECK(mclz_expand(bad, 3, out, 10) != 0, "bad offset rejected"); }
	printf(fails ? "FAIL\n" : "PASS\n");
	return fails != 0;
}
