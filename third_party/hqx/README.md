# hqx

The hq2x, hq3x and hq4x pixel art scalers of Maxim Stepin, in the C version of
Cameron Zemek and Francois Gannaz (https://github.com/grom358/hqx, commit
a1c7d415f4bb7b947c4c2e47faf220b0148f4bac), under the GNU Lesser General Public
License 2.1 (see `COPYING`). The game uses them to enlarge the pictures of an
LGR file when the level is zoomed.

Changed for Elasto Mania: the RGB to YUV conversion is computed instead of
looked up in a 64 MB table (`common.h`), so `hqxInit` does nothing
(`init.c`). The command line tool `hqx.c` is left out.
