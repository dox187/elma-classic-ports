"""Verify custom gameplay bindings survive option saves and SRAM reboot.

The former Navigator key occupies the same KEY_VIEW slot as Apple Counter.
Uses the existing UI test's SRAM encoder, menu script and state decoder.
"""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import ui_test


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--rom', default='build/test_ui.sfc')
    ap.add_argument('--out', default='build/keys_persist')
    ap.add_argument('--levels', type=int, default=54)
    a = ap.parse_args()
    st = ui_test.State()
    st.nplayers, st.player = 1, 0
    st.sound = st.anim_menus = st.anim_objects = st.detail = 1
    st.players[0] = {'name': 'BOB', 'done': 1, 'current': 0, 'skipped': []}
    # Every binding differs from defaults, including Apple Counter and Time.
    st.keys = [0x0010, 0x0040, 0x0100, 0x0200, 0x0080, 0x4000, 0x8000]
    image = ui_test.sram_image(st, a.levels)
    args = SimpleNamespace(rom=a.rom, out=a.out, levels=a.levels, pcref=None)
    ui_test.options(args, image)
    saved = (Path(a.out) / 'options/sram.bin').read_bytes()
    copies = ui_test.read_sram(saved)
    newest = max(copies, key=lambda copy: copy[1])[2]
    ui_test.check(newest.keys == st.keys, 'all custom bindings persist through an options save')
    _, restored, _ = ui_test.run(args, 'keys_reboot', 'W40 START W120 A W50', sram=saved)
    ui_test.check(restored.keys == st.keys, 'all custom bindings persist through reboot')
    result = {'ok': not ui_test.FAILS, 'keys': restored.keys,
              'apple_counter_key': restored.keys[5], 'failures': ui_test.FAILS}
    (Path(a.out) / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    return 1 if ui_test.FAILS else 0


if __name__ == '__main__':
    raise SystemExit(main())
