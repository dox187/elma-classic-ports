#ifndef ELMA_PS3_CONTROLS_H
#define ELMA_PS3_CONTROLS_H
// SDL's PS3 joystick order. Bindings are separate from the keyboard/state.dat.
enum Ps3Button { PS3_SELECT, PS3_L3, PS3_R3, PS3_START,
    PS3_UP, PS3_RIGHT, PS3_DOWN, PS3_LEFT, PS3_L2, PS3_R2,
    PS3_L1, PS3_R1, PS3_TRIANGLE, PS3_CIRCLE, PS3_CROSS, PS3_SQUARE,
    PS3_BUTTON_COUNT };
enum Ps3Action { PS3_THROTTLE, PS3_BRAKE, PS3_ROTATE_LEFT, PS3_ROTATE_RIGHT,
    PS3_TURN, PS3_NAVIGATOR, PS3_TIME, PS3_SHOW_HIDE, PS3_ALOVOLT,
    PS3_SCREENSHOT, PS3_SCREEN_PLUS, PS3_SCREEN_MINUS, PS3_ZOOM_PLUS,
    PS3_ZOOM_MINUS, PS3_CONTROL_COUNT };
void ps3_controls_load();
void ps3_controls_save();
void ps3_controls_reset();
int ps3_binding(int player, int action);
// Zoom is routed directly, so its action key is zero.
int ps3_action_key(int player, int action);
// Preserve keyboard zoom while reading configured pad zoom independently.
bool ps3_zoom_down(bool zoom_in, bool keyboard_down);
const char* ps3_button_name(int button);
// Swap occupied buttons; reject any change that would clear a required action.
bool ps3_assign(int player, int action, int button);
bool ps3_action_required(int action);
bool ps3_controls_capturing();
// Backend-owned raw button state; bits use Ps3Button above.
unsigned ps3_button_mask(int player);
class pic8;
// General lines for PS3 UI; legacy pic8::line accepts only axis-aligned lines.
void ps3_draw_line(pic8* picture,int x1,int y1,int x2,int y2,unsigned char ink);
// Customization overlay, called after menu rendering and before presentation.
void ps3_controls_overlay(pic8* picture);
void ps3_controller_customize();
void ps3_controller_help();
#endif
