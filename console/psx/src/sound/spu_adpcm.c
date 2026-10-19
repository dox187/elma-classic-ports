/* SPU ADPCM encoder and decoder, see spu_adpcm.h. */

#include "spu_adpcm.h"

/* Filter coefficients in 1/64 units; the SPU has these four in common with
 * XA ADPCM (the SPU knows a fifth one that the encoder does not use). */
static const int16_t filter0[4] = { 0, 60, 115, 98 };
static const int16_t filter1[4] = { 0, 0, -52, -55 };

static inline int32_t clamp16(int32_t v)
{
	if (v > 32767) return 32767;
	if (v < -32768) return -32768;
	return v;
}

void spu_adpcm_reset(SpuAdpcmState *st)
{
	st->p1 = st->p2 = 0;
	st->no_history = 1;
}

/* Quantizes with the given filter and step 2^k (shift = 12 - k). Returns 0
 * if a code had to be clipped. On success the state is advanced. */
static int quantize(SpuAdpcmState *st, const int16_t *pcm, int filter, int k,
                    uint8_t *out)
{
	const int32_t c0 = filter0[filter], c1 = filter1[filter];
	const int32_t half = (1 << k) >> 1;
	int32_t p1 = st->p1, p2 = st->p2;
	int clipped = 0;

	for (int i = 0; i < SPU_ADPCM_SAMPLES; i++) {
		const int32_t pred = (p1 * c0 + p2 * c1 + 32) >> 6;
		int32_t q = (pcm[i] - pred + half) >> k;
		if (q > 7) { q = 7; clipped = 1; }
		else if (q < -8) { q = -8; clipped = 1; }
		const int32_t dec = clamp16(pred + q * (1 << k));
		p2 = p1;
		p1 = dec;
		if (i & 1)
			out[2 + (i >> 1)] |= (uint8_t)(q << 4);
		else
			out[2 + (i >> 1)] = (uint8_t)(q & 15);
	}
	if (clipped && k < 12)
		return 0;
	st->p1 = p1;
	st->p2 = p2;
	return 1;
}

void spu_adpcm_encode_block(SpuAdpcmState *st, const int16_t *pcm, uint8_t *out)
{
	int best_filter = 0;
	int32_t best_peak;

	/* Silence, the most common input: all zero codes. */
	if (st->p1 == 0 && st->p2 == 0) {
		int i = 0;
		while (i < SPU_ADPCM_SAMPLES && pcm[i] == 0)
			i++;
		if (i == SPU_ADPCM_SAMPLES) {
			for (i = 0; i < SPU_ADPCM_BYTES; i++)
				out[i] = 0;
			st->no_history = 0;
			return;
		}
	}

	/* Open loop: peak residual of each filter against the original signal. */
	if (st->no_history) {
		best_peak = 0;
		for (int i = 0; i < SPU_ADPCM_SAMPLES; i++) {
			int32_t a = pcm[i] < 0 ? -pcm[i] : pcm[i];
			if (a > best_peak) best_peak = a;
		}
		/* Filter 0 only: the decoder history is unknown. */
	} else {
		int32_t peak[4] = { 0, 0, 0, 0 };
		/* Every second sample is enough to pick the filter and the step (a
		 * block that clips is redone below), and halves the cost. */
		for (int i = 0; i < SPU_ADPCM_SAMPLES; i += 2) {
			const int32_t x = pcm[i];
			const int32_t p1 = i >= 1 ? pcm[i - 1] : st->p1;
			const int32_t p2 = i >= 2 ? pcm[i - 2] : st->p2;
			const int32_t r0 = x < 0 ? -x : x;
			int32_t r1 = x - ((p1 * 60 + 32) >> 6);
			int32_t r2 = x - ((p1 * 115 - p2 * 52 + 32) >> 6);
			int32_t r3 = x - ((p1 * 98 - p2 * 55 + 32) >> 6);
			if (r1 < 0) r1 = -r1;
			if (r2 < 0) r2 = -r2;
			if (r3 < 0) r3 = -r3;
			if (r0 > peak[0]) peak[0] = r0;
			if (r1 > peak[1]) peak[1] = r1;
			if (r2 > peak[2]) peak[2] = r2;
			if (r3 > peak[3]) peak[3] = r3;
		}
		best_peak = peak[0];
		for (int f = 1; f < 4; f++) {
			if (peak[f] < best_peak) {
				best_peak = peak[f];
				best_filter = f;
			}
		}
	}

	/* Smallest step (2^k) that holds the peak in the 4 bit code range. */
	int k = 0;
	while (k < 12 && ((best_peak + ((1 << k) >> 1)) >> k) > 7)
		k++;

	SpuAdpcmState saved = *st;
	while (!quantize(st, pcm, best_filter, k, out)) {
		*st = saved;
		k++;
	}
	st->no_history = 0;
	out[0] = (uint8_t)((best_filter << 4) | (12 - k));
	out[1] = 0;
}

void spu_adpcm_decode_block(SpuAdpcmState *st, const uint8_t *in, int16_t *pcm)
{
	const int filter = (in[0] >> 4) & 7;
	int shift = in[0] & 15;
	const int32_t c0 = filter < 4 ? filter0[filter] : 0;
	const int32_t c1 = filter < 4 ? filter1[filter] : 0;
	if (shift > 12)
		shift = 9;
	int32_t p1 = st->p1, p2 = st->p2;

	for (int i = 0; i < SPU_ADPCM_SAMPLES; i++) {
		int32_t nib = (in[2 + (i >> 1)] >> ((i & 1) * 4)) & 15;
		if (nib & 8) nib -= 16;
		const int32_t s = clamp16(((nib * 4096) >> shift) +
		                          ((p1 * c0 + p2 * c1 + 32) >> 6));
		p2 = p1;
		p1 = s;
		pcm[i] = (int16_t)s;
	}
	st->p1 = p1;
	st->p2 = p2;
	st->no_history = 0;
}
