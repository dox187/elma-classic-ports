#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdio.h>
#include "suspension.h"
#include "mul16.h"
#include "mul_vectors.h"

volatile uint8_t probe_done;
volatile uint16_t probe_frames;
volatile uint8_t probe_math_ok;
static suspension_input_t axles[2] = {
    {-870, -614, 31, -17, 341, -512},
    {870, -614, -23, 47, -172, 239}
};
suspension_output_t probe_result;

void main(void) {
    uint16_t start, i;
    cpu_fast();
    probe_math_ok = 1;
    for (i = 0; i < MUL_VECTOR_COUNT; ++i)
        if (gbc_mul16(mul_vectors[i].a,mul_vectors[i].b) != mul_vectors[i].product)
            probe_math_ok = 0;
    printf("ELMA GBC\nSUSPENSION PROBE\nNOT FULL PHYSICS\n\n");
    vsync();
    __critical { start = sys_time; }
    for (i = 0; i < 1024; ++i) suspension_impulses(axles, &probe_result);
    __critical { probe_frames = sys_time - start; }
    probe_done = 1;
    printf("1024 CALLS\n%u DISPLAY FRAMES\n", probe_frames);
    while (1) vsync();
}
