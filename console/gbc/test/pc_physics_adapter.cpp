// C ABI around the existing full-header original-source test fixture.
// Contact builds use an observational copy of BEALLIT; all math is unchanged.
#define main pc_fixture_unused_main
#include "../../ps3/test/physics_trace.cpp"
#undef main

static engine Compare;
static double CompareTime;
static std::vector<double> ObservedTimes;
static double ContactCompletionTime;
static int ContactModes[2] = {-1, -1};
static int ContactObservations[2];
struct contact_event { int wheel, before, count; double time; };
static std::vector<contact_event> ContactEvents;

template<class T> static void state_bytes(std::vector<unsigned char>& out, const T& value) {
    const unsigned char* p = reinterpret_cast<const unsigned char*>(&value);
    out.insert(out.end(), p, p + sizeof(value));
}

extern "C" {
int compare_pc_contact_version(void) {
#ifdef COMPARE_CONTACTS
    return 1;
#else
    return 0;
#endif
}
// Called only after both support filters, for wheels (never the body).
void compare_pc_observe_contact(const void* circle, int count) {
    int wheel = circle == &Compare.pmot->kor2 ? 0 : circle == &Compare.pmot->kor4 ? 1 : -1;
    if (wheel < 0 || count < 0 || count > 2) abort();
    ++ContactObservations[wheel];
    if (ContactModes[wheel] != count) {
        contact_event e = {wheel, ContactModes[wheel], count, ContactCompletionTime};
        ContactEvents.push_back(e);
        ContactModes[wheel] = count;
    }
}
void compare_pc_contact_state(int* modes, int* observations) {
    for (int i=0; i<2; ++i) { modes[i]=ContactModes[i]; observations[i]=ContactObservations[i]; }
}
int compare_pc_contact_count(void) { return (int)ContactEvents.size(); }
void compare_pc_contact_event(int index, int* values, double* time) {
    const contact_event& e = ContactEvents.at(index);
    values[0]=e.wheel; values[1]=e.before; values[2]=e.count; *time=e.time;
}

// All numeric motor/engine state and object activation, excluding C++ padding.
int compare_pc_state_bytes(unsigned char* output) {
    std::vector<unsigned char> out;
    const motorst& m=*Compare.pmot;
    state_bytes(out,CompareTime);
    const kor* circles[]={&m.kor1,&m.kor2,&m.kor4};
    for (int i=0;i<3;++i) {
        const kor& k=*circles[i];
        const double values[]={k.alfa,k.omega,k.sugar,k.m,k.theta,k.r.x,k.r.y,k.v.x,k.v.y};
        for (int j=0;j<9;++j) state_bytes(out,values[j]);
    }
    const double values[]={m.fejr.x,m.fejr.y,m.vezetor.x,m.vezetor.y,m.vezetov.x,m.vezetov.y,
        m.dfek2,m.dfek4,m.ugras1kezd,m.ugras2kezd,m.kezdoomega1,m.kezdoomega2,Compare.utolsougras};
    for (int i=0;i<13;++i) state_bytes(out,values[i]);
    const int flags[]={m.hatra_f,m.hatra_h,m.gravirany,m.kajaszam,m.voltfek,m.ugrasban1,
        m.ugrasban2,Compare.dead,Compare.finished};
    for (int i=0;i<9;++i) state_bytes(out,flags[i]);
    state_bytes(out,Compare.megvanido);
    for (int i=0;i<Nobj;++i) state_bytes(out,Compare.aktiv[i]);
    if (output) memcpy(output,out.data(),out.size());
    return (int)out.size();
}
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
    ContactEvents.clear(); ContactCompletionTime=0;
    for (int i=0;i<2;++i) { ContactModes[i]=-1; ContactObservations[i]=0; }
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
        ContactCompletionTime=CompareTime+dt;
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
