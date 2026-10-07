#include <cerrno>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <poll.h>
#include <sys/ioctl.h>
#include <termios.h>
#include <unistd.h>

#include "all.h"
#include "F_CLI/CLI_TERM.H"

namespace {
bool active = false;
struct termios saved_termios;
volatile sig_atomic_t resized = 0;
bool focus_lost = false;
std::string input;

// Pop the keyboard flags and leave the alternate screen (the kitty protocol
// keeps a separate flag stack for it), then restore the normal terminal.
const char leave_sequence[] =
    "\x1b[<u\x1b[?1004l\x1b[?2026l\x1b[0m\x1b[?7h\x1b[?25h\x1b[?1049l";

void write_all(const char* data, size_t size) {
    while (size > 0) {
        const ssize_t written = ::write(STDOUT_FILENO, data, size);
        if (written < 0) {
            if (errno == EINTR) continue;
            return;
        }
        data += written;
        size -= written;
    }
}

// Also called from signal handlers, so it only uses async-signal-safe calls.
void restore_terminal() {
    if (!active) return;
    active = false;
    write_all(leave_sequence, sizeof(leave_sequence) - 1);
    tcsetattr(STDIN_FILENO, TCSAFLUSH, &saved_termios);
}

void on_fatal_signal(int signal_number) {
    restore_terminal();
    signal(signal_number, SIG_DFL);
    raise(signal_number);
}

void on_resize(int) { resized = 1; }

void read_available(int timeout_ms) {
    struct pollfd fd = {STDIN_FILENO, POLLIN, 0};
    while (poll(&fd, 1, timeout_ms) > 0 && (fd.revents & POLLIN)) {
        char buffer[4096];
        const ssize_t count = ::read(STDIN_FILENO, buffer, sizeof(buffer));
        if (count <= 0) break;
        input.append(buffer, count);
        timeout_ms = 0;
    }
}

// Waits for the answer to the kitty keyboard query. The primary device
// attributes request that follows it is answered by every terminal, so its
// answer marks the end of the wait.
bool detect_kitty_protocol() {
    const char query[] = "\x1b[?u\x1b[c";
    write_all(query, sizeof(query) - 1);
    bool kitty = false;
    for (int waited = 0; waited < 2000; waited += 50) {
        read_available(50);
        size_t start;
        while ((start = input.find("\x1b[?")) != std::string::npos) {
            size_t end = start + 3;
            while (end < input.size() && ((input[end] >= '0' && input[end] <= '9') || input[end] == ';'))
                ++end;
            if (end >= input.size()) break;
            const char final = input[end];
            input.erase(0, end + 1);
            if (final == 'u') kitty = true;
            if (final == 'c') return kitty;
        }
    }
    return kitty;
}

int dik_for_key(int key) {
    static const int letters[26] = {
        DIK_A, DIK_B, DIK_C, DIK_D, DIK_E, DIK_F, DIK_G, DIK_H, DIK_I, DIK_J, DIK_K, DIK_L, DIK_M,
        DIK_N, DIK_O, DIK_P, DIK_Q, DIK_R, DIK_S, DIK_T, DIK_U, DIK_V, DIK_W, DIK_X, DIK_Y, DIK_Z};
    if (key >= 'a' && key <= 'z') return letters[key - 'a'];
    if (key >= 'A' && key <= 'Z') return letters[key - 'A'];
    if (key >= '1' && key <= '9') return DIK_1 + (key - '1');
    if (key >= 57399 && key <= 57408) {  // keypad 0-9
        static const int keypad[10] = {DIK_NUMPAD0, DIK_NUMPAD1, DIK_NUMPAD2, DIK_NUMPAD3, DIK_NUMPAD4,
                                       DIK_NUMPAD5, DIK_NUMPAD6, DIK_NUMPAD7, DIK_NUMPAD8, DIK_NUMPAD9};
        return keypad[key - 57399];
    }
    switch (key) {
    case '0': return DIK_0;
    case 27: return DIK_ESCAPE;
    case 13: return DIK_RETURN;
    case 9: return DIK_TAB;
    case 8: case 127: return DIK_BACK;
    case ' ': return DIK_SPACE;
    case '-': return DIK_MINUS;
    case '=': return DIK_EQUALS;
    case '[': return DIK_LBRACKET;
    case ']': return DIK_RBRACKET;
    case ';': return DIK_SEMICOLON;
    case '\'': return DIK_APOSTROPHE;
    case '`': return DIK_GRAVE;
    case '\\': return DIK_BACKSLASH;
    case ',': return DIK_COMMA;
    case '.': return DIK_PERIOD;
    case '/': return DIK_SLASH;
    // Keypad keys, also with Num Lock off:
    case 57409: return DIK_DECIMAL;
    case 57410: return DIK_DIVIDE;
    case 57411: return DIK_MULTIPLY;
    case 57412: return DIK_SUBTRACT;
    case 57413: return DIK_ADD;
    case 57414: return DIK_NUMPADENTER;
    case 57415: return DIK_NUMPADEQUALS;
    case 57417: return DIK_NUMPAD4;
    case 57418: return DIK_NUMPAD6;
    case 57419: return DIK_NUMPAD8;
    case 57420: return DIK_NUMPAD2;
    case 57421: return DIK_NUMPAD9;
    case 57422: return DIK_NUMPAD3;
    case 57423: return DIK_NUMPAD7;
    case 57424: return DIK_NUMPAD1;
    case 57425: return DIK_NUMPAD0;
    case 57426: return DIK_DECIMAL;
    case 57427: return DIK_NUMPAD5;
    // Modifier and lock keys:
    case 57358: return DIK_CAPITAL;
    case 57359: return DIK_SCROLL;
    case 57360: return DIK_NUMLOCK;
    case 57361: return DIK_SYSRQ;
    case 57363: return DIK_APPS;
    case 57441: return DIK_LSHIFT;
    case 57442: return DIK_LCONTROL;
    case 57443: return DIK_LMENU;
    case 57444: return DIK_LWIN;
    case 57447: return DIK_RSHIFT;
    case 57448: return DIK_RCONTROL;
    case 57449: return DIK_RMENU;
    case 57450: return DIK_RWIN;
    case 57376: return DIK_F13;
    case 57377: return DIK_F14;
    case 57378: return DIK_F15;
    default: return 0;
    }
}

int dik_for_tilde(int number) {
    switch (number) {
    case 2: return DIK_INSERT;
    case 3: return DIK_DELETE;
    case 5: return DIK_PRIOR;
    case 6: return DIK_NEXT;
    case 7: return DIK_HOME;
    case 8: return DIK_END;
    case 11: return DIK_F1;
    case 12: return DIK_F2;
    case 13: return DIK_F3;
    case 14: return DIK_F4;
    case 15: return DIK_F5;
    case 17: return DIK_F6;
    case 18: return DIK_F7;
    case 19: return DIK_F8;
    case 20: return DIK_F9;
    case 21: return DIK_F10;
    case 23: return DIK_F11;
    case 24: return DIK_F12;
    default: return 0;
    }
}

// The same characters the SDL version passes to the menus.
int menu_character(int key, int shifted, bool shift) {
    if (key >= 'a' && key <= 'z') {
        if (!shift) return key;
        return (shifted >= 'A' && shifted <= 'Z') ? shifted : key - 'a' + 'A';
    }
    if (key >= '0' && key <= '9') return key;
    switch (key) {
    case 27: return MK_ESC;
    case 13: case 57414: return MK_ENTER;
    case 8: case 127: return MK_BACKSPACE;
    case ' ': return ' ';
    case '-': return '-';
    case '.': return '.';
    default: return 0;
    }
}

// Splits "a:b:c;d:e" into fields and sub-fields; missing numbers are 0.
std::vector<std::vector<int> > split_parameters(const std::string& parameters) {
    std::vector<std::vector<int> > fields(1, std::vector<int>(1, 0));
    for (size_t i = 0; i < parameters.size(); ++i) {
        const char c = parameters[i];
        if (c == ';')
            fields.push_back(std::vector<int>(1, 0));
        else if (c == ':')
            fields.back().push_back(0);
        else if (c >= '0' && c <= '9')
            fields.back().back() = fields.back().back() * 10 + (c - '0');
    }
    return fields;
}

void decode_csi(const std::string& parameters, char final, std::vector<cli_key_event>* events) {
    if (!parameters.empty() && (parameters[0] == '?' || parameters[0] == '>'))
        return;  // answers to queries
    if (final == 'O') {
        focus_lost = true;
        return;
    }
    if (final == 'I') return;

    const std::vector<std::vector<int> > fields = split_parameters(parameters);
    int modifiers = 1, event_type = 1;
    if (fields.size() > 1) {
        if (fields[1][0] > 0) modifiers = fields[1][0];
        if (fields[1].size() > 1 && fields[1][1] > 0) event_type = fields[1][1];
    }
    const int modifier_bits = modifiers - 1;
    const bool shift = modifier_bits & 1;
    const bool ctrl = modifier_bits & 4;

    cli_key_event event = {0, 0, event_type != 3, event_type == 2, ctrl};
    if (final == 'u') {
        const int key = fields[0][0];
        const int shifted = fields[0].size() > 1 ? fields[0][1] : 0;
        const int base = fields[0].size() > 2 ? fields[0][2] : 0;
        // The base layout key gives the physical key like DirectInput did;
        // the characters follow the active keyboard layout.
        event.dik = dik_for_key(base ? base : key);
        event.character = menu_character(key, shifted, shift);
    } else if (final == '~') {
        event.dik = dik_for_tilde(fields[0][0]);
        switch (fields[0][0]) {
        case 3: event.character = MK_DEL; break;
        case 5: event.character = MK_PGUP; break;
        case 6: event.character = MK_PGDOWN; break;
        }
    } else {
        switch (final) {
        case 'A': event.dik = DIK_UP; event.character = MK_UP; break;
        case 'B': event.dik = DIK_DOWN; event.character = MK_DOWN; break;
        case 'C': event.dik = DIK_RIGHT; event.character = MK_RIGHT; break;
        case 'D': event.dik = DIK_LEFT; event.character = MK_LEFT; break;
        case 'H': event.dik = DIK_HOME; break;
        case 'F': event.dik = DIK_END; break;
        case 'E': event.dik = DIK_NUMPAD5; break;
        case 'P': event.dik = DIK_F1; break;
        case 'Q': event.dik = DIK_F2; break;
        case 'S': event.dik = DIK_F4; break;
        default: return;
        }
    }
    if (!event.press) event.character = 0;
    if (event.dik || event.character) events->push_back(event);
}
}

