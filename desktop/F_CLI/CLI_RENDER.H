#ifndef ELMA_CLI_RENDER_H
#define ELMA_CLI_RENDER_H

#include <stdint.h>
#include <string>
#include <vector>

// Turns the 640x480 8-bit picture of the game into terminal cells, puts the
// registered texts over it and produces the escape sequences that update
// only the changed cells.

enum { CLI_GRAPHICS_HALF_BLOCKS = 0, CLI_GRAPHICS_BRAILLE, CLI_GRAPHICS_ASCII, CLI_GRAPHICS_COUNT };

struct cli_overlay {
    std::string text;
    int x, y;  // in the 640x480 picture
    int align;
    int color;
};

struct cli_frame {
    const unsigned char* pixels;  // 640x480 palette indices
    const uint32_t* palette;      // 0xRRGGBB
    const std::vector<cli_overlay>* overlays;
    bool cursor;
    int cursor_x, cursor_y;
    bool animated_cursor;
    double time;  // seconds, for the cursor animation
    int graphics;
};

class cli_renderer {
public:
    cli_renderer();
    // Appends the escape sequences for the terminal size to out.
    void render(const cli_frame& frame, int cols, int rows, std::string* out);
    // Draws a centered message box over the last frame.
    void render_message(const std::vector<std::string>& lines, int cols, int rows, std::string* out);
    void invalidate() { full_ = true; }

private:
    struct cell {
        uint32_t ch, fg, bg;
        bool operator==(const cell& o) const { return ch == o.ch && fg == o.fg && bg == o.bg; }
    };
    void layout(int cols, int rows);
    void draw_picture(const cli_frame& frame);
    void draw_text(const std::string& text, int col, int row, uint32_t color, bool contrast);
    void emit(std::string* out);
    cell& at(int col, int row) { return cells_[row * cols_ + col]; }

    std::vector<cell> cells_, previous_;
    std::vector<uint32_t> samples_;
    int cols_, rows_;          // terminal
    int left_, top_, width_, height_;  // picture area in cells
    bool full_;
    bool truecolor_;
};

#endif
