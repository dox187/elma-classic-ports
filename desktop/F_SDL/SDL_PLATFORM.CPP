#include "all.h"
#include "SDL_SETTINGS.H"
#include <SDL.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <deque>
#include <string>
#include <vector>
#ifdef ELMA_PS3
#include "PS3_PLATFORM.H"
#include "PS3_MEMORY.H"
#include "PS3_CONTROLS.H"
#include "PS3_INPUT_CONTEXT.H"
#include "PAUSE_CLOCK.H"
#include "MEMORY_BUDGET.H"
#endif

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
// The game, the menus and the editor all draw into this 640x480 picture.
std::array<unsigned char, 640 * 480> pixels;
std::array<unsigned char*, 480> rows;
#else
SDL_Window* window = NULL;
SDL_Renderer* renderer = NULL;
#endif
std::array<uint32_t, 256> palette;
std::array<BYTE, 256> keys;
std::deque<int> chars;
bool locked = false;
bool running = true;
#ifdef ELMA_PS3
elma_pause_clock<std::chrono::steady_clock> stopper_clock;
#else
std::chrono::steady_clock::time_point stopper_start;
#endif

bool fullscreen() {
#if defined(ELMA_HANDHELD) || defined(ELMA_PS3)
    return config_flag("fullscreen", true);
#else
    return config_flag("fullscreen", false);
#endif
}

// Where showing a frame does not wait for the display, frames are kept to
// frame_time milliseconds so that the menus do not keep the CPU busy. Where
// it does wait, frames take that long already and nothing is added.
Uint32 last_frame = 0;
void wait_for_frame(Uint32 frame_time) {
    const Uint32 elapsed = SDL_GetTicks() - last_frame;
    if (elapsed < frame_time) SDL_Delay(frame_time - elapsed);
    last_frame = SDL_GetTicks();
}

#ifndef ELMA_SDL1
// How the picture is scaled to the window (scale in elma.cfg). Sharp
// enlarges it by a whole number with hard pixel edges and smooths it only the
// rest of the way; integer keeps to whole numbers with a black border.
enum Scale { SCALE_SHARP, SCALE_SMOOTH, SCALE_NEAREST, SCALE_INTEGER, SCALE_PIXELART, SCALE_COUNT };
const char* const scale_keys[SCALE_COUNT] = { "sharp", "smooth", "nearest", "integer", "pixelart" };
const char* const scale_names[SCALE_COUNT] = { "Sharp", "Smooth", "Nearest", "Integer", "Pixel Art" };
Scale scale = SCALE_SHARP;

Scale configured_scale() {
    const char* name = config_get("scale", NULL);
    if (name) {
        for (int i = 0; i < SCALE_COUNT; ++i)
            if (stricmp(name, scale_keys[i]) == 0) return Scale(i);
        return SCALE_SHARP;
    }
    // Before elma.cfg, the scaling was chosen with SDL's own variable.
    const char* quality = getenv("SDL_RENDER_SCALE_QUALITY");
    if (!quality) return SCALE_SHARP;
    if (!strcmp(quality, "0") || !stricmp(quality, "nearest")) return SCALE_NEAREST;
    if (!strcmp(quality, "1") || !stricmp(quality, "linear")) return SCALE_SMOOTH;
    if (!strcmp(quality, "2") || !stricmp(quality, "best")) return SCALE_PIXELART;
    return SCALE_SHARP;
}

enum Filter { FILTER_NEAREST, FILTER_LINEAR, FILTER_PIXELART };

// A picture of w x h pixels drawn by the game, and the place it takes in the
// window, in drawable pixels. For sharp scaling it is first enlarged with hard
// edges by factor into upscaled, which is then smoothed to place.
struct Picture {
    int w, h;
    std::vector<unsigned char> pixels; // top row first
    std::vector<unsigned char*> rows;  // handed out by the lock functions
    std::vector<uint32_t> rgba;
    SDL_Texture* texture;
    Filter filter;
    SDL_Texture* upscaled;
    int factor;
    SDL_Rect place;

    Picture(int width, int height)
        : w(0), h(0), texture(NULL), filter(FILTER_NEAREST), upscaled(NULL), factor(0) {
        resize(width, height);
    }
    // The pixels are black again; the textures are made again by layout().
    void resize(int width, int height);
    // The in-game renderer sets Locky0_alul: row 0 is then the bottom row.
    unsigned char** lock(bool bottom_up) {
        for (int y = 0; y < h; ++y) rows[bottom_up ? h - 1 - y : y] = &pixels[size_t(y) * w];
        return rows.data();
    }
};
// The menus, dialogs and the editor draw into this picture (640x480, larger
// menus fill the window: frontbuffermeret), which
// keeps what they drew; the game draws its view into the other one, whose
// size follows the aspect ratio of the window (game_view_size).
Picture ui_picture(640, 480);
Picture game_picture(640, 480);
// The one unlocked last is shown.
Picture* shown = &ui_picture;
Aspect aspect = ASPECT_SCREEN;
SDL_RendererInfo renderer_info;
bool targets = false; // the renderer can draw into textures
#ifdef ELMA_PS3
bool editor_input = false;
unsigned text_input_depth = 0;
int safe_percent() {
    int w = 0, h = 0;
    if (renderer) SDL_GetRendererOutputSize(renderer, &w, &h);
    const char* configured = config_get("safe_area", h <= 576 ? "5" : "2");
    char* end = NULL;
    long value = strtol(configured, &end, 10);
    return *configured && !*end ? int(std::max(0L, std::min(10L, value))) : 2;
}
void view_output_size(int* w, int* h) {
    int physical_w = 0, physical_h = 0;
    if (renderer) SDL_GetRendererOutputSize(renderer, &physical_w, &physical_h);
    ps3_display_size(physical_w, physical_h, w, h);
    const int safe = safe_percent();
    *w -= 2 * (*w * safe / 100);
    *h -= 2 * (*h * safe / 100);
}
#endif
// The largest texture that sharp scaling draws into, in pixels. It is
// lowered when the renderer cannot make one that large.
#ifdef ELMA_PS3
const int target_pixels = 4 * 1024 * 1024;
#else
const int target_pixels = 16 * 1024 * 1024;
#endif
int max_target_pixels = target_pixels;

// The filter of a texture is taken from the hint when the texture is made;
// the override is stronger than SDL_RENDER_SCALE_QUALITY in the environment.
// Every SDL 2 reads it (SDL_SetTextureScaleMode needs 2.0.12). Quality "2"
// selects true Pixel Art in the patched PS3 renderer and sdl2-compat on
// SDL 3.4+; stock SDL 2 uses linear filtering for that hint.
SDL_Texture* create_texture(int w, int h, int access, Filter filter) {
    static const char* const hints[] = { "0", "1", "2" };
    SDL_SetHintWithPriority(SDL_HINT_RENDER_SCALE_QUALITY, hints[filter], SDL_HINT_OVERRIDE);
    return SDL_CreateTexture(renderer, SDL_PIXELFORMAT_ARGB8888, access, w, h);
}

