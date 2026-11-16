"""Real-ROM riding regression. Completion is earned through controller input.

The controller policy starts from a successful route through the existing
original-derived host physics, but only actual GBC state transitions count as
passing this test. No completion or object state is injected into guest memory.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys

from pyboy import PyBoy
import numpy as np

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'tools'))
from zx0 import decompress
RIDING, DEAD, FINISHED, PAUSED, MENU = range(5)


def signed_angle(value):
    return ((value + 32768) % 65536 - 32768) * (2 * math.pi / 65536)


def angle_delta(a, b):
    return (a - b + math.pi) % (2 * math.pi) - math.pi


class Driver:
    def __init__(self, rom, out, gen=None, sound=False):
        self.out = out
        self.out.mkdir(parents=True, exist_ok=True)
        rom_bytes = rom.read_bytes()
        assert rom_bytes[0x143] == 0xc0, 'ROM must be CGB only'
        assert rom_bytes[0x147] in (0x19,0x1a,0x1b), 'ROM must use the MBC5 cartridge header'
        if rom_bytes[0x147] in (0x1a,0x1b):
            assert rom_bytes[0x149] == 4, 'streamed cache requires128KiB cartridge scratch RAM'
        assert len(rom_bytes) == 32768 << rom_bytes[0x148], 'ROM bank count differs from file length'
        assert rom_bytes[0x14d] == (-sum(rom_bytes[0x134:0x14d])-25)&255, 'ROM header checksum'
        assert int.from_bytes(rom_bytes[0x14e:0x150],'big') == (
            sum(rom_bytes)-sum(rom_bytes[0x14e:0x150]))&65535, 'ROM global checksum'
        self.rom_sha256 = hashlib.sha256(rom_bytes).hexdigest()
        self.rom_bytes = rom_bytes
        self.symbols = {k:int(v,16) for k,v in re.findall(
            r'DEF (_\w+) 0x([0-9A-Fa-f]+)', rom.with_suffix('.noi').read_text())}
        self.gen = gen or BASE/'build/gen'
        self.level_manifest = (json.loads((self.gen/'level_manifest.json').read_text())
                               if (self.gen/'level_manifest.json').exists() else None)
        self.level_sources = {}
        def array(path):
            block = re.search(r'\[\] = \{(.*?)\};',path.read_text(),re.S)[1]
            return bytes(map(int,re.findall(r'\d+',block)))
        if self.level_manifest is None:
            self.world_size = json.loads((self.gen/'manifest.json').read_text())['size_px']
            self.patterns = array(self.gen/'patterns.c')
            self.chunks = {int(path.stem.split('_')[1]):array(path)
                           for path in self.gen.glob('world_*.c')}
            for name,data in [('world_patterns',self.patterns)]+[
                    ('world_%d'%bank,data) for bank,data in self.chunks.items()]:
                address = self.symbols['_'+name]
                bank,offset = address >> 16,address & 65535
                index = offset if bank == 0 else bank*16384+(offset&16383)
                assert rom_bytes[index:index+len(data)] == data, 'generated source differs from ROM: '+name
        self.viewport_checks = 0
        self.slot_mirror_checks = 0
        self.viewport_positions = set()
        self.viewport_chunks = set()
        self.last_viewport = None
        required = ['game_state','game_apples_left','game_ready','game_frames',
                    'game_steps','game_overruns','game_time_frames','gbc_bike']
        missing = [name for name in required if '_'+name not in self.symbols]
        if missing:
            raise AssertionError('Missing runtime symbols: '+', '.join(missing))
        self.p = PyBoy(str(rom), window='null', sound_emulated=sound, cgb=True)
        self.p.set_emulation_speed(0)
        self.physics_entries = 0
        self.observer_errors = []
        self.physics_entry_target = 0
        self.input_entries = 0
        self.input_entry_target = 0
        self.phase = None
        self.entry_trace = []
        entry = self.symbols.get('_physics_step')
        if entry is None:
            raise AssertionError('Missing physics_step symbol for input-boundary observation')
        self.p.hook_register(entry >> 16,entry & 65535,self._physics_entry,self)
        input_entry = self.symbols.get('_joypad')
        if input_entry is None:
            raise AssertionError('Missing joypad symbol for controller sampling observation')
        self.p.hook_register(input_entry >> 16,input_entry & 65535,self._input_entry,self)
        # Read the ROM constant from the file: the CGB boot ROM initially
        # overlays low cartridge addresses, including this symbol.
        if '_game_step_interval' in self.symbols:
            address = self.symbols['_game_step_interval']
            bank,offset = address >> 16,address & 65535
            index = offset if bank == 0 else bank*16384+(offset&16383)
            self.frame_interval = rom_bytes[index]
        else:
            self.frame_interval = 1
        if self.frame_interval not in (1,2):
            raise AssertionError('Unsupported display interval: %d'%self.frame_interval)
        if '_game_present_interval' in self.symbols:
            address = self.symbols['_game_present_interval']
            bank,offset = address >> 16,address & 65535
            index = offset if bank == 0 else bank*16384+(offset&16383)
            self.present_interval = rom_bytes[index]
        else:
            self.present_interval = self.frame_interval
        self.held = set()
        self.trace = []
        self.input_trace = []
        self.max_step_display_frames = 0
        self.max_loading_display_frames = 0
        self.max_axle_distance = 0.
        self.max_rider_distance = 0.
        self.start_frame = self.p.frame_count

    @staticmethod
    def _physics_entry(driver):
        # Observe the normal function entry; do not alter registers or state.
        # This lets a button pulse survive a previous slow solver call.
        driver.physics_entries += 1
        driver.physics_entry_target = (driver.word('game_steps')+1)&65535
        if driver.phase is not None:
            try:
                driver.visible_vram()
            except BaseException as error:
                driver.observer_errors.append(error)
            driver.entry_trace.append({'phase':driver.phase,'frame':driver.p.frame_count,
                                       'step':driver.word('game_steps')})

    @staticmethod
    def _input_entry(driver):
        driver.input_entries += 1
        driver.input_entry_target = (driver.word('game_frames')+1)&65535

    def byte(self, name):
        return self.p.memory[self.symbols['_'+name]]

    def word(self, name):
        a = self.symbols['_'+name]
        return self.p.memory[a] | self.p.memory[a+1] << 8

    def time_frames(self):
        a = self.symbols['_game_time_frames']
        return int.from_bytes(bytes(self.p.memory[a:a+4]),'little')

    def bike(self):
        a = self.symbols['_gbc_bike']
        raw = bytes(self.p.memory[a:a+52])
        poses = {}
        for i,name in enumerate(('body','wheel0','wheel1','rider','head')):
            x,y,angle = struct.unpack_from('<iiH',raw,i*10)
            poses[name] = {'x':x/65536,'y':y/65536,'angle':signed_angle(angle)}
        poses['alive'], poses['turned'] = raw[50],raw[51]
        return poses

    def buttons(self, keys):
        keys = set(keys)
        for key in self.held-keys:
            self.p.button_release(key)
        for key in keys-self.held:
            self.p.button_press(key)
        self.held = keys

    def tick(self, count=1, keys=()):
        self.buttons(keys)
        self.p.tick(count)
        if self.observer_errors:
            raise self.observer_errors[0]

    def ready(self):
        for _ in range(100):
            self.tick(5)
            splash=self.symbols.get('_splash_active')
            if splash is not None and self.p.memory[splash]:
                self.p.screen.image.save(self.out/'splash.png')
                self.tick(5,('start',));self.tick(5)
            if self.byte('game_ready'):
                self.last_viewport = None
                return
        raise AssertionError('Game did not become ready')

    def level_menu(self):
        if self.byte('game_state')not in(MENU,PAUSED):self.pulse('select')
        screen=self.symbols.get('_menu_screen')
        if screen is None:return
        if self.p.memory[screen]==2:self.pulse('b')
        if self.p.memory[screen]==0:
            target=2 if self.byte('game_state')==PAUSED else 1
            selected=self.symbols['_menu_selection']
            for _ in range(5):
                if self.p.memory[selected]==target:break
                self.pulse('down')
            assert self.p.memory[selected]==target,'Level Select is missing from main menu'
            self.pulse('a')
        assert self.p.memory[screen]==1,'course list did not open'

    def snapshot(self, name):
        record = {'name':name,'display_frame':self.p.frame_count,
                  'state':self.byte('game_state'), 'apples_left':self.byte('game_apples_left'),
                  'steps':self.word('game_steps'),'time':self.time_frames(),
                  'overruns':self.word('game_overruns'),'bike':self.bike()}
        self.trace.append(record)
        self.p.screen.image.save(self.out/(name+'.png'))
        return record

    def physical_bounds(self, bike):
        body = bike['body']
        distance = lambda p:math.hypot(p['x']-body['x'],p['y']-body['y'])
        axle = max(distance(bike['wheel0']),distance(bike['wheel1']))
        rider = distance(bike['rider'])
        self.max_axle_distance = max(self.max_axle_distance,axle)
        self.max_rider_distance = max(self.max_rider_distance,rider)
        # Deliberately generous: the original axle rest distance is ~1.04m
        # and the seat limits are much smaller than 3m. A flailing detached
        # wheel must never count as a successful pickup/finish route.
        assert axle < 3., 'unstable suspension: body-to-wheel distance %.3fm'%axle
        assert rider < 3., 'unstable rider: body-to-rider distance %.3fm'%rider

    def level_index(self):
        return self.byte('game_level_index') if '_game_level_index' in self.symbols else 0

    def rom_far(self, pointer, size):
        bank,address = pointer
        offset = bank*16384+(address&16383) if bank else address
        return self.rom_bytes[offset:offset+size]

    def rom_constant(self, name, default):
        address=self.symbols.get('_'+name)
        return default if address is None else self.rom_far((address>>16,address&65535),1)[0]

    def graphics_block(self, pointer, size):
        if not self.level_manifest.get('compression_key'):
            return self.rom_far(pointer,size)
        return decompress(self.rom_far(pointer,0x8000-pointer[1]),size)

    def level_source(self, index):
        if index not in self.level_sources:
            record = self.level_manifest['levels'][index]
            with np.load(self.gen/'levels'/('%02d'%(index+1))/'tiles.npz') as source:
                data = {name:source[name].copy() for name in source.files}
            data['patterns'] = bytes(data['patterns'])
            if 'pattern_blocks' in record:
                directory=self.rom_far(record['patterns'],len(record['pattern_blocks'])*4)
                assert list(struct.iter_unpack('<HH',directory))==[tuple(p)for p in record['pattern_blocks']]
                expected=data['patterns'];size=self.level_manifest['pattern_block_bytes']
                actual=b''.join(self.graphics_block(pointer,min(size,len(expected)-i*size))
                                for i,pointer in enumerate(record['pattern_blocks']))
            else:
                actual=self.rom_far(record['patterns'],len(data['patterns']))
            assert actual == data['patterns'], 'ROM pattern payload differs from generated level%d'%(index+1)
            ids,attrs = data['ids'],data['attrs']
            for cy in range(0,ids.shape[0],16):
                for cx in range(0,ids.shape[1],32):
                    values = ids[cy:cy+16,cx:cx+32].ravel()
                    expected = bytes((values&255).astype(np.uint8))+bytes((values>>8).astype(np.uint8))+bytes(attrs[cy:cy+16,cx:cx+32].ravel())
                    chunk = (cy//16)*(ids.shape[1]//32)+cx//32
                    assert self.graphics_block(record['chunks'][chunk],1536) == expected, 'ROM map payload differs from generated level%d chunk%d'%(index+1,chunk)
            data['record'] = record
            self.level_sources[index] = data
        return self.level_sources[index]

    def visible_vram(self, force=False):
        # Physics starts after the complete normal presentation upload. Reading
        # here avoids observing a half-written strip at a host frame boundary.
        camera_x,camera_y = self.word('game_camera_x'),self.word('game_camera_y')
        assert self.p.memory[0xff43] == camera_x&255, 'SCX differs from presented camera'
        assert self.p.memory[0xff42] == camera_y&255, 'SCY differs from presented camera'
        x,y = camera_x>>3,camera_y>>3
        index = self.level_index()
        key = (index,x,y)
        if key == self.last_viewport and not force:
            return
        if self.level_manifest is not None:
            source = self.level_source(index)
            ids,attrs,patterns = source['ids'],source['attrs'],source['patterns']
            self.world_size = source['record']['size_px']
            assert self.word('world_cache_failures') == 0, 'world pattern cache exhausted'
            for ty in range(y,y+19):
                for tx in range(x,x+21):
                    address = 0x9800+(ty&31)*32+(tx&31)
                    tile,attribute = self.p.memory[0,address],self.p.memory[1,address]
                    if tx >= ids.shape[1] or ty >= ids.shape[0]:
                        pattern,expected_attr = 0,0
                    else:
                        pattern,expected_attr = int(ids[ty,tx]),int(attrs[ty,tx])
                    assert attribute&247 == expected_attr, 'streamed viewport attributes differ: level%d (%d,%d)'%(index+1,tx,ty)
                    bank = 1 if attribute&8 else 0
                    physical = tile+256*bank
                    assert physical < 252 or 256 <= physical < 448, 'background overwrote reserved sprite patterns'
                    start = 0x8000+tile*16
                    assert bytes(self.p.memory[bank,start:start+16]) == patterns[pattern*16:pattern*16+16], 'streamed viewport pattern differs: level%d (%d,%d) id%d'%(index+1,tx,ty,pattern)
                    address = 0xa000+(pattern&4095)*2
                    cached = self.p.memory[pattern>>12,address] | self.p.memory[pattern>>12,address+1]<<8
                    assert cached == (physical if physical<252 else physical-4), 'SRAM lookup disagrees with visible cache slot'
                    if '_world_slot_strip_get' in self.symbols:
                        address=0xa000+2*((ty&31)*32+(tx&31))
                        mirrored=self.p.memory[8,address]|self.p.memory[8,address+1]<<8
                        assert mirrored==cached,'SRAM slot mirror disagrees with displayed viewport'
                        self.slot_mirror_checks+=1
                    if tx < ids.shape[1] and ty < ids.shape[0]:
                        self.viewport_chunks.add((index,(ty//16)*(ids.shape[1]//32)+tx//32))
            self.viewport_checks += 1
            self.viewport_positions.add(key)
            self.last_viewport = key
            return
        width,height = (n//8 for n in self.world_size)
        seen_patterns = set()
        for ty in range(y,y+19):
            for tx in range(x,x+21):
                address = 0x9800+(ty&31)*32+(tx&31)
                actual = (self.p.memory[0,address],self.p.memory[1,address])
                if tx >= width or ty >= height:
                    expected = (0,0)
                else:
                    chunk = (ty//16)*((width+31)//32)+tx//32+2
                    self.viewport_chunks.add(chunk)
                    blob = self.chunks[chunk]
                    local = (ty&15)*32+(tx&31)
                    expected = (blob[local],blob[512+local])
                assert actual == expected, 'viewport map mismatch at (%d,%d): %r != %r'%(tx,ty,actual,expected)
                tile,attribute = actual
                bank = 1 if attribute&8 else 0
                pattern = tile+256*bank
                if pattern not in seen_patterns:
                    start = 0x8000+tile*16
                    assert bytes(self.p.memory[bank,start:start+16]) == self.patterns[pattern*16:pattern*16+16], 'viewport pattern mismatch: %d'%pattern
                    seen_patterns.add(pattern)
        self.viewport_checks += 1
        self.viewport_positions.add((x,y))
        self.last_viewport = key

    def step(self, keys=()):
        before_step = self.word('game_steps')
        before_overruns = self.word('game_overruns')
        entry = self.input_entries
        elapsed = 0
        target = None
        for _ in range(30):
            self.tick(1,keys)
            elapsed += 1
            if target is None and self.input_entries != entry:
                target = self.input_entry_target
            if (target is not None and ((self.word('game_frames')-target)&65535)<32768) or self.byte('game_state') != RIDING:
                break
        else:
            raise AssertionError('No input-consuming game update in thirty display frames')
        self.max_step_display_frames = max(self.max_step_display_frames,elapsed)
        bike = self.bike()
        self.physical_bounds(bike)
        self.input_trace.append({'phase':self.phase,'keys':sorted(keys),
            'before_step':before_step,'after_step':self.word('game_steps'),
            'overruns_before':before_overruns,'overruns_after':self.word('game_overruns'),
            'body':bike['body']})
        return bike

    def pulse(self, key):
        # Hold across two completed game loops: a slow diagnostic solver may
        # still be computing the preceding input when the host frame ends.
        for keys in ((key,),()):
            before = self.word('game_frames')
            active_frames = loading_frames = 0
            for _ in range(600):
                self.tick(1,keys)
                if self.byte('game_ready'):
                    active_frames += 1
                else:
                    loading_frames += 1
                assert active_frames < 60, 'No completed active game loop while pulsing '+key
                if ((self.word('game_frames')-before)&65535) >= 2:
                    break
            else:
                raise AssertionError('Level load exceeded ten seconds while pulsing '+key)
            self.max_loading_display_frames=max(self.max_loading_display_frames,loading_frames)

    def advance_physics(self, count, keys=()):
        before = self.word('game_steps')
        while ((self.word('game_steps')-before)&65535) < count:
            if self.byte('game_state') != RIDING:
                break
            self.step(keys)

    def restart(self):
        self.phase = None
        self.pulse('start')
        self.ready()
        assert self.byte('game_state') == RIDING, 'Start did not restart riding'
        assert self.byte('game_apples_left') == 1, 'Warm Up apple was not restored'
        assert self.time_frames() <= 16, 'restart did not reset the race timer'
        pose = self.bike()
        assert pose['alive'] == 1
        assert abs(pose['body']['x'] - (-3.235006730917425+.85)) < .15, 'restart spawn x'
        assert abs(pose['body']['y'] - (.3235286563126514+.6)) < .2, 'restart spawn y'

    def smoke(self):
        self.ready()
        self.restart()
        self.snapshot('spawn')
        turned = self.bike()['turned']
        self.pulse('up')
        assert self.bike()['turned'] != turned, 'Up did not turn the bike'
        self.pulse('up')
        assert self.bike()['turned'] == turned, 'second Up did not restore direction'

        self.pulse('select')
        assert self.byte('game_state') == PAUSED, 'Select did not pause'
        before = (self.word('game_steps'), self.time_frames(), self.bike())
        self.tick(60)
        after = (self.word('game_steps'), self.time_frames(), self.bike())
        assert before == after, 'paused physics/time changed'
        self.snapshot('paused')
        self.pulse('select')
        assert self.byte('game_state') == RIDING, 'Select did not resume'

        self.restart()
        initial = self.bike()['body']
        self.phase = 'gas'
        self.advance_physics(100,('a',))
        driven = self.snapshot('gas')
        assert abs(driven['bike']['body']['x']-initial['x']) > .5, 'gas did not move the bike'
        assert driven['state'] == RIDING, 'bike died during initial gas test'
        assert driven['bike']['body']['y'] > -.5, 'bike fell through Warm Up ground'
        # Brake on the gentle slope near spawn, before an unbalanced rider
        # reaches the hill. Compare equal time windows of actual movement.
        self.restart()
        self.pulse('up')
        self.advance_physics(30//self.frame_interval,('a',))
        x0 = self.bike()['body']['x']
        self.advance_physics(10//self.frame_interval,('a',))
        gas_distance = self.bike()['body']['x']-x0
        assert gas_distance > .1, 'brake fixture did not establish forward speed'
        self.phase = 'brake'
        self.advance_physics(50//self.frame_interval,('b',))
        x0 = self.bike()['body']['x']
        self.advance_physics(10//self.frame_interval,('b',))
        brake_distance = self.bike()['body']['x']-x0
        assert self.byte('game_state') == RIDING, 'bike died during controlled braking'
        assert brake_distance < gas_distance*.6, 'brake did not reduce movement: %.3fm versus %.3fm'%(brake_distance,gas_distance)
        braking = self.snapshot('brake')
        braking['forward_movement_m'] = {'gas_window':gas_distance,'brake_window':brake_distance}

        self.restart()
        initial = self.bike()['body']['angle']
        self.phase = 'rotation'
        self.step(('right',))
        self.advance_physics(15)
        assert abs(angle_delta(self.bike()['body']['angle'],initial)) > .05, 'rotation input had no effect'
        self.snapshot('rotation')

        self.restart()
        self.phase = 'death'
        # Gas in the default left-facing direction eventually drops the rider's
        # head into the ground without balancing. This exercises actual death.
        for _ in range(900):
            self.step(('a',))
            if self.byte('game_state') == DEAD:
                break
        assert self.byte('game_state') == DEAD, 'unbalanced run never reached head-collision death'
        assert self.bike()['alive'] == 0
        self.tick(4)
        self.snapshot('death')
        self.restart()
        self.snapshot('restart-after-death')

    def complete_warmup(self, args):
        self.restart()
        self.pulse('up')
        assert self.bike()['turned'], 'test route expects right-facing after initial turn'
        last_volt = -10000
        apple_step = None
        apple_visible = flower_visible = False
        returned = False
        last_angle = self.bike()['body']['angle']
        base_step = self.word('game_steps')
        previous_step = base_step
        hz = 59.727500569606
        physical_dt = .4368*self.frame_interval/hz
        cooldown = args.cooldown if args.cooldown is not None else math.ceil(.4/physical_dt)
        self.phase = 'route'
        for n in range(args.max_steps):
            if self.byte('game_state') != RIDING:
                break
            pose = self.bike()
            if apple_step is None and not apple_visible and pose['body']['x'] > 13.:
                self.snapshot('approaching-red-apple')
                apple_visible = True
            if apple_step is not None and not flower_visible and pose['body']['x'] < -7.:
                self.snapshot('approaching-white-flower')
                flower_visible = True
            angle = pose['body']['angle']
            current_step = self.word('game_steps')
            clock_step = (current_step-base_step)&65535
            omega = angle_delta(angle,last_angle)/(physical_dt*max(1,(current_step-previous_step)&65535))
            last_angle = angle
            previous_step = current_step
            keys = {'a'}
            if apple_step is not None and clock_step-apple_step <= args.return_brake:
                keys = {'b'}
            if apple_step is not None and not returned and clock_step-apple_step >= args.turn_delay:
                keys.add('up')
                returned = True
            threshold = args.outbound_threshold if apple_step is None else args.return_threshold
            score = angle + (args.outbound_lead if apple_step is None else args.lead)*omega
            if clock_step-last_volt >= cooldown:
                if score > threshold:
                    keys.add('right')
                    last_volt = clock_step
                elif score < -threshold:
                    keys.add('left')
                    last_volt = clock_step
            self.step(keys)
            if n % 60 == 0:
                self.snapshot('route-%04d'%n)
            if apple_step is None and self.byte('game_apples_left') == 0:
                apple_step = (self.word('game_steps')-base_step)&65535
                self.snapshot('apple-collected')
        self.buttons(())
        if self.byte('game_state') == FINISHED:
            self.tick(4)
        final = self.snapshot('route-final')
        assert apple_step is not None, 'route did not collect the apple'
        assert final['state'] == FINISHED, 'route did not reach the unlocked flower alive'
        assert final['bike']['alive'] == 1
        return {'apple_step':apple_step,'finished_step':(self.word('game_steps')-base_step)&65535,'controller':{
            'outbound_threshold':args.outbound_threshold,'return_threshold':args.return_threshold,
            'outbound_lead':args.outbound_lead,
            'lead':args.lead,'cooldown':cooldown,'turn_delay':args.turn_delay,
            'return_brake':args.return_brake}}

    def close(self):
        self.buttons(())
        (self.out/'trace.json').write_text(json.dumps(self.trace,indent=2)+'\n')
        (self.out/'entry-trace.json').write_text(json.dumps(self.entry_trace,indent=2)+'\n')
        (self.out/'input-trace.json').write_text(json.dumps(self.input_trace,indent=2)+'\n')
        self.p.stop(save=False)
        # Profilers may finish with raw PyBoy ticks. Their final callbacks must
        # still fail the run, while preserving an exception already unwinding.
        if self.observer_errors and sys.exc_info()[0]is None:
            raise self.observer_errors[0]

    def timing(self):
        intervals = [b['frame']-a['frame'] for a,b in zip(self.entry_trace,self.entry_trace[1:])
                     if a['phase']==b['phase']]
        return {'target_display_frames_per_physics_step':self.frame_interval,
                'target_display_frames_per_present':self.present_interval,
                'observed_entry_spacing_frames':{'min':min(intervals) if intervals else None,
                                                 'max':max(intervals) if intervals else None,
                                                 'histogram':dict(sorted(Counter(intervals).items()))},
                'max_display_frames_per_input_consuming_step':self.max_step_display_frames,
                'max_loading_display_frames':self.max_loading_display_frames,
                'max_body_wheel_distance_m':self.max_axle_distance,
                'max_body_rider_distance_m':self.max_rider_distance,
                'rom_header_and_checksums_verified':True,
                'viewport_source':str(self.gen.resolve()),
                'viewport_checks':self.viewport_checks,
                'slot_mirror_checks':self.slot_mirror_checks,
                'observer_errors':[str(error)for error in self.observer_errors],
                'viewport_tile_positions':sorted(self.viewport_positions),
                'viewport_chunks':sorted(self.viewport_chunks)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom',type=Path,default=BASE/'build/elma-gbc.gbc')
    p.add_argument('--out',type=Path,default=BASE/'build/playtest')
    p.add_argument('--gen',type=Path,default=BASE/'build/gen',help='generated source maps compiled into this ROM')
    p.add_argument('--smoke',action='store_true',help='run controls/death checks only; does not claim completion')
    p.add_argument('--route-only',action='store_true')
    p.add_argument('--max-steps',type=int,default=4000)
    p.add_argument('--max-overruns',type=int,default=0)
    p.add_argument('--outbound-threshold',type=float,default=.3)
    p.add_argument('--outbound-lead',type=float,default=0.)
    p.add_argument('--return-threshold',type=float,default=0.)
    p.add_argument('--lead',type=float,default=0.)
    p.add_argument('--turn-delay',type=int,default=50)
    p.add_argument('--return-brake',type=int,default=10)
    p.add_argument('--cooldown',type=int,default=None,help='default derives original 0.4-s volt wait from ROM update rate')
    a = p.parse_args()
    d = Driver(a.rom,a.out,a.gen)
    report_path = a.out/'run.json'
    report_path.write_text(json.dumps({'status':'running','real_rom':str(a.rom.resolve())})+'\n')
    route = None
    functional_checks_passed = False
    try:
        if not a.route_only:
            d.smoke()
        else:
            d.ready()
        route = None if a.smoke else d.complete_warmup(a)
        functional_checks_passed = True
        overruns = d.word('game_overruns')
        assert overruns <= a.max_overruns, 'display deadline misses: %d'%overruns
        result = {'status':'passed','real_rom':str(a.rom.resolve()),'smoke_only':a.smoke,
                  'rom_sha256':d.rom_sha256,
                  'route':route,'display_overruns':overruns,
                  'functional_checks_passed':True,
                  'performance_requirement_met':overruns==0,
                  'deadline_budget_relaxed_for_diagnostics':a.max_overruns!=0,
                  **d.timing(),
                  'hardware_tested':False}
        report_path.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))
    except BaseException as error:
        d.snapshot('failure')
        report_path.write_text(json.dumps({'status':'failed','error':str(error),
            'real_rom':str(a.rom.resolve()),'display_frame':d.p.frame_count,
            'rom_sha256':d.rom_sha256,
            'route':route,
            'functional_checks_passed':functional_checks_passed,
            'state':d.byte('game_state'),'apples_left':d.byte('game_apples_left'),
            'bike':d.bike(),
            'overruns':d.word('game_overruns'),**d.timing(),
            'hardware_tested':False},indent=2)+'\n')
        raise
    finally:
        d.close()


if __name__=='__main__':
    main()
