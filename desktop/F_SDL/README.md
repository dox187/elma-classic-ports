# SDL desktop ports

[All ports](../../README.md) · [Terminal version](../F_CLI/README.md) ·
[Handheld builds](../../handheld/README.md)

The native Linux and macOS ports use SDL2 for video, keyboard, mouse, timing
and sound, with the original game and physics code. The handheld builds use
the same backend with SDL2 or SDL 1.2.

- [Linux requirements and build](#native-linux-port)
- [macOS requirements and build](#native-macos-port)
- [Game data and running](#game-data-and-running)
- [Picture and settings](#picture-and-settings)
- [Fixed bugs](#fixed-bugs)

Run the build commands below from the repository root. Both platforms need
CMake 3.13 or newer, a C/C++ compiler, a build tool and pkg-config, plus SDL2
for the windowed game. The desktop build also produces
[`elma-cli`](../F_CLI/README.md); disable it with `-DELMA_BUILD_CLI=OFF`.

## Native Linux port

The SDL2 backend of the macOS port also builds natively on Linux (tested on
Fedora 44, x86_64, GCC 16).

### Dependencies

```sh
sudo dnf install cmake make gcc-c++ pkgconf-pkg-config sdl2-compat-devel  # Fedora
sudo apt install cmake make g++ pkg-config libsdl2-dev                  # Debian, Ubuntu
```

### Build

The default build is the shareware version, as configured in the upstream
source. To play an installation of the registered game (for example version
1.11a), build with `ELMA_REGISTERED`; that build needs the registered
`elma.res` and cannot read the shareware data.

```sh
cmake -S . -B build -DELMA_REGISTERED=ON
cmake --build build -j
```

The build is optimized (`Release`) unless another `CMAKE_BUILD_TYPE` is
given.

## Native macOS port

This fork adds a native Apple Silicon macOS backend using SDL2. It builds the
original game and physics code as a Mach-O arm64 executable; Wine and DOSBox
are not involved.

### Dependencies

Install CMake and SDL2 compatibility libraries with Homebrew:

```sh
brew install cmake pkg-config sdl2-compat
```

### Build

The default is the shareware version. Add `-DELMA_REGISTERED=ON` for the
registered game data, including the Steam release.

```sh
cmake -S . -B build -DCMAKE_CXX_COMPILER=/usr/bin/clang++
cmake --build build -j8
```

## Game data and running

The source release excludes the copyrighted game data. Copy these files
from a legally obtained Elasto Mania installation, matching the shareware
or registered build:

```text
elma.res
lgr/default.lgr
```

Create empty runtime directories in the game directory if they do not exist:

```sh
mkdir -p lev rec snaps
```

Run the executable from the game directory, next to `elma.res`:

```sh
cd /path/to/ElastoMania
/path/to/elma-classic/build/elma
```

File names are matched case-insensitively, like on Windows, so an original
installation (`Elma.res`, `Lgr/Default.lgr`, `Lev/`, `Rec/`) works without
renaming. The on-disk `state.dat` structures use 32-bit fields, so existing
`state.dat` files keep their players and best times. Sound uses the original
mixer of the Windows version, played through SDL.

The data of the Steam release works with the registered build as well. Copy
`base/elma.res` and the `base/lgr` folder from the Steam installation. Its
`default.lgr` is in the newer LGR13 format of the Steam release, with
pictures of four times the resolution and a larger sky; they are resized to
their size in the game when the level is loaded, so with a zoom or a higher
resolution they show more detail. Copy `base/lgr/orig.lgr` as
`lgr/default.lgr` instead for the look of the original game.

With the Steam data, Play first offers the level collections of the Steam
release (Tutorial, Stolen Internals, Quick & Easy and Quick & Hard) next to
the original and the external levels. As with the original levels, a
collection shows its finished levels and the next one, and Play next moves
on. The levels stay inside `elma.res`, so they cannot be edited. Their best
times and the progress of the players are kept in `state-elma-ports.dat`,
because `state.dat` has no room for them and is shared with the original and
the Steam game.

## Picture and settings

The menus and dialogs fill the window: their background is repeated over it
and their text keeps its original size, so longer lists fit (see
`menu_scale`); the editor is a 640x480 picture. The view of the game
takes the aspect ratio of the window or screen: it keeps the original
scale, 480 pixels high on screens wider than 4:3 (854x480 on 16:9, 768x480 on
16:10, up to 1120x480 on 21:9) and 640 wide on narrower ones (up to 640x640 on
square and portrait screens). On a wide screen the game thus shows more of the
level, more of it ahead of the bike, than the original 4:3 picture, while the
bike keeps its size; `aspect = 4:3` gives the original view. On a desktop the
view is also drawn with more pixels for the same part of the level (see
`resolution` below: 1708x960 on a 1920x1080 screen), so the bike and the edges
of the level are sharp. The window opens at the largest whole multiple of the
view that fits on the screen, and at any window size each picture keeps its
shape, with black bars around it where needed. **Alt+Enter** or **F11** switches between the window and full screen.
The 6-bit palette of the game is widened as VGA hardware showed it, so white
is 255 instead of the 252 of the earlier SDL port.

Settings that `state.dat` has no room for (it stays readable by the original
game) are kept in `elma.cfg` in the game directory, one `key = value` per
line, `#` starting a comment. The game writes the file when such a setting is
changed in the game and keeps its other lines as they were. An environment
variable `ELMA_<KEY>` overrides the file, for example `ELMA_SCALE=smooth`.

| Key          | Values |
|--------------|--------|
| `scale`      | `sharp` (default), `smooth`, `nearest`, `integer` or `pixelart`; also under **Options → Scaling** |
| `aspect`     | `screen` (default): the view of the game takes the aspect ratio of the window, or `4:3`: the original 640x480; also under **Options → Aspect Ratio** |
| `fullscreen` | `1` or `0`; the default is `0` on desktops and `1` on handhelds. Alt+Enter and F11 save it |
| `menu_scale` | the menus fill the window with their background and keep their text at 1:1 pixels, so more fits in the lists; `auto` (default) enlarges them by a whole number only on screens of 2000 rows or more (twice on 4K), a number enlarges them that many times. The editor stays 640x480 |
| `resolution` | how many pixels the view of the game has for the same part of the level: `auto` (default on desktops) multiplies the sizes above by the largest whole number that fits the screen, so the pictures of the level are enlarged evenly (1708x960 on 1920x1080), `native` uses every pixel of the screen, `original` (default on handhelds) the sizes above, or a number of rows such as `720`; also under **Options → Resolution**. It takes effect with the next level |
| `zoom`       | size of the bike and the level on the screen, `0.5` to `4` (default `1`, the original size); also under **Options → Zoom** and with the zoom keys in a game |
| `zoom_textures` | `1` (default): the textures, the sky and the ground as well, are enlarged with the zoom; `0`: they keep their original pixel size, crisper but denser; also under **Options → Zoom Textures** |
| `zoom_grass` | `1` (default): the grass pictures are enlarged with the zoom; `0`: they keep their original size |
| `texture_filter` | how the pictures of the level are resized for the zoom and the resolution: `hqx` (default) enlarges them with the hq2x, hq3x and hq4x pixel art scalers and shrinks them by averaging, `smooth` averages the pixels in both directions (whole multiples stay exact copies), `nearest` repeats or drops pixels as the original scaling did; also under **Options → Texture Filter**. The colors are matched to the palette of the LGR file |
| `zoom_in_key`, `zoom_out_key` | the keys that zoom in and out during a game and a replay: a DirectInput name (`PRIOR`, `NEXT`, `HOME`, `END`, `ADD`, `SUBTRACT`, `Z`, `F5`, ...) or a hex code (`0xC9`), `none` for no key; default `PRIOR` (Page Up) and `NEXT` (Page Down) |

- `sharp` enlarges the picture by a whole number with hard pixel edges and
  smooths only the rest of the way: crisp pixels of even width.
- `smooth` scales bilinearly, with soft edges.
- `nearest` keeps hard edges, but at sizes that are not whole multiples some
  pixels are wider than others, which shimmers when the picture scrolls.
- `integer` only uses whole multiples and leaves a black border; in a window
  smaller than 640x480 the picture is smoothed down.
- `pixelart` uses the pixel art filter of SDL 3, which is only reached
  through sdl2-compat on SDL 3.4 or later (as on Fedora 44). With SDL 2
  itself it looks like `smooth`; the software renderer of SDL 3 (through
  sdl2-compat) shows it like `nearest`.

The game waits for the vertical sync of the display; where showing a frame
does not wait for it, the game keeps to the refresh rate of the display.

The zoom enlarges or shrinks everything in the level together: the bike, the
polygons, the pictures, the objects and the grass. The physics does not
change, so times and replays are the same at any zoom. Zooming in shows less
of the level around the bike, zooming out (below 1) shows more of it. The
navigator keeps its scale. **Options → Zoom** steps through 0.5x to 4x and
takes effect with the next level; **Page Up** and **Page Down** change the
zoom by 0.25 during a game or a replay right away, and save it. A zoom key
that is also set for a player, for the screen size or for the screenshot in
**Options → Customize Controls** is ignored. Changing the zoom rebuilds the
picture of the level, which can take a moment on big levels; that time is not
counted in the game. The level editor always shows the original size.

The pictures of the LGR file are resized when the level is loaded, with the
`texture_filter` setting: by default they are enlarged with the hqx pixel art
scalers and shrunk by averaging their pixels, so that zooms that are not
whole numbers (1.5x, 0.75x, ...) look even as well; `zoom_textures = 0` keeps
the textures at their original size.

## Fixed bugs

- **No sound in the SDL port:** the SDL port was silent. The original mixer of
  the Windows version now plays through SDL on every platform.
- **File names on case-sensitive file systems:** an original installation
  (`Elma.res`, `Lgr/Default.lgr`, `Lev/`) was not found on Linux. Files and
  file lists are now matched case-insensitively, as on Windows.
- **`state.dat` on 64-bit systems:** its structures used `long`, which is
  8 bytes on 64-bit Linux, so existing `state.dat` files could not be read.
  They now use 32-bit fields and keep their players and best times.
- **Level names with a stray line ending:** on Linux, level names kept the
  carriage return of the Windows line ending.
- **Demo and random replays freezing:** the random numbers were summed in a
  signed integer, which overflows with modern C libraries (the original
  compiler's `rand()` went only up to 32767). Optimizing compilers turned the
  loop that corrects a negative sum into an endless loop.
- **Physics on ARM:** `char` is unsigned on ARM, and fused multiply-add
  changes floating point results. The builds use signed `char` and no fused
  multiply-add, so the game and its replays behave as on x86.
- **Editor mouse in a resized window:** the mouse was read in window pixels,
  so in the editor it pointed at the wrong place whenever the window was not
  640x480. It now follows the picture at any window size and on high-DPI
  screens.
- **Internal error outside the level:** a bike that got far out of the level
  (falling below it, or pulled away by a gravity apple) ended the game with an
  internal error, when the picture or the view box reached the edge of the
  area drawn around the level or when the bike left the collision grid to the
  right or above. The bike now dies instead, like in any crash: where the
  full-size 640x480 view of the original would have reached that edge, and at
  the edge of the collision grid, whatever the size of the view. A larger view
  shows ground beyond the edge.
