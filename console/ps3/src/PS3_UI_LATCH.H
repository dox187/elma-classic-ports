#ifndef ELMA_PS3_UI_LATCH_H
#define ELMA_PS3_UI_LATCH_H
// These are display-button edges, not riding/physics state. A Tag respawn
// must not turn a continuously held button into another press.
struct Ps3UiLatchSnapshot {
    int view, time, show;
    template<class T> explicit Ps3UiLatchSnapshot(const T& value)
        : view(value.viewnyomva), time(value.timenyomva), show(value.showkepnyomva) {}
    template<class T> void restore(T& value) const {
        value.viewnyomva=view; value.timenyomva=time; value.showkepnyomva=show;
    }
};
#endif
