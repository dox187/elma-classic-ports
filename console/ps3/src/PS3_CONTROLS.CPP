#include "all.h"
#include "SDL_SETTINGS.H"
#include "PS3_CONTROLS.H"
#include "PS3_PLATFORM.H"
#include "PS3_BUTTON_CAPTURE.H"
#include <chrono>

static const int defaults[PS3_CONTROL_COUNT] = { PS3_CROSS, PS3_SQUARE,
    PS3_L1, PS3_R1, PS3_CIRCLE, PS3_TRIANGLE, PS3_L3, PS3_R3,
    PS3_DOWN, PS3_UP, PS3_RIGHT, PS3_LEFT, PS3_R2, PS3_L2 };
static int bindings[2][PS3_CONTROL_COUNT];
static bool loaded = false;
static const char* names[PS3_BUTTON_COUNT] = { "Select", "L3", "R3", "Start",
    "D-pad Up", "D-pad Right", "D-pad Down", "D-pad Left", "L2", "R2",
    "L1", "R1", "Triangle", "Circle", "Cross", "Square" };
static const char* actions[PS3_CONTROL_COUNT] = { "Throttle", "Brake",
    "Rotate left", "Rotate right", "Change direction", "Navigator", "Time", "Show / hide", "Alovolt",
    "Screenshot", "Increase screen", "Decrease screen", "Zoom in", "Zoom out" };
static int overlay_button = -1;
static bool capturing = false;
bool ps3_controls_capturing() { return capturing; }
bool ps3_action_required(int a) { return a>=PS3_THROTTLE && a<=PS3_TURN; }
static void repair_bindings(int p) {
    bool used[PS3_BUTTON_COUNT]={};
    // Reserve every valid mandatory mapping before restoring missing ones.
    for(int a=0;a<=PS3_TURN;++a) {
        int b=bindings[p][a];
        if(b<0 || b>=PS3_BUTTON_COUNT || b==PS3_SELECT || b==PS3_START || used[b])
            bindings[p][a]=-1;
        else used[b]=true;
    }
    for(int a=0;a<=PS3_TURN;++a) if(bindings[p][a]<0) {
        int b=defaults[a];
        if(used[b]) {
            for(b=0;b<PS3_BUTTON_COUNT;++b)
                if(b!=PS3_SELECT && b!=PS3_START && !used[b])break;
        }
        bindings[p][a]=b;used[b]=true;
    }
    for(int a=PS3_TURN+1;a<PS3_CONTROL_COUNT;++a) {
        int b=bindings[p][a];
        if(b<0 || b>=PS3_BUTTON_COUNT || b==PS3_SELECT || b==PS3_START || used[b])
            bindings[p][a]=-1;
        else used[b]=true;
    }
}

