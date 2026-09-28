# Game release
This is NOT a playable release of Elasto Mania. If you're looking to play any of the Elasto Mania games, visit https://elastomania.com.

# Elasto Mania (2000) Source Code
This repository was uploaded in good faith for the purpose of exploring the original source code of this classic game. Non-source-code game assets (sounds, graphics, tools, etc.) are not part of this open source release.

See LICENSE.md for license information.

If you'd like to use this source code in ways other than permitted by the license and this document, contact us at info@elastomania.com.

If you'd like to support continued development of the Elasto Mania franchise, you can do so by buying our games on any store front linked on our website.

*The Elasto Mania Team*

https://elastomania.com

---

# Elma Ports

> The macOS version and the SDL port that the other ports build on were taken
> from the code of [x0o1y](https://github.com/x0o1y/elma) (commit
> [`d2280c7`](https://github.com/x0o1y/elma/commit/d2280c7337f0953ab39549561299101a411c067a),
> *Add native Apple Silicon macOS port*).
>
> The pictures of a zoomed level are enlarged with the
> [hqx](https://github.com/grom358/hqx) scalers (GNU LGPL 2.1, in
> `third_party/hqx`).

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

## Ports

The macOS port replaces the DirectX layer of the Windows version with SDL2.
The Linux port builds on its SDL backend; the handheld ports extend the same
backend with SDL 1.2 and game pads and cross-compile it for ARM. The terminal
version keeps the game and physics code of the Linux port but draws into the
terminal instead of an SDL window, using SDL only for the sound.

1. [Native Linux port](#native-linux-port)
2. [Handheld Linux devices](#handheld-linux-devices)
3. [Terminal version (elma-cli)](#terminal-version-elma-cli)
4. [Native macOS port](#native-macos-port)

## Native Linux port

The SDL2 backend of the macOS port also builds natively on Linux (tested on
Fedora 44, x86_64, GCC 16).

### Dependencies

```sh
sudo dnf install cmake gcc-c++ sdl2-compat-devel   # Fedora
sudo apt install cmake g++ libsdl2-dev             # Debian, Ubuntu
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

### Running

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

### Picture and settings

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

The pictures of the LGR file are enlarged with the nearest pixel when the
level is loaded. At whole-number zooms every pixel becomes an even square; at
other zooms (1.5x, 0.75x, ...) some rows and columns of pixels are wider than
others, which looks uneven on the textures; `zoom_textures = 0` keeps them
crisp.

## Handheld Linux devices

The Miyoo Mini build has been tested on a Miyoo Mini with Onion OS 4.3. The
PortMaster build, for example on ROCKNIX, has not been tested on a device yet,
only in emulation, and neither has MinUI.

The SDL backend also builds for handheld game consoles, cross-compiled in a
container (podman or docker):

- 64-bit ARM handhelds with [PortMaster](https://portmaster.games), for
  example the Powkiddy RGB30 or the Anbernic RG353 and RG35XX H/Plus/SP, on
  ArkOS, ROCKNIX, muOS, Knulli or AmberELEC (SDL 2).
- The Miyoo Mini and Mini Plus with Onion OS or MinUI (SDL 1.2, using the
  Onion toolchain image).

### Build

```sh
handheld/build.sh portmaster -DELMA_REGISTERED=ON
handheld/build.sh miyoomini -DELMA_REGISTERED=ON
```

Leave out `-DELMA_REGISTERED=ON` for the shareware data. The packages are
written to `dist/portmaster` and `dist/miyoomini`. Each contains `LICENSE.md`
and a `NOTICE.txt` with the credits, the source it was built from and the
game data it needs. Keep both with a package when sharing it, only share it
for free, and never add the game data to it.

### Install

- PortMaster: copy `Elasto Mania.sh` and the `elastomania` folder to the
  `ports` folder of the device, then copy the game data (`elma.res`, `lgr`,
  `lev`, and `state.dat` if you want to keep your players and times) into
  `elastomania`. The game shows up among the ports.
- Onion OS, among the ports: copy the `ElastoMania` folder to
  `Roms/PORTS/Games` on the SD card and the game data into it, then copy
  `Elasto Mania.port` to `Roms/PORTS/Shortcuts`. A 256x360 picture saved as
  `Roms/PORTS/Imgs/Elasto Mania.png` is shown as its box art.
- Onion OS, among the apps: copy the `ElastoMania` folder to `App` instead,
  with the game data in it. Put an `icon.png` there for an icon in the Apps
  list.
- MinUI: copy the `ElastoMania` folder to `Tools/miyoomini` on the SD card as
  `Elasto Mania.pak`, and the game data into it.

### Controls

| Button            | In the game                          | In the menus |
|-------------------|--------------------------------------|--------------|
| D-pad, left stick | Up throttle, Down brake, Left/Right rotate | Move   |
| A                 | Throttle                             | Select       |
| B                 | Brake; leaves demos and replays      | Back         |
| X, R1             | Change direction                     | R1: page down |
| Y                 | Toggle navigator                     |              |
| L1                | Toggle time                          | Page up      |
| L2 / R2           | Smaller / larger screen              |              |
| Select            | Leave the level                      | Back         |
| Start             |                                      | Select       |

The buttons press the keys set for player A under Options, Customize
Controls, so they keep working with any key setup. Names are entered with the
d-pad: Up and Down change the last letter, Right starts a new one and Left
deletes one. The level editor needs a mouse and a keyboard, so the handheld
builds leave it out.

The game runs full screen on handhelds, and at 640x480 fills the screen of
most of them. The PortMaster build gives the view of the game the aspect
ratio of the screen (640x640 on the square screen of the RGB30; **Options →
Aspect Ratio** or `aspect = 4:3` for the original view). On other screens it
scales the picture sharply; choose
**Options → Scaling** in the game, `scale = smooth` in `elma.cfg` or
`ELMA_SCALE=smooth` in the launcher for smooth scaling (see
[Picture and settings](#picture-and-settings)). The older
`SDL_RENDER_SCALE_QUALITY=linear` still works when neither of those sets the
scaling. The Miyoo Mini build shows the picture unscaled. `ELMA_FULLSCREEN=0`
or `1` overrides the full screen default on any build.

The zoom works on the handheld builds as well (`zoom` in `elma.cfg`; the
Miyoo Mini has no Options row for it). A zoomed level needs more memory: the
biggest levels of the game data take about 30 MB at zoom 1, 50 MB at zoom 2
and 100 MB at zoom 4 on a 64-bit desktop, so the Miyoo Mini, with 128 MB,
zooms in to 2 at most.

## Terminal version (elma-cli)

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

### Terminal requirements

The game needs to know when a key is released, for example to stop
accelerating, and ordinary terminal input does not report releases. The
terminal must therefore support the
[kitty keyboard protocol](https://sw.kovidgoyal.net/kitty/keyboard-protocol/),
as Ghostty, kitty, foot, Alacritty and WezTerm (with its
`enable_kitty_keyboard` setting) do. In other terminals `elma-cli` exits with
a message.

A terminal with 24-bit color gives the best picture; others get the nearest
of 256 colors.

### Build and run

`elma-cli` is built together with `elma` by the build commands of the Linux
and macOS sections (turn it off with `-DELMA_BUILD_CLI=OFF`); the handheld
builds leave it out. The same `ELMA_REGISTERED` option applies. SDL2 is used
only for the sound; without SDL2 the terminal version is still built, but
silent.

Run it from the game directory, like `elma`:

```sh
cd /path/to/ElastoMania
/path/to/elma-classic/build/elma-cli
```

The keys are the same as in the original game. `Ctrl+C` quits at once.

Tested on Linux in Ghostty. The terminal code uses only POSIX interfaces, so
it should also work on macOS in a supported terminal, but it has not been
tested there yet. Windows is not supported.

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

```sh
cmake -S . -B build -DCMAKE_CXX_COMPILER=/usr/bin/clang++
cmake --build build -j8
```

### Game data

The upstream source release deliberately excludes the copyrighted game data.
Copy these files from a legally obtained Elasto Mania installation:

```text
elma.res
lgr/default.lgr
```

Create empty runtime directories if they do not exist:

```sh
mkdir -p lev rec snaps
```

Run the executable from the repository root so it can find the data:

```sh
./build/elma
```

The current macOS backend provides native video, keyboard, mouse, timing and
sound.
