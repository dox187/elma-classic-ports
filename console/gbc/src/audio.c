#pragma bank 3
#include "audio.h"
#include "riding_constants.h"
#include "runtime.h"
#include "physics_core.h"

/* CH3 has separate original idle/load cycles. CH1 adds a narrow exhaust
 * pulse; CH2/CH4 use source-derived effect contours. No sample streaming,
 * interrupt handler, division or native-state writes. Hardware lengths bound
 * every sound if servicing stops.
 */
typedef struct {
    uint16_t pitch;
    uint8_t envelope, duty;
} effect_step_t;
#include "audio_assets.h"
#include "audio_idle.h"

static const effect_step_t menu_steps[] = {{1923,0x81,0x80}};
static const uint8_t priority[] = {1,2,4,5,0,3,2};
static const effect_step_t *effect_steps;
static uint16_t effect_start;
static uint8_t effect_id, effect_note, effect_active, effect_duration, engine_volume, engine_mode, pulse_volume;
static uint16_t creak_start;
static uint8_t motion_step;
static uint8_t creak_active, creak_note, motion_valid, last_turned, last_volt[2];

static uint16_t audio_now(void) {
    uint16_t now;
    __critical { now=sys_time; }
    return now;
}

static void engine_stop(void) {
    if(engine_volume) {
        NR30_REG=0;
        NR12_REG=0;
        engine_volume=0;
    }
}

static void effect_stop(void) {
    if(effect_id<FX_CRASH)NR22_REG=0;
    else NR42_REG=0;
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
        NR42_REG=0;
        NR42_REG=step->envelope;
        NR43_REG=(uint8_t)step->pitch;
        NR44_REG=0xC0;
    }
    else {
        NR21_REG=step->duty;
        NR22_REG=0;
        NR22_REG=step->envelope;
        NR23_REG=(uint8_t)step->pitch;
        NR24_REG=0xC0|(uint8_t)(step->pitch>>8);
    }
}

static void creak_stop(void) {
    if(creak_active)NR22_REG=0;
    creak_active=0;
}

static void creak_tick(uint16_t now) {
    uint16_t age;
    uint8_t note;
    const effect_step_t *step;
    if(!creak_active)return;
    age=(uint16_t)(now-creak_start);
    if(age>=AUDIO_CREAK_TICKS) { creak_stop();return; }
    note=(uint8_t)age>>2;
    if(note==creak_note)return;
    creak_note=note;
    step=creak_steps+note;
    NR21_REG=step->duty;NR22_REG=0;NR22_REG=step->envelope;
    NR23_REG=(uint8_t)step->pitch;
    NR24_REG=0xC0|(uint8_t)(step->pitch>>8);
}

/* Collision events come from incoming speed along the terrain normal,
 * not from throttle-induced spring travel. Observe each physics step once. */
static void motion_tick(void) {
    uint8_t k;
    if(!gbc_bike.alive) { motion_valid=0;return; }
    if(!(riding_audio_contact[0]|riding_audio_contact[1]))creak_stop();
    if(motion_valid && motion_step==Bike.steps)return;
    for(k=0;k<2;++k) {
        if(motion_valid && Bike.volt[k]>last_volt[k])audio_effect(FX_VOLT);
        last_volt[k]=Bike.volt[k];
    }
    if(motion_valid && gbc_bike.turned!=last_turned)audio_effect(FX_TURN);
    if(motion_valid && (riding_audio_impact[0]|riding_audio_impact[1]))
        audio_effect(FX_CREAK);
    last_turned=gbc_bike.turned;motion_step=Bike.steps;motion_valid=1;
}

void audio_init(void) BANKED {
    uint8_t i;
    NR52_REG=0;
    NR52_REG=0x80;
    NR51_REG=0xFF; /* All four channels centered in both speakers. */
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
    effect_active=0;creak_active=0;motion_valid=0;pulse_volume=255;
    audio_idle_reset(audio_now());
}

void audio_update(uint8_t riding,uint8_t gas,uint8_t brake,uint16_t speed) BANKED {
    uint8_t mode,volume,trigger,pulse_trigger,i,pulse_level;
    uint16_t pitch,pulse_pitch,now;
    const uint8_t *wave;
    now=audio_now();
    effect_tick(now);creak_tick(now);
    if(!riding) { engine_stop();creak_stop();motion_valid=0;return; }
    motion_tick();
    mode=!!gas;
    if(!mode && (engine_mode || !engine_volume))audio_idle_reset(now);
    pulse_level=mode?6:audio_idle_tick(now);
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
    /* The CGB output filter attenuates these low original engine cycles.
     * Use CH3's full range under load; keep idle one level quieter. */
    volume=mode?0x20:0x40;
    pitch=mode?engine_pitch[speed>=32768U?511:(speed>>6)]:AUDIO_IDLE_PERIOD;
    trigger=!(NR52_REG&4);
    pulse_trigger=(NR52_REG&1)?0:0x80;
    if(volume!=engine_volume) {
        NR32_REG=volume;
        engine_volume=volume;
    }
    if(pulse_level!=pulse_volume || !engine_volume || pulse_trigger) {
        NR12_REG=0; /* Disable the DAC before replacing a live envelope. */
        NR12_REG=pulse_level?(pulse_level<<4):0x08;
        pulse_volume=pulse_level;
        pulse_trigger=0x80;
    }
    /* Loaded CH1 is exactly CH3's second harmonic; idle drifts gently.
     * The narrow pulse adds exhaust harmonics without transposing CH3.
     * Refresh the 64/256 s watchdog, but preserve phase on speed updates.
     * Sweep and automatic volume envelopes remain disabled. */
    NR11_REG=0;
    pulse_pitch=mode?pitch:audio_idle_period();
    NR13_REG=(uint8_t)pulse_pitch;
    NR14_REG=0x40|(uint8_t)(pulse_pitch>>8)|pulse_trigger;
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
    if(id>FX_TURN)return;
    now=audio_now();
    effect_tick(now);
    if(id==FX_CREAK) {
        if(creak_active || (effect_active && effect_id!=FX_VOLT && effect_id!=FX_TURN))return;
        creak_start=now;creak_note=255;creak_active=1;creak_tick(now);return;
    }
    if(effect_active && priority[id]<priority[effect_id])return;
    if(effect_active)effect_stop();
    if(id<=FX_FINISH)creak_stop();
    effect_id=id;
    effect_note=255;
    effect_start=now;
    effect_active=1;
    if(id==FX_MENU) { effect_steps=menu_steps;effect_duration=3; }
    else if(id==FX_APPLE) { effect_steps=apple_steps;effect_duration=AUDIO_APPLE_TICKS; }
    else if(id==FX_CRASH) { effect_steps=crash_steps;effect_duration=AUDIO_CRASH_TICKS; }
    else if(id==FX_FINISH) { effect_steps=finish_steps;effect_duration=AUDIO_FINISH_TICKS; }
    else if(id==FX_VOLT) { effect_steps=volt_steps;effect_duration=AUDIO_VOLT_TICKS; }
    else { effect_steps=turn_steps;effect_duration=AUDIO_TURN_TICKS; }
    if(id==FX_CRASH || id==FX_FINISH)engine_stop();
    effect_tick(now);
}
