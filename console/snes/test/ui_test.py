"""Walks through the menus of build/test_ui.sfc (test/snes_ui.c) in Mesen 2
with scripted buttons, checks the saved state, and saves the screens, side
by side with the shots of the original game when a reference set is given.

  ui_test.py [--rom build/test_ui.sfc] [--out DIR] [--pcref SHOTS_DIR]

The levels of the test ROM are a blue screen: A finishes in 12.34 s (plus a
second for each X pressed before), Start or B ends it unfinished.
"""

import argparse
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mesen  # noqa: E402

# save.h / save.c:
PLAYERS, NAME_LEN, TIMES, LEVELS = 16, 8, 10, 64
PLAYER_SIZE = NAME_LEN + 1 + 1 + 1 + LEVELS // 8
TIMES_SIZE = 1 + TIMES + 3 * TIMES
SAVE_SIZE = 8 + PLAYERS * PLAYER_SIZE + LEVELS * TIMES_SIZE
SLOT, DATA_OFS, SEED = 0x1000, 16, 0x5A3C

WAIT = 'W50'   # after a button, until the next screen is drawn
FAILS = []


def checksum(data, seed):
    s = seed & 0xFFFF
    for b in data:
        s = ((s << 1) | (s >> 15)) & 0xFFFF
        s = (s + b) & 0xFFFF
    return s


