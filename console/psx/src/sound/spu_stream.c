/* Streams PCM through one SPU voice, see spu_stream.h. */

#include <string.h>
#include <psxapi.h>
#include <psxetc.h>
#include <psxspu.h>
#include <hwregs_c.h>

#include "spu_adpcm.h"
#include "spu_stream.h"

#define RING   SPU_STREAM_RING_BLOCKS
#define SEG    SPU_STREAM_SEG
#define NSEG   (RING / SEG)
#define BLOCK  SPU_ADPCM_BYTES
#define SAMPLES SPU_ADPCM_SAMPLES

/* Uploads start at least this far beyond ahead_block(): the IRQ address may
 * advance one step while a transfer runs, and a transfer that covers the IRQ
 * address raises the interrupt as well, which would shift the count. */
#define MARGIN (SEG + 2)

#define SPUCNT_IRQ_ENABLE 0x0040

_Static_assert(RING % SEG == 0, "the ring must hold whole IRQ steps");
_Static_assert(RING * SAMPLES % 4 == 0, "the ring must be a whole number of words");

static uint8_t shadow[RING * BLOCK] __attribute__((aligned(4)));

static SpuAdpcmState enc;
static int16_t pending[SAMPLES];
static int pending_count;

/* Absolute block numbers (the ring slot is the number modulo RING). */
static uint32_t wblock;      /* next block to encode */
static uint32_t zero_to;     /* blocks [wblock, zero_to) are silent in the shadow */
static uint32_t dirty_from;  /* blocks [dirty_from, wblock) are not uploaded yet */

static volatile uint32_t irq_steps;
static int started;
static int ready;
static int voice_muted;
static uint32_t audible_from;
static SpuStreamStats spu_stats;

/* Writes SPU_CTRL and waits until the SPU reports the new state. */
static void spu_ctrl_write(uint16_t value)
{
	SPU_CTRL = value;
	for (int i = 0; i < 1000; i++)
		if ((SPU_STAT & 0x3f) == (value & 0x3f))
			break;
}

static uint16_t slot_address(uint32_t slot)
{
	return (uint16_t)((SPU_STREAM_BASE + slot * BLOCK) / 8);
}

/* Loop flags of a ring slot: loop start on the first block, loop end with
 * repeat on the last one. */
static uint8_t slot_flags(uint32_t slot)
{
	if (slot == 0)
		return SPU_ADPCM_FLAG_START;
	if (slot == RING - 1)
		return SPU_ADPCM_FLAG_END | SPU_ADPCM_FLAG_REPEAT;
	return 0;
}

static void silent_block(uint32_t number)
{
	const uint32_t slot = number % RING;
	uint8_t *b = shadow + slot * BLOCK;
	memset(b, 0, BLOCK);
	b[1] = slot_flags(slot);
}

/* One SPU DMA transfer of whole blocks. The SDK rounds a transfer of 64 bytes
 * or more up to a multiple of 64 bytes (and moves the extra bytes), so the
 * blocks go in a part of whole 64 byte units and the remaining one to three
 * blocks as a small transfer, which is exact. */
static void dma_slots(uint8_t *buf, uint32_t slot, uint32_t blocks, int write)
{
	while (blocks) {
		uint32_t n = blocks >= 4 ? blocks & ~3u : blocks;
		SpuSetTransferStartAddr(SPU_STREAM_BASE + slot * BLOCK);
		if (write)
			SpuWrite((const uint32_t *)(buf + slot * BLOCK), n * BLOCK);
		else
			SpuRead((uint32_t *)(buf + slot * BLOCK), n * BLOCK);
		SpuIsTransferCompleted(SPU_TRANSFER_WAIT);
		spu_stats.uploads++;
		slot += n;
		blocks -= n;
	}
}

static void upload_slots(uint32_t slot, uint32_t blocks)
{
	dma_slots(shadow, slot, blocks, 1);
}

/* Uploads the shadow blocks [from, to) (absolute numbers). */
static void upload_range(uint32_t from, uint32_t to)
{
	while (from != to) {
		const uint32_t slot = from % RING;
		uint32_t n = to - from;
		if (n > RING - slot)
			n = RING - slot;
		upload_slots(slot, n);
		from += n;
	}
}

/* Blocks before this are certain to have been played: the voice reads a
 * block up to one block before it is audible. */
static uint32_t safe_block(void)
{
	return irq_steps * SEG - 1;
}

/* Blocks from here on are certain not to have been played. */
static uint32_t ahead_block(void)
{
	return irq_steps * SEG + SEG;
}