void destroy(SDL_Texture*& texture) {
    if (texture) SDL_DestroyTexture(texture);
    texture = NULL;
}

// The textures are made again by the next layout().
void reset_textures(Picture& picture) {
    destroy(picture.texture);
    destroy(picture.upscaled);
    picture.factor = 0;
}

void reset_textures() {
    reset_textures(ui_picture);
    reset_textures(game_picture);
}

void Picture::resize(int width, int height) {
#ifdef ELMA_PS3
    if(!elma_framebuffer_fits(width,height,pixels.capacity(),rows.capacity(),
                             renderer?ps3_memory_available():UINT64_MAX))
        hiba("Framebuffer exceeds the PS3 memory budget. Use Original resolution.");
#endif
    reset_textures(*this);
    w = width;
    h = height;
    pixels.assign(size_t(w) * h, 0);
    rows.assign(h, NULL);
#ifndef ELMA_PS3
    rgba.assign(size_t(w) * h, 0);
#endif
    place.x = place.y = 0;
    place.w = w;
    place.h = h;
}

// Fits the picture into the window with its own aspect ratio and chooses how
// it is scaled there. The textures are only made again when that changes.
void layout(Picture& picture) {
    const int w = picture.w, h = picture.h;
    int out_w = 0, out_h = 0;
    if (SDL_GetRendererOutputSize(renderer, &out_w, &out_h) != 0 || out_w <= 0 || out_h <= 0) {
        out_w = w;
        out_h = h;
    }
#ifdef ELMA_PS3
    const int physical_w = out_w, physical_h = out_h;
    view_output_size(&out_w, &out_h);
    if (out_w <= 0 || out_h <= 0) { out_w = w; out_h = h; }
#endif
    SDL_Rect& place = picture.place;
    if (out_w * h > out_h * w) {
        place.h = out_h;
        place.w = (out_h * w + h / 2) / h;
    } else {
        place.w = out_w;
        place.h = (out_w * h + w / 2) / w;
    }
    const int whole = std::min(out_w / w, out_h / h);
    // The game view takes the aspect ratio of the window only to a whole
    // pixel of its own (854x480 in 1920x1080 or 3840x2160 would leave black
    // rows): a picture short of the window by up to one of its pixels
    // fills it, unless it fits it by a whole number.
    const int slack_w = (out_w + w - 1) / w, slack_h = (out_h + h - 1) / h;
    if (place.w >= out_w - slack_w && place.h >= out_h - slack_h &&
        !(whole >= 1 && place.w == w * whole && place.h == h * whole)) {
        place.w = out_w;
        place.h = out_h;
    }
    Filter filter = FILTER_LINEAR;
    int factor = 0;
    switch (scale) {
    case SCALE_NEAREST: filter = FILTER_NEAREST; break;
    case SCALE_PIXELART: filter = FILTER_PIXELART; break;
    case SCALE_INTEGER:
        // In a window smaller than the picture, it is smoothed down instead.
        if (whole >= 1) {
            place.w = w * whole;
            place.h = h * whole;
            filter = FILTER_NEAREST;
        }
        break;
    case SCALE_SHARP:
        if (whole >= 1 && place.w == w * whole && place.h == h * whole) {
            filter = FILTER_NEAREST;
        } else if (targets) {
            // The smallest whole number that covers the place, within the
            // texture size of the renderer and max_target_pixels.
            factor = std::max((place.w + w - 1) / w, (place.h + h - 1) / h);
            const int max_w = renderer_info.max_texture_width, max_h = renderer_info.max_texture_height;
            while (factor > 1 && ((max_w && w * factor > max_w) || (max_h && h * factor > max_h) ||
                                  w * factor * h * factor > max_target_pixels))
                --factor;
            if (factor > 1) filter = FILTER_NEAREST;
            else factor = 0;
        }
        break;
    default: break;
    }
    place.x = (out_w - place.w) / 2;
    place.y = (out_h - place.h) / 2;
#ifdef ELMA_PS3
    const int inset_x = physical_w * safe_percent() / 100;
    const int inset_y = physical_h * safe_percent() / 100;
    const int usable_w = physical_w - 2 * inset_x;
    const int usable_h = physical_h - 2 * inset_y;
    place.x = inset_x + place.x * usable_w / out_w;
    place.y = inset_y + place.y * usable_h / out_h;
    place.w = place.w * usable_w / out_w;
    place.h = place.h * usable_h / out_h;
#endif

    if (!picture.texture || picture.filter != filter) {
        destroy(picture.texture);
        picture.texture = create_texture(w, h, SDL_TEXTUREACCESS_STREAMING, filter);
        picture.filter = filter;
    }
    if (picture.factor != factor || (factor && !picture.upscaled)) {
        destroy(picture.upscaled);
        picture.factor = factor;
        if (factor) {
            picture.upscaled = create_texture(w * factor, h * factor, SDL_TEXTUREACCESS_TARGET, FILTER_LINEAR);
            // A smaller one is tried then; without any, sharp scaling is
            // smooth.
            if (!picture.upscaled) {
                max_target_pixels = w * factor * h * factor - 1;
                layout(picture);
            }
        }
    }
}

void draw(const Picture& picture) {
    if (picture.upscaled) {
        SDL_SetRenderTarget(renderer, picture.upscaled);
        SDL_RenderCopy(renderer, picture.texture, NULL, NULL);
        SDL_SetRenderTarget(renderer, NULL);
        SDL_RenderCopy(renderer, picture.upscaled, NULL, &picture.place);
    } else {
        SDL_RenderCopy(renderer, picture.texture, NULL, &picture.place);
    }
}

// The mouse is given in window coordinates, which on high-DPI screens are not
// the drawable pixels that the pictures are placed in.
void drawable_ratio(double* x, double* y) {
    int window_w = 0, window_h = 0, out_w = 0, out_h = 0;
    SDL_GetWindowSize(window, &window_w, &window_h);
    SDL_GetRendererOutputSize(renderer, &out_w, &out_h);
    *x = window_w > 0 && out_w > 0 ? double(out_w) / window_w : 1.0;
    *y = window_h > 0 && out_h > 0 ? double(out_h) / window_h : 1.0;
}

