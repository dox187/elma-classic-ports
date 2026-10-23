#ifndef ELMA_PS3_PLATFORM_H
#define ELMA_PS3_PLATFORM_H

// Native console services; video, audio and USB keyboard/mouse use SDL2.
void ps3_prepare(int argc, char** argv);
void ps3_platform_init();
void ps3_platform_finish();
// Call after the renderer is ready; repaint must only clear/flip scanout.
void ps3_install_memory_handler(void (*repaint)());
void ps3_poll();
unsigned ps3_button_mask(int player);
// Connected, with an actual input sample since the last disconnect/read failure.
bool ps3_pad_ready(int player);
int ps3_axis(int player, int axis); // LX, LY, RX, RY, -128..127
bool ps3_exit_requested();
bool ps3_system_menu();
void ps3_display_size(int physical_w, int physical_h, int* w, int* h);
int ps3_refresh_rate();
void ps3_message(const char* message, void (*repaint)());
unsigned ps3_memory_available();
void ps3_set_diagnostics(bool enabled);
void ps3_diagnostic_checkpoint(const char* phase, bool entering);

// Opt-in lifecycle markers let long-running tests distinguish successful
// game/editor/replay transitions from merely sending controller inputs.
class Ps3DiagnosticScope {
    const char* phase_;
public:
    explicit Ps3DiagnosticScope(const char* phase) : phase_(phase) {
        ps3_diagnostic_checkpoint(phase_, true);
    }
    ~Ps3DiagnosticScope() { ps3_diagnostic_checkpoint(phase_, false); }
    Ps3DiagnosticScope(const Ps3DiagnosticScope&) = delete;
    Ps3DiagnosticScope& operator=(const Ps3DiagnosticScope&) = delete;
};

#endif
