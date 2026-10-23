#ifndef ELMA_PS3_SYSTEM_UI_H
#define ELMA_PS3_SYSTEM_UI_H
// PSL1GHT sysutil event values. Menu visibility and system drawing overlap:
// RPCS3 home-menu callbacks use DRAW_BEGIN, MENU_OPEN, MENU_CLOSE, DRAW_END.
// Duplicate notifications are state updates, not nested ownership counts.
class Ps3SystemUiState {
    bool menu_ = false;
    bool drawing_ = false;
public:
    enum Event { DrawBegin=0x0121, DrawEnd=0x0122,
                 MenuOpen=0x0131, MenuClose=0x0132 };
    void event(unsigned long long status) {
        switch(status) {
        case DrawBegin:drawing_=true;break;
        case DrawEnd:drawing_=false;break;
        case MenuOpen:menu_=true;break;
        case MenuClose:menu_=false;break;
        }
    }
    bool active() const { return menu_ || drawing_; }
};
#endif