#if !defined(ELMA_HANDHELD) && !defined(ELMA_PS3)
void toggle_fullscreen() {
    const bool on = !(SDL_GetWindowFlags(window) & SDL_WINDOW_FULLSCREEN);
    if (SDL_SetWindowFullscreen(window, on ? SDL_WINDOW_FULLSCREEN_DESKTOP : 0) != 0) return;
    config_set("fullscreen", on ? "1" : "0");
    config_save();
}
#endif
#endif

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
    case SDLK_HOME: return DIK_HOME; case SDLK_END: return DIK_END;
    case SDLK_INSERT: return DIK_INSERT;
    case SDLK_KP_PLUS: return DIK_ADD; case SDLK_KP_MINUS: return DIK_SUBTRACT;
    case SDLK_KP_MULTIPLY: return DIK_MULTIPLY; case SDLK_KP_DIVIDE: return DIK_DIVIDE;
    case SDLK_KP_PERIOD: return DIK_DECIMAL;
    case SDLK_F1: return DIK_F1; case SDLK_F2: return DIK_F2; case SDLK_F3: return DIK_F3;
    case SDLK_F4: return DIK_F4; case SDLK_F5: return DIK_F5; case SDLK_F6: return DIK_F6;
    case SDLK_F7: return DIK_F7; case SDLK_F8: return DIK_F8; case SDLK_F9: return DIK_F9;
    case SDLK_F10: return DIK_F10; case SDLK_F12: return DIK_F12;
    case SDLK_LEFTBRACKET: return DIK_LBRACKET; case SDLK_RIGHTBRACKET: return DIK_RBRACKET;
    case SDLK_SEMICOLON: return DIK_SEMICOLON; case SDLK_QUOTE: return DIK_APOSTROPHE;
    case SDLK_BACKQUOTE: return DIK_GRAVE; case SDLK_BACKSLASH: return DIK_BACKSLASH;
    case SDLK_SLASH: return DIK_SLASH;
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
    case SDL_SCANCODE_HOME: return DIK_HOME; case SDL_SCANCODE_END: return DIK_END;
    case SDL_SCANCODE_INSERT: return DIK_INSERT;
    case SDL_SCANCODE_KP_PLUS: return DIK_ADD; case SDL_SCANCODE_KP_MINUS: return DIK_SUBTRACT;
    case SDL_SCANCODE_KP_MULTIPLY: return DIK_MULTIPLY; case SDL_SCANCODE_KP_DIVIDE: return DIK_DIVIDE;
    case SDL_SCANCODE_KP_PERIOD: return DIK_DECIMAL;
    case SDL_SCANCODE_F1: return DIK_F1; case SDL_SCANCODE_F2: return DIK_F2;
    case SDL_SCANCODE_F3: return DIK_F3; case SDL_SCANCODE_F4: return DIK_F4;
    case SDL_SCANCODE_F5: return DIK_F5; case SDL_SCANCODE_F6: return DIK_F6;
    case SDL_SCANCODE_F7: return DIK_F7; case SDL_SCANCODE_F8: return DIK_F8;
    case SDL_SCANCODE_F9: return DIK_F9; case SDL_SCANCODE_F10: return DIK_F10;
    case SDL_SCANCODE_F12: return DIK_F12;
    case SDL_SCANCODE_LEFTBRACKET: return DIK_LBRACKET; case SDL_SCANCODE_RIGHTBRACKET: return DIK_RBRACKET;
    case SDL_SCANCODE_SEMICOLON: return DIK_SEMICOLON; case SDL_SCANCODE_APOSTROPHE: return DIK_APOSTROPHE;
    case SDL_SCANCODE_GRAVE: return DIK_GRAVE; case SDL_SCANCODE_BACKSLASH: return DIK_BACKSLASH;
    case SDL_SCANCODE_SLASH: return DIK_SLASH;
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
#if !defined(ELMA_SDL1) && !defined(ELMA_HANDHELD) && !defined(ELMA_PS3)
    // Alt+Enter and F11 switch between the window and full screen; the game
    // does not get these presses. Ctrl+Alt+Enter is left to the menus, which
    // save the times of a replay with it.
    const Uint16 mod = event.keysym.mod;
    if (down && (event.keysym.sym == SDLK_F11 ||
                 (event.keysym.sym == SDLK_RETURN && (mod & KMOD_ALT) && !(mod & KMOD_CTRL)))) {
        if (!repeat) toggle_fullscreen();
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

void present();

#ifdef ELMA_PS3
unsigned pad_previous[2] = {};
Uint32 pad_repeat[PS3_BUTTON_COUNT] = {};
double pad_mouse_x = 320, pad_mouse_y = 240;
bool pad_mouse_used = false;
Uint32 pad_mouse_time = 0;
bool pad_pause = false;
unsigned pad_ui_buttons = 0;

void pad_key(int key) { if (key > 0 && key < 256) button_keys[key] = 1; }

void ps3_input() {
    ps3_poll();
    button_keys.fill(0);
    if (ps3_exit_requested()) { running = false; return; }
    const Uint32 now = SDL_GetTicks();
    const bool game = shown == &game_picture;
    const bool editor = editor_input && !game && text_input_depth == 0;
    const bool system_menu = ps3_system_menu();
    const bool capture = ps3_controls_capturing();
    static Ps3InputContext context_gate;
    unsigned raw_masks[2]={system_menu?0:ps3_button_mask(0),system_menu?0:ps3_button_mask(1)};
    unsigned menu_navigation=raw_masks[0];
    if(!game && !system_menu && !capture) {
        if(ps3_axis(0,0)<-64)menu_navigation|=1u<<PS3_LEFT;
        if(ps3_axis(0,0)>64)menu_navigation|=1u<<PS3_RIGHT;
        if(ps3_axis(0,1)<-64)menu_navigation|=1u<<PS3_UP;
        if(ps3_axis(0,1)>64)menu_navigation|=1u<<PS3_DOWN;
    }
    const int input_context=(game ? 1 : editor_input ? 2+text_input_depth : 0)+(system_menu?1024:0)+(capture?2048:0);
    context_gate.update(input_context,game?raw_masks[0]:menu_navigation,raw_masks[1]);
    if(capture) {
        pad_ui_buttons=0;
        for(int p=0;p<2;++p)pad_previous[p]=raw_masks[p];
        for(int b=0;b<PS3_BUTTON_COUNT;++b)pad_repeat[b]=0;
        return;
    }
    pad_ui_buttons=game?0:context_gate.fresh(0,raw_masks[0]);
    for (int p = 0; p < 2; ++p) {
        const unsigned mask = raw_masks[p];
        const unsigned fresh_mask=context_gate.fresh(p,mask);
        const unsigned pressed = mask & ~pad_previous[p];
        pad_previous[p] = mask;
        if (game) {
            for (int action = 0; action < PS3_CONTROL_COUNT; ++action) {
                const int button = ps3_binding(p, action);
                if (button >= 0 && (mask & (1u << button))) {
                    pad_key(ps3_action_key(p, action));
                    if (action == PS3_ALOVOLT) pad_key(ps3_action_key(p, PS3_ROTATE_RIGHT));
                }
            }
            if (fresh_mask & (1u << PS3_SELECT)) pad_key(DIK_ESCAPE);
            if (pressed & fresh_mask & (1u << PS3_START)) pad_pause = true;
            continue;
        }
        if (p != 0) continue; // Controller 1 owns menus and the editor.
        unsigned navigation = context_gate.fresh(0,menu_navigation);
        static const int menu_keys[PS3_BUTTON_COUNT] = {
            MK_ESC, 0, 0, MK_ENTER, MK_UP, MK_RIGHT, MK_DOWN, MK_LEFT,
            0, 0, MK_PGUP, MK_PGDOWN, 0, MK_ESC, MK_ENTER, MK_BACKSPACE
        };
        for (int b = 0; b < PS3_BUTTON_COUNT; ++b) {
            const bool down = (navigation & (1u << b)) != 0;
            if (!down) { pad_repeat[b] = 0; continue; }
            if (editor && (b == PS3_CROSS || b == PS3_SQUARE || b == PS3_L1 || b == PS3_R1)) continue;
            // Editor dialogs retain their clickable SAVE/LOCKED buttons.
            // Start accepts typed text; Cross and Square remain mouse clicks.
            if (editor_input && text_input_depth && (b == PS3_CROSS || b == PS3_SQUARE)) continue;
            const bool repeats = b >= PS3_UP && b <= PS3_LEFT;
            if (!pad_repeat[b] || (repeats && Sint32(now - pad_repeat[b]) >= 0)) {
                int c = menu_keys[b];
                if (editor) {
                    if (b == PS3_SELECT) c = 'x';
                    if (b == PS3_START) c = 'p';
                    if (b == PS3_TRIANGLE) c = ' ';
                    if (b == PS3_R3) c = MK_ENTER;
                    if (b == PS3_L2) c = 'z';
                    if (b == PS3_R2) c = 'i';
                }
                if (c) chars.push_back(c);
                pad_repeat[b] = now + (pad_repeat[b] ? 90 : 350);
            }
        }
        if (editor_input && !game && !system_menu) {
            if (mask & (1u << PS3_L1)) pad_key(DIK_LCONTROL);
            if (mask & (1u << PS3_R1)) pad_key(DIK_LSHIFT);
            const double dt = std::min(0.05, (now - pad_mouse_time) / 1000.0);
            const int rx = ps3_axis(0, 2), ry = ps3_axis(0, 3);
            if (abs(rx) > 20 || abs(ry) > 20) {
                pad_mouse_used = true;
                const double speed = mask & (1u << PS3_R1) ? 85 : 350;
                if (abs(rx) > 20) pad_mouse_x += dt * speed * rx / 128;
                if (abs(ry) > 20) pad_mouse_y += dt * speed * ry / 128;
                pad_mouse_x = std::max(0.0, std::min(639.0, pad_mouse_x));
                pad_mouse_y = std::max(0.0, std::min(479.0, pad_mouse_y));
            }
        }
    }
    pad_mouse_time = now;
}
#endif

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
#ifndef ELMA_PS3
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
#else
        case SDL_MOUSEMOTION:
            pad_mouse_used = false;
            break;
#endif
        case SDL_WINDOWEVENT:
            // The menus keep their place for the mouse; the game view gets
            // its new size with the next frame.
            if (event.window.event == SDL_WINDOWEVENT_SIZE_CHANGED) layout(ui_picture);
            // The editor only draws when something changes, so the last
            // picture is shown again.
            if ((event.window.event == SDL_WINDOWEVENT_SIZE_CHANGED ||
                 event.window.event == SDL_WINDOWEVENT_EXPOSED) && !locked)
                present();
            break;
        case SDL_RENDER_TARGETS_RESET: case SDL_RENDER_DEVICE_RESET:
            max_target_pixels = target_pixels;
            reset_textures();
            break;
#endif
        }
    }
