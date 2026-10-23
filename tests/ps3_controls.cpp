// Standalone host test; compile with PS3_CONTROLS.CPP and section GC.
#include "all.h"
#include "PS3_CONTROLS.H"
#include "PS3_TEXT.H"
#include "PS3_UI_LATCH.H"
#include "PS3_SYSTEM_UI.H"
#include "PS3_BUTTON_CAPTURE.H"
#include "PS3_INPUT_CONTEXT.H"
#include <map>
#include <string>
#include <cstdio>
#define CHECK(c) do { if(!(c)) { fprintf(stderr,"line %d: %s\n",__LINE__,#c);return 1; } } while(0)
void hiba(char* text,char*,char*) {fprintf(stderr,"%s\n",text);abort();}
void uzenet(char*,char*,char*) {abort();}
void putpixel8_l(int,int,unsigned char) {abort();}
unsigned ps3_memory_available() {return 128u*1024*1024;}
state_s* State=0;
state_s::state_s(char*) {memset(this,0,sizeof(*this));}
state_s::~state_s() {}
static std::map<std::string,std::string> cfg;
const char* config_get(const char* k,const char* fallback) { auto i=cfg.find(k);return i==cfg.end()?fallback:i->second.c_str(); }
void config_set(const char* k,const char* v) {cfg[k]=v;}
void config_save() {}
static int zoom_in_key=0x0d,zoom_out_key=0x0c;
int config_zoom_key(bool in) {return in?zoom_in_key:zoom_out_key;}
static unsigned pad_masks[2]={};
static bool system_menu=false;
unsigned ps3_button_mask(int p) {return pad_masks[p];}
bool ps3_system_menu() {return system_menu;}
int main() {
 // Exercise the actual engine picture and pixel implementation, not a fake
 // line renderer: pic8::line deliberately supports only horizontal/vertical.
 pic8 canvas(16,16);canvas.fillbox(0);
 ps3_draw_line(&canvas,0,0,15,15,7);
 for(int i=0;i<16;++i)CHECK(canvas.gpixel(i,i)==7);
 ps3_draw_line(&canvas,15,0,0,15,9);
 for(int i=0;i<16;++i)CHECK(canvas.gpixel(15-i,i)==9);
 ps3_draw_line(&canvas,-4,8,20,8,11);
 for(int i=0;i<16;++i)CHECK(canvas.gpixel(i,8)==11);
 ps3_draw_line(&canvas,4,4,4,4,13);CHECK(canvas.gpixel(4,4)==13);
 canvas.line(0,15,15,15,15);
 for(int i=0;i<16;++i)CHECK(canvas.gpixel(i,15)==15);

 char text[9]="";
 CHECK(ps3_edit_text(text,8,1,false));CHECK(!strcmp(text,"A"));
 ps3_edit_text(text,8,-1,false);CHECK(!strcmp(text,"9"));
 ps3_edit_text(text,8,2,false);CHECK(!strcmp(text,"9A"));
 ps3_edit_text(text,8,-2,false);CHECK(!strcmp(text,"9"));
 strcpy(text,"ABCDEFGH");ps3_edit_text(text,8,2,false);CHECK(!strcmp(text,"ABCDEFGH"));
 strcpy(text,"z");ps3_edit_text(text,8,1,false);CHECK(!strcmp(text,"0"));
 strcpy(text,"9");ps3_edit_text(text,8,1,true);CHECK(!strcmp(text," "));
 ps3_edit_text(text,8,1,true);CHECK(!strcmp(text,"."));

 ps3_controls_load();CHECK(ps3_binding(0,PS3_THROTTLE)==PS3_CROSS);
 ps3_assign(1,PS3_BRAKE,PS3_L2);ps3_controls_save();ps3_controls_reset();ps3_controls_load();
 CHECK(ps3_binding(1,PS3_BRAKE)==PS3_L2);CHECK(ps3_binding(0,PS3_BRAKE)==PS3_SQUARE);
 config_set("ps3_pad1_action0","99");config_set("ps3_pad1_action1","4junk");
 ps3_controls_load();CHECK(ps3_binding(0,0)==PS3_CROSS);CHECK(ps3_binding(0,1)==PS3_SQUARE);
 ps3_assign(-1,0,0);ps3_assign(0,9,0);ps3_assign(0,0,99);CHECK(ps3_binding(0,0)==PS3_CROSS);
 ps3_assign(0,PS3_BRAKE,PS3_CROSS);
 CHECK(ps3_binding(0,PS3_THROTTLE)==PS3_SQUARE);CHECK(ps3_binding(0,PS3_BRAKE)==PS3_CROSS);
 ps3_assign(0,PS3_BRAKE,PS3_START);CHECK(ps3_binding(0,PS3_BRAKE)==PS3_CROSS);
 ps3_assign(0,PS3_BRAKE,PS3_SELECT);CHECK(ps3_binding(0,PS3_BRAKE)==PS3_CROSS);
 ps3_assign(1,PS3_TIME,-1);ps3_controls_save();ps3_controls_reset();ps3_controls_load();
 CHECK(ps3_binding(0,PS3_THROTTLE)==PS3_SQUARE);CHECK(ps3_binding(1,PS3_TIME)==-1);

 // All fourteen usable buttons start occupied. Every possible assignment
 // must preserve five required actions and a unique binding per button.
 for(int action=0;action<PS3_CONTROL_COUNT;++action)for(int button=-1;button<PS3_BUTTON_COUNT;++button) {
     ps3_controls_reset();
     const bool assigned=ps3_assign(0,action,button);
     CHECK(assigned==(button!=PS3_SELECT && button!=PS3_START &&
         (button>=0 || !ps3_action_required(action))));
     bool occupied[PS3_BUTTON_COUNT]={};
     for(int a=0;a<PS3_CONTROL_COUNT;++a) {
         const int b=ps3_binding(0,a);
         if(ps3_action_required(a))CHECK(b>=0);
         if(b>=0) {CHECK(!occupied[b]);occupied[b]=true;}
         CHECK(ps3_binding(1,a)>=0); // Other player is unchanged.
     }
 }
 ps3_controls_reset();CHECK(ps3_assign(0,PS3_TIME,-1));
 CHECK(!ps3_assign(0,PS3_TIME,PS3_CROSS)); // No button to swap to throttle.
 CHECK(ps3_binding(0,PS3_THROTTLE)==PS3_CROSS && ps3_binding(0,PS3_TIME)==-1);
 CHECK(ps3_assign(0,PS3_TIME,PS3_TRIANGLE)); // Optional owner may be cleared.
 CHECK(ps3_binding(0,PS3_NAVIGATOR)==-1);
 CHECK(ps3_assign(0,PS3_TIME,PS3_CROSS)); // Now swap Triangle to throttle.
 CHECK(ps3_binding(0,PS3_THROTTLE)==PS3_TRIANGLE);
 CHECK(ps3_binding(0,PS3_TIME)==PS3_CROSS);
 CHECK(!ps3_assign(0,PS3_THROTTLE,-1));
 ps3_controls_save();ps3_controls_reset();ps3_controls_load();
 CHECK(ps3_binding(0,PS3_THROTTLE)==PS3_TRIANGLE);
 CHECK(ps3_binding(0,PS3_TIME)==PS3_CROSS); // Reload must not replay swaps.
 // Legacy load reserves valid required bindings before filling missing ones.
 cfg.clear();config_set("ps3_pad1_action1","14");ps3_controls_load();
 CHECK(ps3_binding(0,PS3_BRAKE)==PS3_CROSS);
 CHECK(ps3_binding(0,PS3_THROTTLE)!=PS3_CROSS); // Absent key is missing, too.
 config_set("ps3_pad1_action0","-1");config_set("ps3_pad1_action1","14");
 config_set("ps3_pad1_action8","-1");ps3_controls_load();
 CHECK(ps3_binding(0,PS3_BRAKE)==PS3_CROSS);
 CHECK(ps3_binding(0,PS3_THROTTLE)>=0 && ps3_binding(0,PS3_THROTTLE)!=PS3_CROSS);
 CHECK(ps3_binding(0,PS3_ALOVOLT)==-1); // Optional, never repaired by force.
 cfg.clear();config_set("ps3_pad1_action0","-1");ps3_controls_load();
 CHECK(ps3_binding(0,PS3_THROTTLE)==PS3_CROSS);
 config_set("ps3_pad1_action1","14");config_set("ps3_pad1_action0","14");
 ps3_controls_load();CHECK(ps3_binding(0,PS3_THROTTLE)==PS3_CROSS);
 CHECK(ps3_binding(0,PS3_BRAKE)==PS3_SQUARE);
 cfg.clear();ps3_controls_reset();
 // Capture starts only after opening buttons on BOTH pads have released.
 Ps3ButtonCapture capture;
 const unsigned cross=1u<<PS3_CROSS,circle=1u<<PS3_CIRCLE;
 CHECK(capture.update(0,cross,0)==Ps3ButtonCapture::Waiting);
 CHECK(capture.update(100,cross,0)==Ps3ButtonCapture::Waiting);
 CHECK(capture.update(200,0,cross)==Ps3ButtonCapture::Waiting);
 CHECK(capture.update(300,0,0)==Ps3ButtonCapture::Waiting);
 CHECK(capture.update(400,circle,0)==PS3_CIRCLE); // Circle is a binding, not Escape.
 CHECK(capture.update(500,circle,0)==Ps3ButtonCapture::Waiting);
 CHECK(capture.update(600,0,0)==Ps3ButtonCapture::Waiting);
 CHECK(capture.update(700,cross,0)==PS3_CROSS); // Fresh opening-button edge works.
 Ps3ButtonCapture second;
 CHECK(second.update(0,0,cross)==Ps3ButtonCapture::Waiting);
 CHECK(second.update(100,0,0)==Ps3ButtonCapture::Waiting);
 CHECK(second.update(200,0,circle)==Ps3ButtonCapture::Waiting); // Wrong pad.
 CHECK(second.update(300,1u<<PS3_START,0)==Ps3ButtonCapture::Waiting);
 CHECK(second.update(400,1u<<PS3_SELECT,0)==Ps3ButtonCapture::Waiting);
 CHECK(second.update(4999,0,0)==Ps3ButtonCapture::Waiting);
 CHECK(second.update(5000,circle,0)==Ps3ButtonCapture::TimedOut); // Deadline wins.
 Ps3ButtonCapture overlay;
 CHECK(overlay.update(0,0,0)==Ps3ButtonCapture::Waiting);
 CHECK(overlay.update(100,circle,0,true)==Ps3ButtonCapture::Waiting);
 CHECK(overlay.update(200,circle,0)==Ps3ButtonCapture::Waiting);
 CHECK(overlay.update(300,0,0)==Ps3ButtonCapture::Waiting);
 CHECK(overlay.update(400,circle,0)==PS3_CIRCLE);
 // Disconnect is not a release: reconnecting with a held button cannot bind.
 Ps3ButtonCapture reconnect;
 CHECK(reconnect.update(0,0,0)==Ps3ButtonCapture::Waiting);
 CHECK(reconnect.update(100,0,0,false,false)==Ps3ButtonCapture::Waiting);
 CHECK(reconnect.update(200,circle,0,false,true)==Ps3ButtonCapture::Waiting);
 CHECK(reconnect.update(300,circle,0)==Ps3ButtonCapture::Waiting);
 CHECK(reconnect.update(400,0,0)==Ps3ButtonCapture::Waiting);
 CHECK(reconnect.update(500,circle,0)==PS3_CIRCLE);
 CHECK(reconnect.update(5000,0,0,false,false)==Ps3ButtonCapture::TimedOut);
 // An elapsed timeout leaves a required action intact, clears optional ones.
 const int required_before=ps3_binding(0,PS3_THROTTLE);
 CHECK(!ps3_assign(0,PS3_THROTTLE,-1));CHECK(ps3_binding(0,PS3_THROTTLE)==required_before);
 CHECK(ps3_assign(0,PS3_ALOVOLT,-1));CHECK(ps3_binding(0,PS3_ALOVOLT)==-1);
 // Same context helper used by backend must swallow captured Circle on return.
 Ps3InputContext context;
 context.update(0,cross,0);context.update(2048,cross,0);
 CHECK(!context.fresh(0,cross));
 context.update(2048,0,0);context.update(2048,circle,0);
 context.update(0,circle,0);CHECK(!context.fresh(0,circle));
 context.update(0,0,0);context.update(0,circle,0);CHECK(context.fresh(0,circle)==circle);
 CHECK(ps3_action_key(0,0)==0);CHECK(ps3_binding(2,0)==-1);
 state_s state;State=&state;state.opciok1.billgaz=20;
 CHECK(ps3_action_key(0,PS3_THROTTLE)==20);
 const int brake=ps3_action_key(0,PS3_BRAKE);
 CHECK(brake>0 && brake<256 && brake!=20);
 CHECK(ps3_action_key(1,PS3_BRAKE)!=brake);
 CHECK(ps3_action_key(0,PS3_BRAKE)==brake);
 state.opciok1.billfek=0;CHECK(ps3_action_key(0,PS3_BRAKE)>0);
 CHECK(state.opciok1.billgaz==20);
 // Real pad routing must survive keyboard none and keyboard collisions.
 ps3_controls_reset();
 zoom_in_key=zoom_out_key=0;pad_masks[0]=1u<<PS3_R2;
 CHECK(ps3_zoom_down(true,false));CHECK(!ps3_zoom_down(false,false));
 CHECK(ps3_action_key(0,PS3_ZOOM_PLUS)==0); // Never synthesize throttle.
 zoom_in_key=0xc9;state.opciok1.billgaz=0xc9; // Keyboard throttle=PageUp.
 CHECK(ps3_zoom_down(true,false));CHECK(ps3_action_key(0,PS3_ZOOM_PLUS)==0);
 CHECK(ps3_action_key(0,PS3_THROTTLE)==0xc9); // Keyboard assignment preserved.
 ps3_assign(0,PS3_ZOOM_PLUS,PS3_TRIANGLE);
 CHECK(!ps3_zoom_down(true,false)); // Old physical R2 is no longer zoom.
 pad_masks[0]=1u<<PS3_TRIANGLE;CHECK(ps3_zoom_down(true,false));
 system_menu=true;CHECK(!ps3_zoom_down(true,false));system_menu=false;
 ps3_assign(0,PS3_ZOOM_PLUS,-1);CHECK(!ps3_zoom_down(true,false));
 CHECK(ps3_zoom_down(true,true)); // Valid keyboard zoom still works.
 pad_masks[0]=0;pad_masks[1]=1u<<PS3_L2;
 CHECK(ps3_zoom_down(false,false));CHECK(!ps3_zoom_down(true,false));
 pad_masks[1]=0;CHECK(!ps3_zoom_down(false,false)); // Release/no stuck input.
 zoom_in_key=0x0d;zoom_out_key=0x0c;
 // Actual RPCS3 home-menu order: menu closure must not release drawing.
 Ps3SystemUiState system_ui;CHECK(!system_ui.active());
 const unsigned home_events[]={0x0121,0x0131,0x0132,0x0122};
 const bool expected[]={true,true,true,false};
 for(int i=0;i<4;++i) {system_ui.event(home_events[i]);CHECK(system_ui.active()==expected[i]);}
 // Drawing-only system dialog; unrelated events do not release its pause.
 system_ui.event(0x0121);system_ui.event(0x0132);system_ui.event(0x0101);
 CHECK(system_ui.active());system_ui.event(0x0122);CHECK(!system_ui.active());
 // Independent menu lifetime survives the drawing-end event as well.
 system_ui.event(0x0131);system_ui.event(0x0121);system_ui.event(0x0122);
 CHECK(system_ui.active());system_ui.event(0x0132);CHECK(!system_ui.active());
 // Duplicate state notifications must not leave the game permanently paused.
 system_ui.event(0x0121);system_ui.event(0x0121);system_ui.event(0x0122);
 CHECK(!system_ui.active());
 // Zero-filled QA state must allocate nineteen distinct engine action keys.
 state_s qa;State=&qa;ps3_controls_reset();
 int keys[19],count=0;
 for(int player=0;player<2;++player)for(int action=0;action<8;++action)
     keys[count++]=ps3_action_key(player,action);
 for(int action=PS3_SCREENSHOT;action<=PS3_SCREEN_MINUS;++action)
     keys[count++]=ps3_action_key(0,action);
 CHECK(count==19);
 for(int i=0;i<count;++i) {CHECK(keys[i]>0 && keys[i]<256 && keys[i]!=0x0d && keys[i]!=0x0c);
     for(int j=0;j<i;++j)CHECK(keys[i]!=keys[j]);}
 for(int player=0;player<2;++player) {
     CHECK(ps3_action_key(player,PS3_ALOVOLT)==ps3_action_key(player,PS3_ROTATE_LEFT));
     CHECK(ps3_action_key(player,PS3_ALOVOLT)!=ps3_action_key(player,PS3_ROTATE_RIGHT));
 }
 // The real valtozok layout: hold all three display toggles through repeated
 // respawns. Only release+press may make a second edge; all physics resets stay.
 for(int preserve=0;preserve<2;++preserve) {
 valtozok rider={};int edges[3]={};
 for(int frame=0;frame<8;++frame) {
     const int down=frame!=5;
     int* latch[]={&rider.viewnyomva,&rider.timenyomva,&rider.showkepnyomva};
     for(int k=0;k<3;++k) {if(down && !*latch[k])++edges[k];*latch[k]=down;}
     if(frame==1 || frame==3 || frame==6) {
         rider.utolsougras=42;rider.hatranyomva=1;rider.showkep=1;
         const Ps3UiLatchSnapshot saved(rider);
         memset(&rider,0,sizeof(rider));if(preserve)saved.restore(rider);
         CHECK(rider.utolsougras==0 && rider.hatranyomva==0 && rider.showkep==0);
     }
 }
 for(int k=0;k<3;++k)CHECK(edges[k]==(preserve?2:5));
 }
 State=0;
}
