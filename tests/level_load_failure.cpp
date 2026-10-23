#include "all.h"
static int played,erased,reopened,palette_set,invalidated;
topol* Ptop=NULL;gyuru* Pgy=NULL;kerek* Pker=NULL;sprite* Psp=NULL;
int Valtozott=0;state_s* State=NULL;ddpal* Pal_editor=NULL;
recorder* Prec1=NULL;recorder* Prec2=NULL;
state_s::state_s(char*){memset(this,0,sizeof(*this));}
state_s::~state_s(){}
vekt2::vekt2(){x=y=0;}
recorder::recorder(){}
recorder::~recorder(){}
void recorder::erase(char*){++erased;}
void ddpal::set(){++palette_set;}
void invalidateegesz(){++invalidated;}
int tolt_save(int){abort();}
int floadlevel_p(char*){free(Ptop);Ptop=NULL;return 0;}
int floadlevel_e(char*,int force){if(force!=1)abort();Ptop=(topol*)calloc(1,sizeof(topol));++reopened;return 1;}
long lejatszo(char*){++played;return 0;}
void editornagyitas(){abort();}
void mk_emptychar(){}
void ps3_diagnostic_checkpoint(const char*,bool){}
int main(){
    state_s state;State=&state;strcpy(state.editfilenev,"test.lev");
    Ptop=(topol*)calloc(1,sizeof(topol));
    // Selection pointers refer to the topology which the failed play loader
    // will delete. The editor must not retain any of them after recovery.
    Pgy=reinterpret_cast<gyuru*>(Ptop);Pker=reinterpret_cast<kerek*>(Ptop);Psp=reinterpret_cast<sprite*>(Ptop);
    Pal_editor=(ddpal*)calloc(1,sizeof(ddpal));
    editplay();
    bool okay=Ptop && !Pgy && !Pker && !Psp && reopened==1 && played==0 && erased==0 && palette_set==1 && invalidated>=2;
    free(Ptop);free(Pal_editor);return okay?0:1;
}
