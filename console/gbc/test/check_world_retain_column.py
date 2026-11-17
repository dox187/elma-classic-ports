"""Extend the public native cache fixture with exact READY-X to XY cases.
Run once per frozen reference/candidate source; compare commit-checkpoints.json.
Only the fixture drives native public APIs; instrumentation reads state.
"""
from pathlib import Path
B=Path(__file__).resolve().parents[1]
source=(B/'test/check_world_cache.py').read_text().replace('BASE=Path(__file__).resolve().parents[1]','BASE=Path('+repr(str(B))+')')
extra=r'''
volatile uint16_t retain_cases,retain_guard_checks,retain_failures,retain_extra_views;
volatile uint8_t retain_level,retain_direction,retain_mode;
static uint16_t retain_pending[19],retain_row[20];
void fixture_retain_checkpoint(void) NONBANKED;
#ifdef RETAIN_TEST_HAS_REBASE
static void retain_reject(uint16_t ox,uint16_t oy,uint16_t x,uint16_t y,uint16_t start,uint8_t budgeted) {
 if(prepare_rebase_column(ox,oy,x,y,start,budgeted))++retain_failures;
 ++retain_guard_checks;
}
#endif
void fixture_retain_cases(void) BANKED {
 uint16_t x,y,ox,oy,px,py,i,next,start;int8_t dx,dy;uint8_t stage;
 retain_extra_views=inspected_views;
 for(retain_level=0;retain_level<3;++retain_level)
 for(retain_direction=0;retain_direction<4;++retain_direction)
 for(retain_mode=0;retain_mode<3;++retain_mode) {
  dx=retain_direction&1?8:-8;dy=retain_direction&2?8:-8;
  x=dx>0?255:256;y=dy>0?127:128;
  px=x+dx;ox=x^3;oy=y^5;py=oy+dy;
  DISPLAY_OFF;world_select(retain_level);world_begin(x,y);DISPLAY_ON;
  fixture_verify(retain_level,x,y);
  fixture_prepare(x,y,px,y,1);fixture_verify(retain_level,x,y);
  if(prepare_stage!=PREP_READY || prepare_added_count!=19)++retain_failures;
  world_scroll(x,y,ox,oy);fixture_verify(retain_level,ox,oy);
  px^=2;
  if(retain_mode==2) {
#ifdef RETAIN_TEST_HAS_REBASE
   retain_reject(ox+8,oy,px,py,0,0);
   retain_reject(ox,oy+8,px,py,0,0);
   retain_reject(ox,oy,ox-dx,py,0,0);
   retain_reject(ox,oy,px,oy,0,0);
   retain_reject(ox,oy,px,oy+2*dy,0,0);
   retain_reject(ox,oy,px,py,sys_time-2,1);
   while(LY_REG>=130);while(LY_REG<130);
   retain_reject(ox,oy,px,py,sys_time-1,1);
   for(stage=PREP_NONE;stage<PREP_READY;++stage) {
    prepare_stage=stage;retain_reject(ox,oy,px,py,0,0);
   }
   prepare_stage=PREP_READY;
   prepare_horizontal=0;retain_reject(ox,oy,px,py,0,0);prepare_horizontal=1;
   prepare_vertical=1;retain_reject(ox,oy,px,py,0,0);prepare_vertical=0;
   memcpy(retain_pending,prepare_added,38);memcpy(expected_references,references,888);
   --expected_references[retain_pending[dy>0?0:18]];next=next_slot;
   world_slot_strip_get(dx>0?prepare_left:prepare_old_left,
                        dy>0?prepare_old_top:prepare_old_top+18,0,20,retain_row);
   while(LY_REG>=113);while(LY_REG<113);start=sys_time-1;
   if(!prepare_rebase_column(ox,oy,px,py,start,1))++retain_failures;
   fixture_budget_check(start);
   if(prepare_stage!=PREP_ROW_FETCH || prepare_added_count!=18 || retired_count!=39
      || !prepare_vertical || prepare_index || next_slot!=next
      || memcmp(expected_references,references,888)
      || memcmp(prepare_added,retain_pending+(dy>0?1:0),36)
      || memcmp(retired+19,retain_row,40))++retain_failures;
   fixture_verify(retain_level,ox,oy);
#else
   /* Independently run the original cancellation/rebuild path. */
   prepare_cancel();prepare_begin(ox,oy,px,py);
   fixture_verify(retain_level,ox,oy);
#endif
   prepare_run(0,0);
  } else if(retain_mode==1) {
   fixture_prepare(ox,oy,px,py,1);fixture_verify(retain_level,ox,oy);
  }
  world_scroll(ox,oy,px,py);fixture_verify(retain_level,px,py);
  if(prepare_stage || prepare_added_count || retired_count)++retain_failures;
  fixture_retain_checkpoint();++retain_cases;
 }
 retain_extra_views=inspected_views-retain_extra_views;
}
'''
source=source.replace("    (OUT/'check.c').write_text(","    with (OUT/'inspect.c').open('a') as stream:\n        stream.write(('#define RETAIN_TEST_HAS_REBASE 1\\n' if b'prepare_rebase_column'in sources['world.c'] else '')+"+repr(extra)+")\n    (OUT/'check.c').write_text(",1)
source=source.replace("    flags=[str(BASE", "    check=(OUT/'check.c').read_text().replace('cache_done=1;', 'fixture_retain_cases();cache_done=1;')\n    (OUT/'check.c').write_text('#include <gb/gb.h>\\nvoid fixture_retain_cases(void) BANKED;\\nvoid fixture_retain_checkpoint(void) NONBANKED {}\\n'+check)\n    flags=[str(BASE",1)
source=source.replace("        if fine_phased:expected_views+=89","        expected_views+=word('retain_extra_views')\n        if fine_phased:expected_views+=89",1)
source=source.replace("        assert p.memory[symbols['_cache_done']]", "        report['retain']={name:word('retain_'+name) for name in ['cases','guard_checks','failures','extra_views']}\n        report['retain']['helper_calls']=retain_calls\n        (OUT/'commit-checkpoints.json').write_text(json.dumps(retain_checkpoints,indent=2)+'\\n')\n        assert word('retain_cases')==36 and not word('retain_failures'),report\n        assert p.memory[symbols['_cache_done']]",1)
hooks=r'''
    retain_checkpoints=[];retain_calls=[];retain_stack=[];retain_returns=set()
    local={n:int(a,16)for a,n in re.findall(r'^\s+([0-9A-Fa-f]{8})\s+\d+\s+(_\w+)::?$',(OUT/'inspect.lst').read_text(),re.M)}
    for name in ['prepare_added','prepare_stage','prepare_vertical','prepare_added_count','retired_count']:
        symbols['_'+name]=symbols['_game_world']+local['_'+name]-local['_game_world']
    def retain_snapshot():
        start=symbols['_game_world'];end=symbols['_prepare_added']+78
        return {'world':bytes(p.memory[start:end]),'sram':b''.join((bytes(p.memory[b,0xa000:0xbfff])+bytes([p.memory[b,0xbfff]]))for b in range(4)),
                'vram':b''.join((bytes(p.memory[b,0x8000:0x9fff])+bytes([p.memory[b,0x9fff]]))for b in range(2)),
                'bank':p.memory[symbols['__current_bank']]}
    def retain_checkpoint(_):
        fields={name:bytes(p.memory[symbols['_world_cache_'+name]:symbols['_world_cache_'+name]+size]).hex()for name,size in [('ids',888),('references',888),('free_bits',56),('next',2)]}
        # Hidden stale map cells are permitted. Compare every visible cell, all
        # patterns, all lookup SRAM and every cache allocator byte instead.
        fields['patterns']=hashlib.sha256(b''.join(bytes(p.memory[b,0x8000:0x9800])for b in range(2))).hexdigest()
        fields['lookup']=hashlib.sha256(bytes(p.memory[0,0xa000:0xb000])+b''.join((bytes(p.memory[b,0xa000:0xbfff])+bytes([p.memory[b,0xbfff]]))for b in range(1,4))).hexdigest()
        fields['case']=[p.memory[symbols['_retain_'+n]]for n in ['level','direction','mode']]
        retain_checkpoints.append(fields)
    p.hook_register(0,symbols['_fixture_retain_checkpoint'],observe(retain_checkpoint),None)
    if '_prepare_rebase_column'in local:
        address=symbols['_world_select']-local['_world_select']+local['_prepare_rebase_column']
        def retain_return(key):
            if not retain_stack or retain_stack[-1]['sp']!=p.register_file.SP-9:return
            before=retain_stack.pop();result=p.register_file.A
            if not result:assert before['state']==retain_snapshot(),'rejected rebase mutated world/cache/banks'
            else:
                assert p.memory[symbols['_prepare_stage']]==4
                assert p.memory[symbols['_prepare_added_count']]==18
                assert p.memory[symbols['_retired_count']]==39
            retain_calls.append({'cycles':p._cycles()-before['cycles'],'retained':bool(result)})
        def retain_enter(_):
            sp=p.register_file.SP
            if retain_stack and retain_stack[-1]['sp']==sp:return
            ret=p.memory[sp]+256*p.memory[sp+1];bank=6 if ret>=0x4000 else 0;key=(bank,ret)
            off=bank*16384+(ret&16383)if bank else ret
            assert rom[off]!=0xfb,'unsafe EI hook'
            if key not in retain_returns:p.hook_register(*key,observe(retain_return),key);retain_returns.add(key)
            retain_stack.append({'sp':sp,'cycles':p._cycles(),'state':retain_snapshot()})
        p.hook_register(6,address&65535,observe(retain_enter),None)
'''
source=source.replace("    try:\n        for _ in range(2500",hooks+"\n    try:\n        for _ in range(2500",1)
exec(compile(source,str(B/'test/check_world_cache.py'),'exec'),{'__name__':'__main__','__file__':str(B/'test/check_world_cache.py')})
