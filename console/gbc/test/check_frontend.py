"""Exercise the complete title/menu/riding flow through controller input."""
import argparse
import json
from pathlib import Path
import wave

import numpy as np
from play import BASE,Driver,MENU,PAUSED,RIDING
from all_levels import font_pixels,ui_pixels,menu_check


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    version=(BASE/'VERSION').read_text().strip()
    parser.add_argument('--rom',type=Path,default=BASE/('build/elma-gbc-v%s-4m.gbc'%version))
    parser.add_argument('--gen',type=Path,default=BASE/'build/gen')
    parser.add_argument('--out',type=Path,default=BASE/'build/playtest/frontend')
    args=parser.parse_args();d=Driver(args.rom,args.out,args.gen,sound=True)
    try:
        d.tick(240)
        assert d.byte('splash_active') and not d.byte('game_ready'),'title must precede main menu'
        d.snapshot('title')
        d.tick(30);assert d.byte('splash_active'),'title unexpectedly skipped itself'
        d.tick(30,('start',));d.tick(5);d.ready()
        assert not d.byte('splash_active') and d.byte('menu_screen')==0
        assert d.byte('game_state')==MENU,'held title confirmation skipped the main menu'
        assert np.array_equal(ui_pixels(d,7,2,12),font_pixels(('VERSION '+version).ljust(12))),'main menu version'
        d.snapshot('main')
        d.pulse('up');d.pulse('a');assert d.byte('menu_screen')==2
        d.snapshot('controls');d.pulse('b');assert d.byte('menu_screen')==0
        d.level_menu();names=[r['name']for r in d.level_manifest['levels']]
        menu_check(d,0,names);d.pulse('down');menu_check(d,1,names)
        d.pulse('b');assert d.byte('menu_screen')==0
        d.level_menu();menu_check(d,1,names)
        d.snapshot('levels');d.pulse('a');d.ready()
        assert d.byte('game_state')==RIDING and d.level_index()==1
        audio=[]
        def engine_segment(keys):
            # Isolate the two engine channels for pitch/level assertions;
            # suspension and turn effects now legitimately share this mix.
            d.p.memory[0xff25]=0x55
            chunks=[]
            d.tick(4,keys)
            for _ in range(60):
                d.tick(1,keys);chunk=d.p.sound.ndarray.copy()
                assert d.p.memory[0xff26]&5==5,'a real riding engine channel dropped out'
                assert np.ptp(chunk[:,0].astype(np.int16))>2,'real riding engine PCM is silent'
                chunks.append(chunk);audio.append(chunk)
            d.p.memory[0xff25]=0xff
            return np.concatenate(chunks)
        def engine_pitch(pcm):
            samples=pcm[:,0].astype(float);samples-=np.mean(samples)
            peak=np.argmax(np.abs(np.fft.rfft(samples*np.hanning(len(samples)))))
            return np.fft.rfftfreq(len(samples),1/d.p.sound.sample_rate)[peak]
        idle=engine_segment(())
        assert d.p.memory[0xff1c]&0x60==0x40,'no-throttle wave engine is not quiet'
        assert d.p.memory[0xff12] in (0x08,0x10,0x20),'idle exhaust pulse volume'
        assert 100<engine_pitch(idle)<106,'no-throttle engine is not at its original-cycle pitch'
        for _ in range(30):
            d.tick(1,('a',));audio.append(d.p.sound.ndarray.copy())
        assert any(np.any(chunk)for chunk in audio),'real riding ROM is silent'
        assert d.p.memory[0xff26]&5==5,'a riding engine channel is disabled'
        assert d.p.memory[0xff1c]&0x60==0x20,'throttle did not increase wave engine volume'
        assert d.p.memory[0xff12]==0x60,'loaded exhaust pulse volume'
        coast=engine_segment(())
        assert d.p.memory[0xff1c]&0x60==0x40,'releasing throttle did not lower wave engine volume'
        assert d.p.memory[0xff12] in (0x08,0x10,0x20),'coasting did not lower exhaust pulse volume'
        assert abs(engine_pitch(coast)-engine_pitch(idle))<1,'coasting did not return to idle pitch'
        # Pulse phase survives retriggers; the combined peak need not match
        # after coasting, while both channel volumes must return to idle.
        assert 6<=np.ptp(coast[:,0].astype(np.int16))<=10
        d.pulse('select');assert d.byte('game_state')==PAUSED and d.byte('menu_screen')==0
        assert not d.p.memory[0xff26]&5,'pause left an engine channel running'
        frozen=(d.time_frames(),d.bike(),d.word('game_steps'))
        d.tick(60);assert frozen==(d.time_frames(),d.bike(),d.word('game_steps'))
        d.snapshot('paused')
        d.level_menu();d.pulse('down');menu_check(d,2,names)
        d.pulse('b');d.pulse('b')
        assert d.byte('game_state')==RIDING and d.level_index()==1,'Resume started the browsed course'
        assert d.time_frames()>=frozen[0]
        d.pulse('select');d.pulse('down');d.pulse('a');d.ready()
        assert d.byte('game_state')==RIDING and d.level_index()==1
        assert d.time_frames()<frozen[0],'Restart did not reset the current ride'
        d.visible_vram(force=True);d.snapshot('restarted')
        pcm=np.concatenate(audio)
        with wave.open(str(args.out/'engine.wav'),'wb')as output:
            output.setnchannels(2);output.setsampwidth(1);output.setframerate(d.p.sound.sample_rate)
            output.writeframes((pcm.astype(np.int16)+128).astype(np.uint8).tobytes())
        report={'status':'passed','version':version,'rom_sha256':d.rom_sha256,
                'checks':['title input','main menu version','controls/back','course selection persistence',
                          'continuous CH1+CH3 idle PCM','both engine throttle volumes','coast returns to idle',
                          'real engine PCM','pause mutes engine','pause freezes ride',
                          'resume preserves current course','restart resets current course','restored VRAM'],
                'display_overruns':d.word('game_overruns'),'hardware_tested':False}
        (args.out/'run.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    finally:d.close()


if __name__=='__main__':main()
