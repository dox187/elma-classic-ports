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

#endif
