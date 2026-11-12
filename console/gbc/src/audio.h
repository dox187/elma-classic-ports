#ifndef GBC_AUDIO_H
#define GBC_AUDIO_H

#include <gb/gb.h>
#include <stdint.h>

enum { FX_MENU, FX_APPLE, FX_CRASH, FX_FINISH };

/* Main-loop calls only; bank 3 is restored by the GBDK BANKED trampoline.
 * init also cancels all effects, useful when restarting/changing a level.
 * update runs in every game/menu iteration. speed is absolute driven-wheel
 * omega in the 30 Hz physics units (0..16383; larger values saturate).
 * riding=0 immediately mutes the engine; short effects can finish in menus.
 * Effects are native APU adaptations, not the original game's PCM samples.
 */
void audio_init(void) BANKED;
void audio_update(uint8_t riding, uint8_t gas, uint8_t brake, uint16_t speed) BANKED;
void audio_effect(uint8_t id) BANKED;

#endif
