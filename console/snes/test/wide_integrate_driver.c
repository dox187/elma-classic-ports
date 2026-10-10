#include <snes.h>
#include "core.h"
void wide_integrate_position(void);
void wide_integrate_angle(void);
void wide_integrate_position_wide(void);
void wide_integrate_angle_wide(void);
volatile u16 wi_go, wi_done;
int main(void) {
    consoleInit();
    core_init();
    core_screen_off();
    while (1) {
        if (wi_go) {
            u16 command = wi_go;
            wi_go = 0;
            if (command == 1) wide_integrate_position();
            else if (command == 2) wide_integrate_angle();
            else if (command == 3) wide_integrate_position_wide();
            else wide_integrate_angle_wide();
            wi_done = 1;
        }
        core_frame_done();
    }
    return 0;
}
