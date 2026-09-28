#include <array>
#include <cstddef>
#include <chrono>
#include <deque>
#include <string>
#include <thread>
#include <vector>

#include "all.h"
#include "F_CLI/CLI_TERM.H"
#include "F_CLI/CLI_RENDER.H"

// Platform layer of the terminal version, the counterpart of
// F_SDL/SDL_PLATFORM.CPP. The game keeps drawing into a 640x480 frame
// buffer; each finished frame is converted to terminal cells.

int Win_95 = 1;
int Margrafikus = 0;
int Locky0_alul = 0;

namespace {
std::array<unsigned char, 640 * 480> pixels;
std::array<unsigned char*, 480> rows;
std::array<uint32_t, 256> palette;
std::array<BYTE, 256> keys;
std::deque<int> chars;
bool locked = false;

std::vector<cli_overlay> overlays;
bool cursor_shown = false;
int cursor_x = 0, cursor_y = 0;

cli_renderer renderer;
int graphics = CLI_GRAPHICS_HALF_BLOCKS;
const char config_name[] = "elma-cli.cfg";
const char* const graphics_names[CLI_GRAPHICS_COUNT] = {"Half Blocks", "Braille", "ASCII"};
const char* const graphics_keys[CLI_GRAPHICS_COUNT] = {"halfblocks", "braille", "ascii"};

typedef std::chrono::steady_clock clock_type;
const clock_type::time_point program_start = clock_type::now();
clock_type::time_point stopper_start = program_start;
clock_type::time_point last_present = program_start;

double seconds_since_start() {
    return std::chrono::duration<double>(clock_type::now() - program_start).count();
}

void load_config() {
    FILE* h = fopen(config_name, "rt");
    if (!h) return;
    char line[100];
    while (fgets(line, sizeof(line), h)) {
        char value[64];
        if (sscanf(line, " graphics = %63s", value) == 1)
            for (int i = 0; i < CLI_GRAPHICS_COUNT; ++i)
                if (strcmp(value, graphics_keys[i]) == 0) graphics = i;
    }
    fclose(h);
}

void save_config() {
    FILE* h = fopen(config_name, "wt");
    if (!h) return;
    fprintf(h, "graphics = %s\n", graphics_keys[graphics]);
    fclose(h);
}

void events() {
    if (!cli_term_active()) return;
    std::vector<cli_key_event> key_events;
    cli_term_poll(&key_events);
    for (size_t i = 0; i < key_events.size(); ++i) {
        const cli_key_event& e = key_events[i];
        if (e.dik == DIK_C && e.ctrl && e.press) mv_exit();
        if (e.dik) keys[e.dik] = e.press ? 0x80 : 0;
        if (e.press && e.character) chars.push_back(e.character);
    }
    // Releases while the window is in the background are not reported:
    if (cli_term_focus_lost()) keys.fill(0);
    if (cli_term_resized()) renderer.invalidate();
}

void present() {
    // Frames at most 60 times a second, like the vertical sync of the SDL
    // version; the game measures real time, so it runs at the same speed.
    const clock_type::time_point next = last_present + std::chrono::microseconds(16667);
    if (clock_type::now() < next) std::this_thread::sleep_until(next);
    last_present = clock_type::now();

    events();
    cli_frame frame;
    frame.pixels = pixels.data();
    frame.palette = palette.data();
    frame.overlays = &overlays;
    frame.cursor = cursor_shown;
    frame.cursor_x = cursor_x;
    frame.cursor_y = cursor_y;
    frame.animated_cursor = State && State->animatedmenus;
    frame.time = seconds_since_start();
    frame.graphics = graphics;

    int cols, rows_count;
    cli_term_size(&cols, &rows_count);
    std::string out;
    renderer.render(frame, cols, rows_count, &out);
    cli_term_write(out);

    overlays.clear();
    cursor_shown = false;
}

// Shows a message box until Enter or Esc, like the original did before it
// quit with a message.
void message_box(const std::vector<std::string>& lines) {
    if (!cli_term_active()) {
        for (size_t i = 0; i < lines.size(); ++i) fprintf(stderr, "%s\n", lines[i].c_str());
        return;
    }
    std::vector<std::string> shown = lines;
    shown.push_back("");
    shown.push_back("Press Enter or Esc");
    bool draw = true;
    chars.clear();
    while (true) {
        if (draw) {
            int cols, rows_count;
            cli_term_size(&cols, &rows_count);
            std::string out;
            renderer.render_message(shown, cols, rows_count, &out);
            cli_term_write(out);
            draw = false;
        }
        std::vector<cli_key_event> key_events;
        cli_term_poll(&key_events);
        for (size_t i = 0; i < key_events.size(); ++i) {
            const int c = key_events[i].press ? key_events[i].character : 0;
            if (c == MK_ENTER || c == MK_ESC || (key_events[i].ctrl && key_events[i].dik == DIK_C)) return;
        }
        if (cli_term_resized()) {
            renderer.invalidate();
            draw = true;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
}

void write_error_file(const std::vector<std::string>& lines) {
    FILE* h = fopen("error.txt", "wt");
    if (!h) return;
    for (size_t i = 0; i < lines.size(); ++i) fprintf(h, "%s\n", lines[i].c_str());
    fclose(h);
}

std::vector<std::string> message_lines(char* a, char* b, char* c) {
    std::vector<std::string> lines;
    if (a) lines.push_back(a);
    if (b) lines.push_back(b);
    if (c) lines.push_back(c);
    return lines;
}

int in_error = 0;
}

void cli_text(const char* text, int x, int y, int align, int color) {
    // Control characters would move the terminal cursor, and the renderer
    // relies on every character taking exactly one cell:
    std::string clean;
    for (const char* p = text; *p; ++p)
        if ((unsigned char)*p >= 0x20 && *p != 0x7f) clean.push_back(*p);
    cli_overlay o = {clean, x, y, align, color};
    overlays.push_back(o);
}

void cli_text_at_pixel(const unsigned char* pixel, const char* text, int align, int color) {
    const std::ptrdiff_t offset = pixel - pixels.data();
    if (offset < 0 || offset >= std::ptrdiff_t(pixels.size())) return;
    cli_text(text, int(offset % 640), int(offset / 640), align, color);
}

void cli_cursor(int x, int y) {
    cursor_shown = true;
    cursor_x = x;
    cursor_y = y;
}

const char* cli_graphics_name() { return graphics_names[graphics]; }

void cli_next_graphics() {
    graphics = (graphics + 1) % CLI_GRAPHICS_COUNT;
    save_config();
    renderer.invalidate();
}

void ddinit() {
    const std::string error = cli_term_init();
    if (!error.empty()) {
        fprintf(stderr, "%s\n", error.c_str());
        exit(1);
    }
    renderer.invalidate();
    Margrafikus = 1;
}

void ddfinish() { cli_term_restore(); }

unsigned char** lockbackbuffer(int) {
    if (locked) hiba((char*)"framebuffer already locked");
    locked = true;
    for (int y = 0; y < 480; ++y)
        rows[Locky0_alul ? 479 - y : y] = pixels.data() + y * 640;
    return rows.data();
}

void unlockbackbuffer() {
    locked = false;
    present();
}
// The game view is the 640x480 picture of the menus as well.
void backbuffersize(int* w, int* h) { *w = 640; *h = 480; }
unsigned char** lockfrontbuffer() { return lockbackbuffer(0); }
void unlockfrontbuffer() { unlockbackbuffer(); }

// 6 bits per color, as a VGA card takes them; repeating the top bits makes
// 63 full brightness instead of 252.
static uint32_t vga_color(unsigned char c) { return uint32_t(c) << 2 | c >> 4; }

ddpal::ddpal(unsigned char* colors) {
    std::array<uint32_t, 256>* value = new std::array<uint32_t, 256>;
    for (int i = 0; i < 256; ++i)
        (*value)[i] = vga_color(colors[i * 3]) << 16 | vga_color(colors[i * 3 + 1]) << 8 |
                      vga_color(colors[i * 3 + 2]);
    pddpal = value;
}
ddpal::~ddpal() { delete static_cast<std::array<uint32_t, 256>*>(pddpal); }
void ddpal::set() { palette = *static_cast<std::array<uint32_t, 256>*>(pddpal); }

// The picture is not scaled in the terminal; it has its own graphics setting.
const char* dd_scale_name() { return NULL; }
void dd_next_scale() {}

void mk_init() {
    keys.fill(0);
    chars.clear();
}
int mk_getextchar() {
    while (chars.empty()) {
        mv_check();
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    const int c = chars.front();
    chars.pop_front();
    return c;
}
void mk_emptychar() {
    events();
    chars.clear();
}
int mk_kbhit() {
    events();
    return !chars.empty();
}
int mk_getstate(int code) {
    events();
    return code >= 0 && code < 256 ? keys[code] : 0;
}
int controlaltnyomva() { return keys[DIK_LMENU] && keys[DIK_LCONTROL]; }

void di_reset_state(state_s* state) {
    state->opciok1.billgaz = DIK_UP; state->opciok1.billfek = DIK_DOWN;
    state->opciok1.billugras1 = DIK_RIGHT; state->opciok1.billugras2 = DIK_LEFT;
    state->opciok1.billfordul = DIK_SPACE; state->opciok1.billview = DIK_V;
    state->opciok1.billtime = DIK_T; state->opciok1.billshowkep = DIK_1;
    state->opciok2.billgaz = DIK_NUMPAD5; state->opciok2.billfek = DIK_NUMPAD2;
    state->opciok2.billugras1 = DIK_NUMPAD3; state->opciok2.billugras2 = DIK_NUMPAD1;
    state->opciok2.billfordul = DIK_NUMPAD0; state->opciok2.billview = DIK_B;
    state->opciok2.billtime = DIK_Y; state->opciok2.billshowkep = DIK_2;
    state->billplussz = DIK_EQUALS; state->billminusz = DIK_MINUS; state->billsnap = DIK_I;
}

// Key names for the Customize Controls menu.
char* kodtobillnev(int code) {
    static char name[32];
    static const struct { int code; const char* name; } names[] = {
        {DIK_ESCAPE, "Esc"}, {DIK_MINUS, "-"}, {DIK_EQUALS, "="}, {DIK_BACK, "Backspace"},
        {DIK_TAB, "Tab"}, {DIK_LBRACKET, "["}, {DIK_RBRACKET, "]"}, {DIK_RETURN, "Enter"},
        {DIK_LCONTROL, "Left Ctrl"}, {DIK_SEMICOLON, ";"}, {DIK_APOSTROPHE, "'"}, {DIK_GRAVE, "`"},
        {DIK_LSHIFT, "Left Shift"}, {DIK_BACKSLASH, "\\"}, {DIK_COMMA, ","}, {DIK_PERIOD, "."},
        {DIK_SLASH, "/"}, {DIK_RSHIFT, "Right Shift"}, {DIK_MULTIPLY, "Num *"}, {DIK_LMENU, "Left Alt"},
        {DIK_SPACE, "Space"}, {DIK_CAPITAL, "Caps Lock"}, {DIK_NUMLOCK, "Num Lock"},
        {DIK_SCROLL, "Scroll Lock"}, {DIK_NUMPAD7, "Num 7"}, {DIK_NUMPAD8, "Num 8"},
        {DIK_NUMPAD9, "Num 9"}, {DIK_SUBTRACT, "Num -"}, {DIK_NUMPAD4, "Num 4"}, {DIK_NUMPAD5, "Num 5"},
        {DIK_NUMPAD6, "Num 6"}, {DIK_ADD, "Num +"}, {DIK_NUMPAD1, "Num 1"}, {DIK_NUMPAD2, "Num 2"},
        {DIK_NUMPAD3, "Num 3"}, {DIK_NUMPAD0, "Num 0"}, {DIK_DECIMAL, "Num ."},
        {DIK_NUMPADENTER, "Num Enter"}, {DIK_RCONTROL, "Right Ctrl"}, {DIK_DIVIDE, "Num /"},
        {DIK_RMENU, "Right Alt"}, {DIK_HOME, "Home"}, {DIK_UP, "Up"}, {DIK_PRIOR, "Page Up"},
        {DIK_LEFT, "Left"}, {DIK_RIGHT, "Right"}, {DIK_END, "End"}, {DIK_DOWN, "Down"},
        {DIK_NEXT, "Page Down"}, {DIK_INSERT, "Insert"}, {DIK_DELETE, "Delete"},
    };
    for (size_t i = 0; i < sizeof(names) / sizeof(names[0]); ++i)
        if (names[i].code == code) return (char*)names[i].name;
    static const char letters[] = "QWERTYUIOP\0\0\0\0ASDFGHJKL\0\0\0\0\0ZXCVBNM";
    if (code >= DIK_Q && code <= DIK_M && letters[code - DIK_Q]) {
        snprintf(name, sizeof(name), "%c", letters[code - DIK_Q]);
        return name;
    }
    if (code >= DIK_1 && code <= DIK_0) {
        snprintf(name, sizeof(name), "%d", (code - DIK_1 + 1) % 10);
        return name;
    }
    if (code >= DIK_F1 && code <= DIK_F10) {
        snprintf(name, sizeof(name), "F%d", code - DIK_F1 + 1);
        return name;
    }
    if (code == DIK_F11 || code == DIK_F12) {
        snprintf(name, sizeof(name), "F%d", code == DIK_F11 ? 11 : 12);
        return name;
    }
    snprintf(name, sizeof(name), "Key %02X", code);
    return name;
}

void mv_check(int) {
    hang();
    events();
}
void mv_startstopper() { stopper_start = clock_type::now(); }
double mv_stopperido() {
    return std::chrono::duration<double>(clock_type::now() - stopper_start).count() * 182.0;
}
void getbiostort(unsigned short* bios, unsigned short* fraction) {
    const uint64_t ticks = std::chrono::duration_cast<std::chrono::microseconds>(
                               clock_type::now().time_since_epoch()).count();
    *bios = static_cast<unsigned short>(ticks >> 16);
    *fraction = static_cast<unsigned short>(ticks);
}
int s_random(int max) { return max > 0 ? rand() % max : 0; }

// There is no mouse in the terminal version (the editor is not included).
void getmou(int* x, int* y) { *x = *y = 0; }
void setmou(int, int) {}
int getbutbmou() { return 0; }
int getbutjmou() { return 0; }

void hiba(char* a, char* b, char* c) {
    const std::vector<std::string> lines = message_lines(a, b, c);
    write_error_file(lines);
    if (!in_error++) {
        std::vector<std::string> shown(1, "Sorry, internal error.");
        shown.insert(shown.end(), lines.begin(), lines.end());
        message_box(shown);
    }
    ddfinish();
    for (size_t i = 0; i < lines.size(); ++i) fprintf(stderr, "%s\n", lines[i].c_str());
    exit(1);
}

void uzenet(char* a, char* b, char* c) {
    const std::vector<std::string> lines = message_lines(a, b, c);
    write_error_file(lines);
    if (!in_error++) message_box(lines);
    ddfinish();
    exit(0);
}

void mv_exit(char*) {
    ddfinish();
    exit(0);
}

int main(int, char**) {
    void upgradehakell(); void initqopen();
    void initmenukep1(); void initmenukep2();
    load_config();
    upgradehakell(); initqopen(); mk_init(); initmenukep1();
    ddinit(); initmenukep2(); mv_main();
    return 0;
}
