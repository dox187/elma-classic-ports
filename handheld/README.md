# Handheld Linux devices

[All ports](../README.md) · [SDL backend and settings](../desktop/F_SDL/README.md)

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

<p>
  <img src="docs/miyoo-mini-v2.jpg" width="400" alt="Elasto Mania running on a Miyoo Mini v2">
</p>

Elasto Mania on a Miyoo Mini v2.

## Requirements

- Podman or Docker on the build host; the script provides the cross compiler,
  CMake and SDL libraries through the toolchain container.
- Game data from a legally obtained installation, matching the shareware or
  registered build. See the [game data notes](../desktop/F_SDL/README.md#game-data-and-running)
  for the required files and Steam data support.

## Build

Run these commands from the repository root:

```sh
handheld/build.sh portmaster -DELMA_REGISTERED=ON
handheld/build.sh miyoomini -DELMA_REGISTERED=ON
```

Leave out `-DELMA_REGISTERED=ON` for the shareware data. The packages are
written to `dist/portmaster` and `dist/miyoomini`. Each contains `LICENSE.md`
and a `NOTICE.txt` with the credits, the source it was built from and the
game data it needs. Keep both with a package when sharing it, only share it
for free, and never add the game data to it.

## Install

- PortMaster: copy `Elasto Mania.sh` and the `elastomania` folder to the
  `ports` folder of the device, then copy the game data (`elma.res`, `lgr`,
  `lev`, and `state.dat` if you want to keep your players and times) into
  `elastomania`. The game shows up among the ports.
- Onion OS, among the ports: copy the `ElastoMania` folder to
  `Roms/PORTS/Games` on the SD card and the game data into it, then copy
  `Elasto Mania.port` to `Roms/PORTS/Shortcuts`, then run **~Import ports**
  at the top of the Ports list. The import only lists the game once it finds
  `Roms/PORTS/Games/ElastoMania/elma.res`; otherwise it renames the shortcut
  to `Elasto Mania.notfound` and hides it, and `Roms/PORTS/import.log` shows
  what it checked. A 256x360 picture saved as
  `Roms/PORTS/Imgs/Elasto Mania.png` is shown as its box art.
- Onion OS, among the apps: copy the `ElastoMania` folder to `App` instead,
  with the game data in it. Put an `icon.png` there for an icon in the Apps
  list.
- MinUI: copy the `ElastoMania` folder to `Tools/miyoomini` on the SD card as
  `Elasto Mania.pak`, and the game data into it.

## Controls

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
[Picture and settings](../desktop/F_SDL/README.md#picture-and-settings)). The older
`SDL_RENDER_SCALE_QUALITY=linear` still works when neither of those sets the
scaling. The Miyoo Mini build shows the picture unscaled. `ELMA_FULLSCREEN=0`
or `1` overrides the full screen default on any build.

The zoom works on the handheld builds as well (`zoom` in `elma.cfg`; the
Miyoo Mini has no Options row for it). A zoomed level needs more memory: the
biggest levels of the game data take about 30 MB at zoom 1, 50 MB at zoom 2
and 100 MB at zoom 4 on a 64-bit desktop, so the Miyoo Mini, with 128 MB,
zooms in to 2 at most.
