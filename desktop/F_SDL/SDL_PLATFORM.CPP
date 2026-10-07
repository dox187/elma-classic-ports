#include "all.h"
#include <SDL.h>
#include <array>
#include <chrono>
#include <deque>
#include <string>
#include <vector>

// SDL 2 is used on desktops and on most handhelds; SDL 1.2 on devices that
// only ship that, such as the Miyoo Mini.
#if SDL_MAJOR_VERSION < 2
#define ELMA_SDL1
#endif

int Win_95 = 1;
int Margrafikus = 0;
int Locky0_alul = 0;

namespace {
#ifdef ELMA_SDL1
SDL_Surface* screen = NULL;
// The game is drawn into this surface, which is then blitted to the screen:
// the SDL of the Miyoo Mini turns the picture right side up while blitting,
// but not when flipping.
SDL_Surface* frame = NULL;
std::array<uint32_t, 256> screen_palette;
Uint32 last_flip = 0;
#else
SDL_Window* window = NULL;
SDL_Renderer* renderer = NULL;
SDL_Texture* texture = NULL;
std::array<uint32_t, 640 * 480> rgba;
#endif
std::array<unsigned char, 640 * 480> pixels;
std::array<unsigned char*, 480> rows;
std::array<uint32_t, 256> palette;
std::array<BYTE, 256> keys;
std::deque<int> chars;
bool locked = false;
bool running = true;
std::chrono::steady_clock::time_point stopper_start;

bool env_flag(const char* name, bool fallback) {
    const char* value = getenv(name);
    if (!value || !*value) return fallback;
    return strcmp(value, "0") != 0;
}

bool fullscreen() {
#ifdef ELMA_HANDHELD
    return env_flag("ELMA_FULLSCREEN", true);
#else
    return env_flag("ELMA_FULLSCREEN", false);
#endif
}

// Game pad buttons, named as in SDL's game controller API. The Miyoo Mini
// reports its buttons as keys, which are translated to these as well.
enum Button {
    BUTTON_UP, BUTTON_DOWN, BUTTON_LEFT, BUTTON_RIGHT,
    STICK_UP, STICK_DOWN, STICK_LEFT, STICK_RIGHT,
    BUTTON_A, BUTTON_B, BUTTON_X, BUTTON_Y,
    BUTTON_L1, BUTTON_R1, BUTTON_L2, BUTTON_R2,
    BUTTON_SELECT, BUTTON_START, BUTTON_MENU, BUTTON_COUNT
};

enum Control {
    NO_CONTROL, GAS, BRAKE, ROTATE_LEFT, ROTATE_RIGHT, TURN,
    VIEW, TIME, ZOOM_IN, ZOOM_OUT, LEAVE
};

// While held, a button holds the key that player 1 has bound to its control,
// so the pad works with any key setup in state.dat. When pressed, it also
// sends a menu key.
struct ButtonAction { Control control; int menu; };
const ButtonAction button_actions[BUTTON_COUNT] = {
    { GAS, MK_UP }, { BRAKE, MK_DOWN }, { ROTATE_LEFT, MK_LEFT }, { ROTATE_RIGHT, MK_RIGHT },
    { GAS, MK_UP }, { BRAKE, MK_DOWN }, { ROTATE_LEFT, MK_LEFT }, { ROTATE_RIGHT, MK_RIGHT },
    { GAS, MK_ENTER },       // A
    { BRAKE, MK_ESC },       // B
    { TURN, 0 },             // X
    { VIEW, 0 },             // Y
    { TIME, MK_PGUP },       // L1
    { TURN, MK_PGDOWN },     // R1
    { ZOOM_OUT, 0 },         // L2
    { ZOOM_IN, 0 },          // R2
    { LEAVE, MK_ESC },       // Select
    { NO_CONTROL, MK_ENTER },// Start
    { NO_CONTROL, 0 },       // Menu: left to the system's brightness and volume combos
};

std::array<bool, BUTTON_COUNT> button_down;
std::array<int, BUTTON_COUNT> button_key;
std::array<int, 256> button_keys; // number of pad buttons holding each key

int control_key(Control control) {
    if (control == LEAVE) return DIK_ESCAPE;
    if (!State) return 0;
    const jatekosopciok& player = State->opciok1;
    switch (control) {
    case GAS: return player.billgaz;
    case BRAKE: return player.billfek;
    case ROTATE_LEFT: return player.billugras2;
    case ROTATE_RIGHT: return player.billugras1;
    case TURN: return player.billfordul;
    case VIEW: return player.billview;
    case TIME: return player.billtime;
    case ZOOM_IN: return State->billplussz;
    case ZOOM_OUT: return State->billminusz;
    default: return 0;
    }
}

void press_button(int button, bool down) {
    if (button < 0 || button_down[button] == down) return;
    button_down[button] = down;
    if (down) {
        const ButtonAction& action = button_actions[button];
        const int key = control_key(action.control);
        button_key[button] = key > 0 && key < 256 ? key : 0;
        if (button_key[button]) ++button_keys[button_key[button]];
        if (action.menu) chars.push_back(action.menu);
    } else {
        if (button_key[button]) --button_keys[button_key[button]];
        button_key[button] = 0;
    }
}

void release_buttons() {
    for (int button = 0; button < BUTTON_COUNT; ++button) press_button(button, false);
}

#ifdef ELMA_MIYOO
int miyoo_button(int key) {
    switch (key) {
    case SDLK_UP: return BUTTON_UP; case SDLK_DOWN: return BUTTON_DOWN;
    case SDLK_LEFT: return BUTTON_LEFT; case SDLK_RIGHT: return BUTTON_RIGHT;
    case SDLK_SPACE: return BUTTON_A; case SDLK_LCTRL: return BUTTON_B;
    case SDLK_LSHIFT: return BUTTON_X; case SDLK_LALT: return BUTTON_Y;
    case SDLK_e: return BUTTON_L1; case SDLK_t: return BUTTON_R1;
    case SDLK_TAB: return BUTTON_L2; case SDLK_BACKSPACE: return BUTTON_R2;
    case SDLK_RCTRL: return BUTTON_SELECT; case SDLK_RETURN: return BUTTON_START;
    case SDLK_ESCAPE: return BUTTON_MENU;
    default: return -1;
    }
}
#endif

#ifdef ELMA_SDL1
int dik(int key) {
    static const unsigned char letters[26] = {
        DIK_A, DIK_B, DIK_C, DIK_D, DIK_E, DIK_F, DIK_G, DIK_H, DIK_I,
        DIK_J, DIK_K, DIK_L, DIK_M, DIK_N, DIK_O, DIK_P, DIK_Q, DIK_R,
        DIK_S, DIK_T, DIK_U, DIK_V, DIK_W, DIK_X, DIK_Y, DIK_Z };
    static const unsigned char numpad[10] = {
        DIK_NUMPAD0, DIK_NUMPAD1, DIK_NUMPAD2, DIK_NUMPAD3, DIK_NUMPAD4,
        DIK_NUMPAD5, DIK_NUMPAD6, DIK_NUMPAD7, DIK_NUMPAD8, DIK_NUMPAD9 };
    if (key >= SDLK_a && key <= SDLK_z) return letters[key - SDLK_a];
    if (key >= SDLK_1 && key <= SDLK_9) return DIK_1 + (key - SDLK_1);
    if (key >= SDLK_KP0 && key <= SDLK_KP9) return numpad[key - SDLK_KP0];
    switch (key) {
    case SDLK_0: return DIK_0;
    case SDLK_ESCAPE: return DIK_ESCAPE;
    case SDLK_RETURN: return DIK_RETURN;
    case SDLK_KP_ENTER: return DIK_NUMPADENTER;
    case SDLK_BACKSPACE: return DIK_BACK;
    case SDLK_TAB: return DIK_TAB;
    case SDLK_SPACE: return DIK_SPACE;
    case SDLK_MINUS: return DIK_MINUS;
    case SDLK_EQUALS: return DIK_EQUALS;
    case SDLK_PERIOD: return DIK_PERIOD;
    case SDLK_COMMA: return DIK_COMMA;
    case SDLK_UP: return DIK_UP; case SDLK_DOWN: return DIK_DOWN;
    case SDLK_LEFT: return DIK_LEFT; case SDLK_RIGHT: return DIK_RIGHT;
    case SDLK_PAGEUP: return DIK_PRIOR; case SDLK_PAGEDOWN: return DIK_NEXT;
    case SDLK_DELETE: return DIK_DELETE;
    case SDLK_LCTRL: return DIK_LCONTROL; case SDLK_RCTRL: return DIK_RCONTROL;
    case SDLK_LSHIFT: return DIK_LSHIFT; case SDLK_RSHIFT: return DIK_RSHIFT;
    case SDLK_LALT: return DIK_LMENU; case SDLK_RALT: return DIK_RMENU;
    default: return 0;
    }
}
#else
int dik(SDL_Scancode code) {
    switch (code) {
    case SDL_SCANCODE_ESCAPE: return DIK_ESCAPE;
    case SDL_SCANCODE_1: return DIK_1; case SDL_SCANCODE_2: return DIK_2;
    case SDL_SCANCODE_3: return DIK_3; case SDL_SCANCODE_4: return DIK_4;
    case SDL_SCANCODE_5: return DIK_5; case SDL_SCANCODE_6: return DIK_6;
    case SDL_SCANCODE_7: return DIK_7; case SDL_SCANCODE_8: return DIK_8;
    case SDL_SCANCODE_9: return DIK_9; case SDL_SCANCODE_0: return DIK_0;
    case SDL_SCANCODE_A: return DIK_A; case SDL_SCANCODE_B: return DIK_B;
    case SDL_SCANCODE_C: return DIK_C; case SDL_SCANCODE_D: return DIK_D;
    case SDL_SCANCODE_E: return DIK_E; case SDL_SCANCODE_F: return DIK_F;
    case SDL_SCANCODE_G: return DIK_G; case SDL_SCANCODE_H: return DIK_H;
    case SDL_SCANCODE_I: return DIK_I; case SDL_SCANCODE_J: return DIK_J;
    case SDL_SCANCODE_K: return DIK_K; case SDL_SCANCODE_L: return DIK_L;
    case SDL_SCANCODE_M: return DIK_M; case SDL_SCANCODE_N: return DIK_N;
    case SDL_SCANCODE_O: return DIK_O; case SDL_SCANCODE_P: return DIK_P;
    case SDL_SCANCODE_Q: return DIK_Q; case SDL_SCANCODE_R: return DIK_R;
    case SDL_SCANCODE_S: return DIK_S; case SDL_SCANCODE_T: return DIK_T;
    case SDL_SCANCODE_U: return DIK_U; case SDL_SCANCODE_V: return DIK_V;
    case SDL_SCANCODE_W: return DIK_W; case SDL_SCANCODE_X: return DIK_X;
    case SDL_SCANCODE_Y: return DIK_Y; case SDL_SCANCODE_Z: return DIK_Z;
    case SDL_SCANCODE_RETURN: return DIK_RETURN;
    case SDL_SCANCODE_KP_ENTER: return DIK_NUMPADENTER;
    case SDL_SCANCODE_BACKSPACE: return DIK_BACK;
    case SDL_SCANCODE_TAB: return DIK_TAB;
    case SDL_SCANCODE_SPACE: return DIK_SPACE;
    case SDL_SCANCODE_MINUS: return DIK_MINUS;
    case SDL_SCANCODE_EQUALS: return DIK_EQUALS;
    case SDL_SCANCODE_PERIOD: return DIK_PERIOD;
    case SDL_SCANCODE_COMMA: return DIK_COMMA;
    case SDL_SCANCODE_UP: return DIK_UP; case SDL_SCANCODE_DOWN: return DIK_DOWN;
    case SDL_SCANCODE_LEFT: return DIK_LEFT; case SDL_SCANCODE_RIGHT: return DIK_RIGHT;
    case SDL_SCANCODE_PAGEUP: return DIK_PRIOR; case SDL_SCANCODE_PAGEDOWN: return DIK_NEXT;
    case SDL_SCANCODE_DELETE: return DIK_DELETE;
    case SDL_SCANCODE_LCTRL: return DIK_LCONTROL; case SDL_SCANCODE_RCTRL: return DIK_RCONTROL;
    case SDL_SCANCODE_LSHIFT: return DIK_LSHIFT; case SDL_SCANCODE_RSHIFT: return DIK_RSHIFT;
    case SDL_SCANCODE_LALT: return DIK_LMENU; case SDL_SCANCODE_RALT: return DIK_RMENU;
    case SDL_SCANCODE_KP_0: return DIK_NUMPAD0; case SDL_SCANCODE_KP_1: return DIK_NUMPAD1;
    case SDL_SCANCODE_KP_2: return DIK_NUMPAD2; case SDL_SCANCODE_KP_3: return DIK_NUMPAD3;
    case SDL_SCANCODE_KP_4: return DIK_NUMPAD4; case SDL_SCANCODE_KP_5: return DIK_NUMPAD5;
    case SDL_SCANCODE_KP_6: return DIK_NUMPAD6; case SDL_SCANCODE_KP_7: return DIK_NUMPAD7;
    case SDL_SCANCODE_KP_8: return DIK_NUMPAD8; case SDL_SCANCODE_KP_9: return DIK_NUMPAD9;
    default: return 0;
    }
}

int controller_button(int button) {
    switch (button) {
    case SDL_CONTROLLER_BUTTON_DPAD_UP: return BUTTON_UP;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: return BUTTON_DOWN;
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: return BUTTON_LEFT;
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: return BUTTON_RIGHT;
    case SDL_CONTROLLER_BUTTON_A: return BUTTON_A;
    case SDL_CONTROLLER_BUTTON_B: return BUTTON_B;
    case SDL_CONTROLLER_BUTTON_X: return BUTTON_X;
    case SDL_CONTROLLER_BUTTON_Y: return BUTTON_Y;
    case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: return BUTTON_L1;
    case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: return BUTTON_R1;
    case SDL_CONTROLLER_BUTTON_BACK: return BUTTON_SELECT;
    case SDL_CONTROLLER_BUTTON_START: return BUTTON_START;
    case SDL_CONTROLLER_BUTTON_GUIDE: return BUTTON_MENU;
    default: return -1;
    }
}

// The left stick works as a second d-pad and the triggers as buttons.
void controller_axis(int axis, int value) {
    const int threshold = 16000;
    switch (axis) {
    case SDL_CONTROLLER_AXIS_LEFTX:
        press_button(STICK_LEFT, value < -threshold);
        press_button(STICK_RIGHT, value > threshold);
        break;
    case SDL_CONTROLLER_AXIS_LEFTY:
        press_button(STICK_UP, value < -threshold);
        press_button(STICK_DOWN, value > threshold);
        break;
    case SDL_CONTROLLER_AXIS_TRIGGERLEFT: press_button(BUTTON_L2, value > threshold); break;
    case SDL_CONTROLLER_AXIS_TRIGGERRIGHT: press_button(BUTTON_R2, value > threshold); break;
    }
}
#endif

int character(const SDL_KeyboardEvent& event) {
    const int key = event.keysym.sym;
    if (key >= SDLK_a && key <= SDLK_z)
        return (event.keysym.mod & KMOD_SHIFT) ? key - SDLK_a + 'A' : key;
    if (key >= SDLK_0 && key <= SDLK_9) return key;
    switch (key) {
    case SDLK_ESCAPE: return MK_ESC; case SDLK_RETURN: return MK_ENTER;
    case SDLK_UP: return MK_UP; case SDLK_DOWN: return MK_DOWN;
    case SDLK_LEFT: return MK_LEFT; case SDLK_RIGHT: return MK_RIGHT;
    case SDLK_PAGEUP: return MK_PGUP; case SDLK_PAGEDOWN: return MK_PGDOWN;
    case SDLK_DELETE: return MK_DEL; case SDLK_BACKSPACE: return MK_BACKSPACE;
    case SDLK_SPACE: return ' '; case SDLK_MINUS: return '-'; case SDLK_PERIOD: return '.';
    default: return 0;
    }
}

void key_event(const SDL_KeyboardEvent& event, bool down, bool repeat) {
#ifdef ELMA_MIYOO
    const int button = miyoo_button(event.keysym.sym);
    if (button >= 0) {
        press_button(button, down);
        return;
    }
#endif
#ifdef ELMA_SDL1
    const int code = dik(event.keysym.sym);
#else
    const int code = dik(event.keysym.scancode);
#endif
    if (code) keys[code] = down ? 0x80 : 0;
    if (down && !repeat) {
        const int c = character(event);
        if (c) chars.push_back(c);
    }
}

void events() {
    SDL_Event event;
    while (SDL_PollEvent(&event)) {
        switch (event.type) {
        case SDL_QUIT: running = false; break;
#ifdef ELMA_SDL1
        case SDL_KEYDOWN: case SDL_KEYUP:
            key_event(event.key, event.type == SDL_KEYDOWN, false);
            break;
#else
        case SDL_KEYDOWN: case SDL_KEYUP:
            key_event(event.key, event.type == SDL_KEYDOWN, event.key.repeat != 0);
            break;
        case SDL_CONTROLLERDEVICEADDED:
            SDL_GameControllerOpen(event.cdevice.which);
            break;
        case SDL_CONTROLLERDEVICEREMOVED:
            if (SDL_GameController* controller = SDL_GameControllerFromInstanceID(event.cdevice.which))
                SDL_GameControllerClose(controller);
            release_buttons();
            break;
        case SDL_CONTROLLERBUTTONDOWN: case SDL_CONTROLLERBUTTONUP:
            press_button(controller_button(event.cbutton.button), event.type == SDL_CONTROLLERBUTTONDOWN);
            break;
        case SDL_CONTROLLERAXISMOTION:
            controller_axis(event.caxis.axis, event.caxis.value);
            break;
#endif
        }
    }
    if (!running) mv_exit();
}

#ifdef ELMA_SDL1
void map_palette() {
    if (!frame) return;
    for (int i = 0; i < 256; ++i)
        screen_palette[i] = SDL_MapRGB(frame->format, palette[i] >> 16 & 0xff,
                                       palette[i] >> 8 & 0xff, palette[i] & 0xff);
}

template <typename Pixel>
void convert(Uint8* target, int pitch) {
    for (int y = 0; y < 480; ++y) {
        const unsigned char* source = pixels.data() + y * 640;
        Pixel* line = reinterpret_cast<Pixel*>(target + y * pitch);
        for (int x = 0; x < 640; ++x) line[x] = static_cast<Pixel>(screen_palette[source[x]]);
    }
}

void present() {
    if (SDL_MUSTLOCK(frame) && SDL_LockSurface(frame) != 0) return;
    Uint8* target = static_cast<Uint8*>(frame->pixels);
    if (frame->format->BytesPerPixel == 4) convert<Uint32>(target, frame->pitch);
    else convert<Uint16>(target, frame->pitch);
    if (SDL_MUSTLOCK(frame)) SDL_UnlockSurface(frame);
    // A larger screen than 640x480 shows the game centered.
    SDL_Rect place;
    place.x = static_cast<Sint16>((screen->w - 640) / 2);
    place.y = static_cast<Sint16>((screen->h - 480) / 2);
    place.w = 640;
    place.h = 480;
    SDL_BlitSurface(frame, NULL, screen, &place);
    SDL_Flip(screen);
    // SDL 1.2 does not always wait for the display; keep to 60 frames per
    // second so the menus do not keep the CPU busy.
    const Uint32 frame_time = 16;
    const Uint32 elapsed = SDL_GetTicks() - last_flip;
    if (elapsed < frame_time) SDL_Delay(frame_time - elapsed);
    last_flip = SDL_GetTicks();
}
#else
void present() {
    for (size_t i = 0; i < pixels.size(); ++i) rgba[i] = palette[pixels[i]];
    SDL_UpdateTexture(texture, NULL, rgba.data(), 640 * sizeof(uint32_t));
    SDL_RenderClear(renderer);
    SDL_RenderCopy(renderer, texture, NULL, NULL);
    SDL_RenderPresent(renderer);
}
#endif
}

