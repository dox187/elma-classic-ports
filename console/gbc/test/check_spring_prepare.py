"""Verify spring deadlines, private writes and one-use consumption in a riding ROM."""
import argparse
from collections import Counter
from io import BytesIO
from pathlib import Path
import re

from pyboy import PyBoy

from spring_prepare_bound import bounds, guard_sites


FIELDS = {
    '_Bike':119, '_gbc_bike':52, '_angular_residual':4, '_move_residual':32,
    '_force_residual':16, '_riding_subphase':1, '_riding_audio_contact':2,
    '_riding_audio_impact':2, '_riding_landing_contact':2, '_riding_landing_nx':4,
    '_riding_landing_ny':4, '_q24_fraction':4, '_q24_saturated':1,
    '_riding_pose_anchor':16, '_riding_pose_trig':4, '_riding_pose_rest':4,
    '_riding_force_sums':18,
    '_game_state':1, '_game_apples_left':1, '_game_time_frames':4, '_game_steps':2,
    '_game_frames':2, '_game_level_index':1, '_game_object_active':64,
    '_game_camera_x':2, '_game_camera_y':2,
}
A,B,START,SELECT,LEFT,RIGHT,UP,DOWN=0x10,0x20,0x80,0x40,2,1,4,8
# The register returned by joypad receives each mask at the production sampling
# point. Record both ROMs there so overruns cannot repeat or drop a test input.
RIDE=([0,A,B,A|B,LEFT,A|LEFT,RIGHT,B|RIGHT,UP,0]*4)
SCRIPT=([A,0]+RIDE+[SELECT,0,0,SELECT,0]+RIDE[:16]+[START,0]+
        RIDE[:8]+[SELECT,0,DOWN,0,DOWN,0,A,0,DOWN,0,A,0]+RIDE[:30])
def symbols(rom):
    return {k:int(v,16) for k,v in re.findall(r'DEF (\w+) 0x(\w+)',rom.with_suffix('.noi').read_text())}


