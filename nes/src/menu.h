// The menus, in a bank of their own: call them with banked_call( MENU_BANK, ... ).
#ifndef MENU_H
#define MENU_H

#include <stdint.h>

// The level chosen or finished, a new best time of it, and the answer:
extern uint8_t Menu_level, Menu_best, Menu_choice;

void menu_title( void );
// The list of the levels from Menu_level: Menu_choice 1 to play the level
// chosen (copied into Level), 0 to go back.
void menu_levels( void );
// After a finished level: Menu_choice 1 for the next level (copied into
// Level), 0 for the list.
void menu_result( void );

#endif