#ifdef ELMA_SDL1
void ddinit() {
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_TIMER) != 0) {
        fprintf(stderr, "SDL_Init: %s\n", SDL_GetError());
        exit(1);
    }
    SDL_WM_SetCaption("Elasto Mania", NULL);
    Uint32 flags = SDL_HWSURFACE | SDL_DOUBLEBUF;
    if (fullscreen()) flags |= SDL_FULLSCREEN;
    screen = SDL_SetVideoMode(640, 480, 32, flags);
    if (screen) {
        const SDL_PixelFormat* format = screen->format;
        frame = SDL_CreateRGBSurface(SDL_HWSURFACE, 640, 480, format->BitsPerPixel,
                                     format->Rmask, format->Gmask, format->Bmask, format->Amask);
    }
    if (!frame || (frame->format->BytesPerPixel != 2 && frame->format->BytesPerPixel != 4)) {
        fprintf(stderr, "SDL video: %s\n", frame ? "unsupported screen format" : SDL_GetError());
        SDL_Quit();
        exit(1);
    }
    map_palette();
#ifdef ELMA_HANDHELD
    SDL_ShowCursor(SDL_DISABLE);
#endif
    Margrafikus = 1;
}

void ddfinish() {
    if (frame) SDL_FreeSurface(frame);
    frame = NULL; screen = NULL;
    SDL_Quit();
}
#else
void ddinit() {
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_EVENTS | SDL_INIT_TIMER) != 0) {
        fprintf(stderr, "SDL_Init: %s\n", SDL_GetError());
        exit(1);
    }
    // Game pads are optional; the connected ones arrive as device events.
    if (SDL_InitSubSystem(SDL_INIT_GAMECONTROLLER) == 0)
        SDL_GameControllerAddMappingsFromFile("gamecontrollerdb.txt");
    Uint32 flags = SDL_WINDOW_ALLOW_HIGHDPI | SDL_WINDOW_RESIZABLE;
    if (fullscreen()) flags |= SDL_WINDOW_FULLSCREEN_DESKTOP;
    window = SDL_CreateWindow("Elasto Mania", SDL_WINDOWPOS_CENTERED,
                              SDL_WINDOWPOS_CENTERED, 640, 480, flags);
    if (!window) {
        fprintf(stderr, "SDL_CreateWindow: %s\n", SDL_GetError());
        SDL_Quit();
        exit(1);
    }
    renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
    if (!renderer) renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_SOFTWARE);
    texture = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_ARGB8888,
                                SDL_TEXTUREACCESS_STREAMING, 640, 480);
    SDL_RenderSetLogicalSize(renderer, 640, 480);