class Replay:
    def __init__(self,rom,prepare,stage_limit=None,wide=False,scalar=None):
        self.script=SCRIPT[:16] if wide else SCRIPT
        self.prepare=prepare
        self.wide=wide
        self.seeded=False
        self.sy=symbols(rom)
        image=bytearray(rom.read_bytes())
        # Match real joypad's ABI1 unsigned-char result in A.
        joy=self.sy['_joypad']
        image[joy:joy+3]=b'\x3e\x00\xc9'
        self.sites = guard_sites(rom,self.sy) if prepare else []
        if scalar:
            # Force the existing scalar dispatch for this scale in both
            # copies. Small inputs have the same exact coefficient table.
            index=image[self.sy[scalar]]
            bank=256+image[self.sy['_q24_first_bank_low']]+index//2
            image[bank*0x4000+(index%2)*0x2000+26*256+14]=1
        if prepare is False and not wide and '_physics_prepare_spring' in self.sy:
            s=self.sy['_physics_prepare_spring']
            image[(s>>16)*0x4000+(s&0x3fff)]=0xc9
        elif stage_limit is not None:
            # Return before the next guard with the producer's stack balanced.
            for site,_ in self.sites[stage_limit-1:]:
                image[(site>>16)*0x4000+(site&0x3fff)]=0xc9
        self.emu=PyBoy(BytesIO(image),window='null',cgb=True,sound_emulated=False)
        self.emu.set_emulation_speed(0)
        self.mem=self.emu.memory
        self.samples=[]
        self.takes=Counter()
        self.lifecycle=Counter()
        self.errors=[]
        self.phase_states=set()
        self.levels=set()
        self.producer=None
        self.produced=0
        self.declines=Counter()
        self.attempts=Counter()
        self.declined=None
        self.hook('_joypad',self.input)
        if prepare or wide:
            self.hook('_physics_prepare_spring',self.enter_prepare)
        if wide:
            self.hook('_riding_spring_geometry',self.seed_wide_geometry)
        if prepare:
            for stage,(site,_) in zip((0,*range(2,len(self.sites)+1)),self.sites):
                self.install(site+5, lambda _,s=stage:self.check_guard(s))
            self.hook('_riding_suspension_scheduled',self.consume)
            self.hook('_ph_turn',self.check_before_turn)
            self.hook('_ph_init',self.check_before_init)
        self.pending_revocation=False

    def hook(self,name,callback):
        self.install(self.sy[name],callback)

    def install(self,address,callback):
        def checked(ctx):
            if self.errors:return
            try:
                callback(ctx)
            except Exception as error:
                self.errors.append(error)
        self.emu.hook_register(address>>16,address&65535,checked,None)

    def state(self):
        return {k:bytes(self.mem[self.sy[k]:self.sy[k]+n]) for k,n in FIELDS.items()}

    def input(self,_):
        if not self.mem[self.sy['_game_ready']]:
            keys=START if self.mem[self.sy['_splash_active']] else 0
        else:
            index=len(self.samples)
            if index>=len(self.script):return
            self.samples.append(self.state())
            keys=self.script[index]
            state=self.mem[self.sy['_game_state']]
            self.phase_states.add(state)
            if state==0:self.levels.add(self.mem[self.sy['_game_level_index']])
            if state==3 and '_riding_spring_ready' in self.sy:
                assert self.mem[self.sy['_riding_spring_ready']]==0, 'pause retained a prefix'
        self.mem[0,self.sy['_joypad']+1]=keys

    def check_before_turn(self,_):
        self.lifecycle['turn']+=1
        self.pending_revocation=True

    def check_before_init(self,_):
        self.lifecycle['reset']+=1
        self.pending_revocation=True

    def consume(self,_):
        stage=self.mem[self.sy['_riding_spring_ready']]
        if self.pending_revocation:
            assert stage==0,'retained across turn or reset'
            self.pending_revocation=False
        assert not stage or not self.mem[self.sy['_riding_subphase']]
        self.takes[stage]+=1

    def guarded_state(self):
        sy=self.sy
        rows=sy['_riding_spring_product_rows']
        state=sy['_riding_suspension_state']
        return (bytes(self.mem[sy['_riding_spring_ready']:sy['_riding_spring_scratch_end']]),
                bytes(self.mem[rows:rows+56]),bytes(self.mem[state:state+52]))

    def check_guard(self,stage):
        assert self.producer is not None and self.declined is None
        assert self.mem[self.sy['_riding_spring_ready']]==stage
        if self.emu.register_file.F & 16:
            self.attempts[stage]+=1
        else:
            self.declines[stage]+=1
            self.declined=self.guarded_state()

    def publication(self):
        # Oms at +4..7 is the existing prepared geometry. All committed
        # wheel values, torques, body impulses and fractions stay private
        # to the consumer. Include IE and the actual mapped cartridge data.
        state=self.sy['_riding_suspension_state']
        return (self.state(),self.video(),bytes(self.mem[state:state+4]),
                bytes(self.mem[state+8:state+52]),self.mem[0xffff],
                self.mem[self.sy['__current_bank']],bytes(self.mem[0x4000:0x4040]))

    def enter_prepare(self,_):
        # Compare state at entry and at the banked call return before the
        # current frame can publish its completion or sample the next input.
        assert self.producer is None
        sp=self.emu.register_file.SP
        ret=self.mem[sp]+256*self.mem[sp+1]
        start=int.from_bytes(bytes(self.mem[sp+6:sp+8]),'little')
        self.producer=(sp,self.publication(),start)
        if not hasattr(self,'return_pc'):
            self.return_pc=ret
            self.install(ret,self.leave_prepare)
        assert ret==self.return_pc

    def seed_wide_geometry(self,_):
        # Both wide replays use the first admitted geometry block. A call
        # entering on a scanline transition may legitimately decline work.
        if self.producer is None or self.seeded:return
        omega=self.sy['_Bike']+20
        value=(0x03ffffff).to_bytes(4,'little')
        self.mem[omega:omega+4]=value
        before=self.producer[1][0]
        before['_Bike']=before['_Bike'][:20]+value+before['_Bike'][24:]
        self.seeded=True

    def video(self):
        # Banked VRAM and shadow OAM. The preceding scenery call has finished.
        return tuple(bytes(self.mem[bank,0x8000:0x9fff])+bytes([self.mem[bank,0x9fff]])
                     for bank in (0,1))+(bytes(self.mem[0xc000:0xc0a0]),)

    def leave_prepare(self,_):
        if self.producer is None or self.emu.register_file.SP!=self.producer[0]+2:return
        _,old,start=self.producer
        self.producer=None
        assert old==self.publication(),'published optional work'
        if self.declined is not None:
            assert self.declined==self.guarded_state(),'rejected guard changed spring scratch'
            self.declined=None
        ready=self.sy['_riding_spring_ready']
        if self.mem[ready]:
            self.produced+=1
            clock=self.sy['_sys_time']
            now=int.from_bytes(bytes(self.mem[clock:clock+2]),'little')+(self.mem[0xff0f]&1)
            assert ((now-start)&65535)<2,'producer crossed the scheduled input VBlank'
            bank=self.sy['_physics_prepare_spring']>>16
            assert self.mem[self.sy['__current_bank']]==bank
            assert self.mem[0x4000]==self.mem[bank,0x4000]

        if self.wide and not self.prepare:
            # Recompute on demand in the reference after the same injection.
            self.mem[ready]=0

    def run(self):
        try:
            for i in range(1400):
                self.emu.tick(1,False)
                if self.errors:raise self.errors[0]
                if len(self.samples)==len(self.script):break
            assert len(self.samples)==len(self.script)
            if not self.wide:
                assert self.phase_states>={0,3,4} and self.levels=={0,1}
            else:
                assert self.seeded
            return self.samples
        finally:
            self.emu.stop(save=False)


