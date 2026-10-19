#include <stdlib.h>
#include <string.h>

#include "mclz.h"

#define HASH_BITS 12
#define MIN_MATCH 3
#define MAX_MATCH 258
#define MAX_OFFSET 65536

static unsigned hash3(const uint8_t* p)
{
	return (((unsigned)p[0] << 8) ^ ((unsigned)p[1] << 4) ^ ((unsigned)p[2] * 0x9E5u)) &
	       ((1u << HASH_BITS) - 1);
}

size_t mclz_compress(const uint8_t* src, size_t n, uint8_t* dst)
{
	/* Two candidates per bucket (newest first). */
	int32_t* table = (int32_t*)malloc(sizeof(int32_t) * 2 * (1u << HASH_BITS));
	size_t o = 0, i = 0, ctrl = 0;
	int bit = 8;
	unsigned k;

	if (table)
		for (k = 0; k < 2u << HASH_BITS; k++) table[k] = -1;
	while (i < n) {
		size_t best_len = 0, best_off = 0;
		if (bit == 8) {
			ctrl = o++;
			dst[ctrl] = 0;
			bit = 0;
		}
		if (table && i + MIN_MATCH <= n) {
			unsigned h = hash3(src + i);
			int c;
			for (c = 0; c < 2; c++) {
				int32_t cand = table[2 * h + c];
				if (cand >= 0 && i - (size_t)cand <= MAX_OFFSET) {
					size_t len = 0, max = n - i < MAX_MATCH ? n - i : MAX_MATCH;
					while (len < max && src[(size_t)cand + len] == src[i + len]) len++;
					if (len > best_len) {
						best_len = len;
						best_off = i - (size_t)cand;
					}
				}
			}
		}
		if (best_len >= MIN_MATCH) {
			dst[ctrl] |= (uint8_t)(1 << bit);
			dst[o++] = (uint8_t)((best_off - 1) & 0xFF);
			dst[o++] = (uint8_t)((best_off - 1) >> 8);
			dst[o++] = (uint8_t)(best_len - MIN_MATCH);
		} else {
			best_len = 1;
			dst[o++] = src[i];
		}
		/* Index every position the item covers. */
		if (table) {
			size_t e = i + best_len, j;
			for (j = i; j < e && j + MIN_MATCH <= n; j++) {
				unsigned h = hash3(src + j);
				table[2 * h + 1] = table[2 * h];
				table[2 * h] = (int32_t)j;
			}
		}
		i += best_len;
		bit++;
	}
	free(table);
	return o;
}

int mclz_expand(const uint8_t* src, size_t in_n, uint8_t* dst, size_t out_n)
{
	size_t i = 0, o = 0;
	while (o < out_n) {
		unsigned ctrl, bit;
		if (i >= in_n) return -1;
		ctrl = src[i++];
		for (bit = 0; bit < 8 && o < out_n; bit++) {
			if (ctrl & (1u << bit)) {
				size_t off, len, k;
				if (i + 3 > in_n) return -1;
				off = ((size_t)src[i] | (size_t)src[i + 1] << 8) + 1;
				len = (size_t)src[i + 2] + MIN_MATCH;
				i += 3;
				if (off > o || len > out_n - o) return -1;
				for (k = 0; k < len; k++, o++) dst[o] = dst[o - off];
			} else {
				if (i >= in_n) return -1;
				dst[o++] = src[i++];
			}
		}
	}
	return i == in_n ? 0 : -1;
}

uint32_t mclz_crc32(const uint8_t* data, size_t n, uint32_t crc)
{
	size_t i;
	int k;
	crc = ~crc;
	for (i = 0; i < n; i++) {
		crc ^= data[i];
		for (k = 0; k < 8; k++) crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
	}
	return ~crc;
}
