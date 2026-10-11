#include <cstdio>
#include <cstdlib>
#include <cmath>
#include "VEKT2.H"
#include "PUBGOLY.H"
#include "GOLYOK.H"
#include "F_SDL/SDL_SETTINGS.H"

double K_pip2 = std::acos(-1.0)/2;
void golyofalak(int, int);
FILE* elma_fopen(const char* path, const char* mode) { return std::fopen(path, mode); }
int s_random(int n) { return n/2; }
void hiba(char* text, char*, char*) {
    std::fprintf(stderr, "%s\n", text);
    std::abort();
}
void require(bool ok, const char* message) {
    if (!ok) {
        std::fprintf(stderr, "%s\n", message);
        std::exit(1);
    }
}

int main() {
    unsetenv("ELMA_MENU_SCALE");
    const int outputs[][4] = {
        {640, 480, 640, 480}, {1280, 960, 640, 480},
        {1920, 1080, 854, 480}, {2560, 1440, 854, 480},
        {3840, 2160, 854, 480}, {5120, 2880, 854, 480},
        {2560, 1080, 1138, 480}, {720, 720, 640, 640},
        {1080, 1920, 640, 1138}, {320, 240, 640, 480},
        {0, 0, 640, 480}
    };
    for (const auto& output : outputs) {
        int w, h;
        menu_view_size(output[0], output[1], &w, &h);
        require(w == output[2] && h == output[3], "Automatic menu scale changed with display density");
    }
    int w, h;
    setenv("ELMA_MENU_SCALE", "1", 1);
    menu_view_size(1920, 1080, &w, &h);
    require(w == 1920 && h == 1080, "Explicit native menu scale was ignored");
    setenv("ELMA_MENU_SCALE", "2", 1);
    menu_view_size(3840, 2160, &w, &h);
    require(w == 1920 && h == 1080, "Explicit 2x menu scale was ignored");
    unsetenv("ELMA_MENU_SCALE");

    initgolyo();
    // Resize after the simulation has cached future collisions, then run
    // far enough for the balls to hit both each other and the new walls.
    const int sizes[][2] = {{854,480}, {1920,1080}, {640,640}, {640,480}, {1138,480}};
    for (const auto& size : sizes) {
        golyofalak(size[0], size[1]);
        golyomeret(size[0], size[1]);
        require(std::abs(Golyok[4].rmostani.x - size[0]/2.0) < 1e-9 &&
                std::abs(Golyok[4].rmostani.y - size[1]/2.0) < 1e-9,
                "Balls were not centered after resizing");
        const double scale = std::fmin(size[0]/640.0, size[1]/480.0);
        require(std::abs(Golyok[2].sug - 50*scale) < 1e-9, "Ball radius was not scaled");
        for (int step = 0; step < 12000; ++step) {
            leptetgolyo(1.0);
            for (int i = 0; i < Ngolyok; ++i) {
                const golyo& ball = Golyok[i];
                require(std::isfinite(ball.rmostani.x) && std::isfinite(ball.rmostani.y) &&
                        ball.rmostani.x >= ball.sug-1e-6 && ball.rmostani.x <= size[0]-ball.sug+1e-6 &&
                        ball.rmostani.y >= ball.sug-1e-6 && ball.rmostani.y <= size[1]-ball.sug+1e-6,
                        "Ball escaped the resized menu walls");
            }
        }
    }
    std::puts("Passed menu scaling, centered ball layout and resize collision checks");
}
