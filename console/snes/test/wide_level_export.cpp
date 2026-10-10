// Offline export of the candidate's initialized raw integers and grid order.
// The isolated export build makes szakaszok's fields public; layout is unchanged.
#include "all.h"
#include "pcphys.h"
#include <cinttypes>

static void scalar(wide_scalar x) {printf("%" PRId64,x.raw);}
static void vector(vekt2 v) {scalar(v.x);printf(",");scalar(v.y);}
static void circle(const kor& c) {
    scalar(c.alfa);printf(",");scalar(c.omega);printf(",");scalar(c.sugar);
    printf(",");scalar(c.m);printf(",");scalar(c.theta);printf(",");
    vector(c.r);printf(",");vector(c.v);
}
int main(int argc,char** argv) {
    if(argc!=2 || !pc_load(argv[1]))return 2;
    printf("{\"bits\":%d,\"grid_shape\":[%d,%d],\"grid_scalars\":[",WIDE_BITS,Pszak->xdim,Pszak->ydim);
    scalar(Pszak->cellameret);printf(",");vector(Pszak->origo);
    printf("],\"brush\":[");vector(Pecsetalso->eredetiorigo);printf(",");
    scalar(Pecsetalso->eredetimaxx);printf(",");scalar(Pecsetalso->eredetisorszam);
    printf("],\"motor_scalars\":[");circle(Pmot1->kor1);printf(",");
    circle(Pmot1->kor2);printf(",");circle(Pmot1->kor4);printf(",");
    vector(Pmot1->fejr);printf(",");vector(Pmot1->vezetor);printf(",");vector(Pmot1->vezetov);
    const wide_scalar saved[]={Pmot1->dfek2,Pmot1->dfek4,Pmot1->ugras1kezd,Pmot1->ugras2kezd,Pmot1->kezdoomega1,Pmot1->kezdoomega2};
    for(auto x:saved){printf(",");scalar(x);}
    printf("],\"motor_flags\":[%d,%d,%d,%d,%d,%d,%d],\"objects\":[",
           Pmot1->hatra_f,Pmot1->hatra_h,Pmot1->gravirany,Pmot1->kajaszam,Pmot1->voltfek,Pmot1->ugrasban1,Pmot1->ugrasban2);
    for(int i=0;i<pc_nobjs;++i){const auto* k=Ptop->kerektomb[i];
        printf("%s[",i?",":"");vector(k->r);
        printf(",%d,%d,%d,%d]",k->tipus,k->kajatipus,k->foodsorszam,k->aktiv);
    }
    printf("],\"lines\":[");
    for(int i=0;i<Pszak->szam;++i){const auto& l=Pszak->tomb[i];
        printf("%s[",i?",":"");vector(l.r);printf(",");vector(l.v);printf(",");
        vector(l.egyseg);printf(",");vector(l.wide_endpoint);printf(",");
        vector(l.wide_normal);printf(",");scalar(l.hossz);printf("]");
    }
    printf("],\"cells\":[");
    for(int i=0;i<Pszak->xdim*Pszak->ydim;++i){printf("%s[",i?",":"");bool comma=false;
        for(auto* n=Pszak->tertomb[i];n;n=n->pnext){
            printf("%s%d",comma?",":"",int(n->pvonal-Pszak->tomb));comma=true;
        }
        printf("]");
    }
    printf("],\"constants\":{");bool comma=false;
#define VALUE(name) do{printf("%s\"" #name "\":",comma?",":"");scalar(name);comma=true;}while(0)
    VALUE(K_pi);VALUE(K_pip2);VALUE(Elszakadasisebhat);VALUE(Belsosav);VALUE(G);
    VALUE(Talppontegybeolvadasitav);VALUE(Ugrassebesseg1);VALUE(Ugrassebesseg2);
    VALUE(Ugroturelem);VALUE(Vegenvaras);VALUE(Drsugar);VALUE(Drtang);VALUE(Sr);
    VALUE(Fejsugar);VALUE(Objektumsugar);VALUE(Spritemaxsugar);VALUE(Ketmaxsugar);
    VALUE(Fejkerektavnegyzet);VALUE(Fekegyutthato);VALUE(Kord2x);VALUE(Kord2y);
    VALUE(Kord4x);VALUE(Kord4y);VALUE(Kord5y);
#undef VALUE
    printf("}}\n");
}
