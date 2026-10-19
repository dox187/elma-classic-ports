#pragma once

// Bindings live in the existing state.dat control fields. The low 16 bits
// are physical buttons; the tag selects the player's controller.
enum PsxControlAction {
	PSX_THROTTLE, PSX_BRAKE, PSX_ROTATE_LEFT, PSX_ROTATE_RIGHT,
	PSX_TURN, PSX_NAVIGATOR, PSX_TIME, PSX_SHOW_HIDE, PSX_CONTROL_COUNT
};

int psx_control_binding(int player, int action);
const char* psx_control_name(int binding);
int psx_control_button_count();
const char* psx_control_button_name(int index);
int psx_control_key(int player, int button_index);
bool psx_control_assign(int player, int action, int binding);
bool psx_controls_reset();
void psx_controls_normalize();
