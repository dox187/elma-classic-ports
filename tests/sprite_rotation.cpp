#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <algorithm>
#include <vector>
#include "PIC8.H"
#include "VEKT2.H"
#include "KISKEP.H"
#include "DOBOZ.H"

int Cxsize = 1024, Cysize = 768;
double Hatarx1 = 2, Hatarx2 = Cxsize - 3;
double Hatary1 = 2, Hatary2 = Cysize - 3;

void hiba(char* text, char*, char*) {
    fprintf(stderr, "%s\n", text);
    abort();
}

void uzenet(char* text, char*, char*) {
    fprintf(stderr, "%s\n", text);
    abort();
}

// Memory-only pic8 adapters: the test uses the real kiskep packing and
// dobozki renderer, without loading copyrighted pictures or a display.
pic8::pic8(int w, int h, unsigned char** rows)
    : xsize(w), ysize(h), sormuttomb(rows) {}
pic8::pic8(char*, FILE*) { abort(); }
pic8::~pic8() {}
int pic8::getxsize() { return xsize; }
int pic8::getysize() { return ysize; }
unsigned char pic8::gpixel(int x, int y) { return sormuttomb[y][x]; }

int main() {
    const double pi = acos(-1.0);
    std::vector<unsigned char> source(64 * 64, 0);
    std::vector<unsigned char*> source_rows(64);
    for (int y = 0; y < 64; ++y) {
        source_rows[y] = &source[y * 64];
        for (int x = 0; x < 64; ++x) {
            const double dx = x - 31.5, dy = y - 31.5;
            if (dx * dx + dy * dy < 30 * 30) source_rows[y][x] = 1;
        }
    }
    const int source_area = std::count(source.begin(), source.end(), 1);
    kiskep wheel(NULL, new pic8(64, 64, source_rows.data()));

    std::vector<unsigned char> pixels(Cxsize * Cysize);
    std::vector<unsigned char*> rows(Cysize);
    for (int y = 0; y < Cysize; ++y) rows[y] = &pixels[y * Cxsize];
    pic8 frame(Cxsize, Cysize, rows.data());

    std::vector<double> angles;
    for (int i = 0; i < 72; ++i) angles.push_back(i * pi / 36);
    // Both sides of the renderer's near-horizontal threshold, in each
    // quadrant. These angles used to wrap the distant edge intersections.
    for (int quadrant = 0; quadrant < 4; ++quadrant)
        for (double offset : {-0.005001, -0.004999, -0.000001,
                              0.000001, 0.004999, 0.005001})
            angles.push_back(quadrant * pi / 2 + offset);

    vekt2 centers[] = {
        vekt2(Cxsize / 2, Cysize / 2),
        vekt2(0, Cysize / 2), vekt2(Cxsize - 1, Cysize / 2),
        vekt2(Cxsize / 2, 0), vekt2(Cxsize / 2, Cysize - 1)
    };
    int checks = 0;
    for (double side : {38.0, 76.0, 114.0, 152.0, 190.0, 304.0, 608.0}) {
        const double full_area = source_area * (side / 63) * (side / 63);
        for (int center = 0; center < 5; ++center) {
            // At a screen edge, approximately half the disk remains.
            const double expected_area = full_area * (center == 0 ? 1 : 0.5);
            for (double angle : angles) {
                vekt2 u(cos(angle) * side, sin(angle) * side);
                vekt2 v(sin(angle) * side, -cos(angle) * side);
                vekt2 r = centers[center] - (u + v) * 0.5;
                std::fill(pixels.begin(), pixels.end(), 0);
                dobozki(&frame, &wheel, u, v, r);
                const int area = std::count(pixels.begin(), pixels.end(), 1);
                // Allow rasterization differences, but reject disappearing
                // wheels, missing slices and drawing beyond the clip.
                if (area < expected_area * 0.9 || area > expected_area * 1.1) {
                    fprintf(stderr,
                            "side=%.0f angle=%.9f center=%d: area=%d expected=%.1f\n",
                            side, angle, center, area, expected_area);
                    return 1;
                }
                ++checks;
            }
        }
    }
    printf("Passed %d sprite rotation and clipping checks\n", checks);
    return 0;
}
