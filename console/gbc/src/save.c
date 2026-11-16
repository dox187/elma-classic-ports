#pragma bank 7
#include "save.h"

/* MBC5 battery SRAM bank 0, protected from graphics scratch data.
 * Two 1024-byte slots at B800/BC00, all integers little endian:
 *  0 "ELMS", 4 version=1, 5 committed=A5, 6 payload length=909 (u16),
 *  8 generation (u32), 12 CRC16 (u16), 14..15 reserved zero,
 * 16 player, 17 four zero-padded 11-byte names, 61 four*54 u32 best times,
 * 925..1023 reserved zero. CRC16-CCITT (poly 1021, initial FFFF, no xor)
 * covers every byte except 5, 12 and 13. Invalidate the inactive slot first,
 * stream its replacement, and write A5 last; the prior slot stays intact.
 */
#define SAVE_RAM_BANK 0
#define SLOT_SIZE 1024U
#define SLOT_NONE 255
#define COMMIT_OFFSET 5
#define COMMIT_MARKER 0xa5
#define GENERATION_OFFSET 8
#define CRC_OFFSET 12
#define PLAYER_OFFSET 16
#define NAMES_OFFSET 17
#define TIMES_OFFSET 61U
#define DATA_END 925U

volatile uint8_t save_player;
char save_names[SAVE_PLAYER_COUNT][SAVE_NAME_MAX+1];
static uint8_t current_slot;
static uint32_t generation;
static const uint8_t header[16]={
    'E','L','M','S',1,0,0x8d,0x03,0,0,0,0,0,0,0,0
};

static volatile uint8_t *slot_address(uint8_t slot) {
    return (volatile uint8_t *)(0xb800U+((uint16_t)slot<<10));
}

