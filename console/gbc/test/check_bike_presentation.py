"""Compare visible bike, object and HUD art at matching controller-driven updates."""

import argparse
from collections import Counter
from pathlib import Path

from benchmark_gameplay import controller_plan
from play import BASE, Driver, RIDING


class PresentationDriver(Driver):
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
        memory = self.p.memory
        shadow = self.symbols['_shadow_OAM']
        oam = bytes(memory[shadow:shadow+160])
        patterns = []
        for y, x, tile, attr in zip(oam[0::4], oam[1::4], oam[2::4], oam[3::4]):
            if x and y:
                address = 0x8000 + (tile & 254) * 16
                patterns.append(bytes(memory[(attr >> 3) & 1, address:address+32]))
        return {
            'steps': self.word('game_steps'),
            'camera': (self.word('game_camera_x'), self.word('game_camera_y')),
            'OAM': oam,
            'sprite pixels': patterns,
            'HUD pixels': bytes(memory[1, 0x8dc0:0x8f00]),
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
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--gen', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=BASE/'build/check-bike-presentation')
    args = parser.parse_args()
    frames = cells = 0
    bursts = Counter()
    routes = ((11, 'brake'), (34, 'brake'), (1, 'gas'), (44, 'gas'),
              (32, 'seeded'), (35, 'gas'), (38, 'brake'))
    for level, scenario in routes:
        old, _, _ = trace(args.reference, args.gen, args.out/'reference', level, scenario)
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
