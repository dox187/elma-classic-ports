/* The signed-background cartridge keeps the active course's three row
 * descriptor bytes on separate SRAM0 pages. Only course entry writes them. */
#pragma bank 13
#include <gb/gb.h>
#include "world_memory.h"

extern const uint8_t wheel_terrain_maps[];
extern uint8_t physics_level_index, wheel_course_size[2];

void wheel_prepare_rows(void) BANKED {
    uint8_t descriptor[4], rows[48];
    uint8_t first=0, count, i;
    uint16_t source;
    volatile uint8_t *const low=(uint8_t *)0xad00;
    volatile uint8_t *const high=(uint8_t *)0xae00;
    volatile uint8_t *const banks=(uint8_t *)0xaf00;

    ENABLE_RAM_MBC5;
    SWITCH_RAM_MBC5(0);
    world_far_copy(9,wheel_terrain_maps+(uint16_t)physics_level_index*4,descriptor,4);
    wheel_course_size[0]=descriptor[0];
    wheel_course_size[1]=descriptor[1];
    source=descriptor[2] | (uint16_t)descriptor[3]<<8;
    while(first<descriptor[1]) {
        count=descriptor[1]-first;
        if(count>16)count=16;
        world_far_copy(9,(const uint8_t *)source,rows,3*count);
        for(i=0;i<count;++i) {
            low[first+i]=rows[3*i];
            high[first+i]=rows[3*i+1];
            banks[first+i]=rows[3*i+2];
        }
        first+=count;
        source+=3*count;
    }
}
