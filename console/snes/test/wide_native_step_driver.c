/* Experimental complete-step correctness ROM; no production integration. */
#include <snes.h>
#include "core.h"
#include "wide_port.h"

extern const unsigned char wide_native_level00[];
int wp_load_level(const unsigned char*);
void wide_stack_opcode_proof(void);
volatile u16 wide_step_go,wide_step_done,wide_step_loaded,wide_step_input;
volatile u16 wide_step_events,wide_step_count,wide_step_meta[7];
u16 wide_step_state[120];
unsigned char wide_step_objects[52];
u16 wide_step_time[4];
static wp_scalar dt={{0,0,0,0}};

static void put(unsigned offset,wp_scalar value){unsigned i;for(i=0;i<4;++i)wide_step_state[offset+i]=value.word[i];}
static void snapshot(void){wp_motor* m=*wp_ptr_Pmot1();wp_kor* c;unsigned i,at=0;wp_scalar time=*wp_ptr_pc_time();
 for(i=0;i<3;++i){c=i==0?&m->kor1:(i==1?&m->kor2:&m->kor4);put(at,c->r.x);put(at+4,c->r.y);put(at+8,c->v.x);put(at+12,c->v.y);put(at+16,c->alfa);put(at+20,c->omega);at+=24;}
 put(72,m->vezetor.x);put(76,m->vezetor.y);put(80,m->vezetov.x);put(84,m->vezetov.y);put(88,m->fejr.x);put(92,m->fejr.y);
 put(96,m->dfek2);put(100,m->dfek4);put(104,m->ugras1kezd);put(108,m->ugras2kezd);put(112,m->kezdoomega1);put(116,m->kezdoomega2);
 wide_step_meta[0]=m->hatra_f;wide_step_meta[1]=m->gravirany;wide_step_meta[2]=m->kajaszam;wide_step_meta[3]=*wp_ptr_pc_eaten();
 wide_step_meta[4]=m->voltfek;wide_step_meta[5]=m->ugrasban1;wide_step_meta[6]=m->ugrasban2;
 for(i=0;i<52;++i)wide_step_objects[i]=(unsigned char)wp_array_pc_obj_active()[i];
 for(i=0;i<4;++i)wide_step_time[i]=time.word[i];
}

int main(void){u16 command;consoleInit();core_init();core_screen_off();
 /* Q44 round(.00546*2^44), identical to the fixed source dt literal. */
 dt.word[0]=35756;dt.word[1]=26843;dt.word[2]=22;dt.word[3]=0;
 wide_step_go=wide_step_done=wide_step_count=0;
 while(1){command=wide_step_go;if(command){wide_step_go=0;wide_step_done=0;
  if(command==1){wide_step_loaded=wp_load_level(wide_native_level00);wide_step_count=0;wide_step_events=0;}
  else if(command==2){wide_step_events=wp_pc_step(wide_step_input,dt);++wide_step_count;}
  else if(command==3){wp_pc_turn();}
  else if(command==4){wide_stack_opcode_proof();}
  snapshot();wide_step_done=1;
 }}return 0;
}