#ifdef ELMA_PS3
    ps3_input();
    if (ps3_system_menu() && running && !locked) {
        const bool paused_here=!stopper_clock.paused();
        if(paused_here)mv_pausestopper(1);
        nullazhangot();
        while (ps3_system_menu() && !ps3_exit_requested()) {
            SDL_PumpEvents();
            present();
        }
        if(paused_here)mv_pausestopper(0);
        ps3_input();
        chars.clear();
    }
    if (pad_pause && running && !locked) {
        pad_pause = false;
        const bool paused_here=!stopper_clock.paused();
        if(paused_here)mv_pausestopper(1);
        nullazhangot();
        ps3_message("Paused\n\nPress Cross to continue.", present);
        if(paused_here)mv_pausestopper(0);
        ps3_poll();
        for (int p = 0; p < 2; ++p) pad_previous[p] = ps3_button_mask(p);
        chars.clear();
    }
#endif
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
    // SDL 1.2 does not always wait for the display.
    wait_for_frame(16);
}
#else
// Draws the frame without showing it.
void draw_frame() {
    Picture& picture = *shown;
#ifdef ELMA_PS3
    layout(picture);
    void* pixels_out = NULL;
    int pitch = 0;
    if (SDL_LockTexture(picture.texture, NULL, &pixels_out, &pitch) != 0)
        hiba((char*)"Cannot upload the picture", (char*)SDL_GetError());
    for (int y = 0; y < picture.h; ++y) {
        uint32_t* line = reinterpret_cast<uint32_t*>(static_cast<Uint8*>(pixels_out) + y * pitch);
        const unsigned char* source = picture.pixels.data() + size_t(y) * picture.w;
        for (int x = 0; x < picture.w; ++x) line[x] = palette[source[x]];
    }
    SDL_UnlockTexture(picture.texture);
#else
    for (size_t i = 0; i < picture.pixels.size(); ++i) picture.rgba[i] = palette[picture.pixels[i]];
    layout(picture);
    SDL_UpdateTexture(picture.texture, NULL, picture.rgba.data(), picture.w * sizeof(uint32_t));
#endif
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
    SDL_RenderClear(renderer);
    draw(picture);
}

// A frame at the refresh rate of the display that the window is on, a
// little shorter so that the wait never makes a frame miss the display.
Uint32 frame_time() {
#ifdef ELMA_PS3
    return 900 / ps3_refresh_rate();
#else
    int rate = 60;
    SDL_DisplayMode mode;
    const int display = SDL_GetWindowDisplayIndex(window);
    if (display >= 0 && SDL_GetDesktopDisplayMode(display, &mode) == 0 && mode.refresh_rate > 0)
        rate = mode.refresh_rate;
    return 900 / rate;
#endif
}

