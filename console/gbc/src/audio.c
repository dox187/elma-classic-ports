#pragma bank 3
#include "audio.h"
#include "riding_constants.h"

/* CH3 has separate original idle/load cycles; CH2/CH4 use source-derived
 * effect contours. No sample streaming, interrupt handler, division or
 * physics work. Hardware lengths bound every sound if servicing stops.
 */
typedef struct {
    uint16_t pitch;
    uint8_t envelope, duty;
} effect_step_t;
#include "audio_assets.h"

static const effect_step_t menu_steps[] = {{1923,0x81,0x80}};
static const uint8_t priority[] = {1,2,3,4};
static const effect_step_t *effect_steps;
static uint16_t effect_start;
static uint8_t effect_id, effect_note, effect_active, effect_duration, engine_volume, engine_mode;

static uint16_t audio_now(void) {
    uint16_t now;
    __critical { now=sys_time; }
    return now;
}

static void engine_stop(void) {
    if(engine_volume) {
        NR30_REG=0;
        engine_volume=0;
    }
}

static void effect_stop(void) {
    NR22_REG=0;
    NR42_REG=0;
    effect_active=0;
}

static void effect_tick(uint16_t now) {
    const effect_step_t *step;
    uint16_t age;
    uint8_t index;
    if(!effect_active)return;
    age=(uint16_t)(now-effect_start);
    if(age>=effect_duration) { effect_stop();return; }
    /* Four VBlanks per control step: O(1) lookup, including late updates. */
    index=(uint8_t)age>>2;
    if(index==effect_note)return;
    effect_note=index;
    step=effect_steps+index;
    if(effect_id>=FX_CRASH) {
        NR41_REG=0;
        NR42_REG=step->envelope;
        NR43_REG=(uint8_t)step->pitch;
        NR44_REG=0xC0;
    }
    else {
        NR21_REG=step->duty;
        NR22_REG=step->envelope;
        NR23_REG=(uint8_t)step->pitch;
        NR24_REG=0xC0|(uint8_t)(step->pitch>>8);
    }
}

void audio_init(void) BANKED {
    uint8_t i;
    NR52_REG=0;
    NR52_REG=0x80;
    NR51_REG=0xEE; /* CH2, CH3, CH4 centered in both speakers. */
    NR50_REG=0x55; /* 6/8 master level; no external VIN. */
    NR10_REG=0;
    NR12_REG=0;
    NR22_REG=0;
    NR30_REG=0;
    NR32_REG=0;
    NR42_REG=0;
    /* Begin with the original idle cycle, with its DAC off. */
    for(i=0;i<16;++i)((volatile uint8_t *)0xFF30)[i]=engine_wave[0][i];
    engine_mode=0;
    engine_volume=0;
    effect_active=0;
}

void audio_update(uint8_t riding,uint8_t gas,uint8_t brake,uint16_t speed) BANKED {
    uint8_t mode,volume,trigger,i;
    uint16_t pitch;
    const uint8_t *wave;
    effect_tick(audio_now());
    if(!riding) { engine_stop();return; }
    mode=!!gas;
    if(mode!=engine_mode) {
        /* Only throttle edges replace the cycle. Keep the bounded 16-byte
         * transfer uninterrupted, with the DAC off, then retrigger once. */
        wave=engine_wave[mode];
        __critical {
            NR30_REG=0;
            for(i=0;i<16;++i)((volatile uint8_t *)0xFF30)[i]=*wave++;
        }
        engine_mode=mode;
    }
    /* Braking changes the physical wheel speed, as in the original mixer;
     * it does not artificially divide pitch or change the gas waveform. */
    (void)brake;
    volume=mode?0x40:0x60;
    pitch=mode?engine_pitch[speed>=32768U?511:(speed>>6)]:AUDIO_IDLE_PERIOD;
    trigger=!(NR52_REG&4);
    if(volume!=engine_volume) {
        NR32_REG=volume;
        engine_volume=volume;
    }
    /* NR31 refreshes a 64/256 s watchdog without resetting sample phase.
     * A period change does not need a trigger. Restart only after a wave
     * switch, stop or expired watchdog; active wave RAM is never accessed. */
    NR31_REG=192;
    if(trigger)NR30_REG=0x80;
    NR33_REG=(uint8_t)pitch;
    NR34_REG=0x40|(uint8_t)(pitch>>8)|(trigger?0x80:0);
}

void audio_effect(uint8_t id) BANKED {
    uint16_t now;
    if(id>FX_FINISH)return;
    now=audio_now();
    effect_tick(now);
    if(effect_active && priority[id]<priority[effect_id])return;
    effect_stop();
    effect_id=id;
    effect_note=255;
    effect_start=now;
    effect_active=1;
    if(id==FX_MENU) { effect_steps=menu_steps;effect_duration=3; }
    else if(id==FX_APPLE) { effect_steps=apple_steps;effect_duration=AUDIO_APPLE_TICKS; }
    else if(id==FX_CRASH) { effect_steps=crash_steps;effect_duration=AUDIO_CRASH_TICKS; }
    else { effect_steps=finish_steps;effect_duration=AUDIO_FINISH_TICKS; }
    if(id>=FX_CRASH)engine_stop();
    effect_tick(now);
}
