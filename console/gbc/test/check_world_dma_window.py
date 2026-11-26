"""Sweep native single-tile DMA calls through LCD phases without state patching.

The helper ROM compiles an exact copy of world_dma.c, generates its own banked
ROM input and VRAM guards, and checks bytes, banks and existing IRQ semantics on the
SM83. Read-only instruction hooks measure the real calls and GDMA launches.
The four-T-cycle delay sweep includes line 143, all of late VBlank, line 153,
and the next frame's mode 2. The hardware timing proof uses STAT, so it also
covers early LY=0 during line 153 when the emulator does not model that quirk.
This is not a hardware test.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess

from pyboy import PyBoy

BASE = Path(__file__).resolve().parents[1]
PHASES = 684  # Three double-speed scanlines, stepping by one NOP (4 T).


DRIVER = r'''#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdint.h>
void world_upload_tile(uint16_t,uint16_t,uint16_t) NONBANKED;
void fixture_delay(uint16_t) __sdcccall(0);
volatile uint16_t fixture_case,fixture_bank,fixture_source,fixture_pattern;
volatile uint16_t fixture_phase,fixture_completed,fixture_irqs;
volatile uint16_t byte_failures,guard_failures,bank_failures,register_failures,irq_failures;
volatile uint8_t fixture_anchor,fixture_enabled,fixture_done,fixture_lcd,fixture_observed_irq;
void fixture_checked(void) NONBANKED {__asm nop __endasm;}
void fixture_synced(void) NONBANKED {__asm nop __endasm;}
static void irq(void) NONBANKED {++fixture_irqs;}
static uint8_t value(uint16_t bank,uint16_t offset) {
 return (uint8_t)((bank*13U+offset*29U)^(offset>>8)^(bank>>8)*0x5bU);
}
static uint8_t guard(uint8_t bank,uint8_t offset) {return (uint8_t)(0xa7U+bank*19U+offset*37U);}
static void run(void) {
 uint16_t dest,start,i,before;uint8_t b,expected,svbk;
 disable_interrupts();DISPLAY_OFF;
 dest=0x8000U+((fixture_pattern&255U)<<4);
 start=dest==0x8000U?dest:dest-16U;
 for(b=0;b<2;++b) {
  VBK_REG=b;
  for(i=0;i<48;++i)*(volatile uint8_t*)(start+i)=guard(b,(uint8_t)i);
 }
 /* Ten objects, fine scrolling and the window exercise shortened HBlank. */
 SCX_REG=7;WY_REG=0;WX_REG=7;
 for(i=0;i<40;++i) {
  shadow_OAM[i].y=i<10?(fixture_anchor==142?159:fixture_anchor==1?17:16):0;
  shadow_OAM[i].x=(uint8_t)(8U+i*8U);
  shadow_OAM[i].tile=0;shadow_OAM[i].prop=0;
 }
 for(i=0;i<160;++i)*(volatile uint8_t*)(0xfe00U+i)=((uint8_t*)shadow_OAM)[i];
 SWITCH_ROM(6);rRAMB=3;VBK_REG=1;svbk=SVBK_REG&7;
 IE_REG=VBL_IFLAG;IF_REG=0;
 if(fixture_lcd)DISPLAY_ON;
 if(fixture_enabled)enable_interrupts();
 if(fixture_lcd) {
  /* Anchors avoid polling for LY=153, which is only briefly visible. */
  while(LY_REG==fixture_anchor){}
  while(LY_REG!=fixture_anchor){}
  fixture_synced();
  fixture_delay(fixture_phase);
 }
 world_upload_tile(fixture_bank,fixture_source,fixture_pattern);
 if(CURRENT_BANK!=6 || *(volatile uint8_t*)0x4000!=value(6,0))++bank_failures;
 if((VBK_REG&1) || (SVBK_REG&7)!=svbk || IE_REG!=VBL_IFLAG || HDMA5_REG!=255)++register_failures;
 if(*(volatile uint8_t*)0xa000!=0x63)++bank_failures;
 /* A pending native interrupt exposes the compiler's existing DI/EI
  * critical-section behavior. The observer checks which path was taken. */
 before=fixture_irqs;IF_REG=VBL_IFLAG;
 for(i=0;i<128;++i)__asm nop __endasm;
 fixture_observed_irq=fixture_irqs!=before;
 if(fixture_enabled && !fixture_observed_irq)++irq_failures;
 fixture_checked();
 disable_interrupts();DISPLAY_OFF;
 for(b=0;b<2;++b) {
  VBK_REG=b;
  for(i=0;i<48;++i) {
   expected=guard(b,(uint8_t)i);
   if(b==(fixture_pattern>=256) && start+i>=dest && start+i<dest+16U)
    expected=value(fixture_bank,fixture_source-0x4000U+start+i-dest);
   if(*(volatile uint8_t*)(start+i)!=expected) {
    if(b==(fixture_pattern>=256) && start+i>=dest && start+i<dest+16U)++byte_failures;
    else ++guard_failures;
   }
  }
 }
 VBK_REG=0;++fixture_completed;
}
void main(void) {
 uint16_t phase;uint8_t anchor,enabled,b;
 cpu_fast();disable_interrupts();DISPLAY_OFF;ENABLE_RAM;
 for(b=0;b<4;++b){rRAMB=b;*(volatile uint8_t*)0xa000=(uint8_t)(0x60U+b);}
 LCDC_REG=LCDCF_BGON|LCDCF_OBJON|LCDCF_WINON|LCDCF_WIN9C00|LCDCF_BG8000;
 add_VBL(irq);
 fixture_lcd=1;
 for(enabled=0;enabled<2;++enabled)for(anchor=0;anchor<3;++anchor) {
  fixture_enabled=enabled;fixture_anchor=anchor==0?1:anchor==1?142:151;
  for(phase=0;phase<PHASES;++phase) {
   fixture_phase=phase;fixture_bank=(phase&1)?300:511;
   fixture_source=(phase&2)?0x7ff0:0x4000;
   fixture_pattern=(phase&3)==0?0:(phase&3)==1?255:(phase&3)==2?256:447;
   run();++fixture_case;
  }
 }
 fixture_lcd=0;
 for(enabled=0;enabled<2;++enabled)for(phase=0;phase<4;++phase) {
  fixture_enabled=enabled;fixture_phase=phase;fixture_bank=(phase&1)?300:511;
  fixture_source=(phase&2)?0x7ff0:0x4000;fixture_pattern=phase*170U;
  run();++fixture_case;
 }
 fixture_done=1;while(1){}
}
'''


def build(source, out):
    out.mkdir(parents=True, exist_ok=True)
    payload = source.read_bytes()
    (out/'world_dma.c').write_bytes(payload)
    (out/'driver.c').write_text('#define PHASES %d\n' % PHASES + DRIVER)
    # Jump into an unrolled NOP run: all delay counts have identical setup.
    (out/'delay.s').write_text(''' .module fixture_delay
 .area _CODE
_fixture_delay::
 ld hl,#2
 add hl,sp
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld a,#<delay_end
 sub a,e
 ld l,a
 ld a,#>delay_end
 sbc a,d
 ld h,a
 jp (hl)
''' + ' nop\n'*(PHASES-1) + 'delay_end:\n ret\n')
    data_sources = []
    for bank in (6, 300, 511):
        data = [((bank*13+i*29) ^ (i>>8) ^ (bank>>8)*0x5b)&255 for i in range(16384)]
        path = out/('data%d.c' % bank)
        path.write_text('#include <stdint.h>\n#pragma bank %d\nconst uint8_t data%d[]={\n' % (bank, bank)
                        + ','.join(map(str, data)) + '\n};\n')
        data_sources.append(str(path))
    command = [str(BASE/'.toolchain/gbdk/bin/lcc'), '-msm83:gb', '-Wf--opt-code-size',
               '-Wm-yC', '-Wm-yt0x1a', '-Wm-yo512', '-Wm-ya4', '-Wl-m', '-Wl-j',
               '-o', str(out/'check.gbc'), str(out/'driver.c'), str(out/'world_dma.c'),
               str(out/'delay.s'), *data_sources]
    result = subprocess.run(command, capture_output=True, text=True)
    (out/'compile.log').write_text(result.stdout+result.stderr)
    assert result.returncode == 0, result.stdout+result.stderr
    return hashlib.sha256(payload).hexdigest()


def run(source, out, bounded):
    source_sha = build(source, out)
    symbols = {name: int(address, 16) for name, address in
               re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)', (out/'check.noi').read_text())}
    rom = (out/'check.gbc').read_bytes()
    start = symbols['_world_upload_tile']
    end = min(address for address in symbols.values() if start < address < 0x4000)
    code = rom[start:end]
    epilogue = bytes.fromhex('e1 f1 e9')
    code = code[:code.index(epilogue)+len(epilogue)]
    # A successful STAT read in mode 0/1 is followed by a complete mode 2.
    # Even if the sample was its last dot, the poll through the DMA stall
    # needs only 108 T. The older helper instead waited for a transition.
    high = bytes.fromhex('f0 41 e6 02 20 fa af e0 55')
    assert high in code, 'rederive STAT timing bound'
    if bounded:
        assert b'\xf3'+high+b'\xfb' in code, 'active DMA must stay inside DI/EI'
    dma_sites = [start+i for i in range(len(code)-1) if code[i:i+2] == b'\xe0\x55']
    assert len(dma_sites) == (2 if bounded else 3), dma_sites
    p = PyBoy(str(out/'check.gbc'), window='null', sound_emulated=False, cgb=True)
    p.set_emulation_speed(0)
    calls, errors, returns = [], [], set()
    active, launched, synced = None, None, None
    deferred_completions = 0
    durations, launches = Counter(), Counter()

    def n(name, size=2):
        address = symbols['_'+name]
        # Explicit WRAM-bank reads remain observable during OAM DMA bus lock.
        return int.from_bytes(bytes(p.memory[0, address:address+size]), 'little')

    def checked(callback):
        def observe(context):
            try:
                callback(context)
            except BaseException as error:
                errors.append(str(error))
        return observe

    def entered(_):
        nonlocal active
        sp = p.register_file.SP
        ret = p.memory[sp]+256*p.memory[sp+1]
        if active is not None:
            # An IRQ can preempt the hooked first instruction and resume it.
            # Keep that interruption in this call's elapsed CPU time.
            assert (active['sp'], active['ret'], active['case']) == (sp, ret, n('fixture_case')), 'overlapping upload calls'
            return
        if ret not in returns:
            p.hook_register(0, ret, checked(completed), ret)
            returns.add(ret)
        active = {'case': n('fixture_case'), 'phase': n('fixture_phase'),
                  'anchor': n('fixture_anchor', 1), 'irq': n('fixture_enabled', 1),
                  'lcd': n('fixture_lcd', 1), 'entry_line': p.memory[0xff44],
                  'entry_mode': p.memory[0xff41]&3, 'start': p._cycles(), 'sp': sp, 'ret': ret,
                  'critical': False, 'delay_cycles': p._cycles()-synced if n('fixture_lcd', 1) else 0}

    def completed(ret):
        nonlocal active, launched, deferred_completions
        if active is None or active['ret'] != ret or active['sp']+4 != p.register_file.SP:
            return
        active['cycles'] = p._cycles()-active.pop('start')
        active.pop('ret'); active.pop('sp')
        assert 'launch_line' in active, 'call returned without GDMA'
        if launched is not None:
            assert rom[launched[0]+2] == 0xfb
            deferred_completions += 1
            launched = None
        calls.append(active); active = None

    def synchronized(_):
        nonlocal synced
        synced = p._cycles()

    def critical(_):
        assert active is not None
        active['critical'] = True
        active['poll_start'] = p._cycles()

    def irq_checked(_):
        call = calls[-1]
        assert n('fixture_observed_irq', 1) == bool(call['irq'] or call['critical']), ('IRQ semantics changed', call)

    def launch(site):
        nonlocal launched
        assert active is not None and launched is None
        mode, line = p.memory[0xff41]&3, p.memory[0xff44]
        assert p.register_file.A == 0, 'DMA must transfer exactly 16 bytes'
        assert not active['lcd'] or mode != 3, ('unsafe launch', line, mode)
        active.update(launch_mode=mode, launch_line=line)
        if active['critical']:
            active['poll_cycles'] = p._cycles()-active.pop('poll_start')
        launches['off' if not active['lcd'] else str(mode)] += 1
        launched = (site, p._cycles())

    def transferred(site):
        nonlocal launched
        if launched is None or launched[0] != site:
            return
        durations[p._cycles()-launched[1]] += 1
        assert not active['lcd'] or p.memory[0xff41]&3 != 3, 'GDMA finished in inaccessible VRAM mode'
        launched = None

    p.hook_register(0, start, checked(entered), None)
    critical_site = start+code.index(bytes.fromhex('f3 f0 41 e6 02'))
    assert bytes.fromhex('fb af ea 00 30') in code, 'critical epilogue changed'
    p.hook_register(0, critical_site, checked(critical), None)
    p.hook_register(0, symbols['_fixture_checked'], checked(irq_checked), None)
    p.hook_register(0, symbols['_fixture_synced'], checked(synchronized), None)
    for site in dma_sites:
        p.hook_register(0, site, checked(launch), site)
        # PyBoy can repeat a hook on EI without advancing when an interrupt
        # is pending. Leave that instruction unhooked; the native byte checks
        # still verify that path, and the other sites measure the DMA stall.
        if rom[site+2] != 0xfb:
            p.hook_register(0, site+2, checked(transferred), site)
    try:
        for _ in range(400):
            p.tick(100, render=False)
            if n('fixture_done', 1) or errors:
                break
        failures = {name: n(name+'_failures') for name in ('byte', 'guard', 'bank', 'register', 'irq')}
        grouped = {}
        for irq in (0, 1):
            for anchor in (1, 142, 151):
                values = [c['cycles'] for c in calls if c['lcd'] and c['irq'] == irq and c['anchor'] == anchor]
                grouped['irq%d_line%d' % (irq, anchor)] = {
                    'calls': len(values), 'min': min(values, default=0), 'max': max(values, default=0),
                    'mean': sum(values)/len(values) if values else 0}
        phases = {(c['entry_line'], c['entry_mode']) for c in calls if c['lcd']}
        report = {'source_sha256': source_sha, 'rom_sha256': hashlib.sha256(rom).hexdigest(),
                  'upload_code_bytes': len(code), 'upload_code_hex': code.hex(),
                  'done': n('fixture_done', 1), 'completed': n('fixture_completed'),
                  'failures': failures, 'hook_errors': errors[:8], 'calls': len(calls),
                  'cycles': grouped, 'launch_modes': dict(launches), 'dma_cycles': dict(durations),
                  'maximum_poll_cycles': max((c.get('poll_cycles', 0) for c in calls), default=0),
                  'completions_deferred_past_ei': deferred_completions,
                  'hardware_tested': False,
                  'emulator_gdma_stall_observed': any(t > 12 for t in durations),
                  'emulator_ly153_early_zero_observed': (0, 1) in phases,
                  'entry_line_modes': sorted(phases),
                  'timing_bound_tcycles': {'poll_period': 32, 'poll_and_launch': 44 if bounded else 76,
                                          'dma': 64, 'total': 108 if bounded else 140, 'minimum_mode2': 160}}
        (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
        (out/'calls.json').write_text(json.dumps(calls, indent=2)+'\n')
        assert report['done'] and report['completed'] == 6*PHASES+8, report
        assert not any(failures.values()) and not errors, report
        assert len(calls) == 6*PHASES+8 and sum(durations.values())+deferred_completions == len(calls)
        # This pinned PyBoy runtime does not charge the 64-T GDMA stall. A
        # runtime that models it is also accepted; the hardware proof above
        # always includes the full stall and never relies on this omission.
        assert set(durations) in ({12}, {76}), durations
        assert all(group['calls'] == PHASES for group in grouped.values())
        assert {(143, 0), (144, 1), (152, 1), (153, 1), (0, 2), (0, 3)} <= phases, phases
        for irq in (0, 1):
            for anchor in (1, 142, 151):
                selected = [c for c in calls if c['lcd'] and c['irq'] == irq and c['anchor'] == anchor]
                if not irq:
                    assert len({c['delay_cycles']-4*c['phase'] for c in selected}) == 1, 'native NOP sweep lost phase alignment'
        if bounded:
            assert max(c['cycles'] for c in calls) < 4000, report
            assert report['maximum_poll_cycles'] < 800, report
            assert 44+64 == report['timing_bound_tcycles']['total'] < 160
        assert source.read_bytes() == (out/'world_dma.c').read_bytes(), 'source changed during test'
        return report
    finally:
        p.stop(save=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=BASE/'src/world_dma.c')
    parser.add_argument('--baseline', type=Path, help='optional retained pre-fix source for comparison')
    parser.add_argument('--out', type=Path, default=BASE/'build/v091-dma-window')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    report = {'candidate': run(args.source.resolve(), args.out.resolve()/'candidate', True)}
    if args.baseline:
        report['baseline'] = run(args.baseline.resolve(), args.out.resolve()/'baseline', False)
        before = report['baseline']['cycles']
        after = report['candidate']['cycles']
        assert all(after[group]['mean'] < before[group]['mean'] for group in before)
    (args.out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
