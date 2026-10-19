/*
 * Elasto Mania PSX port: sound output test.
 *
 * Runs src/sound/psx_sound.cpp (initdsound, hang, nullazhangot) with a mixer
 * that produces the known signal of signal.h, streams it through the SPU for
 * a few seconds and checks, inside the PS1:
 *   - SPU RAM, read back by DMA, equals the encoded data in main RAM
 *   - the streamed data decodes to the signal at the right place
 *   - playback advances at the right speed and nothing underruns
 *   - nullazhangot() and a long stall recover without a repeat of old audio
 *   - the encoder output equals the one of the host build (CRC)
 * and measures the CPU cycles of hang() and of the encoder.
 *
 * The state lives in `sound_state` for test/sound_test.lua, which reads it
 * from emulator RAM. Nothing is audible in the headless harness.
 */

#include <stdint.h>
#include <string.h>
#include <psxapi.h>
#include <psxetc.h>
#include <psxgpu.h>
#include <hwregs_c.h>

extern "C" {
#include "sound/spu_adpcm.h"
#include "sound/spu_stream.h"
}
#include "signal.h"

int Hangenabled = 1;
int Mute = 0;
void hiba(char*, const char*) { for (;;) {} }

void initdsound(int);
void hang();
void nullazhangot();
void CustomMixer(void* buffer1, int byteszam1, void* buffer2, int byteszam2, int bitmod16);

#define MAGIC 0x534e4421u /* "SND!" */

enum {
	FAIL_READBACK = 1 << 0,
	FAIL_DECODE   = 1 << 1,
	FAIL_SPEED    = 1 << 2,
	FAIL_UNDERRUN = 1 << 3,
	FAIL_RESET    = 1 << 4,
	FAIL_STALL    = 1 << 5,
	FAIL_CRC      = 1 << 6,
	FAIL_SILENCE  = 1 << 7,
};

/* Read by test/sound_test.lua. Keep the field names stable. */
struct SoundState {
	volatile uint32_t magic;
	volatile uint32_t done;
	volatile uint32_t fail_mask;
	volatile uint32_t frame;          /* VSync count of the program */
	volatile uint32_t irq_steps;
	volatile uint32_t underruns;
	volatile uint32_t resyncs;
	volatile uint32_t overflows;
	volatile uint32_t uploads;
	volatile uint32_t readbacks;
	volatile uint32_t readback_bad;   /* ring blocks that differ */
	volatile uint32_t decode_checks;
	volatile uint32_t decode_min_ratio; /* signal/error energy, min of the checks */
	volatile uint32_t speed_per_mille;  /* IRQ steps against the elapsed time */
	volatile uint32_t crc;
	volatile uint32_t hang_calls;
	volatile uint32_t hang_cycles_avg;
	volatile uint32_t hang_cycles_max;
	volatile uint32_t enc_cycles_signal;  /* per 550 samples */
	volatile uint32_t enc_cycles_noise;
	volatile uint32_t enc_cycles_silence;
	volatile uint32_t mixed_samples;
	volatile uint32_t hang_cycles_a;      /* average of the steady phase A */
	volatile uint32_t dma_cycles_1;       /* one 16 byte SPU DMA transfer */
	volatile uint32_t dma_cycles_40;      /* 640 bytes */
	volatile uint32_t irq_cycles;         /* in the SPU IRQ handler, whole run */
	volatile uint32_t mixer_cycles_a;     /* of the test mixer within hang_cycles_a, per call */
	volatile uint32_t dbg0, dbg1, dbg2, dbg3; /* first mismatch: abs block, readbacks, play, wblock */
};
SoundState sound_state;

/* Root counter 2 at system clock / 8. */
static inline uint32_t timer_now() { return TIMER_VALUE(2) & 0xffff; }
static inline uint32_t timer_delta(uint32_t start) { return ((timer_now() - start) & 0xffff) * 8; }

static uint32_t mix_pos; /* next sample number of the signal */
static uint64_t mix_total; /* cycles spent in CustomMixer */
static int signal_on = 1;

/* The mixer of the test: the known signal, or silence. */
void CustomMixer(void* buffer1, int byteszam1, void*, int, int)
{
	const uint32_t t = timer_now();
	int16_t *out = (int16_t *)buffer1;
	const int n = byteszam1 / 2;
	for (int i = 0; i < n; i++)
		out[i] = signal_on ? sound_signal(mix_pos + i) : 0;
	mix_pos += n;
	mix_total += timer_delta(t);
	sound_state.mixed_samples = mix_pos;
}

static uint32_t crc32_update(uint32_t crc, const uint8_t *p, uint32_t n)
{
	crc = ~crc;
	while (n--) {
		crc ^= *p++;
		for (int k = 0; k < 8; k++)
			crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1)));
	}
	return ~crc;
}

#define RING SPU_STREAM_RING_BLOCKS
#define SEG  SPU_STREAM_SEG

static uint8_t readback[RING * SPU_ADPCM_BYTES] __attribute__((aligned(4)));