void present() {
#ifdef ELMA_PS3
    const bool diagnostics = config_flag("ps3_diagnostics", false);
    ps3_set_diagnostics(diagnostics);
    SDL_SetHint("ELMA_PS3_SDL_PROFILE", diagnostics ? "1" : "0");
    const Uint32 draw_started = SDL_GetTicks();
#endif
    draw_frame();
#ifdef ELMA_PS3
    const Uint32 draw_ms = SDL_GetTicks() - draw_started;
#endif
    SDL_RenderPresent(renderer);
#ifdef ELMA_PS3
    const Uint32 flip_finished = SDL_GetTicks();
#endif
    // Whether presenting waits for the display is not known: the software
    // renderer of SDL 2.0.18 and later reports vertical sync even where it
    // cannot wait.
    wait_for_frame(frame_time());
#ifdef ELMA_PS3
    const Uint32 frame_finished = SDL_GetTicks();
    static Uint32 previous_frame_finished = 0;
    const Uint32 outside_ms = previous_frame_finished ? draw_started - previous_frame_finished : 0;
    previous_frame_finished = frame_finished;
    if (config_flag("ps3_diagnostics", false)) {
        static unsigned frames = 0, draw_total = 0, flip_total = 0, cap_total = 0, outside_total = 0;
        static Uint32 started = draw_started;
        draw_total += draw_ms;
        flip_total += flip_finished - draw_started - draw_ms;
        cap_total += frame_finished - flip_finished;
        outside_total += outside_ms;
        if (++frames == 300) {
            const Uint32 elapsed = frame_finished - started;
            const Ps3RsxMemory rsx = ps3_rsx_memory();
            printf("ELMA PS3 frame: %dx%d, %.1f fps, frame %.2f ms, upload/draw %.2f ms, "
                   "flip/rewind %.2f ms, cap %.2f ms, engine/events %.2f ms, refresh=%d Hz, free RAM=%u KiB, "
                   "RSX used=%u bytes, peak=%u bytes, allocations=%u, complete=%d, failures=%u\n",
                   shown->w, shown->h, elapsed ? frames * 1000.0 / elapsed : 0,
                   double(elapsed) / frames, double(draw_total) / frames,
                   double(flip_total) / frames, double(cap_total) / frames,
                   double(outside_total) / frames, ps3_refresh_rate(), ps3_memory_available() / 1024,
                   rsx.used, rsx.peak, rsx.allocations, rsx.complete, rsx.failures);
            started = frame_finished;
            frames = draw_total = flip_total = cap_total = outside_total = 0;
        }
    }
#endif
}
#ifdef ELMA_PS3
// A failed texture allocation/upload must not recurse through draw_frame()
// while trying to report the failure. Native dialogs only need scanout flips.
void present_dialog_backdrop() {
    if (!renderer) return;
    SDL_SetRenderTarget(renderer, NULL);
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
    SDL_RenderClear(renderer);
    SDL_RenderPresent(renderer);
    wait_for_frame(frame_time());
}
#endif
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

// SDL 1.2 shows the picture unscaled.
const char* dd_scale_name() { return NULL; }
void dd_next_scale() {}

// The zoom is only set in elma.cfg (and with the keys during a game).
const char* dd_zoom_name() { return NULL; }
void dd_next_zoom() {}
const char* dd_zoom_textures_name() { return NULL; }
void dd_next_zoom_textures() {}
const char* dd_texture_filter_name() { return NULL; }
void dd_next_texture_filter() {}
#else
void ddinit() {
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_EVENTS | SDL_INIT_TIMER) != 0) {
        fprintf(stderr, "SDL_Init: %s\n", SDL_GetError());
        exit(1);
    }
#ifdef ELMA_PS3
    ps3_platform_init();
    ps3_controls_load();
#else
    // Game pads are optional; the connected ones arrive as device events.
    if (SDL_InitSubSystem(SDL_INIT_GAMECONTROLLER) == 0)
        SDL_GameControllerAddMappingsFromFile("gamecontrollerdb.txt");
#endif
    scale = configured_scale();
    aspect = config_aspect();
    int width = 640, height = 480;
#if !defined(ELMA_HANDHELD) && !defined(ELMA_PS3)
    // The window starts at the largest whole multiple of the game view that
    // fits on the screen with room for the title bar and the window frame,
    // with the aspect ratio of the screen (or 4:3).
    SDL_Rect usable;
    SDL_DisplayMode mode;
    const int decorations = 64;
    if (SDL_GetDisplayUsableBounds(0, &usable) == 0) {
        int step_w = 640, step_h = 480;
        if (SDL_GetDesktopDisplayMode(0, &mode) == 0)
            base_view_size(aspect, mode.w, mode.h, &step_w, &step_h);
        width = step_w;
        height = step_h;
        while (width + step_w + decorations <= usable.w && height + step_h + decorations <= usable.h) {
            width += step_w;
            height += step_h;
        }
    }
#endif
    Uint32 flags = SDL_WINDOW_ALLOW_HIGHDPI | SDL_WINDOW_RESIZABLE;
#ifdef ELMA_PS3
    SDL_DisplayMode output_mode;
    if (SDL_GetDesktopDisplayMode(0, &output_mode) == 0) {
        width = output_mode.w; height = output_mode.h;
    }
    flags = SDL_WINDOW_FULLSCREEN_DESKTOP;
#endif
    if (fullscreen()) flags |= SDL_WINDOW_FULLSCREEN_DESKTOP;
    window = SDL_CreateWindow("Elasto Mania", SDL_WINDOWPOS_CENTERED,
                              SDL_WINDOWPOS_CENTERED, width, height, flags);
    if (!window) {
        fprintf(stderr, "SDL_CreateWindow: %s\n", SDL_GetError());
        SDL_Quit();
        exit(1);
    }
#if !defined(ELMA_HANDHELD) && !defined(ELMA_PS3)
    SDL_SetWindowMinimumSize(window, 320, 240);
#endif
    renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
    if (!renderer) renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_SOFTWARE | SDL_RENDERER_PRESENTVSYNC);
    // Up to SDL 2.0.16 the software renderer does not offer vertical sync,
    // and asking for it finds no renderer.
    if (!renderer) renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_SOFTWARE);
    if (renderer) {
        SDL_GetRendererInfo(renderer, &renderer_info);
#ifdef ELMA_PS3
        printf("ELMA PS3 video: %dx%d, renderer=%s, free RAM=%u KiB\n",
               width, height, renderer_info.name, ps3_memory_available() / 1024);
        #ifdef ELMA_CLASSIC_X87
        printf("ELMA PS3 physics: classic_x87 (experimental)\n");
        #else
        printf("ELMA PS3 physics: sdl\n");
        #endif
#endif
        targets = SDL_RenderTargetSupported(renderer) == SDL_TRUE;
        max_target_pixels = target_pixels;
        layout(ui_picture);
    }
    if (!ui_picture.texture) {
        fprintf(stderr, "SDL renderer: %s\n", SDL_GetError());
        SDL_Quit();
        exit(1);
    }
