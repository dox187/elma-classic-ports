#include <snes.h>
#include "core.h"
void wnt_mul40(void);void wnt_mul29(void);void wnt_mul17(void);
volatile u16 wnt_go,wnt_done;
int main(void){consoleInit();core_init();core_screen_off();while(1){if(wnt_go){u16 command=wnt_go;wnt_go=0;if(command==1)wnt_mul40();else if(command==2)wnt_mul29();else wnt_mul17();wnt_done=1;}core_frame_done();}return 0;}
