/*
 * Streams 11025 Hz 16 bit mono PCM through one SPU voice.
 *
 * The voice loops over a ring of ADPCM blocks in SPU RAM at pitch 0x400
 * (11025 Hz). The PCM is encoded into a shadow copy of the ring in main RAM
 * (spu_adpcm.h) and the new blocks are uploaded by SPU DMA, followed by
 * silent blocks up to the part of the ring that is still being played, so an
 * underrun plays silence instead of a repeat of old audio.
 *
 * The play position comes from the SPU IRQ: the IRQ address walks along the
 * ring in steps of SPU_STREAM_SEG blocks and an interrupt handler counts the
 * steps. That gives the position to within one step and does not depend on
 * the video timing.
 */

#ifndef SPU_STREAM_H
#define SPU_STREAM_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define SPU_STREAM_RATE        11025
#define SPU_STREAM_BASE        0x2000  /* ring start in SPU RAM, bytes */
#define SPU_STREAM_RING_BLOCKS 160     /* 4480 samples, 406 ms */
#define SPU_STREAM_SEG         5       /* IRQ step in blocks, 12.7 ms */
#define SPU_STREAM_VOICE       0

typedef struct {
	uint32_t blocks_written; /* ADPCM blocks encoded since init or reset */
	uint32_t irq_steps;      /* SPU IRQ steps counted since the voice started */
	uint32_t underruns;      /* the voice certainly ran past the data */
	uint32_t resyncs;        /* the stream was restarted behind the voice */
	uint32_t late_blocks;    /* blocks dropped because the voice was past them */
	uint32_t overflows;      /* samples dropped for lack of ring space */
	uint32_t uploads;        /* SPU DMA transfers */
	uint32_t irq_cycles;     /* CPU cycles in the IRQ handler (SPU_STREAM_PROFILE only) */
} SpuStreamStats;

/* Initializes the SPU and prepares the voice. The voice starts with the
 * first spu_stream_flush(). Returns 1 on success. */
int spu_stream_init(void);
void spu_stream_shutdown(void);

/* Samples that are certain to be queued ahead of the voice (a lower bound). */
int spu_stream_queued(void);

/* Encodes samples into the ring (not yet uploaded). */
void spu_stream_write(const int16_t *pcm, int count);

/* Restarts the stream behind the voice if it has caught up with the data.
 * Call before writing after a long pause. */
void spu_stream_sync(void);

/* Uploads what was written and starts the voice at the first call. Also
 * restarts the stream if the voice has caught up with the data. */
void spu_stream_flush(void);

/* Mutes immediately and drops queued data. The producer unmutes after
 * preparing fresh data when playback resumes. */
void spu_stream_reset(void);

/* Changes output gain between silence and unity without moving the voice
 * or its IRQ-derived play position. */
void spu_stream_set_muted(int muted);

/* Holds the SPU IRQ source while its CPU interrupt is masked, as during a
 * BIOS memory-card transfer. The caller restores the returned enable state
 * after clearing the CPU's pending IRQ and before unmasking it. */
int spu_stream_pause_irq(void);
void spu_stream_resume_irq(int enabled);

const SpuStreamStats *spu_stream_stats(void);

/* For tests: the shadow of the ring (what SPU RAM should contain), the
 * absolute block numbers of the write position and the last IRQ step. */
const uint8_t *spu_stream_shadow(void);
uint32_t spu_stream_write_block(void);
uint32_t spu_stream_play_block(void);

/* End of submitted PCM, including a partially encoded final block, and
 * whether all blocks before that exclusive end are certainly audible. */
uint32_t spu_stream_end_block(void);
int spu_stream_has_played(uint32_t end_block);

/* For tests: reads blocks of the ring back from SPU RAM by DMA into dst,
 * a buffer of the size of the ring (each slot lands at its own place). */
void spu_stream_readback(uint8_t *dst, int first_slot, int blocks);

#ifdef __cplusplus
}
#endif

#endif