def guard_matrix(rom,sy,limits):
    """Run the linked guard with controlled LY, IF and sys_time samples."""
    image=bytearray(rom.read_bytes())
    bank=sy['_physics_prepare_spring']>>16
    sites=guard_sites(rom,sy)
    guard=sy['_riding_spring_budget']&65535
    thresholds=[lines for _,lines in sites]
    assert len(limits)==len(thresholds)
    assert all(cycles+2*912 <= lines*912 for cycles,lines in zip(limits,thresholds))
    start=bank*0x4000+(guard&0x3fff)
    # The three hardware samples become individually controllable HRAM bytes.
    # Leave all arithmetic, control flow and both sys_time loads intact.
    body=image[start:start+60]
    n1=body.index(b'\xf0\x44')+1
    ni=body.index(b'\xf0\x0f')+1
    n2=body.index(b'\xf0\x44',n1)+1
    image[start+n1],image[start+ni],image[start+n2]=0xf4,0xf5,0xf6
    code=sy['_riding_suspension_scheduled']&65535
    offset=bank*0x4000+(code&0x3fff)
    image[offset:offset+6]=bytes([0xcd,guard&255,guard>>8,0,0x18,0xfa])
    image[0x100:0x102]=b'\x18\xfe'
    emu=PyBoy(BytesIO(image),window='null',cgb=True,sound_emulated=False)
    try:
        emu.set_emulation_speed(0)
        emu.tick(160,False)
        mem=emu.memory
        mem[0xffff]=0
        mem[0x2000]=mem[sy['__current_bank']]=bank
        regs=emu.register_file
        regs.PC,regs.SP=code,0xdf80
        states=[(line,(line+change)%154,interrupt,epoch,age,lines)
                for line in range(154) for change in (-1,0,1,2) for interrupt in (0,1)
                for epoch in (0,0xffff) for age in (0,1,2,0xffff) for lines in thresholds]
        pos=0
        failures=[]
        def load(_):
            if pos==len(states):return
            ly,after,irq,epoch,age,lines=states[pos]
            mem[0xfff4:0xfff7]=bytes([ly,irq,after])
            mem[sy['_sys_time']:sy['_sys_time']+2]=((epoch+age)&65535).to_bytes(2,'little')
            regs.A,regs.D,regs.E=lines,epoch>>8,epoch&255
        def check(_):
            nonlocal pos
            if pos==len(states):return
            ly,after,irq,_,age,lines=states[pos]
            same_epoch = ly == after or ('ss_prepare_changed' in sy and ly+1 == after < 144)
            expected=(not irq and same_epoch and
                      (age==0 or age==1 and (after>=144 or 143-after>=lines)))
            if bool(regs.F&16)!=expected:failures.append(states[pos])
            pos+=1
        emu.hook_register(bank,code,load,None)
        emu.hook_register(bank,code+3,check,None)
        for _ in range(400):
            emu.tick(1,False)
            if pos==len(states):break
        assert pos==len(states) and not failures,(pos,failures[:1])
        return pos
    finally:
        emu.stop(save=False)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--rom',type=Path,required=True)
    ap.add_argument('--reference',type=Path)
    a=ap.parse_args()
    sy=symbols(a.rom)
    sites=guard_sites(a.rom,sy)
    # Count the entire suffix from RET NC through stage publication to the
    # next guard or return, including every call, branch and stack operation.
    labels=('geometry','wheel inputs','spring products','damper products')
    if len(sites)>=6:
        labels=('geometry','wheel velocities and symmetry','first moment','second moment','spring products','damper products')
    if len(sites)>=7:
        labels+=('angular damping moment',)
    if len(sites)==8:
        labels+=('base forces',)
    paths=bounds(a.rom,sy,{k:pc+5 for k,(pc,_) in zip(labels,sites)},
                 {pc for pc,_ in sites})
    print('Worst-case reachable SM83 T-cycles after each guard',paths)
    print(guard_matrix(a.rom,sy,list(paths.values())),'deadline guard cases passed')
    immediate=Replay(a.rom,False,wide=True).run()
    wide=Replay(a.rom,True,wide=True)
    assert immediate==wide.run() and wide.takes[1],wide.takes
    print('Wide angular velocity consumed the arms-only prefix')
    ref=Replay(a.reference,None).run() if a.reference else Replay(a.rom,False).run()
    for mode in (None,*range(2,len(sites)+1)):
        trial=Replay(a.rom,True,mode)
        output=trial.run()
        for i,(want,have) in enumerate(zip(ref,output)):
            for k in FIELDS: assert want[k]==have[k],(i,k,want[k].hex(),have[k].hex())
        assert trial.produced and trial.takes[mode or len(sites)+1],trial.takes
        assert trial.lifecycle['turn']>0 and trial.lifecycle['reset']>=3,trial.lifecycle
        print(len(output),'completed input samples matched, consumed stages',dict(trial.takes),
              'insufficient guard no-ops by retained stage',dict(trial.declines))
    for scalar,label in (('_q24_index_C_SPRING_FW','spring products'),('_q24_index_C_FRIC_W','damper products')):
        retained=labels.index(label)+1
        trial=Replay(a.rom,True,scalar=scalar)
        assert Replay(a.rom,False,scalar=scalar).run()==trial.run()
        assert trial.attempts[retained] and trial.takes[retained] and max(trial.takes)==retained
        print(scalar,trial.attempts[retained],'unsupported batches deferred to the consumer')


if __name__=='__main__':
    main()
