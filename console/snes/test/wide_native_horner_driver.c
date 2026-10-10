#include <snes.h>
#include "core.h"
void wnt_pair(void);
volatile u16 wnt_go,wnt_done;
int main(void){consoleInit();core_init();core_screen_off();while(1){if(wnt_go){wnt_go=0;wnt_pair();wnt_done=1;}core_frame_done();}return 0;}
