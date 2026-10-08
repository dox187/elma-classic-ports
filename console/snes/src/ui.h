// Everything outside the levels, as the original game shows it: the intro
// picture, the choice of the player, the menus (MAINMENU.CPP, PLAY.CPP,
// OPTIONS.CPP, BESTTIME.CPP, JATEKOS.CPP, SKIP.CPP) on their background with
// the turning helmet and the balls (MENUKEP.CPP, GOLYOK.CPP). The menus
// own all of VRAM, CGRAM and OAM while they are shown.
//
// Buttons in the menus: Up/Down move, L/R a page up/down (PgUp/PgDn), A or
// Start is Enter, B is Esc. Entering a name: Up/Down change the last letter
// (A-Z, 0-9), Right adds a letter, Left removes the last one (the game pad
// of the original's later versions, nyilasbetu).
//
// The game uses them like this (PLAY.CPP, playlevel):
//
//   ui_intro();                         // intro picture, then the player
//   while( 1 ) {
//       ui_main_menu();                 // returns when Play was chosen
//       while( (level = ui_level_menu()) >= 0 ) {
//           while( 1 ) {
//               ... play the level (Start ends it: not finished) ...
//               r = ui_after_play(level, finished, time_hs);
//               if( r == UI_PLAY_NEXT ) level++;
//               else if( r != UI_PLAY_AGAIN ) break;  // UI_BACK: the list
//           }
//       }
//   }
//
// ui_level_menu and ui_after_play return in forced blank when a level is to
// be played (the game loads it); the other returns keep the menu on the
// screen for the next menu. ui_after_play records the time and the progress
// of the player and writes the SRAM; the game must not do it.
#ifndef UI_H
#define UI_H

#include <snes.h>

// Results:
#define UI_PLAY       1         // ui_main_menu: Play
#define UI_PLAY_AGAIN 2         // ui_after_play: the same level again
#define UI_PLAY_NEXT  3         // ui_after_play: the next level (Play next, Skip level)
#define UI_BACK       4         // ui_after_play: Esc, back to the list of the levels
#define UI_CONTINUE   5         // ui_pause_menu: go on playing
#define UI_QUIT       6         // ui_pause_menu: leave the level

// The intro picture until a button, then the first menu scrolls in: the
// name of a new player, or Choose Player if there are players already.
// Reads the saved state (save_load) first.
void ui_intro(void);
// Main Menu: Play, Options, Help, Best Times; the last three are shown from
// here. Returns UI_PLAY.
u16 ui_main_menu(void);
// Select Level!: the levels finished and the next one. Returns the level
// chosen (0-based, in forced blank), or -1 for Esc.
s16 ui_level_menu(void);
// The menu after a level: finished (time_hs in hundredths) or not (a crash
// or Esc). Records the time and the progress, then Play again, Play next or
// Skip level, Best times. Returns UI_PLAY_AGAIN, UI_PLAY_NEXT (in forced
// blank) or UI_BACK.
u16 ui_after_play(u16 level, u8 finished, u32 time_hs);
// The original game has no pause menu: Esc ends the level at once and shows
// the menu after it (as a crash). Returns UI_QUIT right away.
u16 ui_pause_menu(void);
// The VRAM of the menus was overwritten (the game loaded something): the
// next menu loads it again. Starting a level does this by itself.
void ui_invalidate(void);
// The time as the original shows it (ido2string): "mm:ss:hh", 9 bytes.
void ui_time_string(u32 hs, char* text);

#endif
