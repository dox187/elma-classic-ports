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
