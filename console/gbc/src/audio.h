#ifndef GBC_AUDIO_H
#define GBC_AUDIO_H

#include <gb/gb.h>
#include <stdint.h>

enum { FX_MENU, FX_APPLE, FX_CRASH, FX_FINISH };

/* Main-loop calls only; bank 3 is restored by the GBDK BANKED trampoline.
 * init also cancels all effects, useful when restarting/changing a level.
 * update runs in every game/menu iteration. speed is absolute driven-wheel
 * omega in the generated physics units (0..32768; larger values saturate).
 * gas=0 keeps a quiet, constant idle regardless of wheel speed or brake.
 * riding=0 immediately mutes the engine; short effects can finish in menus.
 * CH3 uses separate original idle/load cycles and the original saturating
 * 1..2 playback-rate curve. Brake affects pitch through physical speed.
 * CH1 reinforces the exhaust at twice CH3's base rate with a 12.5% pulse,
 * volume 6 at idle / 15 under load. Both engine channels stop together.
 * Wave RAM changes only on init or throttle-mode changes, with its DAC off.
 * Effects use offline CH2/CH4 contours; no PCM streaming or music is added.
 */
void audio_init(void) BANKED;
void audio_update(uint8_t riding, uint8_t gas, uint8_t brake, uint16_t speed) BANKED;
void audio_effect(uint8_t id) BANKED;

#endif
