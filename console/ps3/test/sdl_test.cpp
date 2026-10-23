#include <SDL.h>
#include <sys/process.h>
#include <sysutil/video.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
SYS_PROCESS_PARAM(1001,0x100000);
#ifndef ELMA_PS3_SDL_TEST_FLIPS
#define ELMA_PS3_SDL_TEST_FLIPS 1200
#endif
static int failures;
static void check(bool ok,const char* label) { printf("%s %s (%s)\n",ok?"PASS":"FAIL",label,ok?"":SDL_GetError());if(!ok)++failures; }
static void finish(SDL_Renderer* r,SDL_Texture* t) { SDL_SetRenderTarget(r,NULL);SDL_RenderCopy(r,t,NULL,NULL);SDL_RenderPresent(r);SDL_SetRenderTarget(r,t); }
static float bounded(float x) {return x<0?0:(x>1?1:x);}
static void pixelart_check(SDL_Renderer* r,SDL_Texture* source,const Uint32* input,int width,int height,bool clipped) {
 SDL_Texture* target=SDL_CreateTexture(r,SDL_PIXELFORMAT_ARGB8888,SDL_TEXTUREACCESS_TARGET,width,height);
 check(target!=NULL,"Pixel Art target allocation");if(!target)return;
 SDL_SetTextureScaleMode(source,SDL_ScaleModeBest);SDL_SetRenderTarget(r,target);
 SDL_SetRenderDrawColor(r,0,0,0,255);SDL_RenderClear(r);
 SDL_Rect clip={3,4,width-6,height-8};if(clipped)SDL_RenderSetClipRect(r,&clip);
 SDL_RenderCopy(r,source,NULL,NULL);SDL_RenderSetClipRect(r,NULL);finish(r,target);
 Uint32 output[80*80];int status=SDL_RenderReadPixels(r,NULL,SDL_PIXELFORMAT_ARGB8888,output,width*4);
 int errors=0,max_error=0;const float bx=fminf(1.f,32.f/width),by=fminf(1.f,32.f/height);
 for(int y=0;y<height;++y)for(int x=0;x<width;++x) {
  Uint32 expected=0xff000000;
  if(!clipped||(x>=clip.x&&x<clip.x+clip.w&&y>=clip.y&&y<clip.y+clip.h)) {
   float px=(x+.5f)*32.f/width-.5f*bx,py=(y+.5f)*32.f/height-.5f*by;
   int ix=(int)floorf(px),iy=(int)floorf(py);
   float tx=bounded(((px-ix)-(1-bx))/bx),ty=bounded(((py-iy)-(1-by))/by);
   tx=tx*tx*(3-2*tx);ty=ty*ty*(3-2*ty);
   int xx[2]={ix,ix+1},yy[2]={iy,iy+1};
   for(int k=0;k<2;++k){if(xx[k]<0)xx[k]=0;if(xx[k]>31)xx[k]=31;if(yy[k]<0)yy[k]=0;if(yy[k]>31)yy[k]=31;}
   for(int shift=0;shift<24;shift+=8) {
    float a=(input[yy[0]*32+xx[0]]>>shift)&255,b=(input[yy[0]*32+xx[1]]>>shift)&255;
    float c=(input[yy[1]*32+xx[0]]>>shift)&255,d=(input[yy[1]*32+xx[1]]>>shift)&255;
    expected|=(Uint32)floorf(((a+(b-a)*tx)*(1-ty)+(c+(d-c)*tx)*ty)+.5f)<<shift;
   }
  }
  Uint32 actual=output[y*width+x];if((actual>>24)!=255)++errors;
  for(int shift=0;shift<24;shift+=8) {int delta=abs((int)((actual>>shift)&255)-(int)((expected>>shift)&255));if(delta>max_error)max_error=delta;if(delta>2)++errors;}
 }
 printf("Pixel Art %dx%d clipped=%d max-channel-error=%d mismatches=%d\n",width,height,clipped,max_error,errors);
 check(status==0&&errors==0,"Pixel Art matches independent CPU smoothstep reference");
 SDL_SetRenderTarget(r,NULL);SDL_DestroyTexture(target);SDL_SetTextureScaleMode(source,SDL_ScaleModeNearest);
}
int main() {
 setvbuf(stdout,NULL,_IONBF,0);
 videoState before={};check(videoGetState(VIDEO_PRIMARY,0,&before)==0,"firmware video state before SDL");
 SDL_SetHint("ELMA_PS3_SDL_PROFILE","1");
 check(SDL_Init(SDL_INIT_VIDEO|SDL_INIT_TIMER|SDL_INIT_AUDIO)==0,"SDL video audio timer init");
 videoState after={};check(videoGetState(VIDEO_PRIMARY,0,&after)==0,"firmware video state after SDL");
 printf("Video mode before/after: resolution %u/%u aspect %u/%u scan %u/%u refresh %u/%u\n",before.displayMode.resolution,after.displayMode.resolution,before.displayMode.aspect,after.displayMode.aspect,before.displayMode.scanMode,after.displayMode.scanMode,before.displayMode.refreshRates,after.displayMode.refreshRates);
 check(before.displayMode.aspect==after.displayMode.aspect,"SDL preserves firmware television aspect");
 check(before.displayMode.resolution==after.displayMode.resolution&&before.displayMode.scanMode==after.displayMode.scanMode&&before.displayMode.refreshRates==after.displayMode.refreshRates,"SDL preserves firmware mode scan and refresh");
 SDL_Window* w=SDL_CreateWindow("Elma SDL regression",0,0,1280,720,0);
 SDL_Renderer* r=SDL_CreateRenderer(w,-1,SDL_RENDERER_ACCELERATED|SDL_RENDERER_PRESENTVSYNC);
 check(r!=NULL,"accelerated renderer");if(!r)return 2;
 Uint32 colors[4]={0xffff0000,0xff00ff00,0xff0000ff,0xffffffff},input[32*32];
 for(int y=0;y<32;++y)for(int x=0;x<32;++x)input[y*32+x]=colors[(y>=16)*2+(x>=16)];
 SDL_Texture* source=SDL_CreateTexture(r,SDL_PIXELFORMAT_ARGB8888,SDL_TEXTUREACCESS_STREAMING,32,32);
 SDL_UpdateTexture(source,NULL,input,128);
 SDL_SetTextureScaleMode(source,SDL_ScaleModeNearest);
 const int large_w=2562,large_h=2148;
 SDL_Texture* large=SDL_CreateTexture(r,SDL_PIXELFORMAT_ARGB8888,SDL_TEXTUREACCESS_TARGET,large_w,large_h);
 check(large!=NULL,"large render target allocation");SDL_SetRenderTarget(r,large);SDL_RenderCopy(r,source,NULL,NULL);finish(r,large);
 Uint32 pixel=0;SDL_Rect point={0,0,1,1};
 check(SDL_RenderReadPixels(r,&point,SDL_PIXELFORMAT_ARGB8888,&pixel,4)==0&&pixel==colors[0],"ARGB red target origin");
 point.x=large_w-1;point.y=large_h-1;pixel=0;SDL_Rect vp;SDL_RenderGetViewport(r,&vp);printf("viewport %d %d %d %d\n",vp.x,vp.y,vp.w,vp.h);SDL_RenderReadPixels(r,&point,SDL_PIXELFORMAT_ARGB8888,&pixel,4);
 printf("corner pixel %08x\n",pixel);check(pixel==colors[3],"target pitch and extent white corner");
 point.x=large_w-1;point.y=0;pixel=0;SDL_RenderReadPixels(r,&point,SDL_PIXELFORMAT_ARGB8888,&pixel,4);
 check(pixel==colors[1],"ARGB green top-right target");
 point.x=0;point.y=large_h-1;pixel=0;SDL_RenderReadPixels(r,&point,SDL_PIXELFORMAT_ARGB8888,&pixel,4);
 check(pixel==colors[2],"ARGB blue bottom-left target");
 SDL_Rect band={0,1000,large_w,200};
 const size_t band_pixels=(size_t)band.w*band.h;
 Uint32* band_memory=(Uint32*)SDL_malloc((band_pixels+2)*sizeof(Uint32));
 check(band_memory!=NULL,"bounded multi-chunk readback allocation");
 if(band_memory) {
  band_memory[0]=0x12345678;band_memory[band_pixels+1]=0x87654321;
  Uint32* band_data=band_memory+1;
  int read=SDL_RenderReadPixels(r,&band,SDL_PIXELFORMAT_ARGB8888,band_data,band.w*4);
  bool valid=read==0&&band_data[0]==colors[0]&&band_data[band.w-1]==colors[1]
      &&band_data[band_pixels-band.w]==colors[2]&&band_data[band_pixels-1]==colors[3]
      &&band_memory[0]==0x12345678&&band_memory[band_pixels+1]==0x87654321;
  check(valid,"multi-chunk readback row pitch and buffer guards");SDL_free(band_memory);
 }
 SDL_SetRenderTarget(r,NULL);SDL_RenderCopy(r,large,NULL,NULL);
 int output_w=0,output_h=0;SDL_GetRendererOutputSize(r,&output_w,&output_h);
 printf("window output %dx%d\n",output_w,output_h);
 for(int corner=0;corner<4;++corner) {
  point.x=(corner&1)?output_w-1:0;point.y=(corner&2)?output_h-1:0;pixel=0;
  int read=SDL_RenderReadPixels(r,&point,SDL_PIXELFORMAT_ARGB8888,&pixel,4);
  check(read==0&&pixel==colors[corner],"window surface corner before present");
 }
 SDL_RenderPresent(r);SDL_SetRenderTarget(r,large);
 SDL_Texture* reduced=SDL_CreateTexture(r,SDL_PIXELFORMAT_ARGB8888,SDL_TEXTUREACCESS_TARGET,64,64);
 SDL_SetRenderTarget(r,reduced);SDL_RenderCopy(r,large,NULL,NULL);finish(r,reduced);
 for(int corner=0;corner<4;++corner) {
  point.x=(corner&1)?63:0;point.y=(corner&2)?63:0;pixel=0;
  SDL_RenderReadPixels(r,&point,SDL_PIXELFORMAT_ARGB8888,&pixel,4);
  check(pixel==colors[corner],"source width/height above2047 scales without signed overflow");
 }
 SDL_SetRenderTarget(r,NULL);SDL_DestroyTexture(reduced);SDL_DestroyTexture(large);
 SDL_Texture* small=SDL_CreateTexture(r,SDL_PIXELFORMAT_ARGB8888,SDL_TEXTUREACCESS_TARGET,64,64);
 SDL_SetTextureScaleMode(source,SDL_ScaleModeLinear);SDL_SetRenderTarget(r,small);SDL_RenderCopy(r,source,NULL,NULL);finish(r,small);
 point.x=31;point.y=31;pixel=0;SDL_RenderReadPixels(r,&point,SDL_PIXELFORMAT_ARGB8888,&pixel,4);
 bool mixed=(pixel>>24)==255;
 const int expected[3]={159,64,64};
 for(int channel=0;channel<3;++channel) {
  int actual=(pixel>>(16-8*channel))&255;
  if(actual<expected[channel]-2||actual>expected[channel]+2)mixed=false;
 }
 printf("linear pixel %08x\n",pixel);check(mixed,"bilinear matches expected ARGB blend");
 for(int y=0;y<32;++y)for(int x=0;x<32;++x)input[y*32+x]=0xff000000|(((x*53+y*17)&255)<<16)|(((x*11+y*71)&255)<<8)|((x*97+y*29)&255);
 SDL_UpdateTexture(source,NULL,input,128);pixelart_check(r,source,input,80,72,false);pixelart_check(r,source,input,19,17,true);
 SDL_SetRenderTarget(r,small);
 SDL_SetTextureScaleMode(source,SDL_ScaleModeNearest);for(int i=0;i<32*32;++i)input[i]=0xffffffff;SDL_UpdateTexture(source,NULL,input,128);
 SDL_SetRenderDrawColor(r,0,0,0,255);SDL_RenderClear(r);SDL_Rect clip={16,16,32,32};SDL_RenderSetClipRect(r,&clip);SDL_RenderCopy(r,source,NULL,NULL);finish(r,small);
 point.x=0;point.y=0;pixel=0;SDL_RenderReadPixels(r,&point,SDL_PIXELFORMAT_ARGB8888,&pixel,4);printf("clip outside %08x\n",pixel);check(pixel==0xff000000,"clip preserves black outside");
 point.x=31;point.y=31;pixel=0;SDL_RenderReadPixels(r,&point,SDL_PIXELFORMAT_ARGB8888,&pixel,4);check(pixel==0xffffffff,"clip writes white inside");
 SDL_RenderSetClipRect(r,NULL);
 SDL_Rect offset_view={5,7,32,32};SDL_RenderSetViewport(r,&offset_view);
 SDL_SetRenderDrawColor(r,0,0,0,255);SDL_RenderClear(r);
 SDL_SetRenderDrawColor(r,255,255,255,255);SDL_RenderDrawPoint(r,2,3);
 SDL_Rect fill={4,5,3,2};SDL_RenderFillRect(r,&fill);
 point.x=7;point.y=10;pixel=0;SDL_RenderReadPixels(r,&point,SDL_PIXELFORMAT_ARGB8888,&pixel,4);
 check(pixel==0xffffffff,"offset viewport point and absolute readback");
 point.x=9;point.y=12;pixel=0;SDL_RenderReadPixels(r,&point,SDL_PIXELFORMAT_ARGB8888,&pixel,4);
 check(pixel==0xffffffff,"integer fill rectangle coordinates");
 SDL_Rect line_clip={0,0,8,8};SDL_RenderSetClipRect(r,&line_clip);
 SDL_SetRenderDrawColor(r,255,0,0,255);
 SDL_RenderDrawLine(r,0,0,12,0);SDL_RenderDrawLine(r,0,0,6,6);
 point.x=8;point.y=7;pixel=0;SDL_RenderReadPixels(r,&point,SDL_PIXELFORMAT_ARGB8888,&pixel,4);
 check(pixel==0xffff0000,"offset horizontal line pixel");
 point.x=8;point.y=10;pixel=0;SDL_RenderReadPixels(r,&point,SDL_PIXELFORMAT_ARGB8888,&pixel,4);
 check(pixel==0xffff0000,"offset diagonal line pixel");
 point.x=13;point.y=7;pixel=0;SDL_RenderReadPixels(r,&point,SDL_PIXELFORMAT_ARGB8888,&pixel,4);
 check(pixel==0xff000000,"line clipping preserves outside pixel");
 SDL_RenderSetClipRect(r,NULL);SDL_RenderSetViewport(r,NULL);
 for(int y=0;y<32;++y)for(int x=0;x<32;++x)input[y*32+x]=colors[(y>=16)*2+(x>=16)];
 SDL_UpdateTexture(source,NULL,input,128);SDL_RenderCopy(r,source,NULL,NULL);
 SDL_Texture* chain=SDL_CreateTexture(r,SDL_PIXELFORMAT_ARGB8888,SDL_TEXTUREACCESS_TARGET,64,64);
 SDL_SetRenderTarget(r,chain);SDL_RenderCopy(r,small,NULL,NULL);finish(r,chain);
 for(int corner=0;corner<4;++corner) {
  point.x=(corner&1)?63:0;point.y=(corner&2)?63:0;pixel=0;
  SDL_RenderReadPixels(r,&point,SDL_PIXELFORMAT_ARGB8888,&pixel,4);
  check(pixel==colors[corner],"same-submit patterned target sampling without present");
 }
 SDL_SetRenderTarget(r,NULL);SDL_DestroyTexture(chain);
 SDL_SetRenderTarget(r,NULL);SDL_RenderSetClipRect(r,NULL);
 SDL_Texture* cycling=SDL_CreateTexture(r,SDL_PIXELFORMAT_ARGB8888,SDL_TEXTUREACCESS_TARGET,1708,960);
 for(int frame=0;frame<ELMA_PS3_SDL_TEST_FLIPS;++frame) {
  SDL_SetRenderTarget(r,frame%2?cycling:small);SDL_RenderSetClipRect(r,NULL);
  SDL_RenderCopy(r,source,NULL,NULL);SDL_SetRenderTarget(r,NULL);
  SDL_RenderCopy(r,frame%2?cycling:small,NULL,NULL);SDL_RenderPresent(r);
  if(frame%100==0)printf("flip-progress %d\n",frame);
 }
 printf("PASS %d flips with alternating targets\n",ELMA_PS3_SDL_TEST_FLIPS);SDL_DestroyTexture(cycling);
 SDL_DestroyTexture(source);SDL_DestroyTexture(small);
 SDL_AudioSpec want={};want.freq=11025;want.format=AUDIO_S16SYS;want.channels=1;want.samples=512;
 SDL_AudioDeviceID audio=SDL_OpenAudioDevice(NULL,0,&want,NULL,0);check(audio!=0,"11025 mono S16SYS queued audio conversion");
 if(audio){short sound[11025]={};for(int i=0;i<11025;++i)sound[i]=(i%25<12)?3000:-3000;SDL_QueueAudio(audio,sound,sizeof(sound));Uint32 before=SDL_GetQueuedAudioSize(audio);SDL_PauseAudioDevice(audio,0);Uint32 tick=SDL_GetTicks();SDL_Delay(200);Uint32 after=SDL_GetQueuedAudioSize(audio);check(after<before,"audio queue drains on native audio event thread");check(SDL_GetTicks()-tick>=190,"timer advances during delay");SDL_CloseAudioDevice(audio);}
 SDL_DestroyRenderer(r);
 r=SDL_CreateRenderer(w,-1,SDL_RENDERER_ACCELERATED|SDL_RENDERER_PRESENTVSYNC);
 check(r!=NULL,"renderer recreation with retained GPU label");
 if(r){SDL_SetRenderDrawColor(r,0,255,0,255);SDL_RenderClear(r);SDL_RenderPresent(r);SDL_DestroyRenderer(r);}
 printf("SDL RESULT %s %d failures\n",failures?"FAIL":"PASS",failures);SDL_DestroyWindow(w);SDL_Quit();return failures?1:0;
}
