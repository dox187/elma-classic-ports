// Component test driver: Python supplies independent view pairs and alpha.
// Only the real rendering routines execute; the solver is never stepped.
#include <snes.h>
#include <string.h>
#include "core.h"
#include "phys.h"

void game_render_reset(void);
void game_render_capture(void);
void game_render_previous(void);
void game_camera(u16 level);
void game_render_begin(u16 alpha);
void game_render_end(void);
u16 render_test_work_over(u16 reserve);
u16 render_test_dma_left(u16 direct_page);
extern u16 core_dmaq_n;

volatile u16 render_test_go, render_test_done, render_test_alpha;
volatile u16 render_test_value, render_test_d, render_test_result;
u8 render_test_view[52], render_test_restored[52];

int main(void) {
    u16 command;
    consoleInit();
    core_init();
    core_screen_off();
    render_test_go = render_test_done = 0;
    while(1) {
        command = render_test_go;
        if(command) {
            render_test_go = 0;
            if(command == 1) {
                game_render_begin(render_test_alpha);
                memcpy(render_test_view, &phys_view, 52);
                game_render_end();
            } else if(command == 2) {
                game_render_reset();
                memcpy(render_test_view, &phys_view, 52);
            } else if(command == 3) {
                game_render_capture();
                memcpy(render_test_view, &phys_view, 52);
            } else if(command == 4) {
                game_render_previous();
                memcpy(render_test_view, &phys_view, 52);
            } else if(command == 5) {
                game_camera(render_test_alpha);
                memcpy(render_test_view, &phys_view, 52);
            } else if(command == 6) {
                core_work_begin();
            } else if(command == 7) {
                render_test_result = render_test_work_over(render_test_alpha);
            } else if(command == 8) {
                render_test_result = render_test_dma_left(render_test_alpha);
                core_dmaq_n = core_dmaq_bytes = 0;
            }
            memcpy(render_test_restored, &phys_view, 52);
            render_test_done = 1;
        }
        core_frame_done();
    }
    return 0;
}
