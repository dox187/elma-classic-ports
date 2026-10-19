#include "all.h"
#include "sound/spu_stream.h"

// PlayStation counterpart of SDL_SOUND.CPP. As there, the game mixes the sound
// itself (CustomMixer in SDL_HHIGH.CPP) on the main thread whenever hang() is
// called. The blocks go to one SPU voice that loops over a ring of ADPCM
// blocks (spu_stream.h), and about two blocks are kept ahead of playback.

int Mostvoltegynemcurpos = 0;

void CustomMixer(void* buffer1, int byteszam1, void* buffer2, int byteszam2, int bitmod16);

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
    spu_stream_sync();
    // The queue is a lower bound of what is ahead of the voice, so the loop
    // is bounded in case the position stops advancing.
    for (int i = 0; i < 4 && spu_stream_queued() < queued_samples_target; ++i) {
        CustomMixer(block, sizeof(block), NULL, 0, 1);
        spu_stream_write(block, block_samples);
    }
    spu_stream_flush();
}

void nullazhangot() {
    if (!Hangenabled || !device)
        return;
    spu_stream_reset();
}
