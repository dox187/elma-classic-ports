"""Runs the ROM in the cynes emulator with a script of buttons and saves
screenshots, for testing without a window.

  run.py ROM OUTDIR "START5 W60 A5 W120 SHOT:title R30 ..."

Steps: a button name (A B SELECT START UP DOWN LEFT RIGHT, joined with +)
followed by the number of frames to hold it, W for frames without buttons,
SHOT:name to save the screen as OUTDIR/name.png.
"""

import os
import sys

from cynes import NES
from PIL import Image

BUTTONS = {
    'RIGHT': 0x01, 'LEFT': 0x02, 'DOWN': 0x04, 'UP': 0x08,
    'START': 0x10, 'SELECT': 0x20, 'B': 0x40, 'A': 0x80,
}


def main():
    rom, out, script = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(out, exist_ok=True)
    nes = NES(rom)
    frame = None
    total = 0
    for step in script.split():
        if step.startswith('SHOT:'):
            Image.fromarray(frame).save(os.path.join(out, step[5:] + '.png'))
            continue
        name = step.rstrip('0123456789')
        n = int(step[len(name):] or 1)
        buttons = 0
        if name != 'W':
            for b in name.split('+'):
                buttons |= BUTTONS[b]
        nes.controller = buttons
        frame = nes.step(n)
        total += n
        if nes.has_crashed:
            print('crashed after %d frames' % total)
            break
    print('ran %d frames' % total)


if __name__ == '__main__':
    main()
