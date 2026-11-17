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
static uint16_t creak_start, motion_last[2];
static uint8_t motion_wheel, compression_valid, creak_latched;
static uint8_t creak_active, creak_note, motion_valid, last_turned, last_volt[2];
static int16_t last_down[2];

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

/* Original LEPTET.CPP surlodasverseny requires both spring compression
 * and inward relative movement along the bike's down axis. Observe the
 * exported poses only: no extra physics work or modified native state.
 * Q6 positions and 32 Q4 directions bound the cost. Actual wheel contact,
 * at least 10/64 m compression and 4/64 m inward travel reject airborne
 * oscillation and ordinary spring movement. Re-arm below 6/64 m compression;
 * the stronger onset threshold suits this fixed-volume effect.
 */
static const int8_t motion_sine[32]={
    0,3,6,9,11,13,15,16,16,16,15,13,11,9,6,3,
    0,-3,-6,-9,-11,-13,-15,-16,-16,-16,-15,-13,-11,-9,-6,-3
};
/* The projection coefficients are at most 16. Avoid the general 16-bit
 * multiplier's fixed 16 iterations for these tiny, known coefficients. */
static int16_t motion_scale(int16_t value,int8_t factor) {
    if(factor<0) { value=-value;factor=-factor; }
    switch(factor) {
        case 0:return 0;
        case 3:return (value<<1)+value;
        case 6:return (value<<2)+(value<<1);
        case 9:return (value<<3)+value;
        case 11:return (value<<3)+(value<<1)+value;
        case 13:return (value<<3)+(value<<2)+value;
        case 15:return (value<<4)-value;
        default:return value<<4;
    }
}

static void motion_tick(uint16_t now) {
    static uint8_t k,angle,valid;
    static int16_t x,y,down,compression,travel;
    static uint16_t elapsed;
    if(!gbc_bike.alive) { motion_valid=0;compression_valid=0;creak_latched=0;return; }
    if(!(riding_audio_contact[0]|riding_audio_contact[1]))creak_stop();
    for(k=0;k<2;++k) {
        if(motion_valid && Bike.volt[k]>last_volt[k])audio_effect(FX_VOLT);
        last_volt[k]=Bike.volt[k];
    }
    if(motion_valid && gbc_bike.turned!=last_turned)audio_effect(FX_TURN);
    last_turned=gbc_bike.turned;motion_valid=1;
    if(creak_active || (effect_active && effect_id!=FX_VOLT && effect_id!=FX_TURN)) {
        compression_valid=0;return;
    }
    /* Each wheel is sampled every other update, with its own timestamp.
     * Volts and turns remain serviced every update. This bounds the cost
     * without adding work to the physics or fixed-ROM frame loop. */
    k=motion_wheel;motion_wheel^=1;
    valid=1U<<k;
    elapsed=(uint16_t)(now-motion_last[k]);
    angle=(uint8_t)((gbc_bike.body.angle+1024U)>>11)&31;
    /* Subtract modular Q8 positions before reducing to Q6. Translation,
     * including a world-coordinate wrap, cancels; rounding is <1 Q6 unit. */
    y=(int16_t)((uint16_t)(gbc_bike.wheel[k].y>>8)-(uint16_t)(gbc_bike.body.y>>8))>>2;
    if(y>511)y=511;else if(y< -511)y= -511;
    if(!(angle&15))down=angle?y:-y;
    else {
        x=(int16_t)((uint16_t)(gbc_bike.wheel[k].x>>8)-(uint16_t)(gbc_bike.body.x>>8))>>2;
        if(x>511)x=511;else if(x< -511)x= -511;
        if(!(angle&7))down=angle==8?x:-x;
        else down=(motion_scale(x,motion_sine[angle])-motion_scale(y,motion_sine[(angle+8)&31]))>>4;
    }
    compression=(int16_t)(F_BODY_Y>>12)-down;
    travel=last_down[k]-down;
    /* A contact is required: airborne spring oscillation is not an impact.
     * Hysteresis permits one sound per substantial compression, not a loop
     * on every tiny inward movement after the previous contour ends. */
    if(compression<=6)creak_latched&=~valid;
    if(riding_audio_contact[k] && !(creak_latched&valid)
       && (compression_valid&valid) && elapsed && elapsed<=8
       && compression>=10 && travel>=4 && compression<128 && travel<128
       && (uint16_t)(compression*travel)>=12U*elapsed) {
        audio_effect(FX_CREAK);creak_latched=3;
    }
    last_down[k]=down;motion_last[k]=now;compression_valid|=valid;
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
    effect_active=0;creak_active=0;motion_valid=0;compression_valid=0;creak_latched=0;motion_wheel=0;pulse_volume=255;
    audio_idle_reset(audio_now());
}

void audio_update(uint8_t riding,uint8_t gas,uint8_t brake,uint16_t speed) BANKED {
    uint8_t mode,volume,trigger,pulse_trigger,i,pulse_level;
    uint16_t pitch,pulse_pitch,now;
    const uint8_t *wave;
    now=audio_now();
    effect_tick(now);creak_tick(now);
    if(!riding) { engine_stop();creak_stop();motion_valid=0;compression_valid=0;creak_latched=0;return; }
    motion_tick(now);
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
