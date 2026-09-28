// Before all.h: <cstdio> would undefine its fopen, which finds elma.cfg
// under any case.
#include <sys/stat.h>
#include <string>
#include <vector>
#include "all.h"
#include "SDL_SETTINGS.H"

namespace {
const char config_name[] = "elma.cfg";
// Windows Notepad starts UTF-8 files with it.
const char byte_order_mark[] = "\xEF\xBB\xBF";

// The lines of the file as they were read, with the key and value of the
// "key = value" ones and the line ending, so that saving keeps everything
// else as it was.
struct Line {
    std::string text, key, value, ending;
};
std::vector<Line> lines;
bool has_byte_order_mark = false;
std::string newline = "\n"; // of the file, for the lines that are added
bool loaded = false;        // elma.cfg was found, under any case

std::string trim(const std::string& text) {
    const char* const space = " \t\r\n";
    const size_t first = text.find_first_not_of(space);
    if (first == std::string::npos) return "";
    return text.substr(first, text.find_last_not_of(space) - first + 1);
}

Line parse(const std::string& text) {
    Line line;
    line.text = text;
    const std::string content = text.substr(0, text.find('#'));
    const size_t equals = content.find('=');
    if (equals != std::string::npos) {
        line.key = trim(content.substr(0, equals));
        line.value = trim(content.substr(equals + 1));
    }
    return line;
}

// The last line of a key counts.
Line* find(const char* key) {
    for (size_t i = lines.size(); i-- > 0;)
        if (!lines[i].key.empty() && stricmp(lines[i].key.c_str(), key) == 0) return &lines[i];
    return NULL;
}
}

void config_load() {
    lines.clear();
    has_byte_order_mark = false;
    newline = "\n";
    loaded = false;
    FILE* h = fopen(config_name, "rb");
    if (!h) return;
    loaded = true;
    std::string content;
    int c;
    while ((c = fgetc(h)) != EOF) content += char(c);
    fclose(h);
    size_t start = 0;
    if (content.compare(0, 3, byte_order_mark) == 0) {
        has_byte_order_mark = true;
        start = 3;
    }
    bool newline_known = false;
    while (start < content.size()) {
        const size_t end = content.find('\n', start);
        std::string text = content.substr(start, end == std::string::npos ? std::string::npos : end - start);
        std::string ending;
        if (end != std::string::npos) {
            ending = "\n";
            if (!text.empty() && text[text.size() - 1] == '\r') {
                text.erase(text.size() - 1);
                ending = "\r\n";
            }
            if (!newline_known) newline = ending;
            newline_known = true;
            start = end + 1;
        } else {
            start = content.size();
        }
        lines.push_back(parse(text));
        lines.back().ending = ending;
    }
}

const char* config_get(const char* key, const char* fallback) {
    std::string name = "ELMA_";
    for (const char* p = key; *p; ++p) name += char(toupper((unsigned char)*p));
    const char* value = getenv(name.c_str());
    if (value && *value) return value;
    const Line* line = find(key);
    return line && !line->value.empty() ? line->value.c_str() : fallback;
}

void config_set(const char* key, const char* value) {
    Line* line = find(key);
    if (!line) {
        lines.push_back(Line());
        line = &lines.back();
    }
    // A comment after the old value stays.
    const size_t comment = line->text.find('#');
    line->text = std::string(key) + " = " + value +
                 (comment == std::string::npos ? "" : " " + line->text.substr(comment));
    line->key = key;
    line->value = value;
}

void config_save() {
    std::string content = has_byte_order_mark ? byte_order_mark : "";
    for (size_t i = 0; i < lines.size(); ++i)
        content += lines[i].text + (lines[i].ending.empty() ? newline : lines[i].ending);
    // A new file, or a plain file of this very name, is written next to it
    // and then put in its place, so that an interrupted save keeps the old
    // settings. A file found under another case (Elma.cfg) or a link is
    // written in place.
    struct stat status;
    const bool replace = lstat(config_name, &status) == 0 ? S_ISREG(status.st_mode) : !loaded;
    const std::string temporary = std::string(config_name) + ".tmp";
    FILE* h = fopen(replace ? temporary.c_str() : config_name, "wb");
    if (!h) return;
    const bool written = fwrite(content.data(), 1, content.size(), h) == content.size();
    if (fclose(h) == 0 && written && (!replace || rename(temporary.c_str(), config_name) == 0)) return;
    if (replace) remove(temporary.c_str());
}

