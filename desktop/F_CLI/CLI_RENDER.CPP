#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "F_CLI/CLI_HOOK.H"
#include "F_CLI/CLI_RENDER.H"

namespace {
const int picture_width = 640;
const int picture_height = 480;

const uint32_t black = 0x000000;
const uint32_t menu_yellow = 0xf0e040;
const uint32_t cursor_red = 0xe02828;
const uint32_t upper_half_block = 0x2580;
const uint32_t braille_blank = 0x2800;

int red(uint32_t c) { return (c >> 16) & 0xff; }
int green(uint32_t c) { return (c >> 8) & 0xff; }
int blue(uint32_t c) { return c & 0xff; }
uint32_t rgb(int r, int g, int b) { return (uint32_t(r) << 16) | (uint32_t(g) << 8) | uint32_t(b); }
int luminance(uint32_t c) { return (red(c) * 299 + green(c) * 587 + blue(c) * 114) / 1000; }

uint32_t average(uint32_t a, uint32_t b) {
    return rgb((red(a) + red(b)) / 2, (green(a) + green(b)) / 2, (blue(a) + blue(b)) / 2);
}

void append_utf8(std::string* out, uint32_t c) {
    if (c < 0x80) {
        out->push_back(char(c));
    } else if (c < 0x800) {
        out->push_back(char(0xc0 | (c >> 6)));
        out->push_back(char(0x80 | (c & 0x3f)));
    } else {
        out->push_back(char(0xe0 | (c >> 12)));
        out->push_back(char(0x80 | ((c >> 6) & 0x3f)));
        out->push_back(char(0x80 | (c & 0x3f)));
    }
}

void append_number(std::string* out, int n) {
    char digits[12];
    int count = 0;
    do {
        digits[count++] = char('0' + n % 10);
        n /= 10;
    } while (n > 0);
    while (count > 0) out->push_back(digits[--count]);
}

// Nearest color of the 256-color palette, for terminals without true color.
int xterm_color(uint32_t c) {
    static const int levels[6] = {0, 95, 135, 175, 215, 255};
    int cube[3];
    const int channels[3] = {red(c), green(c), blue(c)};
    for (int i = 0; i < 3; ++i) {
        int best = 0;
        for (int j = 1; j < 6; ++j)
            if (std::abs(levels[j] - channels[i]) < std::abs(levels[best] - channels[i])) best = j;
        cube[i] = best;
    }
    const int cube_index = 16 + 36 * cube[0] + 6 * cube[1] + cube[2];
    const uint32_t cube_color = rgb(levels[cube[0]], levels[cube[1]], levels[cube[2]]);
    const int gray_step = std::min(23, std::max(0, (luminance(c) - 8) / 10));
    const int gray_level = 8 + gray_step * 10;
    const uint32_t gray_color = rgb(gray_level, gray_level, gray_level);
    int cube_distance = 0, gray_distance = 0;
    for (int i = 0; i < 3; ++i) {
        const int shift = 16 - 8 * i;
        cube_distance += std::abs(int((cube_color >> shift) & 0xff) - channels[i]);
        gray_distance += std::abs(int((gray_color >> shift) & 0xff) - channels[i]);
    }
    return gray_distance < cube_distance ? 232 + gray_step : cube_index;
}

bool terminal_has_truecolor() {
    const char* colorterm = getenv("COLORTERM");
    if (colorterm && (strstr(colorterm, "truecolor") || strstr(colorterm, "24bit"))) return true;
    const char* term = getenv("TERM");
    return term && (strstr(term, "ghostty") || strstr(term, "kitty") || strstr(term, "direct") ||
                    strstr(term, "wezterm") || strstr(term, "alacritty") || strstr(term, "foot"));
}
}

cli_renderer::cli_renderer()
    : cols_(0), rows_(0), left_(0), top_(0), width_(0), height_(0), full_(true),
      truecolor_(terminal_has_truecolor()) {}

// Keeps the 4:3 shape of the picture; a terminal cell is about twice as
// high as it is wide.
void cli_renderer::layout(int cols, int rows) {
    if (cols != cols_ || rows != rows_) {
        cols_ = cols;
        rows_ = rows;
        full_ = true;
    }
    width_ = cols;
    height_ = (width_ * 3 + 4) / 8;
    if (height_ > rows) {
        height_ = rows;
        width_ = std::min(cols, (height_ * 8 + 1) / 3);
    }
    left_ = (cols - width_) / 2;
    top_ = (rows - height_) / 2;
    const cell empty = {' ', black, black};
    cells_.assign(size_t(cols) * rows, empty);
}