#if defined(ELMA_HANDHELD) || defined(ELMA_PS3)
    SDL_ShowCursor(SDL_DISABLE);
#endif
#ifdef ELMA_PS3
    ps3_install_memory_handler(present_dialog_backdrop);
#endif
    Margrafikus = 1;
}

void ddfinish() {
#ifdef ELMA_PS3
    ps3_platform_finish();
#endif
    reset_textures();
    if (renderer) SDL_DestroyRenderer(renderer);
    if (window) SDL_DestroyWindow(window);
    renderer = NULL; window = NULL;
    SDL_Quit();
#ifdef ELMA_PS3
    ps3_diagnostic_checkpoint("shutdown", false);
#endif
}

const char* dd_scale_name() { return scale_names[scale]; }
#ifdef ELMA_PS3
void ps3_text_input(bool enabled) {
    if (enabled) ++text_input_depth;
    else if (text_input_depth) --text_input_depth;
    chars.clear();
}
const char* dd_ps3_safe_name() {
    static char text[24];
    snprintf(text, sizeof(text), "%d%%", safe_percent());
    return text;
}
void dd_ps3_next_safe() {
    char text[12];
    snprintf(text, sizeof(text), "%d", (safe_percent() + 1) % 11);
    config_set("safe_area", text); config_save();
    layout(ui_picture); layout(game_picture);
}
#endif

void dd_next_scale() {
    scale = Scale((scale + 1) % SCALE_COUNT);
    config_set("scale", scale_keys[scale]);
    config_save();
    reset_textures();
    layout(ui_picture);
}

const char* dd_aspect_name() { return aspect_name(aspect); }

// The game view takes the new size with its next frame.
void dd_next_aspect() {
    aspect = Aspect((aspect + 1) % ASPECT_COUNT);
    config_set("aspect", aspect_key(aspect));
    config_save();
}

// The game view takes the new size with its next frame, the next level is
// drawn in its detail.
const char* dd_resolution_name() { return resolution_name(config_resolution()); }
#ifdef ELMA_PS3
static bool picture_fits(const Picture& picture,int w,int h) {
    return elma_framebuffer_fits(w,h,picture.pixels.capacity(),picture.rows.capacity(),ps3_memory_available());
}
static void frame_memory_warning(const char* text) {
    const bool paused_here=!stopper_clock.paused();
    if(paused_here)mv_pausestopper(1);
    printf("elma: framebuffer admission refused: %s; available %u KiB\n",text,ps3_memory_available()/1024);
    ps3_message(text,present_dialog_backdrop);
    if(paused_here)mv_pausestopper(0);
}
void dd_next_resolution() {
    const int next=next_resolution_option(config_resolution());
    int out_w=0,out_h=0,w=0,h=0;view_output_size(&out_w,&out_h);
    game_view_size_at_resolution(aspect,out_w,out_h,next,&w,&h);
    if(!picture_fits(game_picture,w,h)){
        frame_memory_warning("This resolution exceeds the PS3 framebuffer budget. The current resolution is kept. Choose Original or a lower zoom.");return;
    }
    set_config_resolution(next);
}
#else
void dd_next_resolution() { set_config_resolution(next_resolution_option(config_resolution())); }
#endif

// The next level is loaded with the new zoom.
const char* dd_zoom_name() { return zoom_name(config_zoom()); }
void dd_next_zoom() { set_config_zoom(next_zoom_option(config_zoom())); }
const char* dd_zoom_textures_name() { return config_zoom_textures() ? "Yes" : "No"; }
void dd_next_zoom_textures() { set_config_zoom_textures(!config_zoom_textures()); }
// HQx, Smooth, Nearest; the next level is loaded with it.
const char* dd_texture_filter_name() { return texture_filter_name(config_texture_filter()); }
void dd_next_texture_filter() {
    static const int next[3] = { SZURO_HQX, SZURO_LEGKOZELEBBI, SZURO_SIMA };
    set_config_texture_filter(next[config_texture_filter()]);
}
#endif

#ifdef ELMA_MIYOO
// The biggest levels take about 50 MB at zoom 2 and 100 MB at zoom 4 (on a
// 64-bit desktop); the Miyoo Mini has 128 MB.
const double max_zoom = 2.0;
#else
const double max_zoom = NAGYITASMAX;
#endif
double dd_zoom() { return std::min(config_zoom(), max_zoom); }
void dd_set_zoom(double zoom) { set_config_zoom(std::min(zoom, max_zoom)); }
int dd_zoom_textures() { return config_zoom_textures(); }
int dd_zoom_grass() { return config_zoom_grass(); }
int dd_texture_filter() { return config_texture_filter(); }
int dd_zoom_key(int zoom_in) { return config_zoom_key(zoom_in != 0); }

int dd_center_bike() { return config_flag("center_bike", true); }
const char* dd_center_bike_name() { return dd_center_bike() ? "Yes" : "No"; }
void dd_next_center_bike() {
    config_set("center_bike", dd_center_bike() ? "0" : "1");
    config_save();
}

#ifdef ELMA_SDL1
// SDL 1.2 shows the 640x480 picture unscaled.
unsigned char** lockbackbuffer(int) {
    if (locked) hiba((char*)"framebuffer already locked");
    locked = true;
    for (int y = 0; y < 480; ++y)
        rows[Locky0_alul ? 479 - y : y] = pixels.data() + y * 640;
    return rows.data();
}

void unlockbackbuffer() { locked = false; present(); }
void backbuffersize(int* w, int* h) { *w = 640; *h = 480; }
unsigned char** lockfrontbuffer() { return lockbackbuffer(0); }
void unlockfrontbuffer() { unlockbackbuffer(); }

const char* dd_aspect_name() { return NULL; }
void dd_next_aspect() {}
void dd_menumeret(int* w, int* h) { *w = 640; *h = 480; }
void frontbuffermeret(int, int) {}
const char* dd_resolution_name() { return NULL; }
void dd_next_resolution() {}
#else
namespace {
bool game_locked = false;

// Between frames, the game view takes the size that the window asks for.
void resize_game_view() {
    if (game_locked) return;
    int out_w = 0, out_h = 0;
    if (!renderer || SDL_GetRendererOutputSize(renderer, &out_w, &out_h) != 0) out_w = out_h = 0;
#ifdef ELMA_PS3
    view_output_size(&out_w, &out_h);
#endif
    int w, h;
    game_view_size(aspect, out_w, out_h, &w, &h);
#ifdef ELMA_PS3
    static int refused_w=0,refused_h=0;
    if((w!=game_picture.w || h!=game_picture.h) && !picture_fits(game_picture,w,h)) {
        if(w==refused_w && h==refused_h)return;
        // An unsafe hand-edited config must not produce the same failure on
        // every frame or next boot. Keep the allocated viewport while falling
        // back once to the original logical resolution.
        set_config_resolution(RESOLUTION_ORIGINAL);
        frame_memory_warning("The configured resolution exceeds the PS3 framebuffer budget. Original resolution has been selected and saved.");
        game_view_size(aspect,out_w,out_h,&w,&h);
        if(!picture_fits(game_picture,w,h)){refused_w=w;refused_h=h;return;}
    }
    refused_w=refused_h=0;
#endif
    if (w != game_picture.w || h != game_picture.h) game_picture.resize(w, h);
}
}