class State:
    """The saved state (save_t)."""

    def __init__(self, data=None):
        data = data or bytes(SAVE_SIZE)
        (self.nplayers, self.player, self.sound, self.anim_menus,
         self.anim_objects, self.detail) = data[:6]
        self.players = []
        for i in range(PLAYERS):
            p = data[8 + i * PLAYER_SIZE:8 + (i + 1) * PLAYER_SIZE]
            name = p[:NAME_LEN + 1].split(b'\0')[0].decode('latin-1')
            skipped = [l for l in range(LEVELS) if p[11 + l // 8] >> (l % 8) & 1]
            self.players.append({'name': name, 'done': p[9], 'current': p[10],
                                 'skipped': skipped})
        self.times = []
        base = 8 + PLAYERS * PLAYER_SIZE
        for l in range(LEVELS):
            t = data[base + l * TIMES_SIZE:base + (l + 1) * TIMES_SIZE]
            n = t[0]
            self.times.append([(t[1 + i], t[11 + 3 * i] | t[12 + 3 * i] << 8 | t[13 + 3 * i] << 16)
                               for i in range(min(n, TIMES))])

    def pack(self):
        out = bytearray(SAVE_SIZE)
        out[:6] = bytes([self.nplayers, self.player, self.sound, self.anim_menus,
                         self.anim_objects, self.detail])
        for i, p in enumerate(self.players[:self.nplayers]):
            o = 8 + i * PLAYER_SIZE
            out[o:o + len(p['name'])] = p['name'].encode('latin-1')
            out[o + 9] = p['done']
            out[o + 10] = p['current']
            for l in p['skipped']:
                out[o + 11 + l // 8] |= 1 << (l % 8)
        base = 8 + PLAYERS * PLAYER_SIZE
        for l, ts in enumerate(self.times):
            o = base + l * TIMES_SIZE
            out[o] = len(ts)
            for i, (pl, t) in enumerate(ts):
                out[o + 1 + i] = pl
                out[o + 11 + 3 * i:o + 14 + 3 * i] = struct.pack('<I', t)[:3]
        return bytes(out)


def sram_image(state, levels, seq=(1, 2), broken=None):
    """8 KB of SRAM with the state in both copies, written seq[0] and
    seq[1] times."""
    data = state.pack()
    out = bytearray(0x2000)
    for slot in (0, 1):
        s = seq[slot]
        o = slot * SLOT
        out[o + DATA_OFS:o + DATA_OFS + SAVE_SIZE] = data
        total = checksum(data, SEED + s)
        out[o:o + 12] = b'ELMS' + bytes([1, levels]) + struct.pack('<HHH', s, total, total ^ 0xFFFF)
    if broken is not None:
        out[broken * SLOT + DATA_OFS + 20] ^= 0x55
    return bytes(out)


def read_sram(data):
    """The valid copies of an SRAM image: [(slot, seq, State)]."""
    out = []
    for slot in (0, 1):
        o = slot * SLOT
        if data[o:o + 4] != b'ELMS':
            continue
        seq, total, inv = struct.unpack_from('<HHH', data, o + 6)
        body = data[o + DATA_OFS:o + DATA_OFS + SAVE_SIZE]
        if total ^ inv == 0xFFFF and checksum(body, SEED + seq) == total:
            out.append((slot, seq, State(body)))
    return out


def check(cond, what):
    print(('ok   ' if cond else 'FAIL ') + what)
    if not cond:
        FAILS.append(what)


def press(*buttons):
    """Buttons pressed one after the other (a frame each, a few apart: each
    can draw the screen again)."""
    return ' '.join('%s W6' % b for b in buttons)


def name_keys(name):
    """Up/Right presses entering a name of A-Z (nyilasbetu)."""
    keys = []
    for ch in name:
        keys.append('RIGHT')
        keys += ['UP'] * (ord(ch) - ord('A'))
    return press(*keys)


def run(args, name, script, sram=None, peek_save=True):
    out = os.path.join(args.out, name)
    os.makedirs(out, exist_ok=True)
    sram_path = None
    if sram is not None:
        sram_path = os.path.join(out, 'sram_in.bin')
        with open(sram_path, 'wb') as f:
            f.write(sram)
    script += ' SRAM:sram.bin'
    if peek_save:
        script += ' PEEK:save:%d' % SAVE_SIZE
    res = mesen.run(args.rom, script, out, sram=sram_path)
    peeks = {n: d for k, n, d in res if k == 'PEEK'}
    sram_out = open(os.path.join(out, 'sram.bin'), 'rb').read()
    return out, (State(peeks['save']) if 'save' in peeks else None), sram_out


def compare(args, out, pairs):
    if not args.pcref:
        return
    try:
        from PIL import Image
    except ImportError:
        return
    for pc, sn in pairs:
        a = Image.open(os.path.join(args.pcref, pc)).convert('RGB').resize((256, 192), Image.LANCZOS)
        b = Image.open(os.path.join(out, sn)).convert('RGB')
        img = Image.new('RGB', (516, 224), (255, 0, 255))
        img.paste(a, (0, 16))
        img.paste(b, (260, 0))
        img = img.resize((516 * 2, 448), Image.NEAREST)
        img.save(os.path.join(out, 'cmp_' + sn))


def first_boot(args, levels):
    # Intro, the name of the first player, Warm Up finished, Flat Track
    # skipped, Twin Peaks finished in 14.34, the screens of the menus.
    s = ' '.join([
        'W40 SHOT:01_intro.png START W40 SHOT:02_intro_to_menu.png W80',
        'SHOT:03_name_prompt.png', name_keys('BOB'), WAIT, 'SHOT:04_name_typed.png',
        'A', WAIT, 'SHOT:05_main.png',
        'A', WAIT, 'SHOT:06_play_first.png',
        'A W6 SHOT:07_loading.png W30 A', WAIT, 'SHOT:08_finished.png',
        'A W40 START', WAIT, 'SHOT:09_failed.png',
        press('DOWN'), 'A', WAIT, 'SHOT:10_skip.png',
        'A W40 X W2 X W2 A', WAIT, 'SHOT:11_finished3.png',
        'B', WAIT, 'SHOT:12_list.png',
        'B', WAIT, press('DOWN', 'DOWN', 'DOWN'), 'A', WAIT, 'SHOT:13_best_times.png',
        'A', WAIT, 'SHOT:14_best_times_warmup.png',
        'B', WAIT, 'B', WAIT, press('UP', 'UP'), 'A', WAIT, 'SHOT:15_options.png',
        'B', WAIT, press('DOWN'), 'A', WAIT, 'SHOT:16_help.png', 'B', WAIT])
    out, st, sram = run(args, 'first_boot', s, sram=bytes(0x2000))
    p = st.players[0]
    check(st.nplayers == 1 and p['name'] == 'BOB', 'a new player BOB')
    check(p['done'] == 3, 'three levels done (one skipped): %d' % p['done'])
    check(p['skipped'] == [1], 'Flat Track skipped: %s' % p['skipped'])
    check(p['current'] == 3, 'the list stays at level 4: %d' % p['current'])
    check(st.times[0] == [(0, 1234)], 'Warm Up 12.34: %s' % st.times[0])
    check(st.times[1] == [], 'no time of Flat Track')
    check(st.times[2] == [(0, 1434)], 'Twin Peaks 14.34: %s' % st.times[2])
    copies = read_sram(sram)
    check(len(copies) == 2, 'two valid copies in the SRAM')
    newest = max(copies, key=lambda c: c[1])[2]
    check(newest.pack() == st.pack(), 'the SRAM holds the state')
    compare(args, out, [('menu_01_intro.png', '01_intro.png'),
                        ('menu_02_intro_to_menu.png', '02_intro_to_menu.png'),
                        ('menu_03_name_prompt.png', '03_name_prompt.png'),
                        ('menu_05_main.png', '05_main.png'),
                        ('menu_06_play_first.png', '06_play_first.png'),
                        ('menu_07_loading.png', '07_loading.png'),
                        ('wu_25_finished_menu.png', '08_finished.png'),
                        ('wu_17_crash_menu.png', '09_failed.png'),
                        ('menu_17_best_times_single.png', '13_best_times.png'),
                        ('menu_18_best_times_warmup.png', '14_best_times_warmup.png'),
                        ('menu_08_options.png', '15_options.png'),
                        ('menu_09_help.png', '16_help.png')])
    return sram


def reboot(args, sram):
    # The state after a reset: Choose Player, the list where it was.
    s = ' '.join(['W40 START W120 SHOT:01_choose_player.png A', WAIT,
                  'A', WAIT, 'SHOT:02_list.png', 'B', WAIT])
    out, st, sram2 = run(args, 'reboot', s, sram=sram)
    before = max(read_sram(sram), key=lambda c: c[1])[2]
    check(st.pack() == before.pack(), 'the state comes back from the SRAM')
    compare(args, out, [('menu_14_choose_player.png', '01_choose_player.png'),
                        ('menu_19_play_after_warmup.png', '02_list.png')])


def top_ten(args, levels):
    # Ten times of Warm Up by other players; new times go into their places.
    st = State()
    st.nplayers, st.player, st.sound, st.anim_menus, st.anim_objects, st.detail = 3, 2, 1, 1, 1, 1
    st.players = [{'name': n, 'done': 1, 'current': 0, 'skipped': []} for n in ('ANN', 'CID', 'EVE')]
    st.times = [[] for _ in range(LEVELS)]
    first = [1000, 1100, 1200, 1300, 1334, 1400, 1500, 1600, 1700, 1800]
    st.times[0] = [(0 if t in (1000, 1200, 1400, 1600, 1800) else 1, t) for t in first]
    # EVE: 13.34 (after the equal time of CID: "You Made the Top Ten"), then
    # 12.34, then 25.34 (not in the list).
    s = ' '.join(['W40 START W120 A', WAIT, 'A', WAIT, 'A', WAIT,
                  'X W2 A', WAIT, 'SHOT:01_top_ten.png', 'A', WAIT,
                  'A', WAIT, 'SHOT:02_again.png', 'A', WAIT,
                  ' '.join(['X W2'] * 13), 'A', WAIT, 'SHOT:03_not_in.png',
                  press('DOWN', 'DOWN'), 'A', WAIT, 'SHOT:04_times.png', 'B', WAIT])
    out, st2, _ = run(args, 'top_ten', s, sram=sram_image(st, levels))
    got = [t for _, t in st2.times[0]]
    want = sorted(first + [1334, 1234])[:10]
    check(got == want, 'Warm Up times in order: %s' % got)
    who = [p for p, t in st2.times[0]]
    check(who == [0, 1, 0, 2, 1, 1, 2, 0, 1, 0], 'the new times are EVE\'s, after the equal time: %s' % who)


def garbage(args, levels):
    # Random SRAM: the first start (the name of a player) and two valid copies.
    rnd = random.Random(7)
    junk = bytes(rnd.randrange(256) for _ in range(0x2000))
    s = 'W40 START W120 SHOT:01_name_prompt.png ' + name_keys('Z') + ' A ' + WAIT + ' SHOT:02_main.png'
    out, st, sram = run(args, 'garbage', s, sram=junk)
    check(st.nplayers == 1 and st.players[0]['name'] == 'Z', 'random SRAM: a new state with player Z')
    check(len(read_sram(sram)) == 2, 'random SRAM: two valid copies written')


def broken_copy(args, levels):
    # The copy written last is broken (a power loss): the other one is read.
    st = State()
    st.nplayers, st.player, st.sound, st.anim_menus, st.anim_objects, st.detail = 1, 0, 1, 1, 1, 1
    st.players = [{'name': 'OLD', 'done': 5, 'current': 4, 'skipped': []}]
    st.times = [[] for _ in range(LEVELS)]
    img = bytearray(sram_image(st, levels, seq=(7, 8)))
    st.players[0]['name'] = 'NEW'
    newer = sram_image(st, levels, seq=(7, 8), broken=1)
    img[SLOT:] = newer[SLOT:]
    s = 'W40 START W120 SHOT:01_choose_player.png A ' + WAIT
    out, st2, _ = run(args, 'broken_copy', s, sram=bytes(img))
    check(st2.players[0]['name'] == 'OLD' and st2.players[0]['done'] == 5,
          'a broken newer copy: the older one is read (%s)' % st2.players[0]['name'])


def options(args, sram):
    # Options: Animated Menus off (a still helmet, no balls), a new player
    # from Player A, Sound off; written when leaving Options.
    s = ' '.join(['W40 START W120 A', WAIT, press('DOWN'), 'A', WAIT,
                  press('DOWN', 'DOWN'), 'A', WAIT, 'SHOT:01_static.png', 'W30 SHOT:02_static.png',
                  press('UP', 'UP'), 'A', WAIT, 'SHOT:03_choose_player.png',
                  press('UP'), 'A', WAIT, name_keys('AL'), 'A', WAIT, 'SHOT:04_options.png',
                  press('DOWN'), 'A', WAIT, 'B', WAIT, 'SHOT:05_main.png'])
    out, st, sram2 = run(args, 'options', s, sram=sram)
    check(st.nplayers == 2 and st.players[1]['name'] == 'AL' and st.player == 1,
          'a second player AL plays: %d %s %d' % (st.nplayers, st.players[1]['name'], st.player))
    check(st.anim_menus == 0 and st.sound == 0, 'Animated Menus and Sound off')
    newest = max(read_sram(sram2), key=lambda c: c[1])[2]
    check(newest.pack() == st.pack(), 'the options are in the SRAM')
    from PIL import Image
    a = Image.open(os.path.join(out, '01_static.png'))
    b = Image.open(os.path.join(out, '02_static.png'))
    check(a.tobytes() == b.tobytes(), 'nothing moves without Animated Menus')


def all_levels(args, levels):
    # A player with every level done: the top and the bottom of the list.
    st = State()
    st.nplayers, st.player, st.sound, st.anim_menus, st.anim_objects, st.detail = 1, 0, 1, 1, 1, 1
    st.players = [{'name': 'Peter', 'done': levels, 'current': 0, 'skipped': []}]
    st.times = [[] for _ in range(LEVELS)]
    s = ' '.join(['W40 START W120 A', WAIT, 'A', WAIT, 'SHOT:01_list_top.png',
                  ' '.join(['R W12'] * 5), WAIT, 'SHOT:02_list_bottom.png',
                  'L', WAIT, 'SHOT:03_page_up.png', 'B', WAIT,
                  press('DOWN', 'DOWN', 'DOWN'), 'A', WAIT, 'SHOT:04_best_times.png',
                  'B', WAIT, 'CLOCK', 'R', 'W1', 'CLOCK'])
    out, st2, _ = run(args, 'all_levels', s, sram=sram_image(st, levels))
    compare(args, out, [('menu_15_play_all_top.png', '01_list_top.png'),
                        ('menu_16_play_all_bottom.png', '02_list_bottom.png')])


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--rom', default=os.path.join(here, '..', 'build', 'test_ui.sfc'))
    ap.add_argument('--out', default='ui_test_out')
    ap.add_argument('--pcref', help='the shots of the original game (pcref/shots)')
    ap.add_argument('--levels', type=int, default=54, help='LEVEL_COUNT of the ROM')
    args = ap.parse_args()
    sram = first_boot(args, args.levels)
    reboot(args, sram)
    options(args, sram)
    top_ten(args, args.levels)
    garbage(args, args.levels)
    broken_copy(args, args.levels)
    all_levels(args, args.levels)
    print('%d failed' % len(FAILS) if FAILS else 'all passed')
    sys.exit(1 if FAILS else 0)


if __name__ == '__main__':
    main()
