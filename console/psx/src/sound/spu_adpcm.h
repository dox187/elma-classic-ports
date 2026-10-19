/*
 * SPU ADPCM encoder and decoder (host independent, no SDK headers).
 *
 * One ADPCM block is 16 bytes and holds 28 samples:
 *   byte 0  (filter << 4) | shift
 *   byte 1  flags (bit 0 loop end, bit 1 repeat, bit 2 loop start)
 *   byte 2..15  14 bytes of 4 bit codes, the low nibble comes first
 *
 * The encoder is a fast one for real time use on the 33.87 MHz R3000: it
 * picks the filter from an open loop estimate (filters 0..3), derives the
 * step from the peak residual and then quantizes in closed loop, so the
 * result decodes exactly like the encoder tracked it. A block is redone with
 * a larger step if a code would clip.
 */

#ifndef SPU_ADPCM_H
#define SPU_ADPCM_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define SPU_ADPCM_SAMPLES 28
#define SPU_ADPCM_BYTES   16

#define SPU_ADPCM_FLAG_END    1
#define SPU_ADPCM_FLAG_REPEAT 2
#define SPU_ADPCM_FLAG_START  4

typedef struct {
	int32_t p1, p2;   /* the last two decoded samples */
	int     no_history; /* next block must not depend on p1/p2 (filter 0) */
} SpuAdpcmState;

/* Start of a stream, or after a cut that left unknown samples in the decoder. */
void spu_adpcm_reset(SpuAdpcmState *st);

/* Encodes 28 samples. out[1] (the flags) is set to 0. */
void spu_adpcm_encode_block(SpuAdpcmState *st, const int16_t *pcm, uint8_t *out);

/* Decodes a block the way the SPU does; the flags are ignored. */
void spu_adpcm_decode_block(SpuAdpcmState *st, const uint8_t *in, int16_t *pcm);

#ifdef __cplusplus
}
#endif

#endif
