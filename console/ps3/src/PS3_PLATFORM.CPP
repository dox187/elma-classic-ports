#include "PS3_PLATFORM.H"
#include "PS3_SYSTEM_UI.H"
#include "PS3_CONTROLS.H"
#include "PS3_MEMORY.H"
#include <SDL.h>
#include <io/pad.h>
#include <sys/process.h>
#include <sys/memory.h>
#include <sysutil/sysutil.h>
#include <sysutil/video.h>
#include <sysutil/msg.h>
#include <sys/stat.h>
#include <unistd.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <malloc.h>
#include <new>
#include <atomic>
#include "ATOMIC_FILE.H"

SYS_PROCESS_PARAM(1001, 0x100000);

namespace {
unsigned masks[2] = {};
int axes[2][4] = {};
bool quit_requested = false, initialized = false;
Ps3SystemUiState system_ui;
static_assert(SYSUTIL_DRAW_BEGIN == Ps3SystemUiState::DrawBegin &&
              SYSUTIL_DRAW_END == Ps3SystemUiState::DrawEnd &&
              SYSUTIL_MENU_OPEN == Ps3SystemUiState::MenuOpen &&
              SYSUTIL_MENU_CLOSE == Ps3SystemUiState::MenuClose, "sysutil event ABI");
bool diagnostics_enabled = false;
int television_aspect = VIDEO_ASPECT_16_9;
int refresh_rate = 60;
// Keep enough allocator space to report an unexpected allocation failure.
// Ordinary oversized zoom requests are rejected before rebuilding graphics.
void* emergency_memory = NULL;
void (*memory_repaint)() = NULL;
std::new_handler previous_memory_handler = NULL;
bool memory_handler_installed = false;
std::atomic_flag reporting_memory_failure = ATOMIC_FLAG_INIT;
void memory_exhausted() __attribute__((noreturn));
void memory_exhausted() {
    // A callback or another thread may fail while reporting the first OOM.
    // Never recurse through the renderer or continue with partial objects.
    if (reporting_memory_failure.test_and_set(std::memory_order_acq_rel))
        sysProcessExit(1);
    std::free(emergency_memory);
    emergency_memory = NULL;
    static const char message[] =
        "Elasto Mania ran out of PS3 memory.\n"
        "The game will close safely. Select Original resolution or a lower zoom "
        "before loading this level again.";
    std::fputs(message, stderr);
    std::fputs("\n", stderr);
    ps3_message(message, memory_repaint);
    sysProcessExit(1);
}
void system_event(u64 status, u64, void*) {
    if (status == SYSUTIL_EXIT_GAME) quit_requested = true;
    system_ui.event(status);
}
bool dialog_done = false;
void dialog_closed(msgButton, void*) { dialog_done = true; }
bool have_data() {
    struct stat st;
    char cwd[1024] = {};
    if (!getcwd(cwd, sizeof(cwd))) return false;
    for (const char* name : {"elma.res", "Elma.res", "ELMA.RES"}) {
        std::string path = std::string(cwd) + "/" + name;
        if (stat(path.c_str(), &st) == 0) return true;
    }
    return false;
}
}

void ps3_prepare(int argc, char** argv) {
    // Preserve the XMB's configured display shape before SDL configures RSX.
    videoState state = {};
    if (videoGetState(VIDEO_PRIMARY, 0, &state) == 0) {
        television_aspect = state.displayMode.aspect;
        if (state.displayMode.refreshRates & VIDEO_REFRESH_50HZ) refresh_rate = 50;
    }
    // PSL1GHT does not guarantee the executable directory is the working
    // directory. A test/dev launch can pass an explicit data directory.
    if (argc > 1 && argv[1][0] == '/') chdir(argv[1]);
    if (!have_data() && argc && argv[0]) {
        std::string executable(argv[0]);
        size_t slash = executable.find_last_of('/');
        if (slash != std::string::npos) chdir(executable.substr(0, slash).c_str());
    }
    if (!have_data()) chdir("/dev_hdd0/game/ELMAC0001/USRDIR");
    setvbuf(stdout, NULL, _IONBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);
    char cwd[1024] = {};
    getcwd(cwd, sizeof(cwd));
    for (const char* name : {"lev", "rec", "snaps"}) {
        std::string path = std::string(cwd) + "/" + name;
        mkdir(path.c_str(), 0777);
    }
    elma_restore_replay_directory("rec");
    elma_restore_save_directory("lev",".lev");
    printf("ELMA PS3 %s: data=%s, free RAM=%u KiB\n", ELMA_PS3_VERSION,
           cwd, ps3_memory_available() / 1024);
}