void cli_renderer::draw_picture(const cli_frame& frame) {
    int sub_x = 1, sub_y = 2;
    if (frame.graphics == CLI_GRAPHICS_BRAILLE) {
        sub_x = 2;
        sub_y = 4;
    } else if (frame.graphics == CLI_GRAPHICS_ASCII) {
        sub_y = 1;
    }
    const int grid_x = width_ * sub_x, grid_y = height_ * sub_y;
    if (grid_x <= 0 || grid_y <= 0) return;

    // Average color of the picture area behind each sub-cell sample:
    samples_.assign(size_t(grid_x) * grid_y, 0);
    std::vector<int> x_start(grid_x), x_end(grid_x);
    for (int i = 0; i < grid_x; ++i) {
        x_start[i] = std::min(picture_width - 1, i * picture_width / grid_x);
        x_end[i] = std::max(x_start[i] + 1, (i + 1) * picture_width / grid_x);
    }
    std::vector<uint32_t> sums(size_t(grid_x) * 4);
    for (int j = 0; j < grid_y; ++j) {
        const int y1 = std::min(picture_height - 1, j * picture_height / grid_y);
        const int y2 = std::max(y1 + 1, (j + 1) * picture_height / grid_y);
        std::fill(sums.begin(), sums.end(), 0);
        for (int y = y1; y < y2; ++y) {
            const unsigned char* row = frame.pixels + y * picture_width;
            for (int i = 0; i < grid_x; ++i) {
                uint32_t* sum = &sums[i * 4];
                for (int x = x_start[i]; x < x_end[i]; ++x) {
                    const uint32_t c = frame.palette[row[x]];
                    sum[0] += red(c);
                    sum[1] += green(c);
                    sum[2] += blue(c);
                    ++sum[3];
                }
            }
        }
        for (int i = 0; i < grid_x; ++i) {
            const uint32_t* sum = &sums[i * 4];
            samples_[size_t(j) * grid_x + i] = rgb(sum[0] / sum[3], sum[1] / sum[3], sum[2] / sum[3]);
        }
    }

    for (int row = 0; row < height_; ++row) {
        for (int col = 0; col < width_; ++col) {
            cell& c = at(left_ + col, top_ + row);
            if (frame.graphics == CLI_GRAPHICS_HALF_BLOCKS) {
                const uint32_t upper = samples_[size_t(row * 2) * grid_x + col];
                const uint32_t lower = samples_[size_t(row * 2 + 1) * grid_x + col];
                c.ch = upper == lower ? ' ' : upper_half_block;
                c.fg = upper;
                c.bg = lower;
            } else if (frame.graphics == CLI_GRAPHICS_BRAILLE) {
                // Two colors per cell: the dots brighter than the cell
                // average get the foreground, the others the background.
                static const int dot_bits[4][2] = {{0x01, 0x08}, {0x02, 0x10}, {0x04, 0x20}, {0x40, 0x80}};
                uint32_t dots[4][2];
                int lum[4][2], lum_sum = 0, lum_min = 255, lum_max = 0;
                for (int dy = 0; dy < 4; ++dy)
                    for (int dx = 0; dx < 2; ++dx) {
                        dots[dy][dx] = samples_[size_t(row * 4 + dy) * grid_x + col * 2 + dx];
                        lum[dy][dx] = luminance(dots[dy][dx]);
                        lum_sum += lum[dy][dx];
                        lum_min = std::min(lum_min, lum[dy][dx]);
                        lum_max = std::max(lum_max, lum[dy][dx]);
                    }
                int bits = 0, on[4] = {0, 0, 0, 0}, off[4] = {0, 0, 0, 0};
                for (int dy = 0; dy < 4; ++dy)
                    for (int dx = 0; dx < 2; ++dx) {
                        const bool lit = lum_max - lum_min >= 24 && lum[dy][dx] * 8 > lum_sum;
                        int* target = lit ? on : off;
                        if (lit) bits |= dot_bits[dy][dx];
                        target[0] += red(dots[dy][dx]);
                        target[1] += green(dots[dy][dx]);
                        target[2] += blue(dots[dy][dx]);
                        ++target[3];
                    }
                c.bg = off[3] ? rgb(off[0] / off[3], off[1] / off[3], off[2] / off[3]) : black;
                c.fg = on[3] ? rgb(on[0] / on[3], on[1] / on[3], on[2] / on[3]) : c.bg;
                c.ch = bits ? braille_blank + bits : ' ';
            } else {
                static const char ramp[] = " .:-=+*#%@";
                const uint32_t color = samples_[size_t(row) * grid_x + col];
                c.ch = ramp[luminance(color) * 10 / 256];
                c.fg = color;
                c.bg = black;
            }
        }
    }
}

// Writes text over the picture; the cells keep the color behind them, so the
// text looks like it is written onto the scene.
void cli_renderer::draw_text(const std::string& text, int col, int row, uint32_t color, bool contrast) {
    if (row < 0 || row >= rows_) return;
    for (size_t i = 0; i < text.size(); ++i) {
        const int x = col + int(i);
        if (x < 0 || x >= cols_) continue;
        cell& c = at(x, row);
        if (c.ch == upper_half_block) c.bg = average(c.fg, c.bg);
        c.ch = (unsigned char)text[i];
        c.fg = contrast ? (luminance(c.bg) > 140 ? 0x101010 : 0xf8f8f8) : color;
    }
}

