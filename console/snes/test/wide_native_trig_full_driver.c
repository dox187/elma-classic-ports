#include <snes.h>
#include "core.h"
void wnt_trig(void);void wnt_cache_reset(void);
extern volatile u8 wnt_ram[];
u8 wnf_angle[6],wnf_sin[4],wnf_cos[4];
volatile u16 wnt_go,wnt_done;
void wide_trig_pair(const u8* angle48Q32,u8* sinQ30,u8* cosQ30){
 u16 i;
 for(i=0;i<6;i++)wnt_ram[i]=angle48Q32[i];
 wnt_trig();
 for(i=0;i<4;i++){sinQ30[i]=wnt_ram[80+i];cosQ30[i]=wnt_ram[88+i];}
}
void wide_trig_pair_words(const u8* angle48Q32,u8* sinQ30,u8* cosQ30){
 *(volatile u16*)(wnt_ram+0)=*(const u16*)(angle48Q32+0);
 *(volatile u16*)(wnt_ram+2)=*(const u16*)(angle48Q32+2);
 *(volatile u16*)(wnt_ram+4)=*(const u16*)(angle48Q32+4);
 wnt_trig();
 *(u16*)(sinQ30+0)=*(volatile u16*)(wnt_ram+80);
 *(u16*)(sinQ30+2)=*(volatile u16*)(wnt_ram+82);
 *(u16*)(cosQ30+0)=*(volatile u16*)(wnt_ram+88);
 *(u16*)(cosQ30+2)=*(volatile u16*)(wnt_ram+90);
}
int main(void){consoleInit();core_init();core_screen_off();wnt_cache_reset();while(1){if(wnt_go){u16 command=wnt_go;wnt_go=0;if(command==1)wnt_trig();else if(command==2)wide_trig_pair(wnf_angle,wnf_sin,wnf_cos);else if(command==3)wide_trig_pair_words(wnf_angle,wnf_sin,wnf_cos);else wnt_cache_reset();wnt_done=1;}core_frame_done();}return 0;}
