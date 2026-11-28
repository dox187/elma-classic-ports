#include <gb/gb.h>
#include <stdint.h>
#include <string.h>
#include "world.h"
#include "world_memory.h"

#pragma bank 33

extern const uint16_t world_scenery_slots[];
extern uint8_t world_level_index;

uint8_t world_load_scenery_slots(void) BANKED {
    uint16_t address, count=game_world.pattern_count;
    if(count<=492 || count>1024)return 0;
    world_far_copy(504,(const uint8_t *)&world_scenery_slots[world_level_index],
                   (uint8_t *)&address,sizeof(address));
    if(!address)return 0;
    world_far_copy(504,(const uint8_t *)address,(uint8_t *)0xa000,count-256);
    /* High bytes in the active ID range are 1..3. */
    memset((void *)0xa400,0xff,236);
    return 2;
}
