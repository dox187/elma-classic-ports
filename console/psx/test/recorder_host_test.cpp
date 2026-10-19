// Compile with ELMA_PSX and recorder_host/ first on the include path.
// The linked RECORDER.CPP is the shipping implementation, not a test copy.
#include "recorder_host/all.h"
#include <new>

static int allocations, failures;
#define CHECK(condition) do { if (!(condition)) { \
    printf("FAIL recorder line %d: %s\n", __LINE__, #condition); ++failures; } } while (0)

void* operator new(size_t bytes) { ++allocations; return malloc(bytes); }
void* operator new[](size_t bytes) { ++allocations; return malloc(bytes); }
void operator delete(void* p) noexcept { free(p); }
void operator delete[](void* p) noexcept { free(p); }
void hiba(char* message) { fprintf(stderr, "FAIL recorder: %s\n", message); abort(); }

int main() {
    static_assert(sizeof(recorder) == 20, "PSX recorder must contain metadata only");
    recorder record;
    record.settag(7);
    char name[] = "QWQUU001.LEV";
    record.erase(name);
    hanginfo sound = { 1.5, 1, 0.25 };
    motorst bike;
    for (int i = 0; i < 10000; ++i) {
        record.store(&bike, i / 30.0, &sound);
        record.addhang(i / 30.0, char(i % 8), 0.5, i);
    }
    CHECK(sound.frekvencia == 1.5 && sound.gaz == 1 && sound.surlero == 0.25);
    CHECK(record.gettag() == 7 && !strcmp(record.palyanev, name));
    record.rewind();
    CHECK(record.recall(&bike, 0, &sound) == 0);
    CHECK(sound.frekvencia == 1 && sound.gaz == 0 && sound.surlero == 0);
    CHECK(record.gethang(0, NULL, NULL, NULL) == 0);

    // Recording removal must preserve the live, bounded physics-sound FIFO.
    resetwavegyujto();
    for (int i = 0; i < 201; ++i) startwavegyujto(i, i * 0.25, 500 - i);
    for (int i = 0; i < 200; ++i) {
        int id = -1, object = -1;
        double volume = -1;
        CHECK(getwavegyujto(&id, &volume, &object));
        CHECK(id == i && volume == i * 0.25 && object == 500 - i);
    }
    int id, object;
    double volume;
    CHECK(!getwavegyujto(&id, &volume, &object));
    startwavegyujto(42, 0.75, 123);
    resetwavegyujto();
    CHECK(!getwavegyujto(&id, &volume, &object));
    startwavegyujto(9, 0.5, 12);
    CHECK(getwavegyujto(&id, &volume, &object));
    CHECK(id == 9 && volume == 0.5 && object == 12);
    CHECK(allocations == 0);
    printf("%s: 20-byte PSX recorder, 10000 no-op samples/events, zero allocations, live 200-event sound FIFO\n",
           failures ? "FAIL" : "PASS");
    return failures ? 1 : 0;
}