std::string cli_term_init() {
    if (!isatty(STDIN_FILENO) || !isatty(STDOUT_FILENO))
        return "elma-cli must be started in a terminal.";
    if (tcgetattr(STDIN_FILENO, &saved_termios) != 0)
        return "Could not read the terminal settings.";

    struct termios raw = saved_termios;
    raw.c_iflag &= ~(BRKINT | ICRNL | INPCK | ISTRIP | IXON);
    raw.c_oflag &= ~OPOST;
    raw.c_cflag |= CS8;
    raw.c_lflag &= ~(ECHO | ICANON | IEXTEN | ISIG);
    raw.c_cc[VMIN] = 0;
    raw.c_cc[VTIME] = 0;
    if (tcsetattr(STDIN_FILENO, TCSAFLUSH, &raw) != 0)
        return "Could not switch the terminal to raw mode.";
    active = true;

    static bool handlers_installed = false;
    if (!handlers_installed) {
        handlers_installed = true;
        const int fatal[] = {SIGINT, SIGTERM, SIGHUP, SIGQUIT, SIGSEGV, SIGABRT, SIGBUS, SIGFPE};
        for (size_t i = 0; i < sizeof(fatal) / sizeof(fatal[0]); ++i)
            signal(fatal[i], on_fatal_signal);
        struct sigaction action;
        memset(&action, 0, sizeof(action));
        action.sa_handler = on_resize;
        action.sa_flags = SA_RESTART;
        sigaction(SIGWINCH, &action, NULL);
        atexit(cli_term_restore);
    }

    if (!detect_kitty_protocol()) {
        restore_terminal();
        return "This terminal does not support the kitty keyboard protocol, which "
               "elma-cli needs to know when a key is released.\n"
               "Terminals with support: Ghostty, kitty, WezTerm, foot, Alacritty.";
    }
    input.clear();

    // Alternate screen, no cursor, no line wrap; then key events with
    // releases, alternate (physical) keys and all keys as escape codes,
    // and focus change reports.
    const char enter_sequence[] = "\x1b[?1049h\x1b[?25l\x1b[?7l\x1b[2J\x1b[>15u\x1b[?1004h";
    write_all(enter_sequence, sizeof(enter_sequence) - 1);
    return "";
}

