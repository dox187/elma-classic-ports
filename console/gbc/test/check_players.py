"""Exercise player UI, the visible race clock, retry and persistent records.

Menus and crashes use controller input. The finish integration check places
one wheel on the unlocked flower at object-touch entry; it validates result
handling and saving, and does not claim a completed player-controlled route.
"""
import argparse
import json
from pathlib import Path
import shutil

import numpy as np

from all_levels import font_pixels, ui_pixels
from play import BASE, Driver, RIDING, DEAD, FINISHED, MENU, PAUSED


def text_check(d, x, y, value, window=False):
    assert x*2+len(value) <= 40, 'text exceeds the visible screen'
    assert np.array_equal(ui_pixels(d, x, y, len(value), window), font_pixels(value)), value


def name(d, index):
    address = d.symbols['_save_names'] + index * 11
    return bytes(d.p.memory[address:address+11]).split(b'\0')[0].decode()


def menu_item(d, index):
    assert d.byte('menu_screen') == 0
    for _ in range(4):
        if d.byte('menu_selection') == index:
            break
        d.pulse('down')
    assert d.byte('menu_selection') == index
    d.pulse('a')


def keyboard_key(d, letter):
    target = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'.index(letter)
    for _ in range(16):
        current = d.byte('menu_keyboard_selection')
        if current == target:
            d.pulse('a')
            return
        assert current < 36
        if current // 9 != target // 9:
            d.pulse('down' if current // 9 < target // 9 else 'up')
        else:
            d.pulse('right' if current % 9 < target % 9 else 'left')
    raise AssertionError('keyboard navigation did not reach '+letter)


def finish_fixture(d, at_frames=None, expect_new=True):
    """Keep the normal clock/finish/save path; supply only flower contact."""
    address = d.symbols['_gbc_object_touch']
    called = []
    frozen_patterns, frozen_maps, frozen_sprites = {}, [], []
    overlay = d.symbols['_result_overlay']
    def freeze(_):
        # Verify that the panel never steals a pattern still used by the
        # visible frozen scenery, even when tiles repeat elsewhere in VRAM.
        sx, sy = d.p.memory[0xff43], d.p.memory[0xff42]
        base = 0x9c00 if d.p.memory[0xff40] & 8 else 0x9800
        frozen_maps.extend(bytes(d.p.memory[bank,base:base+1024]) for bank in (0,1))
        for row in range(((sy & 7)+120+7)//8):
            for col in range(((sx & 7)+160+7)//8):
                cell = base+(((sy//8+row)&31)*32)+((sx//8+col)&31)
                tile, attr = d.p.memory[0,cell], d.p.memory[1,cell]
                bank = 1 if attr & 8 else 0
                start = 0x8000+tile*16
                frozen_patterns[bank,start] = bytes(d.p.memory[bank,start:start+16])
        shadow = d.symbols['_shadow_OAM']
        frozen_sprites.append(bytes(d.p.memory[shadow:shadow+160]))
    d.p.hook_register(overlay >> 16, overlay & 65535, freeze, None)
    def touch(_):
        if called or (at_frames is not None and d.time_frames() < at_frames):
            return
        called.append(True)
        source = d.level_manifest['levels'][d.level_index()]['objects']
        flower = next(i for i, obj in enumerate(source) if obj[2] == 1)
        objects = d.symbols['_game_objects']
        coords = bytes(d.p.memory[objects+flower*14+5:objects+flower*14+13])
        wheel = d.symbols['_gbc_bike'] + 10
        d.p.memory[wheel:wheel+8] = list(coords)
        active = d.symbols['_game_object_active']
        for i in range(len(source)):
            d.p.memory[active+i] = int(i == flower)
        d.p.memory[d.symbols['_game_apples_left']] = 0
    d.p.hook_register(address >> 16, address & 65535, touch, None)
    try:
        for _ in range(600):
            d.tick()
            if called and d.byte('game_state') == FINISHED:
                break
        assert called and d.byte('game_state') == FINISHED
        # Wait for the synchronous save and complete results-screen upload.
        for _ in range(180):
            d.tick()
            if d.byte('game_ready') and d.p.memory[0xff40] & 0xa0 == 0xa0 and d.p.memory[0xff4a] == 120:
                break
        else:
            raise AssertionError('result screen did not finish loading')
        d.tick(3)
        assert frozen_patterns, 'finish did not publish the frozen-frame panel'
        base = 0x9c00 if d.p.memory[0xff40] & 8 else 0x9800
        assert frozen_maps == [bytes(d.p.memory[bank,base:base+1024]) for bank in (0,1)]
        for (bank,start), expected in frozen_patterns.items():
            assert bytes(d.p.memory[bank,start:start+16]) == expected, 'panel corrupted visible scenery'
        assert bytes(d.p.memory[0xfe00:0xfea0]) == frozen_sprites[0], 'panel changed the frozen sprites'
        assert bool(d.byte('game_new_record')) == expect_new
        if at_frames is not None:
            assert d.time_frames() == at_frames, 'finish fixture missed the requested simulation time'
        return d.time_frames()
    finally:
        d.p.hook_deregister(address >> 16, address & 65535)
        d.p.hook_deregister(overlay >> 16, overlay & 65535)


def time_string(frames):
    centiseconds = frames * 10000 // 5973
    return '%02d:%02d.%02d' % (centiseconds // 6000 % 100,
                              centiseconds // 100 % 60, centiseconds % 100)


def result_check(d, frames, previous, status):
    assert d.byte('game_state') == FINISHED
    assert d.p.memory[0xff40] & 0x22 == 0x22, 'frozen result must retain sprites and show its window'
    assert d.p.memory[0xff4a] == 120, 'result must use a three-row bottom panel'
    text_check(d, 0, 0, ('TIME '+time_string(frames)+'  '+status).ljust(40), True)
    old_time = time_string(previous) if previous else '--:--.--'
    text_check(d, 0, 1, ('PREV '+old_time).ljust(40), True)
    text_check(d, 0, 2, 'A:NEXT START:RETRY B/SELECT:MENU UP:INFO'.ljust(40), True)


def details_check(d, frames, previous, status):
    assert d.byte('game_state') == FINISHED and d.byte('menu_screen') == 5
    assert not d.p.memory[0xff40] & 0x22
    text_check(d, 6, 2, 'LEVEL COMPLETE'.ljust(16))
    text_check(d, 2, 9, ('TIME          '+time_string(frames)).ljust(32))
    text_check(d, 2, 11, ('PREVIOUS BEST '+(time_string(previous) if previous else '--:--.--')).ljust(32))
    text_check(d, 2, 12, status.ljust(32))
    text_check(d, 2, 14, 'UP LAST FRAME'.ljust(32))
    for y, hint in enumerate(('A NEXT LEVEL', 'START RETRY', 'B/SELECT MENU'), 15):
        text_check(d, 2, y, hint.ljust(32))


def timer_cadence(d):
    """Check each presentation's VRAM and changes in the actual LCD output."""
    checks, changes = [], []
    address = d.symbols['_physics_step']
    def observe(_):
        Driver._physics_entry(d)
        try:
            now = d.time_frames()
            text_check(d, 16, 0, time_string(now), True)
            checks.append(now)
        except BaseException as error:
            d.observer_errors.append(error)
    d.p.hook_deregister(address >> 16, address & 65535)
    d.p.hook_register(address >> 16, address & 65535, observe, None)
    old_pixels = None
    overruns = d.word('game_overruns')
    try:
        for _ in range(180):
            d.tick()
            pixels = np.asarray(d.p.screen.image)[136:144,128:160].copy()
            if old_pixels is not None and not np.array_equal(pixels, old_pixels):
                changes.append(d.p.frame_count)
            old_pixels = pixels
        assert len(checks) >= 88 and len(changes) >= 88, 'timer does not update at the riding rate'
        intervals = np.diff(changes).tolist()
        assert max(intervals) <= 3, ('visible clock stalls between updates', intervals)
        cadence_checks = len(checks)
        # Exercise carries into tens of seconds and minutes with the same
        # real clock and exact tile checks, without injecting a counter.
        d.tick(3600)
        assert any(time_string(t).startswith('01:00.') for t in checks)
        assert d.word('game_overruns') == overruns, 'live timer introduced idle-ride deadline misses'
        return {'physics_publications_checked': len(checks), 'cadence_publications': cadence_checks,
                'lcd_changes_in_180_frames': len(changes), 'minute_rollover_verified': True,
                'lcd_change_intervals_frames': sorted(set(intervals)), 'idle_deadline_misses': 0}
    finally:
        d.p.hook_deregister(address >> 16, address & 65535)
        d.p.hook_register(address >> 16, address & 65535, Driver._physics_entry, d)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    version = (BASE/'VERSION').read_text().strip()
    parser.add_argument('--rom', type=Path, default=BASE/('build/elma-gbc-v%s-4m.gbc'%version))
    parser.add_argument('--gen', type=Path, default=BASE/'build/gen')
    parser.add_argument('--alternate-rom', type=Path, help='reload the same save in the other ROM size')
    parser.add_argument('--alternate-gen', type=Path, help='generated assets for the alternate ROM')
    parser.add_argument('--out', type=Path, default=BASE/'build/playtest/players')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    # Isolate battery files from the user's playable ROM and previous tests.
    rom = args.out/'players-test.gbc'
    shutil.copyfile(args.rom, rom)
    shutil.copyfile(args.rom.with_suffix('.noi'), rom.with_suffix('.noi'))
    Path(str(rom)+'.ram').unlink(missing_ok=True)
    d = Driver(rom, args.out, args.gen)
    try:
        d.ready()
        assert d.rom_bytes[0x147] == 0x1b
        assert d.rom_bytes[0x149] == 3, 'release must target 32KiB cartridge RAM'
        assert d.byte('save_player') == 0
        assert [name(d, i) for i in range(4)] == ['PLAYER %d' % i for i in range(1, 5)]
        menu_item(d, 2)
        assert d.byte('menu_screen') == 3
        d.snapshot('players')
        d.pulse('down')
        assert d.byte('menu_player_selection') == 1
        d.pulse('select')
        assert d.byte('menu_screen') == 4
        d.snapshot('name-keyboard')
        for _ in range(8):
            d.pulse('b')
        d.pulse('start')
        assert d.byte('menu_screen') == 4, 'empty name must stay in editor'
        assert name(d, 1) == 'PLAYER 2'
        for _ in range(11):
            keyboard_key(d, 'A')
        text_check(d, 5, 3, 'AAAAAAAAAA')
        d.pulse('b')
        text_check(d, 5, 3, 'AAAAAAAAA_')
        d.pulse('select')
        assert d.byte('menu_screen') == 3 and name(d, 1) == 'PLAYER 2'
        d.pulse('select')
        for _ in range(8):
            d.pulse('b')
        for letter in 'DOX':
            keyboard_key(d, letter)
        text_check(d, 5, 3, 'DOX_')
        d.pulse('down')
        d.pulse('down')
        assert d.byte('menu_keyboard_selection') == 37
        d.pulse('a')  # DEL
        text_check(d, 5, 3, 'DO_ ')
        d.pulse('left')
        d.pulse('a')  # SPACE
        text_check(d, 5, 3, 'DO _')
        d.pulse('right')
        d.pulse('a')  # DEL
        d.pulse('up')
        keyboard_key(d, 'X')
        d.snapshot('name-entered')
        d.pulse('right')
        d.pulse('down')
        d.pulse('down')
        assert d.byte('menu_keyboard_selection') == 38
        d.pulse('a')  # OK
        assert d.byte('menu_screen') == 3 and name(d, 1) == 'DOX'
        d.pulse('a')
        assert d.byte('menu_screen') == 0 and d.byte('save_player') == 1
        text_check(d, 5, 3, 'PLAYER: DOX'.ljust(20))
        text_check(d, 5, 6, 'BEST --:--.--'.ljust(20))
        menu_item(d, 0)
        d.ready()
        assert d.byte('game_player_index') == 1
        d.tick(90)
        assert d.byte('game_state') == RIDING
        text_check(d, 13, 0, 'TIME  ', True)
        visible = ui_pixels(d, 16, 0, 8, True)
        now = d.time_frames()
        assert any(np.array_equal(visible, font_pixels(time_string(t)))
                   for t in range(max(0, now-16), now+1)), 'visible timer is stale or wrong'
        cadence = timer_cadence(d)
        d.snapshot('riding-time')
        d.pulse('select')
        assert d.byte('game_state') == PAUSED
        frozen = d.time_frames()
        d.tick(80)
        assert d.time_frames() == frozen
        d.pulse('select')
        assert d.byte('game_state') == RIDING
        # Real unbalanced Warm Up ride, with no injected death state.
        for _ in range(900):
            d.step(('a',))
            if d.byte('game_state') == DEAD:
                break
        assert d.byte('game_state') == DEAD
        d.tick(15)
        text_check(d, 0, 0, 'CRASH A/START RETRY B/SELECT MENU', True)
        d.snapshot('crash-controls')
        frozen = d.time_frames()
        d.tick(60)
        assert d.time_frames() == frozen
        d.pulse('a')
        d.ready()
        assert d.byte('game_state') == RIDING and d.time_frames() < frozen
        assert d.byte('game_apples_left') == 1
        d.tick(60)
        frames = finish_fixture(d)
        result_check(d, frames, 0, 'FIRST RECORD')
        d.snapshot('finish-first-record')
        d.tick(60)
        assert d.time_frames() == frames
        result_check(d, frames, 0, 'FIRST RECORD')
        frozen = np.asarray(d.p.screen.image).copy()
        d.pulse('up')
        details_check(d, frames, 0, 'FIRST RECORD')
        d.snapshot('finish-details')
        d.pulse('up')
        d.tick(3)
        result_check(d, frames, 0, 'FIRST RECORD')
        assert np.array_equal(np.asarray(d.p.screen.image), frozen), 'return from details changed the frozen frame'
        results = [{'status': 'FIRST RECORD', 'frames': frames, 'previous': 0}]
        for status, target in [('NO IMPROVEMENT', frames+60), ('BEST MATCHED', frames),
                               ('NEW RECORD', frames-20)]:
            d.pulse('start')
            d.ready()
            assert d.byte('game_state') == RIDING and d.level_index() == 0
            improved = status == 'NEW RECORD'
            completed = finish_fixture(d, at_frames=target, expect_new=improved)
            result_check(d, completed, frames, status)
            results.append({'status': status, 'frames': completed, 'previous': frames})
            d.snapshot('finish-'+status.lower().replace(' ', '-'))
            if improved:
                frames = completed
        d.pulse('b')
        assert d.byte('game_state') == MENU
        text_check(d, 5, 6, ('BEST '+time_string(frames)).ljust(20))
        d.snapshot('saved-record')
        d.p.stop(save=True)
        tested_sha=d.rom_sha256
        reboot_gen=args.gen
        if args.alternate_rom:
            alternate=args.out/'alternate-test.gbc'
            shutil.copyfile(args.alternate_rom,alternate)
            shutil.copyfile(args.alternate_rom.with_suffix('.noi'),alternate.with_suffix('.noi'))
            shutil.copyfile(Path(str(rom)+'.ram'),Path(str(alternate)+'.ram'))
            rom=alternate;reboot_gen=args.alternate_gen or args.gen
        d = Driver(rom, args.out/'reboot', reboot_gen)
        d.ready()
        assert d.rom_bytes[0x149] == 3
        assert d.byte('save_player') == 1 and name(d, 1) == 'DOX'
        text_check(d, 5, 6, ('BEST '+time_string(frames)).ljust(20))
        menu_item(d, 2)
        d.pulse('up')
        d.pulse('a')
        assert d.byte('save_player') == 0
        text_check(d, 5, 6, 'BEST --:--.--'.ljust(20))
        menu_item(d, 2)
        d.pulse('down')
        d.pulse('a')
        text_check(d, 5, 6, ('BEST '+time_string(frames)).ljust(20))
        d.level_menu()
        text_check(d, 2, 13, ('BEST '+time_string(frames)).ljust(20))
        d.pulse('down')
        text_check(d, 2, 13, 'BEST --:--.--'.ljust(20))
        d.pulse('a')
        d.ready()
        assert d.level_index() == 1
        d.level_menu()
        d.pulse('up')
        text_check(d, 2, 13, ('BEST '+time_string(frames)).ljust(20))
        d.pulse('a')
        d.ready()
        completed = finish_fixture(d, at_frames=frames+20, expect_new=False)
        result_check(d, completed, frames, 'NO IMPROVEMENT')
        d.pulse('a')
        d.ready()
        assert d.byte('game_state') == RIDING and d.level_index() == 1, 'A did not start the next course'
        d.visible_vram(force=True)
        report = {'status': 'passed', 'rom_sha256': tested_sha,
                  'reboot_rom_sha256':d.rom_sha256,
                  'cross_profile_reload':bool(args.alternate_rom),
                  'fixture_finish_frames': frames, 'hardware_tested': False,
                  'timer_cadence': cadence, 'result_cases': results,
                  'finish_is_contact_fixture': True,
                  'checks': ['keyboard navigation, editing, limit, cancel and blank rejection',
                             'player selection and name persistence', 'visible live timer and pause',
                             'natural crash hints and A retry', 'finish records through contact fixture',
                             'first, slower, tied and improved result times', 'result retry/next/menu controls',
                             'battery reload', 'player and course record isolation']}
        (args.out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report, indent=2))
    finally:
        d.close()


if __name__ == '__main__':
    main()
