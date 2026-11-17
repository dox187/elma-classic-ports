// C ABI around the existing full-header original-source test fixture.
// LEPTET/BEALLIT/UTKOZES/UTKOZES2/SZAKASZ/VEKT2 are linked unchanged.
#define main pc_fixture_unused_main
#include "../../ps3/test/physics_trace.cpp"
#undef main

static engine Compare;
static double CompareTime;
static std::vector<double> ObservedTimes;

extern "C" {
void compare_pc_close(void) {
    if (!Top) return;
    delete Pszak; Pszak = NULL;
    for (int i=0; i<MAXGYURU; ++i) if (Top->ptomb[i]) {
        delete[] Top->ptomb[i]->ponttomb; free(Top->ptomb[i]);
    }
    for (int i=0; i<MAXKEREK; ++i) free(Top->kerektomb[i]);
    free(Top); free(Ecset); Top = NULL; Ecset = NULL;
    Ptop = NULL; Pecsetalso = NULL;
}

int compare_pc_load(const char* path) {
    compare_pc_close();
    if (!load(path)) return 0;
    Compare = engine(); Compare.name = "original"; Compare.pmot = Pmot1;
    Kajakell = Ptop->setallaktiv(Pmot1);
    eng_reset(&Compare); CompareTime = 0; ObservedTimes.clear();
    return 1;
}

// Three circles: x,y,vx,vy,angle,omega; rider x,y,vx,vy; head x,y.
void compare_pc_get(double* out, int* flags) {
    const motorst& m = *Compare.pmot;
    const kor* circles[] = {&m.kor1, &m.kor2, &m.kor4};
    for (int i=0; i<3; ++i) {
        const kor& k = *circles[i];
        *out++=k.r.x; *out++=k.r.y; *out++=k.v.x; *out++=k.v.y;
        *out++=k.alfa; *out++=k.omega;
    }
    *out++=m.vezetor.x; *out++=m.vezetor.y;
    *out++=m.vezetov.x; *out++=m.vezetov.y;
    *out++=m.fejr.x; *out++=m.fejr.y;
    flags[0]=Compare.dead; flags[1]=Compare.finished; flags[2]=m.hatra_f;
    flags[3]=m.gravirany; flags[4]=m.kajaszam;
}

// Used only at t=0: both engines start with the same quantized world state.
// This does not change masses, force constants, geometry or physics code.
void compare_pc_seed(const double* in, int turned) {
    motorst& m = *Compare.pmot;
    kor* circles[] = {&m.kor1, &m.kor2, &m.kor4};
    for (int i=0; i<3; ++i) {
        kor& k = *circles[i];
        k.r.x=*in++; k.r.y=*in++; k.v.x=*in++; k.v.y=*in++;
        k.alfa=*in++; k.omega=*in++;
    }
    m.vezetor.x=*in++; m.vezetor.y=*in++;
    m.vezetov.x=*in++; m.vezetov.y=*in++;
    m.fejr.x=*in++; m.fejr.y=*in++;
    m.hatra_f=turned;
}

void compare_pc_turn(void) { eng_turn(&Compare); }

// LEJATSZO.CPP: a variable frame target, capped steps, then the remainder.
// Runtime keys are left=4/right=8; the original inner loop uses the reverse.
double compare_pc_step(int runtime_input, double interval) {
    const int in=(runtime_input&3)|((runtime_input&4)<<1)|((runtime_input&8)>>1);
    const double target=CompareTime+interval;
    while (CompareTime <= target-0.000001 && !Compare.dead && !Compare.finished) {
        const double dt=std::min(0.0055,target-CompareTime);
        const size_t before=Compare.events.size();
        eng_step(&Compare,in,CompareTime,dt);
        CompareTime+=dt;
        for (size_t i=before; i<Compare.events.size(); ++i) ObservedTimes.push_back(CompareTime);
    }
    return CompareTime;
}

int compare_pc_event_count(void) { return (int)Compare.events.size(); }
void compare_pc_event(int index, int* kind_object, double* times) {
    const event& e=Compare.events.at(index);
    kind_object[0]=e.type; kind_object[1]=e.obj;
    times[0]=e.t; times[1]=ObservedTimes.at(index);
}
double compare_pc_pi(void) { return K_pi; }
}