static int block_is_silent(const uint8_t *b)
{
	for (int i = 0; i < 16; i++)
		if (i != 1 && b[i])
			return 0;
	return 1;
}

/* Compares SPU RAM with the shadow ring, skipping the blocks where the IRQ
 * address is or may move to (reading them by DMA would raise the interrupt).
 * Also requires the ring to be silent after the data. */
static void check_ring()
{
	const uint8_t *shadow = spu_stream_shadow();
	const uint32_t play = spu_stream_play_block();
	const uint32_t wblock = spu_stream_write_block();
	const uint32_t safe = play - 1;

	/* Absolute block ranges [safe, play + SEG) and [play + 3 * SEG + 1,
	 * safe + RING). */
	const uint32_t ranges[2][2] = { { safe, play + SEG }, { play + 3 * SEG + 1, safe + RING } };
	for (int r = 0; r < 2; r++) {
		uint32_t from = ranges[r][0];
		while (from != ranges[r][1]) {
			const uint32_t slot = from % RING;
			uint32_t n = ranges[r][1] - from;
			if (n > RING - slot)
				n = RING - slot;
			spu_stream_readback(readback, slot, n);
			for (uint32_t i = 0; i < n; i++) {
				const uint32_t s = slot + i;
				if (memcmp(readback + s * 16, shadow + s * 16, 16)) {
					if (!sound_state.readback_bad) {
						sound_state.dbg0 = from + i;
						sound_state.dbg1 = sound_state.readbacks;
						sound_state.dbg2 = play;
						sound_state.dbg3 = wblock;
					}
					sound_state.readback_bad++;
				}
				/* Silent after the data (slot flags apart). */
				const uint32_t abs = from + i;
				if ((int32_t)(abs - wblock) >= 0 && (int32_t)(abs - (safe + RING - 3 * SEG)) < 0 &&
				    !block_is_silent(readback + s * 16))
					sound_state.fail_mask |= FAIL_SILENCE;
			}
			from += n;
		}
	}
	sound_state.readbacks++;
	if (sound_state.readback_bad)
		sound_state.fail_mask |= FAIL_READBACK;
}

/* Decodes the last blocks that were written (from the SPU readback of
 * check_ring) and compares them with the signal. Only valid while the stream
 * has not been restarted. */
static void check_decode()
{
	const uint32_t wblock = spu_stream_write_block();
	const uint32_t play = spu_stream_play_block();
	const uint32_t first = wblock - 25;
	if ((int32_t)(first - (play + 3 * SEG + 1)) < 0)
		return;
	SpuAdpcmState dec;
	dec.p1 = sound_signal(first * 28 - 1);
	dec.p2 = sound_signal(first * 28 - 2);
	int64_t sig = 0, err = 0;
	for (uint32_t b = first; b != wblock; b++) {
		int16_t pcm[28];
		spu_adpcm_decode_block(&dec, readback + (b % RING) * 16, pcm);
		if (b - first < 3)
			continue; /* the decoder history settles */
		for (int i = 0; i < 28; i++) {
			const int32_t want = sound_signal(b * 28 + i);
			sig += (int64_t)want * want;
			err += (int64_t)(pcm[i] - want) * (pcm[i] - want);
		}
	}
	const uint32_t ratio = (uint32_t)(sig / (err + 1));
	if (sound_state.decode_checks == 0 || ratio < sound_state.decode_min_ratio)
		sound_state.decode_min_ratio = ratio;
	sound_state.decode_checks++;
	if (ratio < 1000) /* 30 dB; the host encoder gives 40 dB on this signal */
		sound_state.fail_mask |= FAIL_DECODE;
}

static void frames(int n, bool call_hang)
{
	while (n-- > 0) {
		VSync(0);
		sound_state.frame++;
		if (call_hang) {
			const uint32_t t = timer_now();
			hang();
			const uint32_t c = timer_delta(t);
			sound_state.hang_calls++;
			static uint64_t total;
			total += c;
			sound_state.hang_cycles_avg = (uint32_t)(total / sound_state.hang_calls);
			if (c > sound_state.hang_cycles_max)
				sound_state.hang_cycles_max = c;
		}
		const SpuStreamStats *st = spu_stream_stats();
		sound_state.irq_steps = st->irq_steps;
		sound_state.underruns = st->underruns;
		sound_state.resyncs = st->resyncs;
		sound_state.overflows = st->overflows;
		sound_state.uploads = st->uploads;
		sound_state.irq_cycles = st->irq_cycles;
	}
}

static uint32_t bench_encode(int kind)
{
	SpuAdpcmState enc;
	spu_adpcm_reset(&enc);
	static int16_t pcm[550 + 28];
	static uint8_t out[16];
	uint32_t total = 0, lcg = 12345, pos = 0;
	const int rounds = 50;
	for (int r = 0; r < rounds; r++) {
		for (int i = 0; i < 550; i++) {
			if (kind == 0) pcm[i] = sound_signal(pos++);
			else if (kind == 1) { lcg = lcg * 1103515245u + 12345u; pcm[i] = (int16_t)((lcg >> 16) % 16001) - 8000; }
			else pcm[i] = 0;
		}
		const uint32_t t = timer_now();
		for (int b = 0; b + 28 <= 550; b += 28)
			spu_adpcm_encode_block(&enc, pcm + b, out);
		total += timer_delta(t);
	}
	/* 550 samples are 19.6 blocks; 19 blocks were timed, scale up. */
	return total / rounds * 550 / (19 * 28);
}

