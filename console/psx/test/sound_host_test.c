/*
 * Host test of the SPU ADPCM encoder (src/sound/spu_adpcm.c): encodes sine,
 * noise, a speech-like sweep and any WAV files given on the command line,
 * decodes them again and requires a reasonable signal to noise ratio. Also
 * prints the CRC32 of the encoded test signal of soundtest/signal.h, which
 * the PS1 test compares with what the PS1 encoder produces.
 *
 *   sound_host_test [--crc-only] [file.wav ...]
 *
 * WAV files are 16 bit mono with a 44 byte header, as the game reads them.
 */

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "spu_adpcm.h"
#include "signal.h"

#define CRC_BLOCKS 2000

static uint32_t crc32_update(uint32_t crc, const uint8_t *p, size_t n)
{
	crc = ~crc;
	while (n--) {
		crc ^= *p++;
		for (int k = 0; k < 8; k++)
			crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1)));
	}
	return ~crc;
}

/* Encodes the whole signal (padded with silence to whole blocks) and returns
 * the SNR in dB of the decoded signal. */
static double snr_of(const int16_t *pcm, int count, uint32_t *crc, int *peak_err)
{
	const int blocks = (count + 27) / 28;
	SpuAdpcmState enc, dec;
	spu_adpcm_reset(&enc);
	dec.p1 = dec.p2 = 0;
	double sig = 0, err = 0;
	int worst = 0;
	for (int b = 0; b < blocks; b++) {
		int16_t in[28] = { 0 }, out[28];
		uint8_t code[16];
		for (int i = 0; i < 28 && b * 28 + i < count; i++)
			in[i] = pcm[b * 28 + i];
		spu_adpcm_encode_block(&enc, in, code);
		if (crc)
			*crc = crc32_update(*crc, code, 16);
		spu_adpcm_decode_block(&dec, code, out);
		if (dec.p1 != enc.p1 || dec.p2 != enc.p2) {
			printf("encoder and decoder disagree in block %d\n", b);
			exit(1);
		}
		for (int i = 0; i < 28; i++) {
			const double d = out[i] - in[i];
			sig += (double)in[i] * in[i];
			err += d * d;
			if (fabs(d) > worst) worst = (int)fabs(d);
		}
	}
	if (peak_err)
		*peak_err = worst;
	if (err == 0)
		return 99;
	if (sig == 0)
		return 0;
	return 10 * log10(sig / err);
}

static int failures;

static void check(const char *name, const int16_t *pcm, int count, double min_db)
{
	int peak = 0;
	const double db = snr_of(pcm, count, NULL, &peak);
	const int ok = db >= min_db;
	printf("%-28s %7d samples  SNR %5.1f dB (min %.0f)  peak error %5d  %s\n",
	       name, count, db, min_db, peak, ok ? "ok" : "FAIL");
	if (!ok)
		failures++;
}

int main(int argc, char **argv)
{
	int crc_only = 0;
	int first_file = 1;
	if (argc > 1 && !strcmp(argv[1], "--crc-only")) {
		crc_only = 1;
		first_file = 2;
	}

	uint32_t crc = 0;
	{
		SpuAdpcmState enc;
		spu_adpcm_reset(&enc);
		for (uint32_t b = 0; b < CRC_BLOCKS; b++) {
			int16_t in[28];
			uint8_t code[16];
			for (int i = 0; i < 28; i++)
				in[i] = sound_signal(b * 28 + i);
			spu_adpcm_encode_block(&enc, in, code);
			crc = crc32_update(crc, code, 16);
		}
	}
	printf("crc=%08x blocks=%d\n", crc, CRC_BLOCKS);
	if (crc_only)
		return 0;

	enum { N = 44100 };
	static int16_t buf[N];

	for (int i = 0; i < N; i++)
		buf[i] = (int16_t)lrint(8000 * sin(2 * M_PI * 440 * i / 11025));
	check("sine 440 Hz, 8000", buf, N, 30);
	for (int i = 0; i < N; i++)
		buf[i] = (int16_t)lrint(30000 * sin(2 * M_PI * 1000 * i / 11025));
	check("sine 1000 Hz, 30000", buf, N, 30);
	for (int i = 0; i < N; i++)
		buf[i] = (int16_t)lrint(12000 * sin(2 * M_PI * 3000 * i / 11025));
	check("sine 3000 Hz, 12000", buf, N, 20);
	for (int i = 0; i < N; i++) {
		const double f = 100 + 4000.0 * i / N;
		buf[i] = (int16_t)lrint(10000 * sin(2 * M_PI * f * i / 11025));
	}
	check("sweep 100..4100 Hz", buf, N, 20);
	srand(1);
	for (int i = 0; i < N; i++)
		buf[i] = (int16_t)((rand() % 16001) - 8000);
	check("white noise +-8000", buf, N, 14);
	for (int i = 0; i < N; i++)
		buf[i] = (int16_t)((rand() % 1601) - 800);
	check("white noise +-800", buf, N, 14);
	for (int i = 0; i < N; i++)
		buf[i] = sound_signal((uint32_t)i);
	check("test signal (soundtest)", buf, N, 25);
	for (int i = 0; i < N; i++)
		buf[i] = (i / 1000) % 2 ? 20000 : -20000;
	check("square wave +-20000", buf, N, 20);
	memset(buf, 0, sizeof buf);
	buf[5000] = 30000; /* a click in silence */
	check("single click 30000", buf, N, 6);

	for (int f = first_file; f < argc; f++) {
		FILE *h = fopen(argv[f], "rb");
		if (!h) {
			printf("cannot open %s\n", argv[f]);
			failures++;
			continue;
		}
		fseek(h, 0, SEEK_END);
		const long size = ftell(h);
		fseek(h, 44, SEEK_SET);
		const int count = (int)((size - 44) / 2);
		int16_t *pcm = malloc((size_t)count * 2);
		if (fread(pcm, 2, (size_t)count, h) != (size_t)count) {
			printf("cannot read %s\n", argv[f]);
			failures++;
		} else {
			const char *name = strrchr(argv[f], '/');
			check(name ? name + 1 : argv[f], pcm, count, 16);
		}
		free(pcm);
		fclose(h);
	}

	printf(failures ? "FAIL\n" : "PASS\n");
	return failures ? 1 : 0;
}
