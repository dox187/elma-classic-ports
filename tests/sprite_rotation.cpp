#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <algorithm>
#include <vector>
#include <stdint.h>
#include <string.h>
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

// Transparent pixels dominate these fixtures. Skip an all-zero machine word
// while still examining every nonzero byte, without unaligned/aliasing loads.
static int count_ones(const std::vector<unsigned char>& pixels) {
    int count=0;size_t offset=0;
    for(;offset+sizeof(uint64_t)<=pixels.size();offset+=sizeof(uint64_t)) {
        uint64_t word;memcpy(&word,pixels.data()+offset,sizeof(word));
        if(!word)continue;
        for(size_t b=0;b<sizeof(word);++b)count+=pixels[offset+b]==1;
    }
    for(;offset<pixels.size();++offset)count+=pixels[offset]==1;
    return count;
}

static uint64_t hash_pixels(uint64_t hash,const std::vector<unsigned char>& pixels) {
    const uint64_t prime=UINT64_C(1099511628211);
    uint64_t zero_word=1;
    for(int byte=0;byte<8;++byte)zero_word*=prime;
    size_t offset=0;
    for(;offset+8<=pixels.size();offset+=8) {
        uint64_t word;memcpy(&word,pixels.data()+offset,8);
        // Eight zero-byte FNV steps are exactly multiplication by prime^8.
        // This preserves the existing byte-for-byte hash on both endians.
        if(!word)hash*=zero_word;
        else for(size_t byte=0;byte<8;++byte) {hash^=pixels[offset+byte];hash*=prime;}
    }
    for(;offset<pixels.size();++offset) {hash^=pixels[offset];hash*=prime;}
    return hash;
}

static void result_file(bool passed,int checks,uint64_t hash) {
#ifdef ELMA_PS3
    FILE* result=fopen("/dev_hdd0/game/ELMAC0001/USRDIR/sprite-result.txt","w");
    if(result) {
        fprintf(result,"%s checks=%d hash=%016llx\n",passed?"PASS":"FAIL",checks,(unsigned long long)hash);
        fclose(result);
    }
#else
    (void)passed;(void)checks;(void)hash;
#endif
}

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
        // A rotated disk retains its diameter. This viewport leaves four
        // guard pixels around the largest centered disk, while retaining all
        // four edge clips. Tiny sprites need not scan a full HD-sized buffer.
        Cxsize=Cysize=std::max(80,int(side)+8);
        Hatarx2=Cxsize-3;Hatary2=Cysize-3;
        std::vector<unsigned char> case_pixels(Cxsize*Cysize);
        std::vector<unsigned char*> case_rows(Cysize);
        for(int y=0;y<Cysize;++y)case_rows[y]=case_pixels.data()+y*Cxsize;
        pic8 case_frame(Cxsize,Cysize,case_rows.data());
        const vekt2 case_centers[]={vekt2(Cxsize/2,Cysize/2),vekt2(0,Cysize/2),
            vekt2(Cxsize-1,Cysize/2),vekt2(Cxsize/2,0),vekt2(Cxsize/2,Cysize-1)};
        const double full_area = source_area * (side / 63) * (side / 63);
        for (int center = 0; center < 5; ++center) {
            // At a screen edge, approximately half the disk remains.
            const double expected_area = full_area * (center == 0 ? 1 : 0.5);
            for (double angle : angles) {
                vekt2 u(cos(angle) * side, sin(angle) * side);
                vekt2 v(sin(angle) * side, -cos(angle) * side);
                vekt2 r = case_centers[center];
                r = r - (u + v) * 0.5;
                std::fill(case_pixels.begin(), case_pixels.end(), 0);
                dobozki(&case_frame, &wheel, u, v, r);
                const int area = count_ones(case_pixels);
                // Allow rasterization differences, but reject disappearing
                // wheels, missing slices and drawing beyond the clip.
                if (area < expected_area * 0.9 || area > expected_area * 1.1) {
                    fprintf(stderr,
                            "side=%.0f angle=%.9f center=%d: area=%d expected=%.1f\n",
                            side, angle, center, area, expected_area);
                    result_file(false,checks,0);
                    return 1;
                }
                ++checks;
            }
        }
    }
    Cxsize=1024;Cysize=768;Hatarx2=Cxsize-3;Hatary2=Cysize-3;
    // The area checks catch disappearing sprites. This second fixture checks
    // orientation and both texture-coordinate words using varied palette bytes.
    // Integer-valued transforms are exactly representable on host and PPC, so
    // this hash does not depend on small platform libm differences in sin/cos.
    for(int y=0;y<64;++y) for(int x=0;x<64;++x)
        if(source[y*64+x])source[y*64+x]=(unsigned char)(1+(x*3+y*5)%31);
    kiskep patterned(NULL,new pic8(64,64,source_rows.data()));
    const int directions[][2]={{5,0},{3,4},{0,5},{-3,4},{-5,0},{-3,-4},{0,-5},{3,-4}};
    uint64_t hash=UINT64_C(14695981039346656037);
    for(int scale : {8,16,32}) for(int center=0;center<5;++center)
        for(const auto& direction : directions) {
            vekt2 u(direction[0]*scale,direction[1]*scale);
            vekt2 v(direction[1]*scale,-direction[0]*scale);
            vekt2 r=centers[center]-(u+v)*0.5;
            std::fill(pixels.begin(),pixels.end(),0);
            dobozki(&frame,&patterned,u,v,r);
            hash=hash_pixels(hash,pixels);
        }
    printf("Sprite raster hash %016llx\n",(unsigned long long)hash);
    // Expected value is shared by x86 host and native big-endian PPC runs.
    const uint64_t expected=UINT64_C(0x18552202131d5665);
    if(hash!=expected) {result_file(false,checks,hash);return 1;}
    result_file(true,checks,hash);
    printf("Passed %d sprite rotation and clipping checks\n", checks);
    return 0;
}