namespace {
const char* const aspect_keys[ASPECT_COUNT] = { "screen", "4:3" };
const char* const aspect_names[ASPECT_COUNT] = { "Screen", "4:3" };
}

Aspect config_aspect() {
    const char* value = config_get("aspect", NULL);
    if (value)
        for (int i = 0; i < ASPECT_COUNT; ++i)
            if (stricmp(value, aspect_keys[i]) == 0) return Aspect(i);
    return ASPECT_SCREEN;
}

const char* aspect_key(Aspect aspect) { return aspect_keys[aspect]; }
const char* aspect_name(Aspect aspect) { return aspect_names[aspect]; }

namespace {
const int resolution_options[] = { RESOLUTION_AUTO, RESOLUTION_NATIVE, RESOLUTION_ORIGINAL };
bool resolution_read = false;
int current_resolution = RESOLUTION_AUTO;
}

int config_resolution() {
    if (!resolution_read) {
        resolution_read = true;
#ifdef ELMA_HANDHELD
        current_resolution = RESOLUTION_ORIGINAL; // the CPU draws every pixel
#endif
        const char* value = config_get("resolution", NULL);
        if (value) {
            if (stricmp(value, "auto") == 0) current_resolution = RESOLUTION_AUTO;
            else if (stricmp(value, "native") == 0) current_resolution = RESOLUTION_NATIVE;
            else if (stricmp(value, "original") == 0) current_resolution = RESOLUTION_ORIGINAL;
            else if (atoi(value) > 0) current_resolution = atoi(value);
        }
    }
    return current_resolution;
}

void set_config_resolution(int resolution) {
    resolution_read = true;
    current_resolution = resolution;
    char text[32];
    if (resolution == RESOLUTION_AUTO) strcpy(text, "auto");
    else if (resolution == RESOLUTION_NATIVE) strcpy(text, "native");
    else if (resolution == RESOLUTION_ORIGINAL) strcpy(text, "original");
    else snprintf(text, sizeof(text), "%d", resolution);
    config_set("resolution", text);
    config_save();
}

const char* resolution_name(int resolution) {
    static char text[32];
    if (resolution == RESOLUTION_AUTO) return "Auto";
    if (resolution == RESOLUTION_NATIVE) return "Native";
    if (resolution == RESOLUTION_ORIGINAL) return "Original";
    snprintf(text, sizeof(text), "%d", resolution);
    return text;
}

int next_resolution_option(int resolution) {
    const int count = sizeof(resolution_options) / sizeof(resolution_options[0]);
    for (int i = 0; i < count; ++i)
        if (resolution_options[i] == resolution) return resolution_options[(i + 1) % count];
    return resolution_options[0];
}

void base_view_size(Aspect aspect, int out_w, int out_h, int* w, int* h) {
    *w = 640;
    *h = 480;
    if (out_w <= 0 || out_h <= 0) return;
    // In 64 bits, as out_w * 480 of a huge window must not overflow.
    const long long ow = out_w, oh = out_h;
    if (aspect != ASPECT_SCREEN) {
    } else if (ow * 9 > oh * 21) {
        *w = 1120; // 480 * 21 / 9
    } else if (ow * 3 >= oh * 4) {
        // 2 * round(240 * ow / oh)
        *w = int(2 * ((480 * ow + oh) / (2 * oh)));
    } else if (ow > oh) {
        // 2 * round(320 * oh / ow)
        *h = int(2 * ((640 * oh + ow) / (2 * ow)));
    } else {
        *h = 640;
    }
}