void cli_term_restore() { restore_terminal(); }
bool cli_term_active() { return active; }

void cli_term_size(int* cols, int* rows) {
    struct winsize size;
    if (ioctl(STDOUT_FILENO, TIOCGWINSZ, &size) == 0 && size.ws_col > 0 && size.ws_row > 0) {
        *cols = size.ws_col;
        *rows = size.ws_row;
    } else {
        *cols = 80;
        *rows = 24;
    }
}

bool cli_term_resized() {
    if (!resized) return false;
    resized = 0;
    return true;
}

bool cli_term_focus_lost() {
    const bool lost = focus_lost;
    focus_lost = false;
    return lost;
}

void cli_term_write(const std::string& data) { write_all(data.data(), data.size()); }

void cli_term_poll(std::vector<cli_key_event>* events) {
    if (!active) return;
    read_available(0);
    size_t i = 0;
    while (i < input.size()) {
        const unsigned char c = input[i];
        if (c == 0x1b) {
            if (i + 1 >= input.size()) break;  // rest of the sequence not read yet
            if (input[i + 1] != '[') {
                i += 2;
                continue;
            }
            size_t end = i + 2;
            while (end < input.size() && input[end] >= 0x30 && input[end] <= 0x3f) ++end;
            while (end < input.size() && input[end] >= 0x20 && input[end] <= 0x2f) ++end;
            if (end >= input.size()) break;
            decode_csi(input.substr(i + 2, end - i - 2), input[end], events);
            i = end + 1;
            continue;
        }
        // Plain text, for example pasted into a name field:
        if (c >= 32 && c < 127) {
            cli_key_event event = {0, c, true, false, false};
            events->push_back(event);
        }
        ++i;
    }
    input.erase(0, i);
}
