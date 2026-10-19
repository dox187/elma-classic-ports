/* memcpy for the PlayStation build. The one of PSn00bSDK copies byte by
 * byte, which made every picture copy of the game (blt8, the menus, the RAM
 * file store) several times slower than it needs to be. The link replaces
 * every call of memcpy with this one (-Wl,--wrap=memcpy, gpu.cmake).
 *
 * Overlapping areas keep the byte by byte forward copy of the original, so
 * code that relied on it behaves the same. */
#include <stddef.h>
#include <stdint.h>

typedef struct __attribute__((packed)) {
	uint32_t v;
} unaligned_word;

void* __wrap_memcpy(void* dst, const void* src, size_t n) {
	uint8_t* d = (uint8_t*)dst;
	const uint8_t* s = (const uint8_t*)src;
	if (n >= 16 && (d + n <= s || s + n <= d)) {
		while ((uintptr_t)d & 3) {
			*d++ = *s++;
			n--;
		}
		uint32_t* dw = (uint32_t*)d;
		if (((uintptr_t)s & 3) == 0) {
			const uint32_t* sw = (const uint32_t*)s;
			for (; n >= 32; n -= 32, dw += 8, sw += 8) {
				const uint32_t a = sw[0], b = sw[1], c = sw[2], e = sw[3];
				const uint32_t f = sw[4], g = sw[5], h = sw[6], i = sw[7];
				dw[0] = a, dw[1] = b, dw[2] = c, dw[3] = e;
				dw[4] = f, dw[5] = g, dw[6] = h, dw[7] = i;
			}
			for (; n >= 4; n -= 4) *dw++ = *sw++;
			s = (const uint8_t*)sw;
		} else {
			/* The loads of an unaligned source become lwl/lwr pairs. */
			const unaligned_word* sw = (const unaligned_word*)s;
			for (; n >= 16; n -= 16, dw += 4, sw += 4) {
				const uint32_t a = sw[0].v, b = sw[1].v, c = sw[2].v, e = sw[3].v;
				dw[0] = a, dw[1] = b, dw[2] = c, dw[3] = e;
			}
			for (; n >= 4; n -= 4) *dw++ = (sw++)->v;
			s = (const uint8_t*)sw;
		}
		d = (uint8_t*)dw;
	}
	while (n--) *d++ = *s++;
	return dst;
}
