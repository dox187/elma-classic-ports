"""Check original volt cooldown semantics through actual ROM controller input.

Observe the physics input at function entry; never write guest RAM or registers.
The original accepts held keys, shares one cooldown between directions, and
requires strictly more than Ugroturelem model seconds between impulses.
"""
import argparse
import json
import math
from pathlib import Path
import re

from play import BASE, Driver, PAUSED, RIDING


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    version = (BASE / 'VERSION').read_text().strip()
    parser.add_argument('--rom', type=Path, default=BASE / f'build/elma-gbc-v{version}-4m.gbc')
    parser.add_argument('--gen', type=Path, default=BASE / 'build/gen')
    parser.add_argument('--out', type=Path, default=BASE / 'build/playtest/volt-input')
    args = parser.parse_args()
    original = (BASE.parents[1] / 'src/ADATOK.CPP').read_text()
    cooldown = float(re.search(r'^\s*Ugroturelem\s*=\s*([\d.]+);', original, re.M)[1])
    rate = float(re.search(r'#define PH_RATE ([\d.]+)', (args.gen / 'riding_constants.h').read_text())[1])
    clock_scale = 182 * 0.0024  # LEJATSZO.CPP: stopwatch ticks -> model time.
    interval = math.floor(cooldown * rate / clock_scale) + 1
    d = Driver(args.rom, args.out, args.gen)
    calls, events, cases = [], [], {}

    def observe(_):
        # ph_step uses the SM83 SDCC register ABI: uint8_t argument in A.
        record = {'step': d.word('game_steps'), 'frame': d.p.frame_count,
                  'input': d.p.register_file.A,
                  'volt_before': list(d.p.memory[d.symbols['_Bike']+103:d.symbols['_Bike']+105])}
        calls.append(record)
        if record['input'] & 12:
            events.append(record)

    address = d.symbols['_ph_step']
    d.p.hook_register(address >> 16, address & 65535, observe, None)

    def until(predicate, keys=()):
        for _ in range(500):
            if predicate():
                return
            assert d.byte('game_state') == RIDING, 'rider died before input check completed'
            d.tick(1, keys)
        raise AssertionError('expected physics input did not arrive: ' + str(keys))

    def advance(count, keys=()):
        start = d.word('game_steps')
        until(lambda: (d.word('game_steps')-start)&65535 >= count, keys)

    def next_event(keys, mask):
        target = len(events) + 1
        until(lambda: len(events) >= target, keys)
        assert events[-1]['input'] & 12 == mask, events[-1]
        return events[-1]

    def restart():
        d.pulse('start')
        d.ready()
        assert d.level_index() == 43 and d.byte('game_state') == RIDING
        calls.clear()
        events.clear()

    def gap(first, second):
        return (second['step'] - first['step']) & 65535

    report = {'status': 'running', 'rom_sha256': d.rom_sha256,
              'original_model_cooldown': cooldown, 'original_seconds': cooldown / clock_scale,
              'physics_steps_between_volts': interval, 'nominal_gbc_seconds': interval / rate,
              'hardware_tested': False}
    try:
        d.ready()
        d.level_menu()
        assert d.level_manifest['levels'][43]['name'].lower() == 'freefall'
        for _ in range(4):
            d.pulse('right')
        for _ in range(7):
            d.pulse('down')
        d.pulse('start')
        d.ready()
        assert d.level_index() == 43

        for key, mask in [('left', 8), ('right', 4)]:
            restart()
            accepted = [next_event((key,), mask) for _ in range(2)]
            assert gap(*accepted) == interval
            assert len({event['step'] for event in events}) == len(events), 'volt repeated inside one frame'
            if '#define RIDING_PC_SCHEDULE 1' in (args.gen / 'riding_constants.h').read_text():
                # PC ends the impulse at the first microstep whose start is
                # strictly more than 0.1 model seconds after its acceptance.
                origin = calls.index(accepted[0])
                channel = 1 if mask == 8 else 0
                elapsed = 0.0
                release = None
                for offset in range(1, len(calls)-origin):
                    elapsed += .0055 if (offset-1)%3 < 2 else clock_scale/rate-.011
                    if elapsed > cooldown*.25:
                        release = offset
                        break
                assert release is not None
                remaining = [call['volt_before'][channel] for call in calls[origin+1:origin+release+2]]
                assert remaining == list(range(release, -1, -1)), (release, remaining)
            cases['held_' + key] = accepted

        restart()
        first = next_event(('left',), 8)
        advance(8)
        second = next_event(('right',), 4)
        assert gap(first, second) == interval, 'early held opposite direction was lost or accepted too soon'
        cases['early_opposite_held'] = [first, second]

        restart()
        first = next_event(('left',), 8)
        advance(4, ('right',))
        advance(interval + 2)
        assert len(events) == 1, 'released input was queued past cooldown'
        cases['early_released_not_queued'] = list(events)

        restart()
        first = next_event(('left',), 8)
        advance(8)
        d.pulse('select')
        assert d.byte('game_state') == PAUSED
        frozen = (d.word('game_steps'), len(events))
        d.tick(90)
        assert (d.word('game_steps'), len(events)) == frozen
        d.pulse('select')
        second = next_event(('right',), 4)
        assert gap(first, second) == interval, 'pause consumed the riding cooldown'
        cases['pause_freezes_cooldown'] = [first, second]

        restart()
        next_event(('left',), 8)
        restart()
        accepted = next_event(('right',), 4)
        assert gap(calls[0], accepted) <= 1, 'restart retained the preceding ride cooldown'
        cases['restart_clears_cooldown'] = accepted
        report.update(status='passed', cases=cases)
    except BaseException as error:
        report.update(status='failed', error=str(error), cases=cases, events=events)
        raise
    finally:
        (args.out / 'run.json').write_text(json.dumps(report, indent=2) + '\n')
        d.close()
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
