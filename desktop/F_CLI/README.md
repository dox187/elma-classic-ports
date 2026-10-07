# Terminal version (elma-cli)

[All ports](../../README.md) · [SDL desktop ports](../F_SDL/README.md)

`elma-cli` plays the game inside a terminal. It is built from the same game
and physics code as `elma`; only the display, keyboard and timing layer is
different.

- Menus, best times and the in-game timers are shown as terminal text. The
  bouncing balls of the original menus move behind the text.
- The picture of the game is drawn with half blocks, Braille dots or ASCII
  characters. Choose the style under **Options → Terminal Graphics**; the
  choice is saved in `elma-cli.cfg` next to the game data.
- The picture keeps its 4:3 shape and follows the size of the terminal
  window when it is resized.
- The bike keeps its original size (no zoom).
- The level editor is not included in the terminal version.

## Terminal requirements

The game needs to know when a key is released, for example to stop
accelerating, and ordinary terminal input does not report releases. The
terminal must therefore support the
[kitty keyboard protocol](https://sw.kovidgoyal.net/kitty/keyboard-protocol/),
as Ghostty, kitty, foot, Alacritty and WezTerm (with its
`enable_kitty_keyboard` setting) do. In other terminals `elma-cli` exits with
a message.

A terminal with 24-bit color gives the best picture; others get the nearest
of 256 colors.

## Build and run

The build needs CMake 3.13 or newer, a C/C++ compiler, a build tool and
pkg-config. See the dependency commands for
[Linux](../F_SDL/README.md#native-linux-port) or
[macOS](../F_SDL/README.md#native-macos-port). SDL2 is used only for the
sound; without SDL2 the terminal version is still built, but silent.

Run these commands from the repository root:

```sh
cmake -S . -B build -DELMA_BUILD_CLI=ON -DELMA_REGISTERED=ON
cmake --build build --target elma-cli -j
```

Leave out `-DELMA_REGISTERED=ON` for shareware data in a fresh build, or set
it to `OFF` when reusing a registered build directory. The game data must
match the build; see the [game data notes](../F_SDL/README.md#game-data-and-running).

The normal desktop build produces both `elma` and `elma-cli` when SDL2 is
available. Turn off the terminal version with `-DELMA_BUILD_CLI=OFF`;
handheld builds leave it out by default.

Run it from the game directory, like `elma`:

```sh
cd /path/to/ElastoMania
/path/to/elma-classic/build/elma-cli
```

The keys are the same as in the original game. `Ctrl+C` quits at once.

Tested on Linux in Ghostty. The terminal code uses only POSIX interfaces, so
it should also work on macOS in a supported terminal, but it has not been
tested there yet. Windows is not supported.
