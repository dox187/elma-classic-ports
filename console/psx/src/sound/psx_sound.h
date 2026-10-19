#pragma once

#ifdef ELMA_PSX
// Finish the mixer's pending effects and their queued SPU output before mute.
void psx_wait_for_effects(void);

#endif
