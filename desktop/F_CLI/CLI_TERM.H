#ifndef ELMA_CLI_TERM_H
#define ELMA_CLI_TERM_H

#include <string>
#include <vector>

// Terminal handling of the CLI version: raw mode, alternate screen and key
// events through the kitty keyboard protocol, which reports key releases as
// well, so keys can be held like on a real keyboard.

struct cli_key_event {
    int dik;        // DirectInput scan code of the physical key, 0 if none
    int character;  // MK_* code or character for menus, 0 if none
    bool press;     // press or auto-repeat; false for release
    bool repeat;
    bool ctrl;
};

// Returns an error message, or an empty string on success.
std::string cli_term_init();
void cli_term_restore();
bool cli_term_active();

void cli_term_size(int* cols, int* rows);
// True once after the terminal has been resized.
bool cli_term_resized();
// True once after the terminal window has lost focus.
bool cli_term_focus_lost();

void cli_term_write(const std::string& data);
// Reads and decodes the pending input without waiting.
void cli_term_poll(std::vector<cli_key_event>* events);

#endif
