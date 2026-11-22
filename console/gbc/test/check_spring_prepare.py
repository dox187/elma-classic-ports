"""Verify spring deadlines, private writes and one-use consumption in a riding ROM."""
import argparse
from collections import Counter
from io import BytesIO
from pathlib import Path
import re

from pyboy import PyBoy

from spring_prepare_bound import bounds


FIELDS = {
    '_Bike':119, '_gbc_bike':52, '_angular_residual':4, '_move_residual':32,
    '_force_residual':16, '_riding_subphase':1, '_riding_audio_contact':2,
    '_riding_audio_impact':2, '_riding_landing_contact':2, '_riding_landing_nx':4,
    '_riding_landing_ny':4, '_q24_fraction':4, '_riding_pose_anchor':16,
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
    def __init__(self,rom,prepare,stage_limit=None,wide=False):
        self.script=SCRIPT[:7] if wide else SCRIPT
        self.wide=wide
        self.seeded=False
        self.sy=symbols(rom)
        image=bytearray(rom.read_bytes())
        # Match real joypad's ABI1 unsigned-char result in A.
        joy=self.sy['_joypad']
        image[joy:joy+3]=b'\x3e\x00\xc9'
        if not prepare and '_physics_prepare_spring' in self.sy:
            s=self.sy['_physics_prepare_spring']
            image[(s>>16)*0x4000+(s&0x3fff)]=0xc9
        elif stage_limit==2:
            # Return immediately before the second block would start. Its
            # unconsumed spin products still form the legitimate stage-2 state.
            s=self.sy['_physics_prepare_spring']
            offset=(s>>16)*0x4000+(s&0x3fff)
            call=b'\xcd'+(self.sy['_riding_spring_inputs']&65535).to_bytes(2,'little')
            location=image.index(call,offset,offset+64)
            image[location]=0xc9
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
        self.hook('_joypad',self.input)
        if prepare or wide:
            self.hook('_physics_prepare_spring',self.enter_prepare)
        if prepare:
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

    def enter_prepare(self,_):
        # Compare state at entry and at the banked call return before the
        # current frame can publish its completion or sample the next input.
        assert self.producer is None
        if self.wide and not self.seeded:
            omega=self.sy['_Bike']+20
            self.mem[omega:omega+4]=(0x03ffffff).to_bytes(4,'little')
            self.seeded=True
        sp=self.emu.register_file.SP
        ret=self.mem[sp]+256*self.mem[sp+1]
        start=int.from_bytes(bytes(self.mem[sp+6:sp+8]),'little')
        self.producer=(sp,self.state(),self.video(),start)
        if not hasattr(self,'return_pc'):
            self.return_pc=ret
            self.install(ret,self.leave_prepare)
        assert ret==self.return_pc

    def video(self):
        # Banked VRAM and shadow OAM. The preceding scenery call has finished.
        return tuple(bytes(self.mem[bank,0x8000:0x9fff])+bytes([self.mem[bank,0x9fff]])
                     for bank in (0,1))+(bytes(self.mem[0xc000:0xc0a0]),)

    def leave_prepare(self,_):
        if self.producer is None or self.emu.register_file.SP!=self.producer[0]+2:return
        _,old,video,start=self.producer
        self.producer=None
        assert old==self.state() and video==self.video(),'published optional work'
        ready=self.sy['_riding_spring_ready']
        if self.mem[ready]:
            self.produced+=1
            clock=self.sy['_sys_time']
            now=int.from_bytes(bytes(self.mem[clock:clock+2]),'little')+(self.mem[0xff0f]&1)
            assert ((now-start)&65535)<2,'producer crossed the scheduled input VBlank'
            bank=self.sy['_physics_prepare_spring']>>16
            assert self.mem[self.sy['__current_bank']]==bank
            assert self.mem[0x4000]==self.mem[bank,0x4000]

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
    entry=sy['_physics_prepare_spring']&65535
    offset=bank*0x4000+(entry&0x3fff)
    calls=[(int.from_bytes(operand,'little'),lines[0]) for lines,operand in
           re.findall(b'\x3e(.)\xcd(..)',image[offset:offset+60],re.S)]
    (guard,first),(other,second)=calls[:2]
    assert guard==other and len(limits)==2
    assert all(cycles+2*912 <= lines*912 for cycles,lines in zip(limits,(first,second)))
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
                for line in range(154) for change in (0,1) for interrupt in (0,1)
                for epoch in (0,0xffff) for age in (0,1,2,0xffff) for lines in (first,second)]
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
            expected=(not irq and ly==after and
                      (age==0 or age==1 and (ly>=144 or 143-ly>=lines)))
            if bool(regs.F&16)!=expected:failures.append(states[pos])
            pos+=1
        emu.hook_register(bank,code,load,None)
        emu.hook_register(bank,code+3,check,None)
        for _ in range(200):
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
    paths=bounds(a.rom,sy,{k:sy[k] for k in ('_riding_spring_geometry','_riding_spring_inputs')})
    print('Worst-case reachable SM83 T-cycles',paths)
    print(guard_matrix(a.rom,sy,list(paths.values())),'deadline guard cases passed')
    immediate=Replay(a.rom,False,wide=True).run()
    wide=Replay(a.rom,True,wide=True)
    assert immediate==wide.run() and wide.takes[1],wide.takes
    print('Wide angular velocity consumed the arms-only prefix')
    ref=Replay(a.reference or a.rom,False).run()
    for mode in (None,2):
        trial=Replay(a.rom,True,mode)
        output=trial.run()
        for i,(want,have) in enumerate(zip(ref,output)):
            for k in FIELDS: assert want[k]==have[k],(i,k,want[k].hex(),have[k].hex())
        assert trial.produced and trial.takes[mode or 3],trial.takes
        assert trial.lifecycle['turn']>0 and trial.lifecycle['reset']>=3,trial.lifecycle
        print(len(output),'completed input samples matched, consumed stages',dict(trial.takes))


if __name__=='__main__':
    main()
