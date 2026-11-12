#pragma bank 3
#include "audio.h"

/* Native APU only: CH1 engine, CH2 feedback, CH4 crash. No interrupt handler,
 * sample streaming, division or physics work. The pulse melodies retain the
 * NES port's apple/finish intervals; they do not reproduce elma.res WAVs.
 * Hardware length counters bound every triggered sound even if the main loop
 * stops servicing audio. Normal timing uses elapsed sys_time, not call count.
 */
typedef struct {
    uint16_t pitch;
    uint8_t ticks;
} note_t;

/* 131072 / (2048-pitch) Hz: 64..344 Hz, in 8 Hz steps. */
static const uint16_t engine_pitch[] = {
    0,228,410,559,683,788,878,956,1024,1084,1138,1186,
    1229,1268,1303,1336,1365,1393,1418,1441,1463,1483,1502,1519,
    1536,1552,1566,1580,1593,1605,1617,1628,1638,1648,1658,1667
};
static const note_t menu_notes[] = {{1923,3}}; /* C6 */
static const note_t apple_notes[] = {{1798,3},{1849,3},{1881,5}};
static const note_t finish_notes[] = {
    {1547,6},{1650,6},{1714,6},{1798,12},{1714,6},{1798,12}
};
static const uint8_t priority[] = {1,2,3,4};
static uint16_t effect_start;
static uint8_t effect_id, effect_note, effect_active, engine_volume;

static uint16_t audio_now(void) {
    uint16_t now;
    __critical { now=sys_time; }
    return now;
}

static void engine_stop(void) {
    if(engine_volume) {
        NR12_REG=0;
        engine_volume=0;
    }
}

static void effect_stop(void) {
    NR22_REG=0;
    NR42_REG=0;
    effect_active=0;
}

static void effect_tick(uint16_t now) {
    const note_t *notes;
    uint16_t age, end;
    uint8_t count, i;
    if(!effect_active)return;
    age=(uint16_t)(now-effect_start);
    if(effect_id==FX_CRASH) {
        if(age>=14)effect_stop();
        return;
    }
    if(effect_id==FX_MENU) { notes=menu_notes;count=1; }
    else if(effect_id==FX_APPLE) { notes=apple_notes;count=3; }
    else { notes=finish_notes;count=6; }
    end=0;
    for(i=0;i<count;++i) {
        end+=notes[i].ticks;
        if(age<end) {
            if(i!=effect_note) {
                /* At most 250 ms even if updates stop. A late update skips
                 * expired notes rather than extending the whole sequence. */
                NR21_REG=0x80;
                NR22_REG=0xA1;
                NR23_REG=(uint8_t)notes[i].pitch;
                NR24_REG=0xC0|(uint8_t)(notes[i].pitch>>8);
                effect_note=i;
            }
            return;
        }
    }
    effect_stop();
}

void audio_init(void) BANKED {
    NR52_REG=0;
    NR52_REG=0x80;
    NR51_REG=0xBB; /* CH1, CH2, CH4 centered in both speakers. */
    NR50_REG=0x55; /* 6/8 master level; no external VIN. */
    NR10_REG=0;
    NR12_REG=0;
    NR22_REG=0;
    NR30_REG=0;
    NR42_REG=0;
    engine_volume=0;
    effect_active=0;
}

void audio_update(uint8_t riding,uint8_t gas,uint8_t brake,uint16_t speed) BANKED {
    uint8_t step,volume,trigger;
    uint16_t pitch;
    effect_tick(audio_now());
    if(!riding) { engine_stop();return; }
    step=speed>=16384U?31:(uint8_t)(speed>>9);
    if(brake) { step>>=1;volume=2; }
    else if(gas) { step+=4;volume=7; }
    else volume=3;
    pitch=engine_pitch[step];
    /* Writing NR11 refreshes the 250 ms watchdog without restarting phase.
     * Retrigger only for a volume change or an expired hardware watchdog. */
    trigger=volume!=engine_volume || !(NR52_REG&1);
    NR11_REG=0x40; /* 25% duty, a rougher exhaust tone than a 50% square. */
    if(trigger) {
        NR12_REG=volume<<4;
        engine_volume=volume;
    }
    NR13_REG=(uint8_t)pitch;
    NR14_REG=0x40|(uint8_t)(pitch>>8)|(trigger?0x80:0);
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
    if(id==FX_CRASH || id==FX_FINISH)engine_stop();
    if(id==FX_CRASH) {
        NR41_REG=0;
        NR42_REG=0xC1; /* Fast decaying broadband impact. */
        NR43_REG=0x55;
        NR44_REG=0xC0;
    }
    else effect_tick(now);
}
