static uint8_t fetch_strip(uint16_t x,uint16_t y,uint8_t vertical,uint8_t count,uint8_t offset,uint8_t partial) {
    uint16_t ci,local;uint8_t run,i=offset;
#ifdef WORLD_GRAPHICS_ZX0
    uint8_t plane;
    if(!partial)prepare_map_plane=0;
#endif
    count+=offset;
    while(i<count) {
        if(x>=game_world.width/8 || y>=game_world.height/8) {
            strip_low[i]=strip_high[i]=strip_attrs[i]=0;++i;
            if(vertical)++y;else ++x;
            continue;
        }
        ci=(y>>4)*game_world.chunks_x+(x>>5);
        if(ci!=last_chunk) {
#ifdef WORLD_GRAPHICS_ZX0
            uint8_t cached;
            for(cached=0;cached<MAP_CACHE_COUNT;++cached)if(map_cache_ids[cached]==ci)break;
            if(cached==MAP_CACHE_COUNT) {
                cached=map_cache_next;
                if(++map_cache_next==MAP_CACHE_COUNT)map_cache_next=0;
                map_cache_ids[cached]=ci;
                map_cache_planes[cached]=0;
            }
            chunk_ram_bank=1;chunk_cache=cached;
            chunk.address=0xa000U+(uint16_t)cached*1536;
            last_chunk=ci;
#else
            world_far_copy(game_world.chunks.bank,(const uint8_t *)(game_world.chunks.address+ci*4),
                           (uint8_t *)&chunk,4);last_chunk=ci;
#endif
        }
        local=(y&15)*32+(x&31);
        run=vertical?16-(y&15):32-(x&31);if(run>count-i)run=count-i;
        if(vertical){if(game_world.height/8-y<run)run=game_world.height/8-y;}
        else if(game_world.width/8-x<run)run=game_world.width/8-x;
#ifdef WORLD_GRAPHICS_ZX0
        /* A complete cached map has no cold work to budget between planes.
         * Gather the fragment once, as for the raw profile, instead of paying
         * three dispatches and cache-budget checks for the same cells. */
        if(map_cache_planes[chunk_cache]==7) {
            world_sram_gather(1,(const uint8_t *)(chunk.address+local),strip_low+i,run,vertical?32:1);
            world_sram_gather(1,(const uint8_t *)(chunk.address+512+local),strip_high+i,run,vertical?32:1);
            world_sram_gather(1,(const uint8_t *)(chunk.address+1024+local),strip_attrs+i,run,vertical?32:1);
            prepare_map_plane=0;
        } else {
        /* A partial fetch completes one plane of this fragment. Its row or
         * column index advances only after all three output arrays are ready. */
        for(plane=partial?prepare_map_plane:0;plane<3;++plane) {
            uint16_t source=chunk.address+((uint16_t)plane<<9);
            uint8_t mask=1U<<plane;
            uint8_t *dest=plane==0?strip_low:plane==1?strip_high:strip_attrs;
            if(!(map_cache_planes[chunk_cache]&mask)) {
                world_far_t pointer;
                world_far_copy(game_world.chunks.bank,
                    (const uint8_t *)(game_world.chunks.address+ci*12U+(uint16_t)plane*4U),
                    (uint8_t *)&pointer,4);
                world_decompress(pointer.bank,pointer.address+WORLD_ZX0_COST_PREFIX,1,source);
                map_cache_planes[chunk_cache]|=mask;
            }
            world_sram_gather(1,(const uint8_t *)(source+local),dest+i,run,vertical?32:1);
            if(partial) {
                if(++prepare_map_plane<3)return 0;
                prepare_map_plane=0;break;
            }
        }
        }
#else
#define gather(source,dest) world_far_gather(chunk.bank,(const uint8_t *)(source),dest,run,vertical?32:1)
        gather(chunk.address+local,strip_low+i);
        gather(chunk.address+512+local,strip_high+i);
        gather(chunk.address+1024+local,strip_attrs+i);
#undef gather
#endif
        i+=run;if(vertical)y+=run;else x+=run;
        if(partial)break;
    }
    return i-offset;
}
