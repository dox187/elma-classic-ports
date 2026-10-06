# Elasto Mania NES demake

An unofficial, fan-made version of Elasto Mania for the Nintendo
Entertainment System. It is a separate program, not a port of the game's
code: the levels of the game are converted into NES graphics and data, and
the physics of the game (`LEPTET.CPP`, `BEALLIT.CPP`) is rewritten in fixed
point and 6502 assembly.

- The 54 internal levels, unlocked one by one; the best time of each level
  is saved in the battery-backed RAM of the cartridge.
- The bike, the rider and the objects are sprites drawn for the NES; the
  ground and the sky of each level are background tiles.
- Not included: the level editor, replays, two players and the LGR
  graphics of the game.

The ROM is an MMC3 cartridge (mapper 4) with 512 KB PRG-ROM, 256 KB
CHR-ROM and 8 KB of battery-backed PRG-RAM. It has been tested in
emulators only.

## Speed

The physics of the game takes steps of 0.003 s of its own time. The NES
takes 50 steps a second by default (`PHYS_HZ=50`), each about three times as
long, and keeps up with the clock on most levels; where it does not, the
game slows down a little. With `PHYS_HZ=60` it takes a step each frame, 2.4
times as long as the game's, but the NES keeps up with only about 75 to 85 %
of the speed. The timer counts the time of the game, so the times are fair
either way.

## Build

Requirements:

- the [llvm-mos SDK](https://github.com/llvm-mos/llvm-mos-sdk), with
  `mos-nes-mmc3-clang` in the `PATH`, in `~/.local/share/llvm-mos` or given
  as `LLVM_MOS=/path/to/llvm-mos`;
- Python 3 with numpy and Pillow;
- `elma.res` from a legally obtained copy of the game.

```sh
cd nes
make ELMA_RES=/path/to/elma.res
```

The ROM is written to `build/elma.nes`. Options:

- `PHYS_HZ=50` or `60`: steps of the physics a second (see above).
- `LEVELS="a.lev b.lev"`: level files added after the internal levels. The
  cartridge has room for little more than the internal levels.

## Controls

| Button            | In the game                        |
|-------------------|------------------------------------|
| A                 | Gas                                |
| B                 | Brake                              |
| Left, Right       | Volt                               |
| Select            | Turn around                        |
| Start             | Play the level again               |
| Start twice       | Back to the list of the levels     |

Start pressed again within half a second of letting it go, with no other
button in between, goes back to the list.

In the list of the levels Up and Down choose a level, Left and Right turn a
page, A plays it and B goes back to the title.

## Tests

`make check ELMA_RES=/path/to/elma.res` runs the fixed point physics next to
the game's physics on the first level, checks that `physics.S` gives the
same bike as `physics.c` to the bit in the simulator of the SDK, and prints
the cycles of a step.

`test/run.py` plays the ROM in the [cynes](https://github.com/Youlixx/cynes)
emulator with a script of buttons and saves screenshots.

## Sources

| File                  | Content                                              |
|-----------------------|------------------------------------------------------|
| `src/physics.c`       | The physics in C: the description of the assembly    |
| `src/physics.S`       | The physics in 6502 assembly, in a bank of its own   |
| `src/mul.s`           | Multiplication with tables of quarter squares        |
| `src/game.c`          | Playing a level: steps, objects, drawing             |
| `src/map.c`           | The map in the nametables, loaded as it scrolls      |
| `src/segs.c`          | The lines of the ground for the physics, by cells    |
| `src/menu.c`          | The title, the list of the levels and the results    |
| `tools/build.py`      | Converts the levels and makes the graphics and data  |
| `tools/physconst.py`  | The constants of the physics                         |
| `test/refphys.c`      | The game's physics in double precision, for the tests |

The original game is © 2000 Balázs Rózsa. This version is not affiliated
with or endorsed by its authors.
