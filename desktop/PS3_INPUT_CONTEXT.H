#ifndef ELMA_PS3_INPUT_CONTEXT_H
#define ELMA_PS3_INPUT_CONTEXT_H
// Buttons held across a screen/modal transition must be released before the
// next screen interprets them as a new command. Gameplay movement can continue
// using raw state; reserved pause/exit and UI commands use filtered state.
class Ps3InputContext {
    int context;
    unsigned blocked[2];
public:
    Ps3InputContext():context(-1) {blocked[0]=blocked[1]=0;}
    void update(int next,unsigned first,unsigned second) {
        unsigned raw[2]={first,second};
        for(int player=0;player<2;++player) {
            if(context>=0 && next!=context)blocked[player]|=raw[player];
            blocked[player]&=raw[player];
        }
        context=next;
    }
    unsigned fresh(int player,unsigned raw) const {
        return player>=0 && player<2 ? raw&~blocked[player] : 0;
    }
};
#endif
