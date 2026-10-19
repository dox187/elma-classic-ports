#include "all.h"
#include "sound/spu_stream.h"
#include "sound/psx_sound.h"
#include <psxgpu.h>

// PlayStation counterpart of SDL_SOUND.CPP. As there, the game mixes the sound
// itself (CustomMixer in SDL_HHIGH.CPP) on the main thread whenever hang() is
// called. The blocks go to one SPU voice that loops over a ring of ADPCM
// blocks (spu_stream.h), and about two blocks are kept ahead of playback.

int Mostvoltegynemcurpos = 0;

void CustomMixer(void* buffer1, int byteszam1, void* buffer2, int byteszam2, int bitmod16);
int getstatesoundon(void);

namespace {
// Same format and block size as the original: 11025 Hz, 16 bit mono.
const int block_samples = 550;
const int queued_samples_target = 2 * block_samples;
short block[block_samples];
bool device = false;
}

void initdsound(int) {
    if (!Hangenabled)
        hiba((char*)"initdsound, pedig !Hangenabled!");
    Hangenabled = 0;

    if (!spu_stream_init())
        return;
    device = true;
    Hangenabled = 1;
}

void hang() {
    if (!Hangenabled || !device)
        return;
    const bool muted = Mute || !getstatesoundon();
    if (muted)
        spu_stream_set_muted(1);
    spu_stream_sync();
    // The queue is a lower bound of what is ahead of the voice, so the loop
    // is bounded in case the position stops advancing.
    for (int i = 0; i < 4 && spu_stream_queued() < queued_samples_target; ++i) {
        CustomMixer(block, sizeof(block), NULL, 0, 1);
        spu_stream_write(block, block_samples);
    }
    spu_stream_flush();
    if (!muted)
        spu_stream_set_muted(0);
}

void nullazhangot() {
    if (!Hangenabled || !device)
        return;
    spu_stream_reset();
}

#ifdef ELMA_PSX
void psx_wait_for_effects() {
    if (!Hangenabled || !device || Mute || !getstatesoundon())
        return;
    // Mixing completion alone leaves about two PCM buffers in the SPU.
    while (vanmegwav())
        VSync(0);
    const uint32_t end = spu_stream_end_block();
    while (!spu_stream_has_played(end)) {
        if (Mute || !getstatesoundon())
            return;
        // Keep servicing the stream, including the final partial ADPCM block.
        hang();
        VSync(0);
    }
}

#endif