static void irq_handler(void)
{
#ifdef SPU_STREAM_PROFILE
	/* Root counter 2 at system clock / 8, set up by the test. */
	const uint32_t t0 = TIMER_VALUE(2);
#endif
	const uint16_t ctrl = SPU_CTRL;
	/* Writing the enable bit as 0 acknowledges the interrupt. */
	spu_ctrl_write(ctrl & ~SPUCNT_IRQ_ENABLE);
	const uint32_t steps = irq_steps + 1;
	irq_steps = steps;
	SPU_IRQ_ADDR = slot_address(((steps + 1) % NSEG) * SEG);
	spu_ctrl_write(ctrl | SPUCNT_IRQ_ENABLE);
#ifdef SPU_STREAM_PROFILE
	spu_stats.irq_cycles += ((TIMER_VALUE(2) - t0) & 0xffff) * 8;
#endif
}

int spu_stream_init(void)
{
	SpuInit();
	SPU_MASTER_VOL_L = 0x3fff;
	SPU_MASTER_VOL_R = 0x3fff;

	SPU_KEY_OFF1 = 1 << SPU_STREAM_VOICE;
	SPU_KEY_OFF2 = 0;

	spu_adpcm_reset(&enc);
	pending_count = 0;
	wblock = 0;
	dirty_from = 0;
	irq_steps = 0;
	started = 0;
	voice_muted = 0;
	audible_from = 0;
	memset(&spu_stats, 0, sizeof spu_stats);
	for (uint32_t i = 0; i < RING; i++)
		silent_block(i);
	zero_to = RING - 1;
	SpuSetTransferMode(SPU_TRANSFER_BY_DMA);
	upload_range(0, RING);

	SPU_CH_VOL_L(SPU_STREAM_VOICE) = 0x3fff;
	SPU_CH_VOL_R(SPU_STREAM_VOICE) = 0x3fff;
	SPU_CH_FREQ(SPU_STREAM_VOICE) = 0x400; /* 44100 * 0x400 / 0x1000 Hz */
	SPU_CH_ADDR(SPU_STREAM_VOICE) = slot_address(0);
	SPU_CH_ADSR1(SPU_STREAM_VOICE) = 0x00ff;
	SPU_CH_ADSR2(SPU_STREAM_VOICE) = 0x0000;

	InterruptCallback(IRQ_SPU, irq_handler);
	ready = 1;
	return 1;
}

void spu_stream_shutdown(void)
{
	if (!ready)
		return;
	ready = 0;
	spu_ctrl_write(SPU_CTRL & ~SPUCNT_IRQ_ENABLE);
	InterruptCallback(IRQ_SPU, 0);
	SPU_KEY_OFF1 = 1 << SPU_STREAM_VOICE;
	SPU_KEY_OFF2 = 0;
	started = 0;
}

int spu_stream_queued(void)
{
	const int32_t lead = (int32_t)(wblock - ahead_block());
	return lead * SAMPLES + pending_count;
}

static void encode_pending_block(const int16_t *pcm)
{
	const uint32_t slot = wblock % RING;
	uint8_t *b = shadow + slot * BLOCK;
	spu_adpcm_encode_block(&enc, pcm, b);
	b[1] = slot_flags(slot);
	wblock++;
	spu_stats.blocks_written++;
}

void spu_stream_write(const int16_t *pcm, int count)
{
	if (!ready)
		return;

	/* Whole blocks need ring space; the voice may still read the slot of
	 * safe_block(). */
	for (;;) {
		if (pending_count) {
			int n = SAMPLES - pending_count;
			if (n > count)
				n = count;
			memcpy(pending + pending_count, pcm, n * sizeof(int16_t));
			pending_count += n;
			pcm += n;
			count -= n;
			if (pending_count < SAMPLES)
				return;
			if ((int32_t)(wblock + 1 - safe_block()) > RING) {
				spu_stats.overflows += SAMPLES;
				pending_count = 0;
				continue;
			}
			encode_pending_block(pending);
			pending_count = 0;
		}
		if (count < SAMPLES)
			break;
		if ((int32_t)(wblock + 1 - safe_block()) > RING) {
			spu_stats.overflows += SAMPLES;
		} else {
			encode_pending_block(pcm);
		}
		pcm += SAMPLES;
		count -= SAMPLES;
	}
	if (count > 0) {
		memcpy(pending, pcm, count * sizeof(int16_t));
		pending_count = count;
	}
}

/* Restarts the stream behind the voice. */
static void restart_after(uint32_t block)
{
	spu_stream_set_muted(1);
	audible_from = block;
	const uint32_t old_zero_to = zero_to;
	/* Encoded but not uploaded blocks before the new start never reach SPU
	 * RAM; keep the shadow equal to SPU RAM. */
	for (uint32_t i = dirty_from; (int32_t)(wblock - i) > 0 && (int32_t)(block - i) > 0; i++)
		silent_block(i);
	if ((int32_t)(old_zero_to - block) > 0) {
		for (uint32_t i = block; i != old_zero_to; i++)
			silent_block(i);
	}
	wblock = block;
	dirty_from = block;
	pending_count = 0;
	spu_adpcm_reset(&enc);
	if ((int32_t)(old_zero_to - block) > 0)
		upload_range(block, old_zero_to);
	else
		zero_to = block;
}

