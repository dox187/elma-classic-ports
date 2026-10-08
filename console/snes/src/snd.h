// The sounds of a level (snd.asm and the driver of the SPC700 in
// spc/driver.asm), as the mixer of the original game plays them: the
// engine, the friction and up to five effects at a time.
#ifndef SND_H
#define SND_H

#include <snes.h>

// The effects, numbered as the original's WAV_* (HANGHIGH.H):
#define SND_BUMP  1   // utodes.wav: a hard hit, its volume from the hit
#define SND_DEAD  2   // torik.wav
#define SND_WIN   3   // siker.wav
#define SND_EAT   4   // eves.wav
#define SND_TURN  5   // fordul.wav
#define SND_VOLT1 6   // ugras.wav
#define SND_VOLT2 7   // ugras.wav
// The volumes the original gives them (startwave: 0.99 and 0.999 of 1.0):
#define SND_VOL_EFFECT 253   // apple, turn, volt
#define SND_VOL_END    255   // death, flower

// Uploads the driver and the samples (about 1.1 s), at the start, before
// the other functions (they do nothing until then); later calls return.
void snd_init(void);
// Every frame of a level (setmotor, setsurlodas): gas 1 while the gas is
// held; wheel_omega the |omega| of the driven wheel (kor4, kor2 when
// turned) in radians per time unit of the game (the PC's), 8.8 fixed point
// (256: 1 rad); friction the PC's Maxsurlodas (inf.surlero) of the last
// step, 8.8 fixed point (256: 1.0, more is 1.0). The first call after
// snd_init or snd_stop starts the engine (startmotor). After a crash or the
// flower the original sets no gas and keeps playing for a second (the
// sound of the end with it): call it with gas 0 meanwhile, then snd_stop.
void snd_frame(u8 gas, u16 wheel_omega, u16 friction);
// Starts an effect (startwave), SND_*, volume 0..255 (256: 1.0; a hit: 256
// times the PC's ero). Dropped while five effects play, as in the original.
// Also starts the sounds of a level if they were not.
void snd_effect(u16 id, u16 volume);
// Every sound off at once (Esc, the end of a level, menus: the original's
// stopmotor and Mute); the engine starts again with the next snd_frame.
void snd_stop(void);

#endif
