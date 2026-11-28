#include <gb/gb.h>
#include <stdint.h>
#include <string.h>
#include "world.h"
#include "world_memory.h"

#pragma bank 5

extern const uint16_t world_scenery_slots[];
extern uint8_t world_level_index;
void world_preload_scenery_slot(uint8_t slot,uint16_t id) BANKED;

uint8_t world_load_scenery_slots(void) BANKED {
    uint16_t i,address,count=game_world.pattern_count;
    uint8_t bits=0;
    if(count<=492 || count>1024)return 0;
    world_far_copy(504,(const uint8_t *)&world_scenery_slots[world_level_index],
                   (uint8_t *)&address,sizeof(address));
    if(!address)return 0;
    count-=256;
    world_far_copy(504,(const uint8_t *)address,(uint8_t *)0xa000,count);
    world_far_copy(504,(const uint8_t *)(address+count),(uint8_t *)0xa500,(count+7)/8);
    /* High bytes in the active ID range are 1..3. */
    memset((void *)0xa400,0xff,236);
    for(i=0;i<count;++i) {
        if(!(i&7))bits=((const uint8_t *)0xa500)[i>>3];
        if(bits&1) {
            uint8_t slot=((const uint8_t *)0xa000)[i];
            uint16_t id=i+256;
            ((uint8_t *)0xa300)[slot]=(uint8_t)id;
            ((uint8_t *)0xa400)[slot]=id>>8;
            world_preload_scenery_slot(slot,id);
        }
        bits>>=1;
    }
    return 2;
}
