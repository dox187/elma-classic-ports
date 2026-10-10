#!/usr/bin/env python3
"""Privately link the complete word-C solver and exact generic ASM backend."""
import argparse
from decimal import Decimal,ROUND_HALF_UP
import json
from pathlib import Path
import re
import shutil
import subprocess
from wide_native_port import ROOT,run
from wide_stack_lower import lower
from wide_fast_scalar_gen import FUNCTIONS as FAST_SCALAR_FUNCTIONS,generate as generate_fast_scalar


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port',type=Path,required=True)
    ap.add_argument('--warmup',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--profile-code',action='store_true',help='Add zero-byte entry/exit/stack-change labels for native profiling')
    ap.add_argument('--fast-scalar',action='store_true',help='Replace17 proven word-C scalar/vector functions with exact assembly')
    ap.add_argument('--exact-trig',type=Path,help='Frozen full-domain exact Q44 trig assembly, with pointer ABI')
    ap.add_argument('--controller',type=Path,help='Frozen layout-compatible controller replacement')
    ap.add_argument('--math',type=Path,help='Frozen layout-compatible word math facade replacement')
    args=ap.parse_args();port=args.port.resolve();warmup=args.warmup.resolve();out=args.out.resolve()
    if out.exists():raise ValueError('Use a fresh output directory')
    out.mkdir(parents=True)
    for p in port.iterdir():
        if p.is_file() and p.suffix in ('.c','.h','.inc'):shutil.copy2(p,out/p.name)
    for name in ('wide_level_config.h','wide_level_globals.inc'):shutil.copy2(warmup/name,out/name)
    if args.controller:shutil.copy2(args.controller,out/'wide_controller.c')
    if args.math:shutil.copy2(args.math,out/'wide_port_native_math.c')
    bits=int(re.search(r'WIDE_PORT_BITS (\d+)',(out/'wide_math_config.h').read_text())[1])
    if args.fast_scalar:
        source=(out/'wide_port_native_math.c').read_text()
        for name in FAST_SCALAR_FUNCTIONS:
            found=list(re.finditer(r'^(?:wp_scalar|wp_vec|int) '+name+r'\([^\n]*?\)\{',source,re.M))
            if len(found)!=1:raise ValueError('Unknown scalar definition '+name)
            start=found[0].start();pos=found[0].end();depth=1
            while depth:
                if source[pos]=='{':depth+=1
                if source[pos]=='}':depth-=1
                pos+=1
            source=source[:start]+source[pos:]
        (out/'wide_port_native_math.c').write_text(source)
        (out/'fast_scalar.asm').write_text('.include "hdr.asm"\n.BASE $80\n'+generate_fast_scalar(bits))
    if args.exact_trig:
        if bits!=44:raise ValueError('Exact native trig is specifically Q44')
        source=(out/'wide_port_native_math.c').read_text()
        for name in ('wp_sin','wp_cos'):
            found=list(re.finditer(r'^wp_scalar '+name+r'\([^\n]*?\)\{',source,re.M))
            if len(found)!=1:raise ValueError('Unknown trig facade definition')
            pos=found[0].end();depth=1
            while depth:
                if source[pos]=='{':depth+=1
                if source[pos]=='}':depth-=1
                pos+=1
            source=source[:found[0].start()]+source[pos:]
        source+='\nvoid wide_q44_trig_pair(const uint16_t*,uint16_t*,uint16_t*);\nwp_scalar wp_sin(wp_scalar a){wp_scalar s,c;wide_q44_trig_pair(a.word,s.word,c.word);return s;}\nwp_scalar wp_cos(wp_scalar a){wp_scalar s,c;wide_q44_trig_pair(a.word,s.word,c.word);return c;}\n'
        (out/'wide_port_native_math.c').write_text(source)
        assembly=args.exact_trig.read_text()
        if 'wide_q44_trig_pair:' not in assembly:raise ValueError('Missing proven pointer ABI')
        assembly='\n'.join(line for line in assembly.splitlines()if not line.startswith('.include '))
        for index,path in enumerate(re.findall(r'\.incbin "([^"]+)"',assembly)):
            destination=out/('exact_trig_table'+str(index)+'.bin');shutil.copy2(path,destination);assembly=assembly.replace(path,str(destination))
        staging='.BASE $00\n.RAMSECTION ".wide_exact_trig_staging" BANK 0 SLOT 1\nwq_angle dsb 8\nwq_sin dsb 8\nwq_cos dsb 8\nwq_status dsb 2\nwq_hit dsb 2\n.ENDS\n'
        assembly='.include "hdr.asm"\n.DEFINE MPYA $211B\n.DEFINE MPYB $211C\n.DEFINE MPYL $2134\n.DEFINE MPYM $2135\n.DEFINE MPYH $2136\n'+staging+'.BASE $80\n'+assembly
        (out/'exact_trig.asm').write_text(assembly)
    raw=int((Decimal('.00546')*(1<<bits)).to_integral_value(rounding=ROUND_HALF_UP))
    driver=(ROOT/'test/wide_native_step_driver.c').read_text()
    driver=re.sub(r'dt.word\[0\]=35756;dt.word\[1\]=26843;dt.word\[2\]=22;dt.word\[3\]=0;',
                  ''.join('dt.word['+str(i)+']='+str((raw>>(16*i))&65535)+';'for i in range(4)),driver)
    (out/'wide_native_step_driver.c').write_text(driver)
    shutil.copy2(ROOT/'test/wide_native_math.asm',out/'wide_native_math.asm')
    # Original table C objects would allocate initialized arrays in WRAM.
    # Emit the identical bytes in independent ROM sections instead.
    table=['.include "hdr.asm"','.BASE $80']
    for kind in ('sin','cos'):
        for i in range(8):
            name='wp_native_'+kind+'_'+str(i)
            values=re.findall(r'\{([^{}]+)\}',(port/(name+'.c')).read_text())
            words=[int(x)for row in values for x in row.split(',')]
            assert len(words)==2048
            table+=['.SECTION ".'+name+'_rom" SUPERFREE',name+':']
            table+=['.dw '+','.join(str(x)for x in words[j:j+16])for j in range(0,len(words),16)]
            table+=['.ENDS']
    (out/'trig_tables.asm').write_text('\n'.join(table)+'\n')
    levels=Path(json.loads((warmup/'build.json').read_text())['levels'])
    shutil.copy2(levels/'lev00.bin',out/'lev00.bin')
    (out/'level_blob.asm').write_text('.include "hdr.asm"\n.BASE $80\n.SECTION ".wide_level00_blob" SUPERFREE\nwide_native_level00:\n.incbin "'+str(out/'lev00.bin')+'"\n.ENDS\n')
    (out/'math_backend.asm').write_text('.include "hdr.asm"\n.DEFINE MPYA $211B\n.DEFINE MPYB $211C\n.DEFINE MPYL $2134\n.DEFINE MPYM $2135\n.DEFINE MPYH $2136\n.include "'+str(out/'wide_native_math.asm')+'"\n.BASE $00\n.RAMSECTION ".wide_stack_load_scratch" BANK 0 SLOT 1\nwide_stack_load_scratch dsb 2\nwide_stack_proof_a dsb 2\nwide_stack_proof_p dsb 2\nwide_stack_proof_x dsb 2\n.ENDS\n')
    proof=['.include "hdr.asm"','.BASE $00','.RAMSECTION ".wide_stack_proof_results" BANK $7E SLOT 2','wide_stack_proof_results dsb 384','.ENDS','.BASE $80','.SECTION ".wide_stack_opcode_proof" SUPERFREE','wide_stack_opcode_proof:','php','rep #$30','pha','phx','phy','tsa','sec','sbc #512','tas']
    cases=[]
    for op in ('lda','sta'):
        for value in (0,1,32768,65535):
            for flags in (0x45,0x0d,0x84,0x06):
                offset=12*len(cases);cases.append({'op':op,'a':value,'flags':flags})
                proof+=['tsx','lda #$cafe','sta.l $7e0000+298,x','lda #$beef','sta.l $7e0000+302,x','lda #'+str(value),'sta.l $7e0000+300,x','stz.w wide_stack_proof_p','ldx #$4321','sep #$20','lda #'+str(flags),'pha','rep #$20','lda #'+str(value),'plp']
                lowered,_=lower(op+' 300,s\n');proof+=lowered.splitlines()
                proof+=['sta.l wide_stack_proof_a','php','sep #$20','pla','sta.l wide_stack_proof_p','rep #$20','txa','sta.l wide_stack_proof_x','lda.l wide_stack_proof_a','sta.l wide_stack_proof_results+'+str(offset),'lda.l wide_stack_proof_x','sta.l wide_stack_proof_results+'+str(offset+2),'lda.l wide_stack_proof_p','sta.l wide_stack_proof_results+'+str(offset+4),'tsx']
                for field,address in ((6,298),(8,300),(10,302)):proof+=['lda.l $7e0000+'+str(address)+',x','sta.l wide_stack_proof_results+'+str(offset+field)]
    proof+=['tsa','clc','adc #512','tas','ply','plx','pla','plp','rtl','.ENDS']
    (out/'stack_proof.asm').write_text('\n'.join(proof)+'\n');(out/'stack_cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    dev=Path.home()/'.local/share/elma-snes/pvsneslib-4.6.0/pvsneslib/devkitsnes';bins=dev/'bin'
    objects=[];commands=[];stack_lowered={};profile_entries={};profile_exits={};profile_stack=[]
    def annotate(text,unit,assembly_backend=False):
        output=[];current=None;index=0
        for line in text.splitlines():
            label=re.fullmatch(r'([^\s:]+):',line)
            if label and ((assembly_backend and label[1] in ('wide_mul64','wide_div64','wide_sqrt64','wide_q44_trig_pair','wq_native_pair')) or
                          (not assembly_backend and (label[1].startswith('wp_')or label[1].startswith('tccs_')or label[1] in ('main',)))):
                current=label[1].replace('{WLA_FILENAME}',str(out/(unit+'.s')));profile_entries[current]=current
            if line=='.ENDS':current=None
            if line.strip()=='rtl' and current:
                name='wide_profile_exit_'+unit+'_'+str(index);index+=1;output.append(name+':');profile_exits[name]=current
            output.append(line)
            if line.strip() in ('tas','tcs','pha','phx','php','phy','phb','phd')or line.strip().startswith(('pei ','pea ')):
                name='wide_profile_stack_'+unit+'_'+str(index);index+=1;output.append(name+':');profile_stack.append(name)
        return '\n'.join(output)+'\n'
    for name in ('wide_controller','wide_level_loader','wide_port_native_math','wide_native_step_driver'):
        command=[str(bins/'816-tcc'),'-Wall','-F','-DWIDE_TARGET_SNES=1','-I'+str(dev/'include'),'-I'+str(dev.parent/'pvsneslib/include'),'-I'+str(out),'-Isrc','-c',str(out/(name+'.c')),'-o',str(out/(name+'.ps'))]
        commands.append(command);run(command,out/(name+'-compile.log'))
        command=[str(dev/'tools/816-opt'),'-i',str(out/(name+'.ps')),'-o',str(out/(name+'.s'))]
        commands.append(command);run(command,out/(name+'-opt.log'))
        assembly,count=lower((out/(name+'.s')).read_text());(out/(name+'.s')).write_text(assembly);stack_lowered[name]=count
        if args.profile_code:(out/(name+'.s')).write_text(annotate(assembly,name))
        command=[str(bins/'wla-65816'),'-d','-s','-x','-Ibuild/gen','-Isrc','-o',str(out/(name+'.obj')),str(out/(name+'.s'))]
        commands.append(command);run(command,out/(name+'-as.log'));objects.append(out/(name+'.obj'))
    for name in ('trig_tables','level_blob','math_backend','stack_proof')+ (('fast_scalar',)if args.fast_scalar else ())+(('exact_trig',)if args.exact_trig else ()):
        if args.profile_code and name=='math_backend':
            (out/'wide_native_math.asm').write_text(annotate((out/'wide_native_math.asm').read_text(),'wide_native_math',True))
        if args.profile_code and name=='exact_trig':
            (out/'exact_trig.asm').write_text(annotate((out/'exact_trig.asm').read_text(),'exact_trig',True))
        command=[str(bins/'wla-65816'),'-h','-s','-x','-Ibuild/gen','-Isrc','-o',str(out/(name+'.obj')),str(out/(name+'.asm'))]
        commands.append(command);run(command,out/(name+'-as.log'));objects.append(out/(name+'.obj'))
    objects.append(ROOT/'build/obj/core.obj')
    lib=dev.parent/'pvsneslib/lib/LoROM_FastROM'
    objects.extend(sorted(lib.glob('*.obj')))
    link=out/'wide_step.sfc.link';link.write_text('[objects]\n'+'\n'.join(map(str,objects))+'\n')
    command=[str(bins/'wlalink'),'-d','-S','-A','-c','-L',str(lib),str(link),str(out/'wide_step.sfc')]
    commands.append(command);run(command,out/'link.log')
    command=['python3','tools/romfix.py',str(out/'wide_step.sfc'),str(out/'wide_step.sfc'),'--tv','ntsc'];commands.append(command);run(command,out/'romfix.log')
    (out/'native_rom.json').write_text(json.dumps({'port':str(port),'warmup':str(warmup),'bits':bits,'dt_raw':raw,'fast_scalar':args.fast_scalar,'exact_trig':str(args.exact_trig)if args.exact_trig else None,'controller':str(args.controller)if args.controller else None,'stack_offsets_lowered':stack_lowered,'commands':commands,'performance':'Correctness first; generic arithmetic cannot sustain60FPS'},indent=2)+'\n')
    if args.profile_code:(out/'profile_labels.json').write_text(json.dumps({'entries':profile_entries,'exits':profile_exits,'stack_changes':profile_stack},indent=2)+'\n')
    print(out/'wide_step.sfc')


if __name__=='__main__':main()
