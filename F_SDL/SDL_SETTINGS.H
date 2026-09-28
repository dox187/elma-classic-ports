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
void game_view_size(Aspect aspect, int out_w, int out_h, int* w, int* h);

#endif