void cli_renderer::render(const cli_frame& frame, int cols, int rows, std::string* out) {
    layout(cols, rows);
    draw_picture(frame);

    const std::vector<cli_overlay>& overlays = *frame.overlays;
    for (size_t i = 0; i < overlays.size(); ++i) {
        const cli_overlay& o = overlays[i];
        const int length = int(o.text.size());
        const int row = top_ + o.y * height_ / picture_height;
        int col = left_ + o.x * width_ / picture_width;
        if (o.align == CLI_ALIGN_CENTER) col -= length / 2;
        if (o.align == CLI_ALIGN_RIGHT) col = left_ + (o.x + 1) * width_ / picture_width - length;
        draw_text(o.text, col, row, menu_yellow, o.color == CLI_COLOR_TIME);
    }

    if (frame.cursor) {
        // A spinning disc in place of the rotating helmet:
        static const uint32_t frames[4] = {0x25d0, 0x25d3, 0x25d1, 0x25d2};
        const uint32_t glyph = frame.animated_cursor ? frames[int(frame.time * 6.0) % 4] : 0x25cf;
        const int col = left_ + frame.cursor_x * width_ / picture_width;
        const int row = top_ + frame.cursor_y * height_ / picture_height;
        if (col >= 0 && col < cols_ && row >= 0 && row < rows_) {
            cell& c = at(col, row);
            if (c.ch == upper_half_block) c.bg = average(c.fg, c.bg);
            c.ch = glyph;
            c.fg = cursor_red;
        }
    }
    emit(out);
}

void cli_renderer::render_message(const std::vector<std::string>& lines, int cols, int rows, std::string* out) {
    if (cols != cols_ || rows != rows_ || cells_.empty()) {
        layout(cols, rows);
    }
    size_t longest = 0;
    for (size_t i = 0; i < lines.size(); ++i) longest = std::max(longest, lines[i].size());
    const int box_width = std::min(cols, int(longest) + 6);
    const int box_height = std::min(rows, int(lines.size()) + 4);
    const int x0 = (cols - box_width) / 2, y0 = (rows - box_height) / 2;
    const uint32_t box_bg = 0x183018, frame_color = menu_yellow;
    for (int y = 0; y < box_height; ++y)
        for (int x = 0; x < box_width; ++x) {
            cell& c = at(x0 + x, y0 + y);
            c.bg = box_bg;
            c.fg = frame_color;
            const bool top = y == 0, bottom = y == box_height - 1, left = x == 0, right = x == box_width - 1;
            if (top && left) c.ch = 0x250c;
            else if (top && right) c.ch = 0x2510;
            else if (bottom && left) c.ch = 0x2514;
            else if (bottom && right) c.ch = 0x2518;
            else if (top || bottom) c.ch = 0x2500;
            else if (left || right) c.ch = 0x2502;
            else c.ch = ' ';
        }
    for (size_t i = 0; i < lines.size() && int(i) + 2 < box_height - 1; ++i) {
        const int col = x0 + (box_width - int(lines[i].size())) / 2;
        for (size_t k = 0; k < lines[i].size() && col + int(k) < x0 + box_width - 1; ++k) {
            cell& c = at(col + int(k), y0 + 2 + int(i));
            c.ch = (unsigned char)lines[i][k];
            c.fg = 0xf8f8f8;
        }
    }
    emit(out);
}

void cli_renderer::emit(std::string* out) {
    out->append("\x1b[?2026h");
    if (full_ || previous_.size() != cells_.size()) {
        out->append("\x1b[0m\x1b[2J");
        previous_.clear();
    }
    const bool full = previous_.empty();
    int cursor_row = -1, cursor_col = -1;
    uint32_t current_fg = 0xffffffff, current_bg = 0xffffffff;
    for (int row = 0; row < rows_; ++row) {
        for (int col = 0; col < cols_; ++col) {
            const size_t index = size_t(row) * cols_ + col;
            const cell& c = cells_[index];
            if (!full && c == previous_[index]) continue;
            if (row != cursor_row || col != cursor_col) {
                out->append("\x1b[");
                append_number(out, row + 1);
                out->push_back(';');
                append_number(out, col + 1);
                out->push_back('H');
            }
            if (c.fg != current_fg || c.bg != current_bg) {
                out->append("\x1b[");
                if (truecolor_) {
                    out->append("38;2;");
                    append_number(out, red(c.fg));
                    out->push_back(';');
                    append_number(out, green(c.fg));
                    out->push_back(';');
                    append_number(out, blue(c.fg));
                    out->append(";48;2;");
                    append_number(out, red(c.bg));
                    out->push_back(';');
                    append_number(out, green(c.bg));
                    out->push_back(';');
                    append_number(out, blue(c.bg));
                } else {
                    out->append("38;5;");
                    append_number(out, xterm_color(c.fg));
                    out->append(";48;5;");
                    append_number(out, xterm_color(c.bg));
                }
                out->push_back('m');
                current_fg = c.fg;
                current_bg = c.bg;
            }
            append_utf8(out, c.ch);
            cursor_row = row;
            cursor_col = col + 1;
        }
    }
    out->append("\x1b[?2026l");
    previous_ = cells_;
    full_ = false;
}
