"""Generate direct 65816 control for the original ordered Q48 trig baseline."""
from pathlib import Path
import re

def generate(out,table_source,specialized=False,control_fast=False,square_fast=False,short_products=False,index_fast=False):
 lines=['.RAMSECTION ".wqa_ram" BANK 0 SLOT 1 ALIGN 256','wqa_ram dsb 256','.ENDS','.SECTION ".wqa_text" SUPERFREE']
 def e(*s):lines.extend(s)
 def cp(src,dst,n=4):
  for j in range(n):e(' lda.b %d'%(src+2*j),' sta.b %d'%(dst+2*j))
 def zero(dst,n=4):
  for j in range(n):e(' stz.b %d'%(dst+2*j))
 def sub(dst,src,n=4):
  e(' sec')
  for j in range(n):e(' lda.b %d'%(dst+2*j),' sbc.b %d'%(src+2*j),' sta.b %d'%(dst+2*j))
 def add(dst,src,n=4):
  e(' clc')
  for j in range(n):e(' lda.b %d'%(dst+2*j),' adc.b %d'%(src+2*j),' sta.b %d'%(dst+2*j))
 def neg(dst,n=4):
  e(' sec')
  for j in range(n):e(' lda #0',' sbc.b %d'%(dst+2*j),' sta.b %d'%(dst+2*j))
 def shl(dst,n=4):
  e(' asl.b %d'%dst)
  for j in range(1,n):e(' rol.b %d'%(dst+2*j))
 def shr(dst,n=4):
  e(' lsr.b %d'%(dst+2*(n-1)))
  for j in range(n-2,-1,-1):e(' ror.b %d'%(dst+2*j))
 counter=0
 multiplication=0
 def ge(x,y,n,yes,no):
  for j in range(n-1,-1,-1):e(' lda.b %d'%(x+2*j),' cmp.b %d'%(y+2*j),' bcc '+no,' bne '+yes)
  e(' jmp '+yes)
 def mul(x,y,dst):
  nonlocal multiplication
  multiplication+=1
  e("wqa_mul%d_begin:"%multiplication)
  if specialized:
   from wide_native_q44_products import product,square
   spec={1:(3,5,False),2:(2,5,False),3:(3,5,True),4:(3,4,True)}[multiplication]
   text=square(x,dst)if square_fast and multiplication==1 else product(x,y,dst,*spec,accbytes=8 if short_products and multiplication==2 else 10 if short_products and multiplication==4 else 12)
   # Function-local labels must be unique across the four product bodies.
   text=text.replace('wqp_', 'wqp_%d_'%multiplication).replace('wqs_', 'wqa_square_')
   lines.extend(text.splitlines());e('wqa_mul%d_end:'%multiplication);return
  # Arguments are PVS4-byte pointers to low-WRAM bank7E buffers.
  for off in [134,dst]:e(' pea $007e',' pea (wqa_ram+%d)'%off)
  e(' pea 48')
  for off in [y,x]:e(' pea $007e',' pea (wqa_ram+%d)'%off)
  e(' jsl wide_mul64',' tsc',' clc',' adc #18',' tcs',' lda.b 134',' ora.l wq_status',' sta.l wq_status')
  e('wqa_mul%d_end:'%multiplication)
 e('wq_native_pair:',' php',' phb',' phd',' rep #$30',' phx',' phy',' sep #$20',' lda.b #$80',' pha',' plb',' rep #$20',' lda #wqa_ram',' tcd')
 for j in range(4):e(' lda.l wq_angle+%d'%(2*j),' sta.b %d'%(2*j))
 e(' lda #0',' sta.l wq_status',' sta.l wq_hit')
 for slot in [160,192]:
  e(' lda.b %d'%(slot+24),' beq wqa_cache_next_%d'%slot)
  for j in range(4):e(' lda.b %d'%(2*j),' cmp.b %d'%(slot+2*j),' bne wqa_cache_next_%d'%slot)
  cp(slot+8,112);cp(slot+16,120);e(' lda #1',' sta.l wq_hit',' jmp wqa_return','wqa_cache_next_%d:'%slot)
 cp(0,8);e(' stz.b 16',' lda.b 6',' bpl wqa_abs_done');neg(8);e('wqa_abs_done:')
 for _ in range(4):shl(8,5)
 period=1768559438007110;pi=period//2;quarter=pi//2
 def constant(dst,value,n=5):
  for j in range(n):e(' lda #%d'%((value>>(16*j))&65535),' sta.b %d'%(dst+2*j))
 if control_fast:
  e(' lda.b 16',' bne wqa_mod_wide',' lda.b 14',' cmp #32',' bcs wqa_mod_low')
  constant(18,period);e('wqa_mod_small:');ge(8,18,5,'wqa_mod_small_sub','wqa_mod_reduced');e('wqa_mod_small_sub:');sub(8,18,5);e(' jmp wqa_mod_small','wqa_mod_wide:',' ldx #14',' lda.b 16','wqa_mod_highbit:',' cmp #2',' bcc wqa_mod_scale',' lsr a',' inx',' jmp wqa_mod_highbit','wqa_mod_low:',' ldx #0',' lda.b 14','wqa_mod_lowbit:',' cmp #8',' bcc wqa_mod_scale',' lsr a',' inx',' jmp wqa_mod_lowbit','wqa_mod_scale:',' txa',' sta.b 136',' asl a',' asl a',' clc',' adc.b 136',' asl a',' tax')
  for j in range(5):e(' lda.l wqa_period_shifts+%d,x'%(2*j),' sta.b %d'%(18+2*j))
  e(' lda.b 136',' inc a',' tax')
 else:
  constant(18,period<<16);e(' ldx #17')
 e('wqa_mod_loop:');ge(8,18,5,'wqa_mod_sub','wqa_mod_next');e('wqa_mod_sub:');sub(8,18,5);e('wqa_mod_next:');shr(18,5);e(' dex',' bne wqa_mod_loop','wqa_mod_reduced:',' lda.b 6',' bpl wqa_mod_done',' lda.b 8',' ora.b 10',' ora.b 12',' ora.b 14',' ora.b 16',' beq wqa_mod_done');constant(18,period);sub(18,8,5);cp(18,8,5);e('wqa_mod_done:',' stz.b 132',' jsr wqa_evaluate');cp(92,112);e(' lda #1',' sta.b 132',' jsr wqa_evaluate');cp(92,120)
 e(' lda.b 224',' and #1',' bne wqa_cache_store1')
 for slot in [160,192]:
  if slot==192:e('wqa_cache_store1:')
  cp(0,slot);cp(112,slot+8);cp(120,slot+16);e(' lda #1',' sta.b %d'%(slot+24))
  if slot==160:e(' jmp wqa_cache_stored')
 e('wqa_cache_stored:',' lda.b 224',' eor #1',' sta.b 224','wqa_return:')
 for dst,name in [(112,'sin'),(120,'cos')]:
  for j in range(4):e(' lda.b %d'%(dst+2*j),' sta.l wq_%s+%d'%(name,2*j))
 e(' ply',' plx',' pld',' plb',' plp','wq_native_pair_end:',' rtl','wq_native_reset:',' php',' phd',' rep #$30',' lda #wqa_ram',' tcd',' stz.b 184',' stz.b 216',' stz.b 224',' pld',' plp',' rtl')
 e('wqa_evaluate:');cp(8,28);e(' lda.b 132',' beq wqa_cos_phase_done');constant(84,quarter,4);add(28,84);constant(84,period,4);ge(28,84,4,'wqa_cos_mod','wqa_cos_phase_done');e('wqa_cos_mod:');sub(28,84);e('wqa_cos_phase_done:',' stz.b 130');constant(84,pi,4)
 # Original negative is strictly a>pi; equality retains positive endpoint.
 for j in range(3,-1,-1):e(' lda.b %d'%(28+j*2),' cmp.b %d'%(84+j*2),' bcc wqa_sign_done',' bne wqa_sign_negative')
 e(' jmp wqa_sign_done','wqa_sign_negative:',' lda #1',' sta.b 130');sub(28,84);e('wqa_sign_done:');constant(84,quarter,4)
 for j in range(3,-1,-1):e(' lda.b %d'%(28+j*2),' cmp.b %d'%(84+j*2),' bcc wqa_reflect_done',' bne wqa_reflect')
 e(' jmp wqa_reflect_done','wqa_reflect:');constant(84,pi,4);sub(84,28);cp(84,28);e('wqa_reflect_done:')
 if index_fast:
  # Original quotient index via a bounded reciprocal and one exact threshold.
  e(' WIDE_MUL48_K 28,144,136,20860',' lda.b 32',' bpl wqa_index_sign_done',' lda.b 150',' clc',' adc #20860',' sta.b 150','wqa_index_sign_done:',' lda.b 34',' beq wqa_index_top_done',' lda.b 150',' clc',' adc #20860',' sta.b 150','wqa_index_top_done:',' lda.b 150',' lsr a',' lsr a',' lsr a',' inc a',' sta.b 128',' jsr wqa_load_threshold')
  ge(28,84,4,'wqa_found','wqa_index_below');e('wqa_index_below:',' dec.b 128','wqa_found:')
 else:
  e(' stz.b 138',' lda #4096',' sta.b 140','wqa_search:',' lda.b 138',' cmp.b 140',' beq wqa_found',' clc',' adc.b 140',' inc a',' lsr a',' sta.b 128',' jsr wqa_load_threshold'if control_fast else' jsr wqa_load_row');ge(28,84,4,'wqa_search_ge','wqa_search_lt');e('wqa_search_ge:',' lda.b 128',' sta.b 138',' jmp wqa_search','wqa_search_lt:',' lda.b 128',' dec a',' sta.b 140',' jmp wqa_search','wqa_found:',' lda.b 138',' sta.b 128')
 e(' jsr wqa_load_row',' lda.b 128',' beq wqa_anchor_done',' cmp #4096',' beq wqa_anchor_done');zero(76);e(' lda #1',' sta.b 76');sub(84,76);e('wqa_anchor_done:');cp(28,36);sub(36,84);mul(36,36,44);mul(44,36,52)
 # d3 is bounded <16000. Exact nearest division by6 using16 restoring bits.
 e(' lda.b 52',' clc',' adc #3',' sta.b 136',' stz.b 84',' stz.b 138',' ldx #16','wqa_div6_loop:',' asl.b 136',' rol.b 138',' asl.b 84',' lda.b 138',' cmp #6',' bcc wqa_div6_next',' sbc #6',' sta.b 138',' inc.b 84','wqa_div6_next:',' dex',' bne wqa_div6_loop');zero(86,3);cp(36,76);sub(76,84);mul(68,76,92);add(92,60);cp(44,84);zero(76);e(' lda #1',' sta.b 76');add(84,76);shr(84);mul(60,84,76);sub(92,76);zero(84);e(' lda #8',' sta.b 84');add(92,84)
 for _ in range(4):shr(92)
 e(' lda.b 130',' beq wqa_evaluate_done');neg(92);e('wqa_evaluate_done:',' rts')
 for label,fields in [('wqa_load_row',[(0,84),(8,60),(16,68)])]+([('wqa_load_threshold',[(0,84)])]if control_fast or index_fast else[]):
  e(label+':',' lda.b 128',' and #511',' asl a',' asl a',' asl a',' sta.b 136',' asl a',' clc',' adc.b 136',' tax',' lda.b 128')
  for _ in range(9):e(' lsr a')
  for bank in range(8):e(' cmp #%d'%bank,' beq '+label+'_%d'%bank)
  e(' jmp '+label+'_8')
  for bank in range(9):
   e(label+'_%d:'%bank)
   for offset,dst in fields:
    for j in range(4):e(' lda.l wq_table%d+%d,x'%(bank,offset+2*j),' sta.b %d'%(dst+2*j))
   e(' rts')
 if control_fast:
  e('wqa_period_shifts:')
  for k in range(18):e('.dw '+','.join(str(((period<<k)>>(16*j))&65535)for j in range(5)))
 e('wide_q44_trig_pair:',' php',' phb',' phd',' rep #$30',' phx',' phy',' lda #wqa_ram',' tcd')
 for stack,dst in [(12,230),(16,234),(20,238)]:e(' lda %d,s'%stack,' sta.b %d'%dst,' lda %d,s'%(stack+2),' sta.b %d'%(dst+2))
 for j in range(4):e(' ldy #%d'%(2*j),' lda [230],y',' sta.l wq_angle+%d'%(2*j))
 e(' jsl wq_native_pair')
 for src,ptr in [('sin',234),('cos',238)]:
  for j in range(4):e(' ldy #%d'%(2*j),' lda.l wq_%s+%d'%(src,2*j),' sta [%d],y'%ptr)
 e(' ply',' plx',' pld',' plb',' plp','wide_q44_trig_pair_end:',' rtl','wqa_text_end:','.ENDS')
 text='\n'.join(lines)+'\n';inv={'bcc':'bcs','bcs':'bcc','beq':'bne','bne':'beq','bpl':'bmi','bmi':'bpl'};n=0
 def branch(m):
  nonlocal n
  n+=1;op,label=m.groups();return ' '+inv[op]+' wqa_long_%d\n jmp '%n+label+'\nwqa_long_%d:'%n
 text=re.sub(r'^ (bcc|bcs|beq|bne|bpl|bmi) ((?:wqa|wqp)_\w+)$',branch,text,flags=re.M)
 path=out/'q44_native.asm';path.write_text(table_source.read_text()+('.include "test/wide_arith.inc"\n'if index_fast else'')+text)
 driver=out/'q44_native_driver.c';driver.write_text('#include <snes.h>\n#include "core.h"\nvoid wq_native_pair(void);void wq_native_reset(void);void wide_q44_trig_pair(const u16*,u16*,u16*);\nu16 wq_angle[4],wq_sin[4],wq_cos[4];volatile u16 wq_go,wq_done,wq_status,wq_hit;\nint main(void){consoleInit();core_init();core_screen_off();wq_native_reset();while(1){if(wq_go){u16 cmd=wq_go;wq_go=0;if(cmd==3)wide_q44_trig_pair((const u16*)0x7f0200,(u16*)0x7f0220,(u16*)0x7f0240);else if(cmd==2)wide_q44_trig_pair(wq_angle,wq_sin,wq_cos);else wq_native_pair();wq_done=1;}core_frame_done();}return 0;}\n')
 return path,driver