void ps3_controls_reset() {
    for (int p=0;p<2;++p) for(int a=0;a<PS3_CONTROL_COUNT;++a) bindings[p][a]=defaults[a];
    loaded=true;
}
void ps3_controls_load() {
    ps3_controls_reset();
    for(int p=0;p<2;++p)for(int a=0;a<=PS3_TURN;++a)bindings[p][a]=-1;
    for(int p=0;p<2;++p) for(int a=0;a<PS3_CONTROL_COUNT;++a) {
        char key[40]; sprintf(key,"ps3_pad%d_action%d",p+1,a);
        const char* value=config_get(key,NULL);
        if(value) { char* end; long b=strtol(value,&end,10);
            if(*value && !*end && b>=-1 && b<PS3_BUTTON_COUNT && b!=PS3_SELECT && b!=PS3_START) bindings[p][a]=(int)b; }
    }
    for(int p=0;p<2;++p)repair_bindings(p);
}
void ps3_controls_save() {
    for(int p=0;p<2;++p) for(int a=0;a<PS3_CONTROL_COUNT;++a) {
        char key[40], value[12]; sprintf(key,"ps3_pad%d_action%d",p+1,a);
        sprintf(value,"%d",bindings[p][a]); config_set(key,value);
    }
    config_save();
}
int ps3_binding(int p,int a) {
    if(!loaded) ps3_controls_load();
    return p>=0 && p<2 && a>=0 && a<PS3_CONTROL_COUNT ? bindings[p][a] : -1;
}
bool ps3_assign(int p,int a,int b) {
    if(!loaded) ps3_controls_load();
    if(p<0 || p>1 || a<0 || a>=PS3_CONTROL_COUNT || b<-1 || b>=PS3_BUTTON_COUNT
        || b==PS3_SELECT || b==PS3_START || (b<0 && ps3_action_required(a)))return false;
    const int previous=bindings[p][a];
    int owner=-1;
    if(b>=0)for(int other=0;other<PS3_CONTROL_COUNT;++other)
        if(other!=a && bindings[p][other]==b) {owner=other;break;}
    // Swapping is deterministic and keeps every mandatory action usable.
    // An unassigned optional action cannot donate a button, so reject that
    // one conflict rather than silently clearing a mandatory action.
    if(owner>=0 && ps3_action_required(owner) && previous<0)return false;
    if(owner>=0)bindings[p][owner]=previous;
    bindings[p][a]=b;
    return true;
}
const char* ps3_button_name(int b) { return b>=0 && b<PS3_BUTTON_COUNT ? names[b] : "Unassigned"; }
// Input still reaches the original engine through its saved key fields. A
// keyboard reassignment can clear one of those fields; reserve an unused high
// scancode on demand so a separately configured pad action remains usable.
static void normalize_missing_keys() {
    int* fields[]={ &State->opciok1.billgaz,&State->opciok1.billfek,
        &State->opciok1.billugras1,&State->opciok1.billugras2,&State->opciok1.billfordul,
        &State->opciok1.billview,&State->opciok1.billtime,&State->opciok1.billshowkep,
        &State->opciok2.billgaz,&State->opciok2.billfek,
        &State->opciok2.billugras1,&State->opciok2.billugras2,&State->opciok2.billfordul,
        &State->opciok2.billview,&State->opciok2.billtime,&State->opciok2.billshowkep,
        &State->billplussz,&State->billminusz,&State->billsnap };
    bool missing=false;
    for(unsigned i=0;i<sizeof(fields)/sizeof(fields[0]);++i)
        if(*fields[i]==0) {missing=true;break;}
    if(!missing)return;
    bool used[256]={};
    for(unsigned i=0;i<sizeof(fields)/sizeof(fields[0]);++i)
        if(*fields[i]>0 && *fields[i]<256) used[*fields[i]]=true;
    const int zin=config_zoom_key(true),zout=config_zoom_key(false);
    if(zin>0 && zin<256)used[zin]=true;
    if(zout>0 && zout<256)used[zout]=true;
    // 0xED..0xFF are outside the physical SDL keyboard map. There are enough
    // codes for all nineteen original action fields, without reusing a key.
    int next=255;
    for(unsigned i=0;i<sizeof(fields)/sizeof(fields[0]);++i) if(*fields[i]==0) {
        while(next>0 && (used[next] || next==MK_ESC || next==MK_ENTER)) --next;
        if(next>0) {*fields[i]=next;used[next]=true;--next;}
    }
}
int ps3_action_key(int p,int a) {
    if(!State || p<0 || p>1) return 0;
    normalize_missing_keys();
    jatekosopciok& o=p ? State->opciok2 : State->opciok1;
    switch(a) { case PS3_THROTTLE:return o.billgaz; case PS3_BRAKE:return o.billfek;
    case PS3_ROTATE_LEFT:return o.billugras2; case PS3_ROTATE_RIGHT:return o.billugras1;
    case PS3_TURN:return o.billfordul; case PS3_NAVIGATOR:return o.billview;
    case PS3_TIME:return o.billtime; case PS3_SHOW_HIDE:return o.billshowkep;
    case PS3_ALOVOLT:return o.billugras2;
    case PS3_SCREENSHOT:return State->billsnap;
    case PS3_SCREEN_PLUS:return State->billplussz;
    case PS3_SCREEN_MINUS:return State->billminusz;
    // Pad zoom must not inject a keyboard key (which may mean throttle,
    // another utility, or none). Its direct path is ps3_zoom_down below.
    case PS3_ZOOM_PLUS:case PS3_ZOOM_MINUS:return 0; }
    return 0;
}
bool ps3_zoom_down(bool zoom_in,bool keyboard_down) {
    if(keyboard_down)return true;
    if(ps3_system_menu())return false;
    const int action=zoom_in ? PS3_ZOOM_PLUS : PS3_ZOOM_MINUS;
    for(int player=0;player<2;++player) {
        const int button=ps3_binding(player,action);
        if(button>=0 && (ps3_button_mask(player)&(1u<<button)))return true;
    }
    return false;
}
// Outlined symbols remain legible with every menu palette, at native resolution.
void ps3_draw_line(pic8* p,int x,int y,int ex,int ey,unsigned char ink) {
    if(!p)return;
    int dx=abs(ex-x),sx=x<ex?1:-1,dy=-abs(ey-y),sy=y<ey?1:-1,error=dx+dy;
    while(1) {
        // ppixel performs the actual image-bound clipping.
        p->ppixel(x,y,ink);
        if(x==ex && y==ey)break;
        const int twice=2*error;
        if(twice>=dy) {error+=dy;x+=sx;}
        if(twice<=dx) {error+=dx;y+=sy;}
    }
}
static void ps3_glyph_line(pic8* p,int x1,int y1,int x2,int y2,unsigned char ink) {
    ps3_draw_line(p,x1,y1,x2,y2,ink);
    ps3_draw_line(p,x1+1,y1,x2+1,y2,ink);
    ps3_draw_line(p,x1,y1+1,x2,y2+1,ink);
}
static unsigned char ps3_palette_color(int red,int green,int blue) {
    int best=0,error=0x7fffffff;
    for(int c=0;c<256;++c) {
        int r=Menupaltomb[c*3]-red,g=Menupaltomb[c*3+1]-green,b=Menupaltomb[c*3+2]-blue;
        int distance=r*r+g*g+b*b;
        if(distance<error) {error=distance;best=c;}
    }
    return (unsigned char)best;
}
static unsigned char ps3_face_color(int button,unsigned char fallback) {
    const int wanted[4][3]={{20,38,63},{63,8,8},{63,20,48},{8,63,24}};
    int index=button==PS3_CROSS ? 0 : button==PS3_CIRCLE ? 1 : button==PS3_SQUARE ? 2 : 3;
    int best=-1,error=0x7fffffff;
    for(int c=0;c<256;++c) {
        int r=Menupaltomb[c*3],g=Menupaltomb[c*3+1],b=Menupaltomb[c*3+2];
        bool hue=index==0 ? b>r && b>=g : index==1 ? r>g*3/2 && r>b*3/2 :
            index==2 ? r>g*6/5 && b>g*6/5 : g>r*6/5 && g>b*6/5;
        if(!hue || r*3+g*6+b<190)continue;
        int dr=r-wanted[index][0],dg=g-wanted[index][1],db=b-wanted[index][2];
        int distance=dr*dr+dg*dg+db*db;
        if(distance<error) {error=distance;best=c;}
    }
    // Some original resource palettes have no pink at all. Keep that symbol
    // bright instead of changing the shared palette or choosing a wrong hue.
    return best<0 ? fallback : (unsigned char)best;
}
void ps3_controls_overlay(pic8* p) {
    if(overlay_button<0 || !p) return;
    int x=320+Menueltolasx, y=385+Menueltolasy, r=22;
    unsigned char ink=0;
    int brightest=-1;
    for(int c=0;c<256;++c) {
        int light=Menupaltomb[c*3]+Menupaltomb[c*3+1]+Menupaltomb[c*3+2];
        if(light>brightest) {brightest=light;ink=(unsigned char)c;}
    }
    const bool face=overlay_button>=PS3_TRIANGLE && overlay_button<=PS3_SQUARE;
    if(face) {
        unsigned char rim=ps3_palette_color(12,12,12),dark=ps3_palette_color(1,1,1);
        // A small circular cap isolates the symbol from animated menu balls.
        for(int yy=-36;yy<=36;++yy) for(int xx=-36;xx<=36;++xx) {
            int distance=xx*xx+yy*yy;
            if(distance<=36*36)p->ppixel(x+xx,y+yy,distance>=34*34 ? rim : dark);
        }
        ink=ps3_face_color(overlay_button,ink);
    }
    if(overlay_button==PS3_CROSS) {
        ps3_glyph_line(p,x-r,y-r,x+r,y+r,ink); ps3_glyph_line(p,x-r,y+r,x+r,y-r,ink);
    } else if(overlay_button==PS3_TRIANGLE) {
        ps3_glyph_line(p,x,y-r,x-r,y+r,ink); ps3_glyph_line(p,x-r,y+r,x+r,y+r,ink); ps3_glyph_line(p,x+r,y+r,x,y-r,ink);
    } else if(overlay_button==PS3_SQUARE) {
        ps3_glyph_line(p,x-r,y-r,x+r,y-r,ink);ps3_glyph_line(p,x+r,y-r,x+r,y+r,ink);
        ps3_glyph_line(p,x+r,y+r,x-r,y+r,ink);ps3_glyph_line(p,x-r,y+r,x-r,y-r,ink);
    } else if(overlay_button==PS3_CIRCLE) {
        int px=x+r,py=y;
        for(int i=1;i<=32;++i) { double t=i*6.283185307179586/32;
            int nx=x+(int)(r*cos(t)),ny=y+(int)(r*sin(t));ps3_glyph_line(p,px,py,nx,ny,ink);px=nx;py=ny; }
    } else if(overlay_button>=PS3_UP && overlay_button<=PS3_LEFT) {
        int dx=overlay_button==PS3_RIGHT ? 1 : overlay_button==PS3_LEFT ? -1 : 0;
        int dy=overlay_button==PS3_DOWN ? 1 : overlay_button==PS3_UP ? -1 : 0;
        int tx=x+dx*r,ty=y+dy*r;
        // A directional arrow matches the physical D-pad, rather than a
        // small text label squeezed inside a shoulder-button outline.
        ps3_glyph_line(p,x-dx*r,y-dy*r,tx,ty,ink);
        ps3_glyph_line(p,tx,ty,tx-dx*14+dy*14,ty-dy*14-dx*14,ink);
        ps3_glyph_line(p,tx,ty,tx-dx*14-dy*14,ty-dy*14+dx*14,ink);
    } else {
        ps3_glyph_line(p,x-32,y-20,x+32,y-20,ink);ps3_glyph_line(p,x+32,y-20,x+32,y+20,ink);
        ps3_glyph_line(p,x+32,y+20,x-32,y+20,ink);ps3_glyph_line(p,x-32,y+20,x-32,y-20,ink);
        Pmenuabc->write(p,x-Pmenuabc->len((char*)names[overlay_button])/2,y-10,(char*)names[overlay_button]);
    }
}
static void choose_button(int p,int a) {
    // A separate input context suppresses translated menu keys (including
    // Circle/Escape) while raw pad buttons are captured, and gates return.
    capturing=true;
    const std::chrono::steady_clock::time_point start=std::chrono::steady_clock::now();
    mk_emptychar();
    Ps3ButtonCapture capture;
    bool rejected=false,shown_rejected=false;
    int shown_seconds=-1;
    szoveglista list;
    overlay_button=ps3_binding(p,a);
    while(!ps3_exit_requested()) {
        const unsigned elapsed=(unsigned)std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now()-start).count();
        const int seconds=elapsed>=5000 ? 0 : (5000-elapsed+999)/1000;
        if(seconds!=shown_seconds || rejected!=shown_rejected) {
            list.clear();char title[96],current[96],countdown[64];
            sprintf(title,"Player %c: %s",'A'+p,actions[a]);
            sprintf(current,"Current: %s",ps3_button_name(ps3_binding(p,a)));
            sprintf(countdown,"Press controller %d button: %d sec",p+1,seconds);
            list.addszoveg_kozep(title,320,35);
            list.addszoveg_kozep(current,320,80);
            list.addszoveg_kozep(countdown,320,125);
            list.addszoveg_kozep((char*)"Release held buttons first",320,170);
            list.addszoveg_kozep((char*)"Circle can bind; Start/Select reserved",320,215);
            list.addszoveg_kozep((char*)(ps3_action_required(a) ? "Timeout: keep required binding" :
                "Timeout: clear optional binding"),320,260);
            list.addszoveg_kozep((char*)(rejected ? "Required button in use: choose another" :
                "Occupied buttons swap bindings"),320,300);
            shown_seconds=seconds;shown_rejected=rejected;
        }
        list.kirajzol();
        // Poll platform events, but never interpret translated menu chars.
        mk_emptychar();
        const unsigned now=(unsigned)std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now()-start).count();
        const int button=capture.update(now,ps3_button_mask(p),ps3_button_mask(1-p),ps3_system_menu(),ps3_pad_ready(p));
        if(button==Ps3ButtonCapture::TimedOut) {
            ps3_assign(p,a,-1); // Required bindings refuse to clear.
            ps3_controls_save();break;
        }
        if(button>=0) {
            if(ps3_assign(p,a,button)) {ps3_controls_save();break;}
            rejected=true;
        }
    }
    overlay_button=-1;
    capturing=false;
    // First poll after the context switch blocks the still-held captured
    // button before the action list can interpret it as accept/back.
    mk_emptychar();
}
void ps3_controller_customize() {
    int current=0;
    while(1) {
        valaszt2 v; v.kur=current;v.egykepen=10;v.x0=75;v.y0=95;v.dy=36;v.escelheto=1;
        strcpy(v.cim,"PS3 Controller Controls");
        strcpy(Rubrikak[0],"Reset both controllers");
        strcpy(Rubrikak[1],"Player A - controller 1");strcpy(Rubrikak[2],"Player B - controller 2");
        v.bead(3);current=v.valassz();if(current<0)return;
        if(current==0) {ps3_controls_reset();ps3_controls_save();continue;}
        int p=current-1, row=0;
        while(1) {
            valaszt2 q;q.kur=row;q.egykepen=8;q.x0=65;q.x0_tab=380;q.y0=90;q.dy=38;q.escelheto=1;
            sprintf(q.cim,"Player %c - choose action",'A'+p);
            for(int a=0;a<PS3_CONTROL_COUNT;++a) {strcpy(Rubrikak[a],actions[a]);strcpy(Rubrikak_tab[a],ps3_button_name(ps3_binding(p,a)));}
            q.bead(PS3_CONTROL_COUNT,1);row=q.valassz();if(row<0)break;choose_button(p,row);
        }
    }
}
void ps3_controller_help() {
    static const char* pages[3][9]={
        {"Cross: gas; Square: brake","Circle: turn; L1/R1: rotate",
         "D-pad Down: alovolt","Triangle: navigator","L3: time; R3: view",
         "D-pad Up: screenshot","Left/Right: screen size","L2/R2: zoom out/in",
         "Start: pause; Select: exit"},
        {"D-pad / left stick: move","Cross / Start: accept","Circle / Select: back",
         "Names: Up/Down picks letter","Right: add; Left: delete",
         "Cross / Start: finish name","Replay files: main menu",
         "Configure each pad separately","USB keyboard / mouse supported"},
        {"Right stick: cursor (R1: slow)","Cross/Square: left/right click",
         "L1: Ctrl; R1: Shift","Triangle: join; R3: direction",
         "Circle: cancel; L2: zoom out","R2: screenshot; Start: test",
         "Select: exit editor","Dialogs: D-pad; Start: accept",
         "Names: D-pad; Start: accept"}
    };
    int page=0;
    while(1) {
        szoveglista s;char title[40];sprintf(title,"PS3 Controller Guide %d/3",page+1);
        s.addszoveg_kozep(title,320,25);
        for(int row=0;row<9;++row)s.addszoveg((char*)pages[page][row],35,80+row*35);
        s.addszoveg_kozep("Left/Right: page; Circle: back",320,425);
        mk_emptychar();int c=0;
        while(!c) {s.kirajzol(1);if(mk_kbhit())c=mk_getextchar();}
        if(c==MK_ENTER||c==MK_ESC)return;
        if(c==MK_LEFT)page=(page+2)%3;
        if(c==MK_RIGHT)page=(page+1)%3;
    }
}