int main()
{
	sound_state.magic = MAGIC;
	ResetGraph(0);
	SetVideoMode(MODE_NTSC);
	TIMER_CTRL(2) = 0x0200;
	TIMER_VALUE(2) = 0;

	/* The encoder of the PS1 must give the bytes of the host build. */
	{
		SpuAdpcmState enc;
		spu_adpcm_reset(&enc);
		uint32_t crc = 0;
		for (uint32_t b = 0; b < 2000; b++) {
			int16_t in[28];
			uint8_t code[16];
			for (int i = 0; i < 28; i++)
				in[i] = sound_signal(b * 28 + i);
			spu_adpcm_encode_block(&enc, in, code);
			crc = crc32_update(crc, code, 16);
		}
		sound_state.crc = crc;
	}

	initdsound(0);
	if (!Hangenabled)
		sound_state.fail_mask |= FAIL_UNDERRUN;

	/* A: five seconds of streaming, hang() once per frame. */
	uint32_t steps_at_start = 0;
	frames(1, true);
	steps_at_start = spu_stream_stats()->irq_steps;
	const uint32_t frame_a0 = sound_state.frame;
	const int checkpoints[] = { 20, 60, 120, 200, 299 };
	int done_frames = 1;
	for (int c = 0; c < 5; c++) {
		frames(checkpoints[c] - done_frames, true);
		done_frames = checkpoints[c];
		check_ring();
		check_decode();
	}
	{
		const uint32_t elapsed = sound_state.frame - frame_a0;
		const uint32_t steps = spu_stream_stats()->irq_steps - steps_at_start;
		/* NTSC: 59.94 frames/s; a step is 140 samples at 11025 Hz. */
		sound_state.speed_per_mille = (uint32_t)((uint64_t)steps * 1000 * 60000 * 140 /
		                                         ((uint64_t)elapsed * 1001 * 11025));
		if (sound_state.speed_per_mille < 950 || sound_state.speed_per_mille > 1050)
			sound_state.fail_mask |= FAIL_SPEED;
	}
	sound_state.hang_cycles_a = sound_state.hang_cycles_avg;
	sound_state.mixer_cycles_a = (uint32_t)(mix_total / sound_state.hang_calls);
	if (sound_state.underruns || sound_state.resyncs || sound_state.overflows)
		sound_state.fail_mask |= FAIL_UNDERRUN;

	/* B: nullazhangot() drops the queue; the stream continues. */
	{
		nullazhangot();
		const uint32_t wb = spu_stream_write_block();
		const uint32_t play = spu_stream_play_block();
		if ((int32_t)(wb - play) > 4 * SEG)
			sound_state.fail_mask |= FAIL_RESET;
		check_ring();
		frames(30, true);
		check_ring();
		if (spu_stream_queued() < 1100 || spu_stream_stats()->underruns)
			sound_state.fail_mask |= FAIL_RESET;
	}

	/* C: the game stalls for 0.7 s, longer than the ring holds. The voice
	 * must have played silence and the stream must restart behind it. */
	{
		const uint32_t before = spu_stream_stats()->underruns;
		frames(42, false);
		hang();
		frames(1, true);
		check_ring();
		if (spu_stream_stats()->underruns != before + 1)
			sound_state.fail_mask |= FAIL_STALL;
		frames(60, true);
		check_ring();
		if (spu_stream_stats()->underruns != before + 1 || spu_stream_queued() < 1100)
			sound_state.fail_mask |= FAIL_STALL;
	}

	/* D: silence (Mute) costs next to nothing and still streams. */
	{
		signal_on = 0;
		frames(60, true);
		check_ring();
	}

	/* Cost of the encoder alone, per 550 samples. */
	sound_state.enc_cycles_signal = bench_encode(0);
	sound_state.enc_cycles_noise = bench_encode(1);
	sound_state.enc_cycles_silence = bench_encode(2);

	{
		/* SPU DMA cost, measured with the read path (same setup as the upload),
		 * away from the IRQ blocks. */
		const uint32_t play = spu_stream_play_block();
		const uint32_t slot = (play + 3 * SEG + 1) % RING;
		uint32_t t = timer_now();
		spu_stream_readback(readback, slot, 1);
		sound_state.dma_cycles_1 = timer_delta(t);
		t = timer_now();
		spu_stream_readback(readback, slot, 40 > RING - slot ? RING - slot : 40);
		sound_state.dma_cycles_40 = timer_delta(t);
	}

	sound_state.done = 1;
	for (;;)
		VSync(0);
}