void ps3_platform_init() {
    ioPadInit(7);
    // SDL owns slot 0. The second callback tracks pause/exit independently.
    sysUtilRegisterCallback(SYSUTIL_EVENT_SLOT1, system_event, NULL);
    initialized = true;
    if (!emergency_memory) emergency_memory = std::malloc(512u * 1024u);
}
void ps3_install_memory_handler(void (*repaint)()) {
    memory_repaint = repaint;
    if (!memory_handler_installed) {
        previous_memory_handler = std::set_new_handler(memory_exhausted);
        memory_handler_installed = true;
    }
}
void ps3_platform_finish() {
    if (memory_handler_installed) {
        std::set_new_handler(previous_memory_handler);
        memory_handler_installed = false;
    }
    memory_repaint = NULL;
    std::free(emergency_memory);
    emergency_memory = NULL;
    if (!initialized) return;
    sysUtilUnregisterCallback(SYSUTIL_EVENT_SLOT1);
    ioPadEnd();
    initialized = false;
}
static bool pad_ready[2]={};
void ps3_poll() {
    if (!initialized) return;
    static Uint32 last_poll = Uint32(-1);
    const Uint32 now = SDL_GetTicks();
    if (now == last_poll) return;
    last_poll = now;
    padInfo2 info = {};
    if (ioPadGetInfo2(&info) != 0) {
        // Unlike a zero-length data packet (no changes), failure to query
        // device status cannot establish that previously held input is live.
        memset(masks,0,sizeof(masks));
        memset(axes,0,sizeof(axes));
        pad_ready[0]=pad_ready[1]=false;
        return;
    }
    for (int p = 0; p < 2; ++p) {
        if (!(info.port_status[p] & 1)) {
            masks[p] = 0;
            pad_ready[p]=false;
            memset(axes[p], 0, sizeof(axes[p]));
            continue;
        }
        padData data = {};
        if (ioPadGetData(p, &data) != 0) {
            masks[p] = 0;
            pad_ready[p]=false;
            memset(axes[p], 0, sizeof(axes[p]));
            continue;
        }
        // A successful empty packet means unchanged input, unlike a failed
        // read, which must not leave a throttle or mouse click stuck down.
        if (data.len == 0) continue;
        pad_ready[p]=true;
        // button[2:3] already use the bit order of Ps3Button.
        masks[p] = (data.button[2] & 255u) | ((data.button[3] & 255u) << 8);
        axes[p][0] = int(data.ANA_L_H) - 128;
        axes[p][1] = int(data.ANA_L_V) - 128;
        axes[p][2] = int(data.ANA_R_H) - 128;
        axes[p][3] = int(data.ANA_R_V) - 128;
    }
}
bool ps3_pad_ready(int player) { return player>=0 && player<2 && pad_ready[player]; }
unsigned ps3_button_mask(int player) { return player >= 0 && player < 2 ? masks[player] : 0; }
int ps3_axis(int player, int axis) { return player >= 0 && player < 2 && axis >= 0 && axis < 4 ? axes[player][axis] : 0; }
bool ps3_exit_requested() { return quit_requested; }
bool ps3_system_menu() { return system_ui.active(); }
int ps3_refresh_rate() { return refresh_rate; }
void ps3_display_size(int physical_w, int physical_h, int* w, int* h) {
    *w = physical_w; *h = physical_h;
    // SD scanout has non-square pixels. A 720x576 PAL framebuffer still
    // fills a 4:3 television (or 16:9 when configured so in XMB).
    if (physical_h <= 576) {
        *w = physical_h * (television_aspect == VIDEO_ASPECT_4_3 ? 4 : 16) /
                          (television_aspect == VIDEO_ASPECT_4_3 ? 3 : 9);
    }
}
void ps3_message(const char* text, void (*repaint)()) {
    dialog_done = false;
    if (msgDialogOpen2(msgType(MSG_DIALOG_NORMAL | MSG_DIALOG_BTN_TYPE_OK),
                       text, dialog_closed, NULL, NULL) != 0) return;
    while (!dialog_done && !quit_requested) {
        sysUtilCheckCallback();
        if (repaint) repaint();
        SDL_Delay(10);
    }
    msgDialogAbort();
}
unsigned ps3_memory_available() {
    struct { u32 total; u32 avail; } memory = {};
    lv2syscall1(352, (u64)&memory);
    // Newlib keeps freed allocations in its arena, which is no longer part
    // of LV2's uncommitted memory but remains available to this process.
    const struct mallinfo heap = mallinfo();
    const u64 available = u64(memory.avail) + (heap.fordblks > 0 ? heap.fordblks : 0);
    return unsigned(available < memory.total ? available : memory.total);
}

void ps3_set_diagnostics(bool enabled) { diagnostics_enabled = enabled; }
void ps3_diagnostic_checkpoint(const char* phase, bool entering) {
    if (!diagnostics_enabled) return;
    const struct mallinfo heap = mallinfo();
    const Ps3RsxMemory rsx = ps3_rsx_memory();
    printf("ELMA PS3 checkpoint: %s %s, free RAM=%u KiB, heap used=%u bytes, "
           "RSX used=%u bytes, peak=%u bytes, allocations=%u, complete=%d, failures=%u\n",
           phase, entering ? "enter" : "leave", ps3_memory_available() / 1024,
           unsigned(heap.uordblks), rsx.used, rsx.peak, rsx.allocations, rsx.complete, rsx.failures);
    fflush(stdout);
}
