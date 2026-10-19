/* Tiny LZSS codec for the memory card save (plain C, host-testable).
 *
 * Stream: groups of one control byte (bit 0 first, 1 = match) followed by up
 * to 8 items. A literal is one byte; a match is 3 bytes: offset-1 (u16 LE)
 * and length-3 (u8), so length 3..258 and offset 1..65536. Matches may
 * overlap their own output (offset 1 is a run of one byte). The encoder is
 * deterministic and keeps one candidate per hash bucket; the decoder checks
 * every bound. */
#ifndef ELMA_PSX_MCLZ_H
#define ELMA_PSX_MCLZ_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Worst-case compressed size for n input bytes. */
#define MCLZ_BOUND(n) ((n) + (n) / 8 + 16)

/* Compresses src into dst (at least MCLZ_BOUND(n) bytes). Returns the size. */
size_t mclz_compress(const uint8_t* src, size_t n, uint8_t* dst);
/* Expands exactly out_n bytes. Returns 0 on success, -1 on a corrupt stream
 * (or one that does not produce exactly out_n bytes from in_n). */
int mclz_expand(const uint8_t* src, size_t in_n, uint8_t* dst, size_t out_n);
uint32_t mclz_crc32(const uint8_t* data, size_t n, uint32_t crc);

#ifdef __cplusplus
}
#endif

#endif