void game_view_size(Aspect aspect, int out_w, int out_h, int* w, int* h) {
    base_view_size(aspect, out_w, out_h, w, h);
    if (out_w <= 0 || out_h <= 0) return;
    // More pixels for the same part of the level:
    const int resolution = config_resolution();
    if (resolution == RESOLUTION_ORIGINAL) return;
    const int base_w = *w, base_h = *h;
    double scale = double(out_w) / base_w < double(out_h) / base_h ? double(out_w) / base_w
                                                                   : double(out_h) / base_h;
    if (resolution == RESOLUTION_AUTO) scale = floor(scale);
    else if (resolution > 0) scale = double(resolution) / base_h;
    if (scale > double(MAXKEPXSIZE) / base_w) scale = double(MAXKEPXSIZE) / base_w;
    if (scale > double(MAXKEPYSIZE) / base_h) scale = double(MAXKEPYSIZE) / base_h;
    if (scale <= 1.0) return;
    *w = 2 * int(base_w * scale / 2);
    *h = int(base_h * scale);
}

bool config_flag(const char* key, bool fallback) {
    const char* value = config_get(key, NULL);
    return value ? strcmp(value, "0") != 0 : fallback;
}

namespace {
bool zoom_read = false, zoom_textures_read = false;
double current_zoom = 1.0;
bool zoom_textures = true;

double limited_zoom(double value) {
    if (!(value >= NAGYITASMIN)) return value != value ? 1.0 : NAGYITASMIN; // NaN: 1
    return value > NAGYITASMAX ? NAGYITASMAX : value;
}
}

double config_zoom() {
    if (!zoom_read) {
        zoom_read = true;
        const char* value = config_get("zoom", NULL);
        char* end = NULL;
        const double number = value ? strtod(value, &end) : 1.0;
        current_zoom = value && end != value ? limited_zoom(number) : 1.0;
    }
    return current_zoom;
}

void set_config_zoom(double value) {
    zoom_read = true;
    current_zoom = limited_zoom(value);
    char text[32];
    snprintf(text, sizeof(text), "%g", current_zoom);
    config_set("zoom", text);
    config_save();
}

bool config_zoom_textures() {
    if (!zoom_textures_read) {
        zoom_textures_read = true;
        zoom_textures = config_flag("zoom_textures", true);
    }
    return zoom_textures;
}

void set_config_zoom_textures(bool on) {
    zoom_textures_read = true;
    zoom_textures = on;
    config_set("zoom_textures", on ? "1" : "0");
    config_save();
}

bool config_zoom_grass() { return config_flag("zoom_grass", true); }

