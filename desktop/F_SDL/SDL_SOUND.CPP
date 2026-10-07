#include "all.h"
#include <SDL.h>
#include <vector>

// SDL counterpart of F_WIN/W_SOUND2.CPP. As with DirectSound in the original,
// the game mixes the sound itself (CustomMixer in SDL_HHIGH.CPP) on the main
// thread whenever hang() is called, and the mixed blocks are queued to the
// audio device.

int Mostvoltegynemcurpos = 0;

void CustomMixer(void* buffer1, int byteszam1, void* buffer2, int byteszam2, int bitmod16);

namespace {
// Same format and block size as the original: 11025 Hz, 16 bit mono,
// 1100 byte blocks, about two blocks queued ahead of playback.
const int block_samples = 550;
short block[block_samples];

#if SDL_MAJOR_VERSION >= 2
SDL_AudioDeviceID device = 0;
const Uint32 queued_bytes_target = 2 * block_samples * sizeof(short);
#else
// SDL 1.2 has no audio queue: the mixed blocks are resampled to the rate of
// the device and put into a ring buffer that the audio callback drains,
// guarded by SDL_LockAudio. The device is opened at 48000 Hz stereo, as the
// RetroArch of the Miyoo Mini does, so no further conversion is needed there.
bool device = false;
SDL_AudioSpec have;
const int ring_frames = 32768;
short ring[ring_frames]; // mono, at the rate of the device
int ring_read = 0, ring_write = 0;
int queued_frames_target = 0;
std::vector<short> resampled;
short previous = 0; // last sample of the previous block
double position = 0; // next output position, 0 being the previous sample

int ring_queued() { return (ring_write - ring_read + ring_frames) % ring_frames; }

void callback(void*, Uint8* stream, int length) {
    short* out = reinterpret_cast<short*>(stream);
    const int frames = length / int(sizeof(short) * have.channels);
    for (int i = 0; i < frames; ++i) {
        short sample = 0;
        if (ring_read != ring_write) {
            sample = ring[ring_read];
            ring_read = (ring_read + 1) % ring_frames;
        }
        for (int channel = 0; channel < have.channels; ++channel)
            *out++ = sample;
    }
}

// Linear interpolation from the 11025 Hz of the mixer to the device rate,
// continuing smoothly from the previous block.
int resample_block() {
    const double step = 11025.0 / have.freq;
    int count = 0;
    while (position < block_samples) {
        const int i = int(position);
        const double fraction = position - i;
        const short a = i == 0 ? previous : block[i - 1];
        const short b = block[i];
        resampled[count++] = short(a + (b - a) * fraction);
        position += step;
    }
    position -= block_samples;
    previous = block[block_samples - 1];
    return count;
}
#endif
}

void initdsound(int) {
    if (!Hangenabled)
        hiba((char*)"initdsound, pedig !Hangenabled!");
    Hangenabled = 0;

    if (SDL_InitSubSystem(SDL_INIT_AUDIO) != 0) {
        fprintf(stderr, "SDL audio: %s\n", SDL_GetError());
        return;
    }
    SDL_AudioSpec want;
    SDL_memset(&want, 0, sizeof(want));
    want.freq = 11025;
    want.format = AUDIO_S16SYS;
    want.channels = 1;
    want.samples = 512;
#if SDL_MAJOR_VERSION >= 2
    device = SDL_OpenAudioDevice(NULL, 0, &want, NULL, 0);
    if (!device) {
        fprintf(stderr, "SDL audio: %s\n", SDL_GetError());
        SDL_QuitSubSystem(SDL_INIT_AUDIO);
        return;
    }
    SDL_PauseAudioDevice(device, 0);
#else
    want.freq = 48000;
    want.channels = 2;
    want.samples = 1024;
    want.callback = callback;
    if (SDL_OpenAudio(&want, &have) != 0) {
        fprintf(stderr, "SDL audio: %s\n", SDL_GetError());
        SDL_QuitSubSystem(SDL_INIT_AUDIO);
        return;
    }
    if (have.format != AUDIO_S16SYS || have.channels < 1 || have.channels > 2 ||
        have.freq < 11025 || have.freq > 192000) {
        // Let SDL convert from the format that was asked for.
        SDL_CloseAudio();
        if (SDL_OpenAudio(&want, NULL) != 0) {
            fprintf(stderr, "SDL audio: %s\n", SDL_GetError());
            SDL_QuitSubSystem(SDL_INIT_AUDIO);
            return;
        }
        have = want;
    }
    fprintf(stderr, "SDL audio: %d Hz, %d channels, %d samples\n",
            have.freq, have.channels, have.samples);
    resampled.resize(block_samples * have.freq / 11025 + 2);
    // Keep a callback's worth and one block ahead of the device.
    queued_frames_target = have.samples + int(resampled.size());
    if (queued_frames_target > ring_frames - int(resampled.size()) - 1)
        queued_frames_target = ring_frames - int(resampled.size()) - 1;
    device = true;
    SDL_PauseAudio(0);
#endif
    Hangenabled = 1;
}

void hang() {
    if (!Hangenabled || !device)
        return;
#if SDL_MAJOR_VERSION >= 2
    while (SDL_GetQueuedAudioSize(device) < queued_bytes_target) {
        CustomMixer(block, sizeof(block), NULL, 0, 1);
        SDL_QueueAudio(device, block, sizeof(block));
    }
#else
    while (true) {
        SDL_LockAudio();
        const int queued = ring_queued();
        SDL_UnlockAudio();
        if (queued >= queued_frames_target)
            break;
        CustomMixer(block, sizeof(block), NULL, 0, 1);
        const int count = resample_block();
        SDL_LockAudio();
        for (int i = 0; i < count; ++i) {
            ring[ring_write] = resampled[i];
            ring_write = (ring_write + 1) % ring_frames;
        }
        SDL_UnlockAudio();
    }
#endif
}

void nullazhangot() {
    if (!Hangenabled || !device)
        return;
#if SDL_MAJOR_VERSION >= 2
    SDL_ClearQueuedAudio(device);
#else
    SDL_LockAudio();
    ring_read = ring_write;
    SDL_UnlockAudio();
#endif
}