unsigned char** lockbackbuffer(int) {
    if (locked) hiba((char*)"framebuffer already locked");
    resize_game_view();
    locked = game_locked = true;
    return game_picture.lock(Locky0_alul != 0);
}

void unlockbackbuffer() {
    locked = game_locked = false;
    shown = &game_picture;
    present();
}

void backbuffersize(int* w, int* h) {
    resize_game_view();
    *w = game_picture.w;
    *h = game_picture.h;
}

unsigned char** lockfrontbuffer() {
    if (locked) hiba((char*)"framebuffer already locked");
    locked = true;
    return ui_picture.lock(Locky0_alul != 0);
}

void dd_menumeret(int* w, int* h) {
    int out_w = 0, out_h = 0;
    if (!renderer || SDL_GetRendererOutputSize(renderer, &out_w, &out_h) != 0) out_w = out_h = 0;
#ifdef ELMA_PS3
    view_output_size(&out_w, &out_h);
#endif
    menu_view_size(out_w, out_h, w, h);
#ifdef ELMA_PS3
    static int refused_w=0,refused_h=0;
    if((*w!=ui_picture.w || *h!=ui_picture.h) && !picture_fits(ui_picture,*w,*h)) {
        if(*w!=refused_w || *h!=refused_h){refused_w=*w;refused_h=*h;
            frame_memory_warning("The menu framebuffer needs more PS3 memory. Its current size is kept.");}
        *w=ui_picture.w;*h=ui_picture.h;
    }else {refused_w=refused_h=0;}
#endif
}

void frontbuffermeret(int w, int h) {
    if (w == ui_picture.w && h == ui_picture.h) return;
    ui_picture.resize(w, h);
    layout(ui_picture);
}

void unlockfrontbuffer() {
    locked = false;
    shown = &ui_picture;
    present();
}
#endif

// 6 bits per color, as a VGA card takes them; repeating the top bits makes
// 63 full brightness instead of 252.
static uint32_t vga_color(unsigned char c) { return uint32_t(c) << 2 | c >> 4; }

ddpal::ddpal(unsigned char* colors) {
    std::array<uint32_t, 256>* value = new std::array<uint32_t, 256>;
    for (int i = 0; i < 256; ++i) {
        const uint32_t r = vga_color(colors[i * 3]);
        const uint32_t g = vga_color(colors[i * 3 + 1]);
        const uint32_t b = vga_color(colors[i * 3 + 2]);
        (*value)[i] = 0xff000000u | r << 16 | g << 8 | b;
    }
    pddpal = value;
}
ddpal::~ddpal() { delete static_cast<std::array<uint32_t, 256>*>(pddpal); }
void ddpal::set() {
    palette = *static_cast<std::array<uint32_t, 256>*>(pddpal);
#ifdef ELMA_PS3
    editor_input = Pal_editor && this == Pal_editor;
#endif
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
int controlaltnyomva() { return (keys[DIK_LMENU] || button_keys[DIK_LMENU]) &&
                              (keys[DIK_LCONTROL] || button_keys[DIK_LCONTROL]); }

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
#ifdef ELMA_PS3
    const int letters[]={DIK_A,DIK_B,DIK_C,DIK_D,DIK_E,DIK_F,DIK_G,DIK_H,DIK_I,
        DIK_J,DIK_K,DIK_L,DIK_M,DIK_N,DIK_O,DIK_P,DIK_Q,DIK_R,DIK_S,DIK_T,
        DIK_U,DIK_V,DIK_W,DIK_X,DIK_Y,DIK_Z};
    for(int i=0;i<26;++i) if(code==letters[i]) {name[0]='A'+i;name[1]=0;return name;}
    if(code>=DIK_1 && code<=DIK_0) {name[0]="1234567890"[code-DIK_1];name[1]=0;return name;}
    const char* label=NULL;
    switch(code) {
    case 0:label="Unassigned";break;
    case DIK_UP:label="Up";break;case DIK_DOWN:label="Down";break;
    case DIK_LEFT:label="Left";break;case DIK_RIGHT:label="Right";break;
    case DIK_ESCAPE:label="Esc";break;case DIK_RETURN:label="Enter";break;
    case DIK_SPACE:label="Space";break;case DIK_TAB:label="Tab";break;
    case DIK_BACK:label="Backspace";break;case DIK_DELETE:label="Delete";break;
    case DIK_PRIOR:label="Page Up";break;case DIK_NEXT:label="Page Down";break;
    case DIK_HOME:label="Home";break;case DIK_END:label="End";break;
    case DIK_INSERT:label="Insert";break;case DIK_MINUS:label="Minus (-)";break;
    case DIK_EQUALS:label="Equals (+)";break;case DIK_LCONTROL:label="Left Ctrl";break;
    case DIK_RCONTROL:label="Right Ctrl";break;case DIK_LSHIFT:label="Left Shift";break;
    case DIK_RSHIFT:label="Right Shift";break;case DIK_LMENU:label="Left Alt";break;
    case DIK_RMENU:label="Right Alt";break;case DIK_NUMPAD0:label="Numpad 0";break;
    case DIK_NUMPAD1:label="Numpad 1";break;case DIK_NUMPAD2:label="Numpad 2";break;
    case DIK_NUMPAD3:label="Numpad 3";break;case DIK_NUMPAD4:label="Numpad 4";break;
    case DIK_NUMPAD5:label="Numpad 5";break;case DIK_NUMPAD6:label="Numpad 6";break;
    case DIK_NUMPAD7:label="Numpad 7";break;case DIK_NUMPAD8:label="Numpad 8";break;
    case DIK_NUMPAD9:label="Numpad 9";break;case DIK_NUMPADENTER:label="Numpad Enter";break;
    case DIK_ADD:label="Numpad +";break;case DIK_SUBTRACT:label="Numpad -";break;
    case DIK_F11:label="F11";break;case DIK_F12:label="F12";break;
    case DIK_F13:label="F13";break;case DIK_F14:label="F14";break;case DIK_F15:label="F15";break;
    case DIK_LBRACKET:label="Left Bracket";break;case DIK_RBRACKET:label="Right Bracket";break;
    case DIK_SEMICOLON:label="Semicolon";break;case DIK_APOSTROPHE:label="Apostrophe";break;
    case DIK_GRAVE:label="Backtick";break;case DIK_BACKSLASH:label="Backslash";break;
    case DIK_COMMA:label="Comma";break;case DIK_PERIOD:label="Period";break;
    case DIK_SLASH:label="Slash";break;case DIK_CAPITAL:label="Caps Lock";break;
    case DIK_NUMLOCK:label="Num Lock";break;case DIK_SCROLL:label="Scroll Lock";break;
    case DIK_DECIMAL:label="Numpad Decimal";break;case DIK_DIVIDE:label="Numpad /";break;
    case DIK_MULTIPLY:label="Numpad *";break;case DIK_SYSRQ:label="Print Screen";break;
    case DIK_LWIN:label="Left Super";break;case DIK_RWIN:label="Right Super";break;
    case DIK_APPS:label="Menu";break;
    }
    if(label) {snprintf(name,sizeof(name),"%s",label);return name;}
    if(code>=DIK_F1 && code<=DIK_F10) {snprintf(name,sizeof(name),"F%d",code-DIK_F1+1);return name;}
    if(code>=0xED && code<=0xFF) {snprintf(name,sizeof(name),"Controller only");return name;}
#endif
    snprintf(name, sizeof(name), "KEY %02X", code);
    return name;
}