namespace {
struct KeyName { const char* name; int code; };
const KeyName key_names[] = {
    {"ESCAPE", DIK_ESCAPE}, {"1", DIK_1}, {"2", DIK_2}, {"3", DIK_3}, {"4", DIK_4},
    {"5", DIK_5}, {"6", DIK_6}, {"7", DIK_7}, {"8", DIK_8}, {"9", DIK_9}, {"0", DIK_0},
    {"MINUS", DIK_MINUS}, {"EQUALS", DIK_EQUALS}, {"BACK", DIK_BACK}, {"TAB", DIK_TAB},
    {"Q", DIK_Q}, {"W", DIK_W}, {"E", DIK_E}, {"R", DIK_R}, {"T", DIK_T}, {"Y", DIK_Y},
    {"U", DIK_U}, {"I", DIK_I}, {"O", DIK_O}, {"P", DIK_P}, {"LBRACKET", DIK_LBRACKET},
    {"RBRACKET", DIK_RBRACKET}, {"RETURN", DIK_RETURN}, {"LCONTROL", DIK_LCONTROL},
    {"A", DIK_A}, {"S", DIK_S}, {"D", DIK_D}, {"F", DIK_F}, {"G", DIK_G}, {"H", DIK_H},
    {"J", DIK_J}, {"K", DIK_K}, {"L", DIK_L}, {"SEMICOLON", DIK_SEMICOLON},
    {"APOSTROPHE", DIK_APOSTROPHE}, {"GRAVE", DIK_GRAVE}, {"LSHIFT", DIK_LSHIFT},
    {"BACKSLASH", DIK_BACKSLASH}, {"Z", DIK_Z}, {"X", DIK_X}, {"C", DIK_C}, {"V", DIK_V},
    {"B", DIK_B}, {"N", DIK_N}, {"M", DIK_M}, {"COMMA", DIK_COMMA}, {"PERIOD", DIK_PERIOD},
    {"SLASH", DIK_SLASH}, {"RSHIFT", DIK_RSHIFT}, {"MULTIPLY", DIK_MULTIPLY},
    {"LMENU", DIK_LMENU}, {"SPACE", DIK_SPACE}, {"F1", DIK_F1}, {"F2", DIK_F2},
    {"F3", DIK_F3}, {"F4", DIK_F4}, {"F5", DIK_F5}, {"F6", DIK_F6}, {"F7", DIK_F7},
    {"F8", DIK_F8}, {"F9", DIK_F9}, {"F10", DIK_F10}, {"F12", DIK_F12},
    {"NUMPAD7", DIK_NUMPAD7}, {"NUMPAD8", DIK_NUMPAD8}, {"NUMPAD9", DIK_NUMPAD9},
    {"SUBTRACT", DIK_SUBTRACT}, {"NUMPAD4", DIK_NUMPAD4}, {"NUMPAD5", DIK_NUMPAD5},
    {"NUMPAD6", DIK_NUMPAD6}, {"ADD", DIK_ADD}, {"NUMPAD1", DIK_NUMPAD1},
    {"NUMPAD2", DIK_NUMPAD2}, {"NUMPAD3", DIK_NUMPAD3}, {"NUMPAD0", DIK_NUMPAD0},
    {"DECIMAL", DIK_DECIMAL}, {"NUMPADENTER", DIK_NUMPADENTER}, {"RCONTROL", DIK_RCONTROL},
    {"DIVIDE", DIK_DIVIDE}, {"RMENU", DIK_RMENU}, {"HOME", DIK_HOME}, {"UP", DIK_UP},
    {"PRIOR", DIK_PRIOR}, {"PGUP", DIK_PRIOR}, {"PAGEUP", DIK_PRIOR}, {"LEFT", DIK_LEFT},
    {"RIGHT", DIK_RIGHT}, {"END", DIK_END}, {"DOWN", DIK_DOWN}, {"NEXT", DIK_NEXT},
    {"PGDN", DIK_NEXT}, {"PGDOWN", DIK_NEXT}, {"PAGEDOWN", DIK_NEXT}, {"INSERT", DIK_INSERT},
    {"DELETE", DIK_DELETE},
};

// A DirectInput name (with or without DIK_) or a hex code (0xC9); 0 for
// "none" or an unknown name.
int key_code(const char* text) {
    std::string name;
    for (const char* p = text; *p; ++p) name += char(toupper((unsigned char)*p));
    if (name.compare(0, 4, "DIK_") == 0) name = name.substr(4);
    if (name.empty() || name == "NONE") return 0;
    if (name.compare(0, 2, "0X") == 0 && name.size() > 2) {
        char* end = NULL;
        const long code = strtol(name.c_str() + 2, &end, 16);
        return *end == 0 && code > 0 && code < 256 ? int(code) : 0;
    }
    for (size_t i = 0; i < sizeof(key_names) / sizeof(key_names[0]); ++i)
        if (name == key_names[i].name) return key_names[i].code;
    return 0;
}
}

int config_zoom_key(bool zoom_in) {
    const char* value = config_get(zoom_in ? "zoom_in_key" : "zoom_out_key", NULL);
    if (!value) return zoom_in ? DIK_PRIOR : DIK_NEXT;
    return key_code(value);
}

const char* zoom_name(double value) {
    static char text[32];
    snprintf(text, sizeof(text), "%gx", value);
    return text;
}

double next_zoom_option(double value) {
    static const double options[] = { 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2, 2.5, 3, 3.5, 4 };
    const int count = int(sizeof(options) / sizeof(options[0]));
    for (int i = 0; i < count; ++i)
        if (options[i] > value + 1e-6) return options[i];
    return options[0];
}
