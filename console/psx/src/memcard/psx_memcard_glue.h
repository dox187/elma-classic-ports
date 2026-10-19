// Memory card saves in the game (psx_memcard_glue.cpp).
#pragma once

// Starts the BIOS card driver: after InitPAD, before StartPAD.
void psx_memcard_init();
// Before the core reads state.dat: puts the saved copy from the card into
// the RAM file layer.
void psx_memcard_restore();
// The core has written state.dat; the card is written at the next menu wait.
void psx_state_saved();
// The same for the times of the external level collections.
void psx_collection_saved();
// In the menu's input waits: writes the card if state.dat changed and no
// level is running (leaving: whatever is on the screen).
void psx_memcard_poll(bool leaving = false);