#ifdef ELMA_HANDHELD
    SDL_ShowCursor(SDL_DISABLE);
#endif
    Margrafikus = 1;
}

void ddfinish() {
    if (texture) SDL_DestroyTexture(texture);
    if (renderer) SDL_DestroyRenderer(renderer);
    if (window) SDL_DestroyWindow(window);
    texture = NULL; renderer = NULL; window = NULL;
    SDL_Quit();
}
#endif

unsigned char** lockbackbuffer(int) {
    if (locked) hiba((char*)"framebuffer already locked");
    locked = true;
    for (int y = 0; y < 480; ++y)
        rows[Locky0_alul ? 479 - y : y] = pixels.data() + y * 640;
    return rows.data();
}

void unlockbackbuffer() { locked = false; present(); }
unsigned char** lockfrontbuffer() { return lockbackbuffer(0); }
void unlockfrontbuffer() { unlockbackbuffer(); }

ddpal::ddpal(unsigned char* colors) {
    std::array<uint32_t, 256>* value = new std::array<uint32_t, 256>;
    for (int i = 0; i < 256; ++i) {
        const uint32_t r = colors[i * 3] << 2;
        const uint32_t g = colors[i * 3 + 1] << 2;
        const uint32_t b = colors[i * 3 + 2] << 2;
        (*value)[i] = 0xff000000u | r << 16 | g << 8 | b;
    }
    pddpal = value;
}
ddpal::~ddpal() { delete static_cast<std::array<uint32_t, 256>*>(pddpal); }
void ddpal::set() {
    palette = *static_cast<std::array<uint32_t, 256>*>(pddpal);
#ifdef ELMA_SDL1
    map_palette();
#endif
}

