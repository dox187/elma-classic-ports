#ifndef ELMA_SDL_SETTINGS_H
#define ELMA_SDL_SETTINGS_H

// Settings of the SDL port that state.dat has no room for, since it has to
// stay readable by the original game. They are kept in elma.cfg next to it,
// one "key = value" per line; # starts a comment. An environment variable
// ELMA_<KEY>, for example ELMA_SCALE, overrides the value in the file.

// Reads elma.cfg; without the file every setting keeps its default.
void config_load();
// The value of key, or fallback if neither the environment nor the file sets
// it. The text stays valid until the next config_set or config_load.
const char* config_get(const char* key, const char* fallback);
// Changes a value of the file; config_save writes it, keeping the comments,
// the keys this version does not know and the line endings.
void config_set(const char* key, const char* value);
void config_save();

// The aspect ratio of the game view (aspect in elma.cfg): that of the window
// or screen, or the 4:3 of the original game.
enum Aspect { ASPECT_SCREEN, ASPECT_4_3, ASPECT_COUNT };
Aspect config_aspect();
const char* aspect_key(Aspect aspect);  // as in elma.cfg: screen, 4:3
const char* aspect_name(Aspect aspect); // as in the Options menu: Screen, 4:3

// The size of the game view for an output of out_w x out_h pixels. The game
// is drawn at its original scale, so a wider or taller output shows more of
// the level. 4:3 gives the original 640x480. For the screen, the aspect ratio
// out_w/out_h is kept between 1 and 21:9 (a wider or taller output gets black
// bars); from 4:3 up the view is 480 high and as wide as the ratio, rounded to
// an even number (1920x1080: 854x480, 2560x1080 and wider: 1120x480), below
// 4:3 it is 640 wide and as high as the ratio (720x720 and taller: 640x640).
// With the resolution setting below, the view gets more pixels for the same
// part of the level; base_view_size gives the size without it.
void base_view_size(Aspect aspect, int out_w, int out_h, int* w, int* h);
void game_view_size(Aspect aspect, int out_w, int out_h, int* w, int* h);

// How many pixels the game view has (resolution in elma.cfg): original, the
// sizes above, which the window then enlarges; auto (the default on desktops),
// those sizes times the largest whole number that fits the output, so that
// the pictures of the level are enlarged evenly (1920x1080: 1708x960);
// native, as many pixels as the output; or a number of rows. The game shows
// the same part of the level, in more detail. At most MAXKEPXSIZE x
// MAXKEPYSIZE.
enum { RESOLUTION_ORIGINAL = 0, RESOLUTION_AUTO = -1, RESOLUTION_NATIVE = -2 };
int config_resolution(); // one of these, or the number of rows
void set_config_resolution(int resolution);
const char* resolution_name(int resolution); // as in the Options menu: Auto, 1080
int next_resolution_option(int resolution);  // Auto, Native, Original, Auto...

// The size of the menus for an output of out_w x out_h pixels: the menus fill
// it with their background and keep their text at 1:1 pixels, so more fits
// (menu_scale in elma.cfg: auto, the default, enlarges them by a whole number
// only on screens over 2000 rows; a number enlarges them that many times). At
// least 640x480.
void menu_view_size(int out_w, int out_h, int* w, int* h);

// A setting of elma.cfg that is 0 or 1 (anything else than 0 is 1).
bool config_flag(const char* key, bool fallback);

// The size of the bike on the screen (zoom in elma.cfg): 1 is the original
// size, from NAGYITASMIN (0.5) to NAGYITASMAX (4); a value out of range is
// taken to the nearest limit, one that is no number is 1. It is read once;
// set_config_zoom changes it and saves it into elma.cfg.
double config_zoom();
void set_config_zoom(double zoom);
// Whether the textures (the sky and the ground as well) are zoomed with the
// bike (zoom_textures, default 1), and whether the grass pictures are
// (zoom_grass, default 1). Also read once; set_config_zoom_textures saves.
bool config_zoom_textures();
void set_config_zoom_textures(bool on);
bool config_zoom_grass();
// The DirectInput code of the key that zooms in or out during a game or a
// replay (zoom_in_key, zoom_out_key: a name such as PRIOR, DIK_NEXT, PGUP or
// ADD, or a hex code such as 0xC9; none for no key). Default PageUp and
// PageDown.
int config_zoom_key(bool zoom_in);
// The zoom as the Options menu shows it: 1x, 1.25x. The text stays valid
// until the next call.
const char* zoom_name(double zoom);
// The value after zoom in the Options menu: 0.5, 0.75, 1, 1.25, 1.5, 1.75,
// 2, 2.5, 3, 3.5, 4, then 0.5 again.
double next_zoom_option(double zoom);

#endif
