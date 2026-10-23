#ifndef ELMA_PS3_BUTTON_CAPTURE_H
#define ELMA_PS3_BUTTON_CAPTURE_H
#include "PS3_CONTROLS.H"
// Elapsed wall milliseconds are supplied by the UI, independently of the
// paused game clock. Both pads must release the opening/previous input first.
class Ps3ButtonCapture {
    bool released_;
    unsigned previous_;
public:
    enum { Waiting=-1, TimedOut=-2 };
    Ps3ButtonCapture():released_(false),previous_(0) {}
    int update(unsigned elapsed,unsigned selected,unsigned other,bool system_ui=false,bool pad_ready=true) {
        if(elapsed>=5000)return TimedOut;
        if(system_ui || !pad_ready) {released_=false;previous_=selected;return Waiting;}
        if(!released_) {
            if(!(selected|other))released_=true;
            previous_=selected;
            return Waiting;
        }
        unsigned pressed=selected&~previous_;
        previous_=selected;
        pressed&=~((1u<<PS3_SELECT)|(1u<<PS3_START));
        // Simultaneous edges choose the lowest physical button index.
        for(int button=0;button<PS3_BUTTON_COUNT;++button)
            if(pressed&(1u<<button))return button;
        return Waiting;
    }
};
#endif