static uint32_t read_u32(const volatile uint8_t *p) {
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|
           ((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}

static uint16_t crc_byte(uint16_t crc,uint8_t value) {
    uint8_t bit;
    crc^=(uint16_t)value<<8;
    for(bit=0;bit<8;++bit)
        crc=crc&0x8000U ? (crc<<1)^0x1021U : crc<<1;
    return crc;
}

static uint8_t name_character(uint8_t c) {
    return (c>='A' && c<='Z') || (c>='0' && c<='9') || c==' ';
}

static uint8_t valid_slot(const volatile uint8_t *p) {
    uint16_t i,crc=0xffffU;
    uint8_t player,j,c,ended;
    if(p[COMMIT_OFFSET]!=COMMIT_MARKER || p[PLAYER_OFFSET]>=SAVE_PLAYER_COUNT)
        return 0;
    for(i=0;i<8;++i)
        if(i!=COMMIT_OFFSET && p[i]!=header[i])return 0;
    for(i=0;i<SLOT_SIZE;++i)
        if(i!=COMMIT_OFFSET && i!=CRC_OFFSET && i!=CRC_OFFSET+1)
            crc=crc_byte(crc,p[i]);
    if(p[CRC_OFFSET]!=(uint8_t)crc || p[CRC_OFFSET+1]!=(uint8_t)(crc>>8))
        return 0;
    for(player=0;player<SAVE_PLAYER_COUNT;++player) {
        const volatile uint8_t *name=p+NAMES_OFFSET+(uint16_t)player*(SAVE_NAME_MAX+1);
        if(!name[0] || name[0]==' ')return 0;
        ended=0;
        for(j=0;j<=SAVE_NAME_MAX;++j) {
            c=name[j];
            if(!c) {
                if(!ended && j && name[j-1]==' ')return 0;
                ended=1;
            } else if(ended || j==SAVE_NAME_MAX || !name_character(c))return 0;
        }
        if(!ended)return 0;
    }
    return 1;
}

/* No record array lives in WRAM: each byte comes directly from the previous
 * slot or the small player/name globals. Compute CRC from the intended byte
 * while writing, so a corrupted SRAM write cannot be included in the CRC. */
static void persist(uint16_t record_offset,uint32_t frames) {
    uint8_t next=current_slot==0 ? 1 : 0;
    volatile uint8_t *destination=slot_address(next);
    const volatile uint8_t *source=current_slot==SLOT_NONE ? 0 : slot_address(current_slot);
    uint32_t next_generation=generation+1;
    uint16_t i,crc=0xffffU;
    uint8_t value;
    destination[COMMIT_OFFSET]=0;
    for(i=0;i<SLOT_SIZE;++i) {
        if(i==COMMIT_OFFSET)continue;
        if(i<16) {
            value=header[i];
            if(i>=GENERATION_OFFSET && i<GENERATION_OFFSET+4)
                value=((const uint8_t *)&next_generation)[i-GENERATION_OFFSET];
        } else if(i==PLAYER_OFFSET)value=save_player;
        else if(i<TIMES_OFFSET)value=((const uint8_t *)save_names)[i-NAMES_OFFSET];
        else value=source && i<DATA_END ? source[i] : 0;
        if(record_offset && i>=record_offset && i<record_offset+4)
            value=((const uint8_t *)&frames)[i-record_offset];
        destination[i]=value;
        if(i!=CRC_OFFSET && i!=CRC_OFFSET+1)crc=crc_byte(crc,value);
    }
    destination[CRC_OFFSET]=(uint8_t)crc;
    destination[CRC_OFFSET+1]=(uint8_t)(crc>>8);
    destination[COMMIT_OFFSET]=COMMIT_MARKER;
    current_slot=next;
    generation=next_generation;
}

static uint16_t time_offset(uint8_t player,uint8_t level) {
    return TIMES_OFFSET+((uint16_t)player*SAVE_LEVEL_COUNT+level)*4U;
}

void save_init(void) BANKED {
    const volatile uint8_t *p;
    uint32_t other,delta;
    uint8_t player,i;
    ENABLE_RAM;
    SWITCH_RAM(SAVE_RAM_BANK);
    current_slot=SLOT_NONE;
    generation=0;
    if(valid_slot(slot_address(0))) {
        current_slot=0;
        generation=read_u32(slot_address(0)+GENERATION_OFFSET);
    }
    if(valid_slot(slot_address(1))) {
        other=read_u32(slot_address(1)+GENERATION_OFFSET);
        delta=other-generation;
        if(current_slot==SLOT_NONE || (delta && delta<0x80000000UL)) {
            current_slot=1;
            generation=other;
        }
    }
    if(current_slot!=SLOT_NONE) {
        p=slot_address(current_slot);
        save_player=p[PLAYER_OFFSET];
        for(i=0;i<SAVE_PLAYER_COUNT*(SAVE_NAME_MAX+1);++i)
            ((uint8_t *)save_names)[i]=p[NAMES_OFFSET+i];
    } else {
        save_player=0;
        for(player=0;player<SAVE_PLAYER_COUNT;++player) {
            for(i=0;i<=SAVE_NAME_MAX;++i)save_names[player][i]=0;
            for(i=0;i<7;++i)save_names[player][i]="PLAYER "[i];
            save_names[player][7]='1'+player;
        }
    }
    SWITCH_RAM(0);
}

void save_select(uint8_t player) BANKED {
    ENABLE_RAM;
    SWITCH_RAM(SAVE_RAM_BANK);
    if(player<SAVE_PLAYER_COUNT && player!=save_player) {
        save_player=player;
        persist(0,0);
    }
    SWITCH_RAM(0);
}

void save_name(uint8_t player,const char *name) BANKED {
    char clean[SAVE_NAME_MAX+1];
    uint8_t i,length=0,start=0,changed=0,c;
    ENABLE_RAM;
    SWITCH_RAM(SAVE_RAM_BANK);
    if(player>=SAVE_PLAYER_COUNT || !name)goto done;
    for(i=0;i<SAVE_NAME_MAX;++i) {
        c=(uint8_t)name[i];
        if(!c)break;
        if(!name_character(c))goto done;
        clean[length++]=(char)c;
    }
    while(start<length && clean[start]==' ')++start;
    while(length>start && clean[length-1]==' ')--length;
    length-=start;
    if(!length)goto done;
    for(i=0;i<=SAVE_NAME_MAX;++i) {
        clean[i]=i<length ? clean[start+i] : 0;
        if(clean[i]!=save_names[player][i])changed=1;
    }
    if(changed) {
        for(i=0;i<=SAVE_NAME_MAX;++i)save_names[player][i]=clean[i];
        persist(0,0);
    }
done:
    SWITCH_RAM(0);
}

uint32_t save_best(uint8_t player,uint8_t level) BANKED {
    uint32_t best=0;
    ENABLE_RAM;
    SWITCH_RAM(SAVE_RAM_BANK);
    if(player<SAVE_PLAYER_COUNT && level<SAVE_LEVEL_COUNT && current_slot!=SLOT_NONE)
        best=read_u32(slot_address(current_slot)+time_offset(player,level));
    SWITCH_RAM(0);
    return best;
}

uint8_t save_record(uint8_t player,uint8_t level,uint32_t frames) BANKED {
    uint32_t best;
    uint16_t offset;
    uint8_t changed=0;
    ENABLE_RAM;
    SWITCH_RAM(SAVE_RAM_BANK);
    if(player<SAVE_PLAYER_COUNT && level<SAVE_LEVEL_COUNT && frames) {
        offset=time_offset(player,level);
        best=current_slot==SLOT_NONE ? 0 : read_u32(slot_address(current_slot)+offset);
        if(!best || frames<best) {
            persist(offset,frames);
            changed=1;
        }
    }
    SWITCH_RAM(0);
    return changed;
}