void mk_init() { keys.fill(0); button_keys.fill(0); button_key.fill(0); button_down.fill(false); chars.clear(); }
int mk_getextchar() { while (chars.empty()) { mv_check(); SDL_Delay(1); } int c = chars.front(); chars.pop_front(); return c; }
void mk_emptychar() { events(); chars.clear(); }
int mk_kbhit() { events(); return !chars.empty(); }
int mk_getstate(int code) {
    events();
    if (code < 0 || code >= 256) return 0;
    return keys[code] || button_keys[code] ? 0x80 : 0;
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

char* kodtobillnev(int code) {
    static char name[32];
    snprintf(name, sizeof(name), "KEY %02X", code);
    return name;
}

void mv_check(int) { hang(); events(); }
void mv_startstopper() { stopper_start = std::chrono::steady_clock::now(); }
double mv_stopperido() {
    const std::chrono::duration<double> elapsed = std::chrono::steady_clock::now() - stopper_start;
    return elapsed.count() * 182.0;
}
void getbiostort(unsigned short* bios, unsigned short* fraction) {
    const uint64_t ticks = std::chrono::steady_clock::now().time_since_epoch().count();
    *bios = static_cast<unsigned short>(ticks >> 16);
    *fraction = static_cast<unsigned short>(ticks);
}
int s_random(int max) { return max > 0 ? rand() % max : 0; }

void getmou(int* x, int* y) { SDL_GetMouseState(x, y); }
#ifdef ELMA_SDL1
void setmou(int x, int y) { SDL_WarpMouse(x, y); }
#else
void setmou(int x, int y) { SDL_WarpMouseInWindow(window, x, y); }
#endif
int getbutbmou() { return SDL_GetMouseState(NULL, NULL) & SDL_BUTTON(SDL_BUTTON_LEFT); }
int getbutjmou() { return SDL_GetMouseState(NULL, NULL) & SDL_BUTTON(SDL_BUTTON_RIGHT); }

static std::string message(char* a, char* b, char* c) {
    std::string text = a ? a : "";
    if (b) text += std::string("\n") + b;
    if (c) text += std::string("\n") + c;
    return text;
}
#ifdef ELMA_SDL1
void hiba(char* a, char* b, char* c) {
    fprintf(stderr, "%s\n", message(a, b, c).c_str());
    ddfinish(); exit(1);
}
void uzenet(char* a, char* b, char* c) { fprintf(stderr, "%s\n", message(a, b, c).c_str()); }
#else
void hiba(char* a, char* b, char* c) {
    const std::string text = message(a, b, c);
    fprintf(stderr, "%s\n", text.c_str());
    if (window) SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR, "Elasto Mania", text.c_str(), window);
    ddfinish(); exit(1);
}
void uzenet(char* a, char* b, char* c) {
    const std::string text = message(a, b, c);
    if (window) SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_INFORMATION, "Elasto Mania", text.c_str(), window);
    else fprintf(stderr, "%s\n", text.c_str());
}
#endif
void mv_exit(char*) { ddfinish(); exit(0); }

int main(int, char**) {
    void upgradehakell(); void initqopen();
    void initmenukep1(); void initmenukep2();
    upgradehakell(); initqopen(); mk_init(); initmenukep1();
    ddinit(); initmenukep2(); mv_main();
    return 0;
}
