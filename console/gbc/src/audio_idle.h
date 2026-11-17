#ifndef GBC_AUDIO_IDLE_H
#define GBC_AUDIO_IDLE_H

/* Included by bank-3 audio.c, after audio_assets.h. All periods are folded
 * at compile time: +/-1% changes audible Hz, not the period register.
 * The two endpoints are reset thresholds, never sustained pitches. */
#define IDLE_PERIOD_PERCENT(p) \
    (2048U-(((2048UL-AUDIO_IDLE_PERIOD)*100UL+(p)/2)/(p)))
static const uint16_t idle_periods[11] = {
    IDLE_PERIOD_PERCENT(95), IDLE_PERIOD_PERCENT(96),
    IDLE_PERIOD_PERCENT(97), IDLE_PERIOD_PERCENT(98),
    IDLE_PERIOD_PERCENT(99), AUDIO_IDLE_PERIOD,
    IDLE_PERIOD_PERCENT(101), IDLE_PERIOD_PERCENT(102),
    IDLE_PERIOD_PERCENT(103), IDLE_PERIOD_PERCENT(104),
    IDLE_PERIOD_PERCENT(105)
};
#undef IDLE_PERIOD_PERCENT

/* 17 VBlanks down (284.6 ms), four up (67.0 ms), at 59.7275 Hz.
 * Quantized to the quiet 0..2 hardware range; two zero-volume ticks ensure
 * the trough remains visible with the game's usual two-VBlank updates.
 * For volume zero the caller uses NR12=0x08 (DAC on, envelope pace zero).
 * Only volume changes need an envelope write and pulse retrigger. */
static const uint8_t idle_volumes[21] = {
    2,2,2,2,2,2,2,2,2, 1,1,1,1,1,1,1,1, 0,0, 1,1
};
static uint16_t idle_last;
static uint8_t idle_phase, idle_cycles_left, idle_pitch_index, idle_random;

static uint8_t audio_idle_random(void) {
    /* Maximal nonzero eight-bit LFSR; no multiplication or runtime divide. */
    idle_random=(idle_random>>1)^((idle_random&1)?0xB8:0);
    return idle_random;
}

/* Reset on init and idle entry after throttle, stop, pause or restart. */
static void audio_idle_reset(uint16_t now) {
    idle_last=now;
    idle_phase=0;
    idle_pitch_index=5;
    idle_random=(uint8_t)now^0xA7;
    if(!idle_random)idle_random=0xA7;
    idle_cycles_left=2+(idle_random&1);
}

static uint8_t audio_idle_tick(uint16_t now) {
    uint16_t elapsed=(uint16_t)(now-idle_last);
    idle_last=now;
    /* A stalled caller restarts cleanly instead of replaying missed cycles.
     * Otherwise there can be at most one boundary: bounded O(1) work, and
     * unsigned subtraction also handles the 16-bit VBlank clock wrap. */
    if(elapsed>=21) {
        audio_idle_reset(now);
        return 2;
    }
    idle_phase+=(uint8_t)elapsed;
    if(idle_phase>=21) {
        idle_phase-=21;
        if(!--idle_cycles_left) {
            if(audio_idle_random()&1)++idle_pitch_index;
            else --idle_pitch_index;
            if(!idle_pitch_index || idle_pitch_index==10)idle_pitch_index=5;
            idle_cycles_left=2+(audio_idle_random()&1);
        }
    }
    return idle_volumes[idle_phase];
}

static uint16_t audio_idle_period(void) {
    return idle_periods[idle_pitch_index];
}

#endif
