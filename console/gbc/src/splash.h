#ifndef GBC_SPLASH_H
#define GBC_SPLASH_H
#include <gb/gb.h>
#include <stdint.h>

extern volatile uint8_t splash_active;

/* Blocking title screen in ROM bank 2. A fresh A/Start press returns. */
void splash_show(void) BANKED;
#endif
