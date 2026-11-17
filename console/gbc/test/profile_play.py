"""Observe real-ROM presentation/physics costs without injecting guest state.

Controller input follows a balanced Warm Up drive. Hooks observe normal call
entries and their actual stack return addresses, including banked trampolines.
An input-to-vsync interval measures all active loop work, excluding idle wait.
"""
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
import re

from play import Driver, RIDING

BASE=Path(__file__).resolve().parents[1]
DISPLAY_CYCLES=140448


def statistics(values):
    return {'calls':len(values),'min_cycles':min(values) if values else None,
            'mean_cycles':sum(values)/len(values) if values else None,
            'max_cycles':max(values) if values else None}


class Profiler:
    def __init__(self,driver,listing=None):
        self.d=driver
        self.p=driver.p
        self.symbols=driver.symbols.copy()
        if listing:
            local={name:int(address,16) for address,name in re.findall(
                r'^\s+([0-9A-Fa-f]{8})\s+\d+\s+(_\w+)::?$',listing.read_text(),re.M)}
            # An isolated -Wa-l compilation retains static function offsets.
            # Resolve its CODE area against the exported function in this ROM.
            base=self.symbols['_game_present']-local['_game_present']
            for name in ('_load_strip','_update_view','_pixels','_position_camera',
                         '_bike_screen','_draw_objects','_touching','_check_objects',
                         '_bike_bounded','_clock_tick','_hud_text','_draw_hud'):
                if name in local:self.symbols[name]=base+local[name]
                elif name=='_pixels':self.symbols[name]=self.symbols['_gbc_video_pixels']
                elif name=='_bike_bounded':self.symbols[name]=self.symbols['_gbc_bike_bounded']
            # Reject a stale listing before observing arbitrary ROM addresses.
            encoded={int(address,16):bytes.fromhex(prefix) for address,prefix in re.findall(
                r'^\s+([0-9A-Fa-f]{8}) ((?:[0-9A-Fa-f]{2} ?)+)',listing.read_text(),re.M)}
            rom=self.d.p.memory
            for name in local.keys() & self.symbols.keys():
                if name not in ('_game_present',) and name not in (
                        '_load_strip','_update_view','_pixels','_position_camera',
                        '_bike_screen','_draw_objects','_touching','_check_objects',
                        '_bike_bounded','_clock_tick','_hud_text','_draw_hud'):continue
                prefix=encoded.get(local[name],b'')
                if prefix and bytes(rom[self.symbols[name]:self.symbols[name]+len(prefix)])!=prefix:
                    raise AssertionError('Stale listing entry bytes: '+name)
        self.stack=[]
        self.returns=set()
        self.records=[]
        self.work=[]
        self.active=None
        self.unclosed_work=0
        self.physics_count=0
        for name in ('_game_present','_bike_render_draw','_set_bkg_tiles','_set_win_tiles',
                     '_load_strip','_update_view','_pixels','_position_camera',
                     '_bike_screen','_draw_objects','_touching','_check_objects',
                     '_bike_bounded','_clock_tick','_hud_text','_draw_hud'):
            if name in self.symbols:
                address=self.symbols[name]
                self.p.hook_register(address>>16,address&65535,self._entry,(self,name))
        # Preserve the existing controller/physics boundary observer callbacks.
        for name,callback in (('_physics_step',self._physics_entry),('_joypad',self._input_entry)):
            address=self.symbols[name]
            self.p.hook_deregister(address>>16,address&65535)
            self.p.hook_register(address>>16,address&65535,callback,self)
        address=self.symbols['_vsync']
        self.p.hook_register(address>>16,address&65535,self._vsync_entry,self)
        # The conditional first-frame wait begins at the same idle boundary
        # as the original inner vsync; include its wait-free fast return too.
        if '_game_wait_first_frame' in self.symbols:
            address=self.symbols['_game_wait_first_frame']
            self.p.hook_register(address>>16,address&65535,self._vsync_entry,self)

    @staticmethod
    def _entry(context):
        profiler,name=context
        profiler.enter(name)

    @staticmethod
    def _physics_entry(profiler):
        Driver._physics_entry(profiler.d)
        profiler.physics_count+=1
        profiler.enter('_physics_step')

    @staticmethod
    def _input_entry(profiler):
        Driver._input_entry(profiler.d)
        if profiler.active is not None:
            profiler.unclosed_work+=1
        profiler.active={'start':profiler.p._cycles(),'phase':profiler.d.phase,
                         'state':profiler.d.byte('game_state'),'frame':profiler.p.frame_count,
                         'steps':profiler.d.word('game_steps'),
                         'overruns_before':profiler.d.word('game_overruns')}

    @staticmethod
    def _vsync_entry(profiler):
        if profiler.active is not None:
            entry=profiler.active
            entry['start_cycle']=entry.pop('start')
            entry['end_cycle']=profiler.p._cycles()
            entry['cycles']=entry['end_cycle']-entry['start_cycle']
            entry['steps_after']=profiler.d.word('game_steps')
            entry['overruns_after']=profiler.d.word('game_overruns')
            profiler.work.append(entry)
            profiler.active=None

    @staticmethod
    def _return(context):
        profiler,key=context
        # A shared callsite may be used by multiple observed functions. Only
        # unwind the active record whose return stack depth actually matches.
        while profiler.stack:
            top=profiler.stack[-1]
            cleanup=(profiler.p.register_file.SP-top['return_sp'])&65535
            # SDCC ABI1 callees may also remove up to three stack arguments
            # before jumping to their saved return PC. Their frame is gone
            # once SP reaches or passes its pre-call depth by those bytes.
            if top['return']!=key or cleanup not in (0,2,4,6):
                break
            profiler.stack.pop()
            top['start_cycle']=top.pop('start')
            top['end_cycle']=profiler.p._cycles()
            cycles=top['end_cycle']-top['start_cycle']
            top['cycles']=cycles
            top['exclusive_cycles']=cycles-top.pop('children')
            top.pop('return');top.pop('return_sp')
            profiler.records.append(top)
            if profiler.stack:profiler.stack[-1]['children']+=cycles

    def enter(self,name):
        sp=self.p.register_file.SP
        pc=self.p.memory[sp]+256*self.p.memory[sp+1]
        bank=0 if pc<0x4000 else self.p.memory[self.symbols['__current_bank']]
        key=(bank,pc)
        if key not in self.returns:
            self.p.hook_register(bank,pc,self._return,(self,key))
            self.returns.add(key)
        self.stack.append({'name':name,'start':self.p._cycles(),'children':0,
                           'return':key,'return_sp':(sp+2)&65535,
                           'phase':self.d.phase,'frame':self.p.frame_count,
                           'step':self.d.word('game_steps')})

    def report(self):
        grouped=collections.defaultdict(list)
        exclusive=collections.defaultdict(list)
        for record in self.records:
            if record['phase'] in ('driving','route'):
                grouped[record['name']].append(record['cycles'])
                exclusive[record['name']].append(record['exclusive_cycles'])
        active=[r for r in self.work if r['phase'] in ('driving','route') and r['state']==RIDING]
        budget=DISPLAY_CYCLES*self.d.present_interval
        worst=[]
        for update in sorted(active,key=lambda x:x['cycles'],reverse=True)[:10]:
            costs=collections.Counter()
            counts=collections.Counter()
            for record in self.records:
                if (record['start_cycle']>=update['start_cycle'] and
                        record['end_cycle']<=update['end_cycle']):
                    costs[record['name']]+=record['cycles']
                    counts[record['name']]+=1
            worst.append({'cycles':update['cycles'],'frame':update['frame'],'step':update['steps'],
                          'function_cycles':dict(costs),'function_calls':dict(counts),
                          'other_loop_cycles':update['cycles']-costs['_game_present']-costs['_physics_step']})
        return {'functions':{name:{'inclusive':statistics(values),
                                  'exclusive':statistics(exclusive[name])}
                             for name,values in grouped.items()},
                'whole_active_update':statistics([r['cycles']for r in active]),
                'update_budget_cycles':budget,
                'updates_exceeding_budget':sum(r['cycles']>budget for r in active),
                'worst_active_updates':worst,
                'display_cycles':DISPLAY_CYCLES,
                'game_overruns':self.d.word('game_overruns'),
                'unfinished_observed_calls':len(self.stack),
                'unfinished_call_names':dict(collections.Counter(r['name'] for r in self.stack)),
                'unclosed_active_updates':self.unclosed_work,
                'physics_entries':self.physics_count}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom',type=Path,default=BASE/'build/elma-gbc-30-profile.gbc')
    parser.add_argument('--gen',type=Path,default=BASE/'build/gen')
    parser.add_argument('--out',type=Path,default=BASE/'build/play-profile')
    parser.add_argument('--steps',type=int,default=300)
    parser.add_argument('--listing',type=Path,help='isolated play.lst compiled from this ROM source/flags')
    args=parser.parse_args()
    d=Driver(args.rom,args.out,args.gen)
    profiler=None
    try:
        d.ready()
        profiler=Profiler(d,args.listing)
        d.phase='restart';d.restart();d.pulse('up')
        previous_step=d.word('game_steps')
        previous_angle=d.bike()['body']['angle']
        last_volt=-10000
        for n in range(args.steps*5):
            if profiler.physics_count>=args.steps:break
            if d.byte('game_state')!=RIDING:
                d.phase='restart';d.restart();d.pulse('up')
                previous_step=d.word('game_steps')
                previous_angle=d.bike()['body']['angle']
                last_volt=-10000
            d.phase='driving'
            pose=d.bike();angle=pose['body']['angle']
            step=d.word('game_steps')
            count=max(1,(step-previous_step)&65535)
            dt=.4368*d.frame_interval/59.727500569606
            omega=((angle-previous_angle+math.pi)%(2*math.pi)-math.pi)/(dt*count)
            previous_angle,previous_step=angle,step
            keys={'a'}
            cooldown=math.ceil(.4/dt)
            if step-last_volt>=cooldown:
                score=angle+.05*omega
                if score>.1:keys.add('right');last_volt=step
                elif score<-.1:keys.add('left');last_volt=step
            d.step(keys)
        else:
            raise AssertionError('did not observe requested physics steps')
        # Finish the currently observed update through its normal next vsync.
        d.buttons(())
        for _ in range(10):
            d.p.tick(1)
            if profiler.active is None and not profiler.stack:break
        report=profiler.report()
        report.update(rom=str(args.rom.resolve()),rom_sha256=hashlib.sha256(args.rom.read_bytes()).hexdigest(),
                      physics_interval=d.frame_interval,present_interval=d.present_interval,
                      source='controller-only real ROM; entry/return hooks; no guest-state injection')
        (args.out/'profile.json').write_text(json.dumps(report,indent=2)+'\n')
        (args.out/'calls.json').write_text(json.dumps(profiler.records,indent=2)+'\n')
        (args.out/'active-updates.json').write_text(json.dumps(profiler.work,indent=2)+'\n')
        d.snapshot('profile-final')
        print(json.dumps(report,indent=2))
    finally:
        d.close()


if __name__=='__main__':main()