void mv_check(int) { hang(); events(); }
#ifdef ELMA_PS3
void mv_startstopper() { stopper_clock.reset(std::chrono::steady_clock::now()); }
void mv_pausestopper(int pause) {
    stopper_clock.pause(pause != 0, std::chrono::steady_clock::now());
}
double mv_stopperido() {
    const std::chrono::duration<double> elapsed = stopper_clock.elapsed(std::chrono::steady_clock::now());
    return elapsed.count() * 182.0;
}
#else
void mv_startstopper() { stopper_start = std::chrono::steady_clock::now(); }
// The time between the two calls moves the start of the stopper on.
void mv_pausestopper(int pause) {
    static bool paused = false;
    static std::chrono::steady_clock::time_point pause_start;
    const std::chrono::steady_clock::time_point now = std::chrono::steady_clock::now();
    if (pause && !paused) pause_start = now;
    if (!pause && paused) stopper_start += now - pause_start;
    paused = pause != 0;
}
double mv_stopperido() {
    const std::chrono::duration<double> elapsed = std::chrono::steady_clock::now() - stopper_start;
    return elapsed.count() * 182.0;
}
#endif
void getbiostort(unsigned short* bios, unsigned short* fraction) {
    const uint64_t ticks = std::chrono::steady_clock::now().time_since_epoch().count();
    *bios = static_cast<unsigned short>(ticks >> 16);
    *fraction = static_cast<unsigned short>(ticks);
}
int s_random(int max) { return max > 0 ? rand() % max : 0; }

#ifdef ELMA_SDL1
void getmou(int* x, int* y) { SDL_GetMouseState(x, y); }
void setmou(int x, int y) { SDL_WarpMouse(x, y); }
#else
// The game gets the mouse in the 640x480 picture of the menus and the
// editor, wherever that is shown.
void getmou(int* x, int* y) {
#ifdef ELMA_PS3
    if (pad_mouse_used && editor_input) { *x = int(pad_mouse_x); *y = int(pad_mouse_y); return; }
#endif
    int window_x = 0, window_y = 0;
    SDL_GetMouseState(&window_x, &window_y);
    const Picture& picture = ui_picture;
    const SDL_Rect& place = picture.place;
    double ratio_x, ratio_y;
    drawable_ratio(&ratio_x, &ratio_y);
    *x = place.w > 0 ? int(((window_x + 0.5) * ratio_x - place.x) * picture.w / place.w) : 0;
    *y = place.h > 0 ? int(((window_y + 0.5) * ratio_y - place.y) * picture.h / place.h) : 0;
    *x = std::max(0, std::min(picture.w - 1, *x));
    *y = std::max(0, std::min(picture.h - 1, *y));
#ifdef ELMA_PS3
    pad_mouse_x = *x; pad_mouse_y = *y;
#endif
}

void setmou(int x, int y) {
#ifdef ELMA_PS3
    pad_mouse_x = x; pad_mouse_y = y;
#endif
    const Picture& picture = ui_picture;
    const SDL_Rect& place = picture.place;
    double ratio_x, ratio_y;
    drawable_ratio(&ratio_x, &ratio_y);
    SDL_WarpMouseInWindow(window, int((place.x + (x + 0.5) * place.w / picture.w) / ratio_x),
                          int((place.y + (y + 0.5) * place.h / picture.h) / ratio_y));
}
#endif
int getbutbmou() {
#ifdef ELMA_PS3
    if (editor_input && !ps3_system_menu() && (pad_ui_buttons & (1u << PS3_CROSS))) return 1;
#endif
    return SDL_GetMouseState(NULL, NULL) & SDL_BUTTON(SDL_BUTTON_LEFT);
}
int getbutjmou() {
#ifdef ELMA_PS3
    if (editor_input && !ps3_system_menu() && (pad_ui_buttons & (1u << PS3_SQUARE))) return 1;
#endif
    return SDL_GetMouseState(NULL, NULL) & SDL_BUTTON(SDL_BUTTON_RIGHT);
}

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
    if (window) {
#ifdef ELMA_PS3
        ps3_message(text.c_str(), present_dialog_backdrop);
#else
        SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR, "Elasto Mania", text.c_str(), window);
#endif
    }
    ddfinish(); exit(1);
}
void uzenet(char* a, char* b, char* c) {
    const std::string text = message(a, b, c);
    if (window) {
#ifdef ELMA_PS3
        ps3_message(text.c_str(), locked ? present_dialog_backdrop : present);
#else
        SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_INFORMATION, "Elasto Mania", text.c_str(), window);
#endif
    }
    else fprintf(stderr, "%s\n", text.c_str());
}
#endif
void mv_exit(char*) {
#ifdef ELMA_PS3
    // XMB Exit Game bypasses the shared menu's save path. Commit preferences
    // before destroying the renderer, while storage errors can still display.
    static bool exiting=false;
    if(!exiting){exiting=true;if(State)State->save();}
#endif
    ddfinish();exit(0);
}

int main(int argc, char** argv) {
    void upgradehakell(); void initqopen();
    void initmenukep1(); void initmenukep2();
#ifdef ELMA_PS3
    ps3_prepare(argc, argv);
#endif
    config_load();
#ifdef ELMA_PS3
    ddinit(); // Show native error dialogs even when game data is missing.
    upgradehakell(); initqopen(); mk_init(); initmenukep1(); initmenukep2(); mv_main();
#else
    upgradehakell(); initqopen(); mk_init(); initmenukep1();
    ddinit(); initmenukep2(); mv_main();
#endif
    return 0;
}