void spu_stream_sync(void)
{
	if (!ready || !started)
		return;
	const uint32_t ahead = ahead_block();
	if ((int32_t)(wblock - safe_block()) <= 0) {
		spu_stats.underruns++;
		spu_stats.resyncs++;
		restart_after(ahead + MARGIN);
	} else if ((int32_t)(wblock - (ahead + MARGIN)) < 0) {
		/* Almost all of the data has been played. */
		spu_stats.resyncs++;
		restart_after(ahead + MARGIN);
	} else if ((int32_t)(dirty_from - (ahead + MARGIN)) < 0) {
		/* The voice has moved on while the data was being encoded: the
		 * early blocks come too late, and uploading them could touch the
		 * block that the IRQ is waiting for. The voice plays silence for
		 * them. */
		for (uint32_t i = dirty_from; i != ahead + MARGIN; i++)
			silent_block(i);
		spu_stats.late_blocks += ahead + MARGIN - dirty_from;
		dirty_from = ahead + MARGIN;
	}
}

void spu_stream_flush(void)
{
	if (!ready)
		return;

	spu_stream_sync();

	if (wblock != dirty_from) {
		upload_range(dirty_from, wblock);
		dirty_from = wblock;
	}

	/* Silence the blocks that the voice has left behind since the last time,
	 * so that the ring always ends in silence after the data. */
	const uint32_t new_zero_to = safe_block() + RING;
	if ((int32_t)(new_zero_to - zero_to) > 0) {
		uint32_t from = zero_to;
		if ((int32_t)(wblock - from) > 0)
			from = wblock;
		for (uint32_t i = from; i != new_zero_to; i++)
			silent_block(i);
		/* Blocks [wblock, from) are silent already. */
		upload_range(from, new_zero_to);
		zero_to = new_zero_to;
	}

	if (!started) {
		/* The IRQ handler follows the voice from here on. */
		SPU_IRQ_ADDR = slot_address(SEG);
		spu_ctrl_write(SPU_CTRL | SPUCNT_IRQ_ENABLE);
		SPU_KEY_ON1 = 1 << SPU_STREAM_VOICE;
		SPU_KEY_ON2 = 0;
		started = 1;
	}
}

void spu_stream_reset(void)
{
	if (!ready)
		return;
	/* The producer may not run again while a menu is open. Old slots
	 * outside the cleared future span must never become audible on wrap. */
	spu_stream_set_muted(1);
	if (!started) {
		pending_count = 0;
		spu_adpcm_reset(&enc);
		return;
	}
	restart_after(ahead_block() + MARGIN);
}

void spu_stream_set_muted(int muted)
{
	if (!ready || voice_muted == !!muted)
		return;
	/* The guarded slots before newly prepared data may still contain old
	 * samples. Resume only once they are certainly behind the voice. */
	if (!muted && started && (int32_t)(safe_block() - audible_from) < 0)
		return;
	voice_muted = !!muted;
	SPU_CH_VOL_L(SPU_STREAM_VOICE) = voice_muted ? 0 : 0x3fff;
	SPU_CH_VOL_R(SPU_STREAM_VOICE) = voice_muted ? 0 : 0x3fff;
}

int spu_stream_pause_irq(void)
{
	if (!ready)
		return 0;
	const uint16_t ctrl = SPU_CTRL;
	spu_ctrl_write(ctrl & ~SPUCNT_IRQ_ENABLE);
	return (ctrl & SPUCNT_IRQ_ENABLE) != 0;
}

void spu_stream_resume_irq(int enabled)
{
	if (ready && enabled)
		spu_ctrl_write(SPU_CTRL | SPUCNT_IRQ_ENABLE);
}

const SpuStreamStats *spu_stream_stats(void)
{
	spu_stats.irq_steps = irq_steps;
	return &spu_stats;
}

const uint8_t *spu_stream_shadow(void)
{
	return shadow;
}

uint32_t spu_stream_write_block(void)
{
	return wblock;
}

uint32_t spu_stream_play_block(void)
{
	return irq_steps * SEG;
}

uint32_t spu_stream_end_block(void)
{
	return wblock + (pending_count != 0);
}

int spu_stream_has_played(uint32_t end_block)
{
	return started && (int32_t)(safe_block() - end_block) >= 0;
}

void spu_stream_readback(uint8_t *dst, int first_slot, int blocks)
{
	/* dst holds the whole ring: the slots are read to their own place. */
	dma_slots(dst, first_slot, blocks, 0);
}
