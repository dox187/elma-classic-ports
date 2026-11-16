"""Check finish audio in the complete game, including save and LCD uploads.

Use the explicit flower-contact fixture; this is not a controller-completed
course. Capture actual APU PCM and observe the normal effect entry.
"""
import argparse
import json
from pathlib import Path
import shutil
import wave

import numpy as np

from check_players import finish_fixture, menu_item
from play import BASE, Driver, FINISHED


def main():
    version = (BASE/'VERSION').read_text().strip()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, default=BASE/f'build/elma-gbc-v{version}-4m.gbc')
    parser.add_argument('--gen', type=Path, default=BASE/'build/gen')
    parser.add_argument('--out', type=Path, default=BASE/'build/playtest/finish-audio')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rom = args.out/'finish-test.gbc'
    shutil.copyfile(args.rom, rom)
    shutil.copyfile(args.rom.with_suffix('.noi'), rom.with_suffix('.noi'))
    Path(str(rom)+'.ram').unlink(missing_ok=True)
    d = Driver(rom, args.out, args.gen, sound=True)
    events, frames, samples = [], [], []
    entry = d.symbols['_audio_effect']
    def effect(_):
        if d.byte('game_state') == FINISHED:
            events.append({'frame': d.p.frame_count, 'time': d.word('sys_time'),
                           'panel_ready': d.p.memory[0xff40]&0xa0 == 0xa0
                                          and d.p.memory[0xff4a] == 120})
    d.p.hook_register(entry >> 16, entry & 65535, effect, None)
    normal_tick = d.tick
    def capture(count=1, keys=()):
        for _ in range(count):
            normal_tick(1, keys)
            pcm = d.p.sound.ndarray.copy()
            samples.append(pcm)
            frames.append({'frame': d.p.frame_count, 'time': d.word('sys_time'),
                           'channels': d.p.memory[0xff26]&15,
                           'level': int(np.ptp(pcm[:,0].astype(np.int16)))})
    try:
        d.ready()
        menu_item(d, 0)
        d.ready()
        d.tick(60)
        d.tick = capture
        finish_fixture(d)
        d.tick(100)
        assert len(events) == 1, 'finish sound was missing or restarted'
        event = events[0]
        assert event['panel_ready'], 'finish sound started before blocking save/upload completed'
        active = [r for r in frames if r['frame'] >= event['frame']]
        for row in active:
            row['age'] = (row['time']-event['time'])&65535
        assert any(r['channels']&8 and r['level']>0 for r in active if r['age']<4), 'finish onset is silent'
        assert any(r['level']>0 for r in active if 12<=r['age']<24), 'finish body is missing'
        assert any(r['level']>0 for r in active if 32<=r['age']<44), 'finish tail is missing'
        assert all(not r['channels']&5 for r in active if r['age']>1), 'an engine channel continued after finish'
        # Original siker.wav is 8460 samples at the mixer rate 11025 Hz:
        # 46 CGB VBlanks. Allow the main loop two updates to publish its stop.
        assert all(not r['channels']&15 and r['level']==0 for r in active if r['age']>=50), 'finish effect remained audible'
        pcm = np.concatenate(samples).astype(np.int16)*256
        with wave.open(str(args.out/'finish.wav'), 'wb') as output:
            output.setnchannels(2)
            output.setsampwidth(2)
            output.setframerate(d.p.sound.sample_rate)
            output.writeframes(pcm.astype('<i2').tobytes())
        report = {'status':'passed', 'rom_sha256':d.rom_sha256,
                  'finish_is_contact_fixture':True, 'hardware_tested':False,
                  'effect_events':events, 'frames':frames}
        (args.out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps({key:value for key,value in report.items() if key!='frames'}, indent=2))
    finally:
        d.p.hook_deregister(entry >> 16, entry & 65535)
        d.close()


if __name__ == '__main__':
    main()
