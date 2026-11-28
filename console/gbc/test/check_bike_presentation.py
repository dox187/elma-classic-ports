"""Compare visible bike, object and HUD art at matching controller-driven updates."""

import argparse
from collections import Counter
from pathlib import Path
import re

from benchmark_gameplay import controller_plan
from play import BASE, Driver, RIDING


def check_body_plans(rom, gen):
    from bike_frames16 import read_array

    symbols = dict(re.findall(r'^DEF (\w+) 0x([0-9A-Fa-f]+)$',
                              rom.with_suffix('.noi').read_text(), re.M))
    if 'body_plan_ids' not in symbols:
        return
    image = rom.read_bytes()

    def offset(name):
        address = int(symbols[name], 16)
        return (address >> 16) * 16384 + (address & 16383)

    frames = []
    for bank in range(3):
        name = f'riding_body_{bank}'
        data = read_array(gen / f'riding16_body_{bank}.c', name)
        start = offset('_' + name)
        assert image[start:start+len(data)] == data
        frames.extend(data[i:i+256] for i in range(0, len(data), 256))
    assert len(frames) == 192
    heads = read_array(gen / 'riding16_parts.c', 'riding_heads')
    start = offset('_riding_heads')
    for i in range(256):
        top = image[start+16*i:start+16*i+16]
        assert top + bytes(16) == heads[i*32:(i+1)*32]

    slots, ids, spans = map(offset, ('body_xor_slots', 'body_plan_ids', 'body_spans'))
    # A freshly selected course can start in any pose with arbitrary old VRAM.
    for previous in [*range(len(frames)), 255]:
        for current, target in enumerate(frames):
            slot = image[slots + (previous ^ current)]
            plan = (15, 255)
            if slot < 16:
                index = current*16 + slot
                if 'body_plan_pairs' in symbols:
                    pair = image[ids + index//2]
                    plan_id = image[offset('body_plan_pairs') + pair*2 + index%2]
                else:
                    plan_id = image[ids + index]
                pos = spans + 2*plan_id
                plan = image[pos:pos+2]
            vram = bytearray(frames[previous] if previous != 255 else [0xa5]*256)
            end = 0
            for span in plan:
                if span == 255:
                    continue
                begin = (span >> 4) * 16
                assert end <= begin
                end = begin + ((span & 15) + 1) * 16
                assert end <= 256
                vram[begin:end] = target[begin:end]
            assert vram == target, (previous, current, plan)
    print('37,056 exact body transitions including course entry, 256 exact heads')


class PresentationDriver(Driver):
    def check_resident_poses(self):
        pointer = self.symbols.get('_body_preload_poses')
        if pointer is None:
            return
        entries = self.rom_far((pointer >> 16, pointer & 65535), 22)
        slots = entries[1::2]
        assert len(set(slots)) == 11
        for pose, slot in zip(entries[::2], slots):
            bank, page = slot >> 7, slot & 127
            assert page < (4 if bank else 7)
            start = 0x8000 + page*256
            expected = self.rom_far((10+pose//64, 0x4000 + (pose%64)*256), 256)
            assert bytes(self.p.memory[bank, start:start+256]) == expected, (pose, bank, page)
        if '_bike_streamed_heads' in self.symbols:
            source = self.symbols['_riding_heads'] & 65535
            for i in range(12):
                pose = (124+i) & 127
                start = 0x8000 + (92+i*2)*16
                expected = self.rom_far((13, source+pose*16),16) + bytes(16)
                assert bytes(self.p.memory[1,start:start+32]) == expected, ('resident head', pose)

    def observe_dma(self):
        # Find the final linked poll/launch sequence inside the renderer.
        # Bound its transition gap (36 T) and successful launch (40 T)
        # separately from the 64-T-per-tile hardware DMA stall PyBoy omits.
        start = self.symbols['_bike_render_hide']
        end = self.symbols['_bike_render_prepare']
        code = self.rom_bytes[start:end]
        poll = bytes.fromhex('f0 41 e6 03 fe 03 20')
        launch = bytes.fromhex('f0 41 1f 38 fb 79 e0 55')
        pos = code.index(launch)
        assert code[pos-len(poll)-1:pos-1] == poll, 'rederive STAT polling bound'
        assert 36 + 40 + 3 * 64 < (87 + 80) * 2
        self.p.hook_register(0, start+pos+len(launch)-2, self._burst, self)

    @staticmethod
    def _burst(driver):
        if driver.phase and driver.byte('game_ready'):
            blocks = driver.p.register_file.A + 1
            mode = driver.p.memory[0xff41] & 3
            if blocks > 3 or mode == 3 or (blocks > 1 and mode != 0):
                driver.observer_errors.append(AssertionError(('sprite DMA', mode, blocks)))
            driver.bursts[mode, blocks] += 1

    @staticmethod
    def _input_entry(driver):
        Driver._input_entry(driver)
        if driver.phase and driver.byte('game_ready') and driver.byte('game_state') == RIDING:
            driver.inputs.append(sorted(driver.held - {'start'}))

    @staticmethod
    def _physics_entry(driver):
        Driver._physics_entry(driver)
        if driver.phase:
            try:
                driver.frames.append(driver.presentation())
            except Exception as error:
                driver.observer_errors.append(error)

    def presentation(self):
        if not self.frames:
            self.check_resident_poses()
        memory = self.p.memory
        shadow = self.symbols['_shadow_OAM']
        oam = bytes(memory[shadow:shadow+160])
        patterns = []
        for y, x, tile, attr in zip(oam[0::4], oam[1::4], oam[2::4], oam[3::4]):
            if x and y:
                address = 0x8000 + (tile & 254) * 16
                patterns.append(bytes(memory[(attr >> 3) & 1, address:address+32]))
        signed_bg = not memory[0xff40]&16
        canonical=bytearray(oam)
        if '_bike_body_slot' in self.symbols:
            slot = self.byte('bike_body_slot')
            bank, page = slot >> 7, slot & 127
            assert page < (5 if bank else 7)
            for i in range(8):
                index = 4*i+2
                assert oam[index] == page*16 + i*2 and oam[index+1] == bank*8
                canonical[index:index+2] = bytes((64+i*2, 8))
        # Compare both halves of the head even when its OAM Y is hidden.
        head = oam[50]
        if signed_bg:
            resident = '_bike_streamed_heads' in self.symbols
            assert head in (88,90) or (resident and 92<=head<116 and head%2==0)
            canonical[50] = 88
            for i in range(0,160,4):
                if any(oam[i:i+3]):canonical[i+2]^=128
        else:
            assert head in (216,218)
            canonical[50] = 216
        assert oam[51] == 12
        start = 0x8000 + 16*head
        patterns.append(bytes(memory[1,start:start+32]))
        hud=0x8ec0 if signed_bg else 0x8dc0
        return {
            'steps': self.word('game_steps'),
            'camera': (self.word('game_camera_x'), self.word('game_camera_y')),
            'OAM': bytes(canonical),
            'sprite pixels': patterns,
            'HUD pixels': bytes(memory[1, hud:hud+320]),
        }


def trace(rom, gen, out, level, scenario, observe_dma=False):
    driver = PresentationDriver(rom, out, gen)
    driver.frames = []
    driver.inputs = []
    driver.bursts = Counter()
    if observe_dma:
        driver.observe_dma()
    try:
        driver.ready()
        driver.level_menu()
        distance = (level - driver.level_index() - 1) % 54
        for _ in range(min(distance, 54-distance)):
            driver.pulse('down' if distance <= 27 else 'up')
        for _ in range(600):
            driver.tick(1, ['start'])
            if driver.byte('game_state') == RIDING:
                break
        assert driver.byte('game_state') == RIDING and driver.level_index()+1 == level
        driver.phase = 'riding'
        plan = controller_plan(scenario, 12345, level, 300)
        for _ in range(3000):
            driver.tick(1, plan[min(len(driver.inputs), len(plan)-1)])
            if len(driver.frames) == len(plan) or driver.byte('game_state') != RIDING:
                break
        assert driver.frames and (len(driver.frames) == len(plan) or driver.byte('game_state') != RIDING)
        assert driver.inputs == plan[:len(driver.frames)], (level, scenario, 'controller samples')
        return driver.frames, driver.slot_mirror_checks, driver.bursts
    finally:
        driver.p.stop(save=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--reference-gen', type=Path, help='asset directory matching the reference ROM')
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--gen', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=BASE/'build/check-bike-presentation')
    args = parser.parse_args()
    check_body_plans(args.rom, args.gen)
    frames = cells = 0
    bursts = Counter()
    routes = ((11, 'brake'), (34, 'brake'), (1, 'gas'), (44, 'gas'),
              (32, 'seeded'), (35, 'gas'), (38, 'brake'))
    for level, scenario in routes:
        old, _, _ = trace(args.reference, args.reference_gen or args.gen, args.out/'reference', level, scenario)
        new, checked, observed = trace(args.rom, args.gen, args.out/'candidate', level, scenario, True)
        bursts.update(observed)
        assert len(old) == len(new), (level, scenario, 'update count', len(old), len(new))
        for step, (expected, actual) in enumerate(zip(old, new)):
            for field in expected:
                assert actual[field] == expected[field], (level, scenario, step, field)
        frames += len(new)
        cells += checked
    assert bursts[0, 3] and bursts[1, 1], 'routes missed active display or late VBlank DMA'
    print(f'Sprite DMA launches by (LCD mode, blocks): {dict(sorted(bursts.items()))}')
    print(f'{len(routes)} routes, {frames} matching presentations, {cells} verified background cells')


if __name__ == '__main__':
    main()
