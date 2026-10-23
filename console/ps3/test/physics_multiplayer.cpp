// Reuse the original-engine fixture's level loader, constants and canonical
// numeric trace. Multiplayer orchestration below follows LEJATSZO.CPP;
// the actual physics and flag-tag state machine are linked unchanged.
#define main single_player_fixture_main
#include "physics_trace.cpp"
#undef main
#include <chrono>
#include "PAUSE_CLOCK.H"

static int Respawns, Apples, TagTransfers;
// initmotor's assignments from ADATOK.CPP deliberately retain the integration
// history on a tag respawn, exactly as the original game does.
static void respawn_motor(motorst* m) {
    m->hatra_f=0;m->hatra_h=0;m->gravirany=1;m->voltfek=0;
    m->kor1.alfa=0;m->kor1.omega=0;m->kor1.sugar=.3;m->kor1.m=200;
    m->kor1.theta=200.0*.55*.55;m->kor1.r=vekt2(2.75,3.6);m->kor1.v=vekt2(0,0);
    m->kor2.alfa=0;m->kor2.omega=0;m->kor2.sugar=.4;m->kor2.m=10;
    m->kor2.theta=.32;m->kor2.r=vekt2(1.9,3.0);m->kor2.v=vekt2(0,0);
    m->kor4.alfa=0;m->kor4.omega=0;m->kor4.sugar=.4;m->kor4.m=10;
    m->kor4.theta=.32;m->kor4.r=vekt2(3.6,3.0);m->kor4.v=vekt2(0,0);
    m->vezetor=vekt2(2.75,4.04);m->vezetov=vekt2(0,0);
    m->kor1.r=m->kor1.r+Kezdetihelydiff;m->kor2.r=m->kor2.r+Kezdetihelydiff;
    m->kor4.r=m->kor4.r+Kezdetihelydiff;m->vezetor=m->vezetor+Kezdetihelydiff;
}
static void pair_step(engine& e,int input,double t,double dt) {
    if(e.dead)return;
    motorst* m=e.pmot;int right=0,left=0;
    if(t>e.utolsougras+Ugroturelem) {
        if(input&IN_VOLT_R){right=1;e.utolsougras=t;}
        if(input&IN_VOLT_L){left=1;e.utolsougras=t;}
    }
    Begyujtve=0;
    leptet(m,t,dt,!!(input&IN_GAS),!!(input&IN_BRAKE),right,left);
    if(!vizsgalat(m)) {
        event ev={Tag?'r':'d',-1,t};e.events.push_back(ev);
        if(!Tag){e.dead=1;return;}
        respawn_motor(m);e.utolsougras=-100;
        if((m==Pmot1 && Aafogo)||(m==Pmot2 && !Aafogo))Aafogo=!Aafogo;
        ++Respawns;
    }
    for(int j=0;j<Begyujtve;++j) {
        int index=Objszam[j];if(index<0)continue;
        kerek* k=Ptop->kerektomb[index];
        if(k->tipus==T_HALALOS){e.dead=1;event ev={'d',index,t};e.events.push_back(ev);}
        else if(k->tipus==T_KAJA) {
            k->aktiv=0;++m->kajaszam;++Apples;
            switch(k->kajatipus){case KT_UP:m->gravirany=0;break;case KT_DOWN:m->gravirany=1;break;case KT_LEFT:m->gravirany=2;break;case KT_RIGHT:m->gravirany=3;break;}
            event ev={'a',index,t};e.events.push_back(ev);
        } else if(k->tipus==T_CEL && Pmot1->kajaszam+Pmot2->kajaszam>=Kajakell) {
            e.megvanido=t*100/(182.0*.0024);e.finished=1;
            event ev={'f',index,t};e.events.push_back(ev);
        }
    }
}
static void sync_objects(engine& a,engine& b) {
    for(int i=0;i<Nobj;++i)a.aktiv[i]=b.aktiv[i]=Ptop->kerektomb[i]->aktiv;
}
static void pair_trace(engine& a,engine& b,int step,double t) {
    sync_objects(a,b);fprintf(Trace,"player1 ");trace(a,step,t);
    fprintf(Trace,"player2 ");trace(b,step,t);
    fprintf(Trace,"tag %d %d",Aafogo,Kozelvannak);number(Afogoido);number(Bfogoido);fprintf(Trace,"\n");
}
static void unload_pair() {
    delete Pszak;Pszak=NULL;
    for(int i=0;i<MAXGYURU;++i)if(Top->ptomb[i]){delete[]Top->ptomb[i]->ponttomb;free(Top->ptomb[i]);}
    for(int i=0;i<MAXKEREK;++i)free(Top->kerektomb[i]);free(Top);free(Ecset);
}
static int pair_case(const char* level,double fps,int tag,int paused,const char* script1,const char* script2) {
    Single=0;Tag=tag;if(!load(level))return 0;
    engine a={},b={};a.pmot=Pmot1;b.pmot=Pmot2;
    Kajakell=Ptop->setallaktiv(Pmot1);Ptop->setallaktiv(Pmot2);eng_reset(&a);eng_reset(&b);
    Aleszfogo=1;fogocskareset();
    std::vector<item> scripts[2]={parse(script1),parse(script2)};
    std::vector<double> starts[2];double duration[2]={};
    for(int p=0;p<2;++p)for(size_t j=0;j<scripts[p].size();++j){starts[p].push_back(duration[p]);duration[p]+=scripts[p][j].n*.0055;}
    double t=0,cel=0,total=std::min(duration[0],duration[1]);size_t cur[2]={},turned[2]={};int step=0,frame=0;
    pair_trace(a,b,step++,t);
    // These are simulation-neutral wall frames. Suspended wall time must
    // never become catch-up steps after the clock resumes.
    typedef std::chrono::steady_clock wall_clock;
    typedef wall_clock::time_point wall_time;
    elma_pause_clock<wall_clock> clock;clock.reset(wall_time{});
    long long wall_ns=0;
    const long long frame_ns=fps>0?static_cast<long long>(1000000000.0/fps):10000000;
    int wall_pause_frames=0;
    while(t<total && !a.finished && !b.finished && !(a.dead&&b.dead)) {
        if(paused && (frame==7 || frame==31 || frame==101)) {
            wall_time before{std::chrono::nanoseconds(wall_ns)};
            wall_clock::duration held=clock.elapsed(before);clock.pause(true,before);
            // Advance only wall time while suspended. This verifies clock
            // integration, not physical pad/USB input handling.
            for(int j=0;j<17;++j){wall_ns+=frame_ns;if(clock.elapsed(wall_time{std::chrono::nanoseconds(wall_ns)})!=held)return 0;++wall_pause_frames;}
            clock.pause(false,wall_time{std::chrono::nanoseconds(wall_ns)});
        }
        wall_ns+=frame_ns;
        cel=fps>0?(std::chrono::duration<double>(clock.elapsed(wall_time{std::chrono::nanoseconds(wall_ns)})).count()*182.0)*.0024:t+.0055;
        while(t<=cel-.000001) {
            double dt=std::min(.0055,cel-t);int in[2]={};
            for(int p=0;p<2;++p){while(cur[p]+1<scripts[p].size() && starts[p][cur[p]+1]<=t+1e-12)++cur[p];in[p]=scripts[p][cur[p]].in;}
            pair_step(a,in[0],t,dt);pair_step(b,in[1],t,dt);
            t+=dt;pair_trace(a,b,step++,t);
            if(a.finished||b.finished||(a.dead&&b.dead))break;
        }
        if(a.finished||b.finished||(a.dead&&b.dead))break;
        if(Tag){int old=Aafogo;fogocska(t);if(old!=Aafogo)++TagTransfers;}
        for(int p=0;p<2;++p)while(turned[p]<scripts[p].size() && starts[p][turned[p]]<=t+1e-12){if(scripts[p][turned[p]].turn)eng_turn(p?&b:&a);++turned[p];}
        ++frame;
    }
    fprintf(Trace,"result %d %d %ld %d %d %ld\n",a.dead,a.finished,a.megvanido,b.dead,b.finished,b.megvanido);
    for(int p=0;p<2;++p){engine& e=p?b:a;for(size_t j=0;j<e.events.size();++j){fprintf(Trace,"event %d %d %d",p,e.events[j].type,e.events[j].obj);number(e.events[j].t);fprintf(Trace,"\n");}}
    // Pause duration is deliberately outside canonical simulation state.
    if(paused && frame>101 && wall_pause_frames!=51)return 0;
    unload_pair();return 1;
}
// Deterministic branch probes ensure tag transfer thresholds and flower
// suppression are exercised even when random riders never reach each other.
static int branch_probes(const char* level) {
    if(!load(level))return 0;Single=0;Tag=1;Ptop->setallaktiv(Pmot1);Ptop->setallaktiv(Pmot2);
    Aleszfogo=1;fogocskareset();Pmot2->kor2.r=Pmot2->kor2.r+vekt2(10,0);Pmot2->kor4.r=Pmot2->kor4.r+vekt2(10,0);
    fogocska(.25);if(Kozelvannak || Aafogo!=1)return 0;
    Pmot2->kor2.r=Pmot1->kor2.r;fogocska(.5);if(!Kozelvannak || Aafogo!=0)return 0;
    fprintf(Trace,"probe tag-transfer %d",Aafogo);number(Afogoido);number(Bfogoido);fprintf(Trace,"\n");
    int flower=-1;for(int i=0;i<Nobj;++i){Ptop->kerektomb[i]->aktiv=0;if(Ptop->kerektomb[i]->tipus==T_CEL)flower=i;}
    if(flower<0)return 0;Ptop->kerektomb[flower]->aktiv=1;
    if(utkozikesprite(Ptop->kerektomb[flower]->r,.1)!=-1)return 0;
    Tag=0;if(utkozikesprite(Ptop->kerektomb[flower]->r,.1)!=flower)return 0;
    fprintf(Trace,"probe flower-suppression PASS\n");unload_pair();return 1;
}
int main(int argc,char**argv) {
#ifdef ELMA_PS3
    const char* cases="/dev_hdd0/game/ELMAC0001/USRDIR/multiplayer-cases.txt";
    const char* output="/dev_hdd0/game/ELMAC0001/USRDIR/multiplayer-trace.txt";
#else
    if(argc!=3)return 2;const char* cases=argv[1];const char* output=argv[2];
#endif
    FILE* f=fopen(cases,"r");Trace=fopen(output,"w");if(!f||!Trace)return 2;
    char line[32768],level[1024];int mode,paused,n,index=0;double fps;
    while(fgets(line,sizeof(line),f)) {
        if(line[0]=='#'||line[0]=='\n')continue;
        if(sscanf(line,"%1023s %lf %d %d %n",level,&fps,&mode,&paused,&n)!=4)return 3;
        char* other=strchr(line+n,'|');if(!other)return 3;*other++=0;
        if(index==0 && !branch_probes(level))return 5;
        fprintf(Trace,"case %d\n",index++);if(!pair_case(level,fps,mode,paused,line+n,other))return 4;fflush(Trace);
    }
    fprintf(Trace,"coverage respawns %d apples %d transfers %d\ncomplete %d\n",Respawns,Apples,TagTransfers,index);
    fclose(f);fclose(Trace);return Respawns>0 && Apples>0?0:6;
}
