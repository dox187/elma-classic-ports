#include "PS3_INPUT_CONTEXT.H"
#include <cstdio>
#define CHECK(c) do {if(!(c)){std::fprintf(stderr,"line %d: %s\n",__LINE__,#c);return 1;}}while(0)
int main() {
    const unsigned select=1u,start=1u<<3,cross=1u<<14,up=1u<<4;
    Ps3InputContext gate;
    gate.update(2,start,0);CHECK(gate.fresh(0,start)==start); // Editor: test level.
    gate.update(1,start,0);CHECK(!gate.fresh(0,start)); // No immediate pause.
    gate.update(1,0,0);gate.update(1,start,0);CHECK(gate.fresh(0,start)==start);
    gate.update(1,select,select);CHECK(gate.fresh(0,select)==select);
    gate.update(2,select,select);CHECK(!gate.fresh(0,select));CHECK(!gate.fresh(1,select));
    gate.update(2,0,0);gate.update(2,select,0);CHECK(gate.fresh(0,select)==select);
    // Closing a text field with Start must not start a play-test in its parent.
    gate.update(3,0,0);gate.update(3,start,0);CHECK(gate.fresh(0,start)==start);
    gate.update(2,start,0);CHECK(!gate.fresh(0,start));
    // Held navigation/click commands do not cascade into a nested dialog.
    gate.update(2,cross|up,0);gate.update(3,cross|up,0);CHECK(!gate.fresh(0,cross|up));
    gate.update(3,up,0);gate.update(3,cross,0);CHECK(gate.fresh(0,cross)==cross);
    CHECK(!gate.fresh(2,cross));
}
