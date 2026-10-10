/* Exact offline snapshot loader. Generated configuration supplies bounds,
 * constants and the C-port globals; this file contains no host allocation. */
#define WIDE_PORT_BRIDGE
#include "wide_port.h"
#include <string.h>
#include "wide_level_config.h"

static wp_motor wl_motor;
static wp_top wl_top;
static wp_brush wl_brush;
static wp_segments wl_segments;
static wp_line wl_lines[WL_MAX_LINES];
static wp_object wl_objects[52];
static wp_node wl_nodes[WL_MAX_CELL];
static const unsigned char *wl_rows,*wl_runs,*wl_lists;

static unsigned int read16(const unsigned char* p){
    return (unsigned int)p[0]|((unsigned int)p[1]<<8);
}
static uint32_t read32(const unsigned char* p){
    return (uint32_t)read16(p)|((uint32_t)read16(p+2)<<16);
}
static wp_scalar read_scalar(const unsigned char* p){
    wp_scalar value;
#ifdef WIDE_TARGET_SNES
    value.word[0]=read16(p);value.word[1]=read16(p+2);
    value.word[2]=read16(p+4);value.word[3]=read16(p+6);
#else
    uint64_t raw=(uint64_t)read32(p)|((uint64_t)read32(p+4)<<32);
    memcpy(&value,&raw,8);
#endif
    return value;
}
static wp_scalar take_scalar(const unsigned char** p){
    wp_scalar value=read_scalar(*p);*p+=8;return value;
}
static wp_scalar compact_scalar(const unsigned char* p,unsigned int size,int is_signed){
    unsigned char expanded[8],fill=0;unsigned int i;
    if(is_signed&&(p[size-1]&128))fill=255;
    for(i=0;i<8;++i)expanded[i]=i<size?p[i]:fill;
    return read_scalar(expanded);
}
static wp_vec compact_point(const unsigned char* points,unsigned int index){
    wp_vec result;const unsigned char* p=points+14UL*index;
    result.x=compact_scalar(p,7,1);result.y=compact_scalar(p+7,7,1);return result;
}
static wp_vec take_vec(const unsigned char** p){
    wp_vec value;value.x=take_scalar(p);value.y=take_scalar(p);return value;
}
static void take_circle(const unsigned char** p,wp_kor* c){
    c->alfa=take_scalar(p);c->omega=take_scalar(p);c->sugar=take_scalar(p);
    c->m=take_scalar(p);c->theta=take_scalar(p);c->r=take_vec(p);c->v=take_vec(p);
}

#include "wide_level_globals.inc"

void wp_hiba(char* a,char* b,char* c){
    (void)b;(void)c;wp_wide_fail(a);
}

wp_scalar wp_constant(unsigned int index){
    if(index>=WL_CONSTANT_COUNT){wp_wide_fail("constant index");}
    return read_scalar(wl_constants+8UL*index);
}

/* Every section has its own far pointer. A section never crosses a LoROM
 * bank; an entire level can exceed32KiB without linear bank-wrap reads. */
int wp_load_level_parts(const unsigned char* blob,const unsigned char* const* parts){
    const unsigned char *p,*constants,*points,*records;
    unsigned int i,nlines,nobjects,version,npoints;
    int apples=0;
    version=read16(blob+4);
    if(memcmp(blob,"WLV1",4)||(version!=1&&version!=2)||read16(blob+6)!=WL_BITS||read16(blob+18)!=7)return 0;
    nlines=read16(blob+8);nobjects=read16(blob+10);
    if(nlines>WL_MAX_LINES||nobjects>52||read16(blob+16)!=WL_LEVEL_CONSTANT_COUNT)return 0;
    memset(&wl_motor,0,sizeof(wl_motor));memset(&wl_top,0,sizeof(wl_top));
    memset(&wl_segments,0,sizeof(wl_segments));
    wl_segments.tomb=wl_lines;wl_segments.szam=nlines;wl_segments.maxszam=nlines;
    wl_segments.xdim=read16(blob+12);wl_segments.ydim=read16(blob+14);
    if(!wl_segments.xdim||!wl_segments.ydim)return 0;
    p=parts[0];
    wl_segments.cellameret=take_scalar(&p);wl_segments.origo=take_vec(&p);
    wl_brush.eredetiorigo=take_vec(&p);
    wl_brush.eredetimaxx=take_scalar(&p);wl_brush.eredetisorszam=take_scalar(&p);
    take_circle(&p,&wl_motor.kor1);take_circle(&p,&wl_motor.kor2);take_circle(&p,&wl_motor.kor4);
    wl_motor.fejr=take_vec(&p);wl_motor.vezetor=take_vec(&p);wl_motor.vezetov=take_vec(&p);
    wl_motor.dfek2=take_scalar(&p);wl_motor.dfek4=take_scalar(&p);
    wl_motor.ugras1kezd=take_scalar(&p);wl_motor.ugras2kezd=take_scalar(&p);
    wl_motor.kezdoomega1=take_scalar(&p);wl_motor.kezdoomega2=take_scalar(&p);
    wl_motor.hatra_f=(int16_t)read16(p);wl_motor.hatra_h=(int16_t)read16(p+2);
    wl_motor.gravirany=(int16_t)read16(p+4);wl_motor.kajaszam=(int16_t)read16(p+6);
    wl_motor.voltfek=(int16_t)read16(p+8);wl_motor.ugrasban1=(int16_t)read16(p+10);
    wl_motor.ugrasban2=(int16_t)read16(p+12);
    constants=parts[1];
    wl_assign_globals(constants);
    p=parts[2];
    for(i=0;i<nobjects;++i){
        wp_object* o=&wl_objects[i];o->r=take_vec(&p);
        o->tipus=(int16_t)read16(p);o->kajatipus=(int16_t)read16(p+2);
        o->foodsorszam=(int16_t)read16(p+4);o->aktiv=(int16_t)read16(p+6);p+=8;
        wl_top.kerektomb[i]=o;wl_pc_obj_active[i]=o->aktiv;
        if(o->tipus==2)++apples;
    }
    p=parts[3];
    if(version==1){
        for(i=0;i<nlines;++i){
            wp_line* l=&wl_lines[i];l->r=take_vec(&p);l->v=take_vec(&p);
            l->egyseg=take_vec(&p);l->wide_endpoint=take_vec(&p);l->wide_normal=take_vec(&p);
            l->hossz=take_scalar(&p);
        }
    }else{
        npoints=read16(p);points=p+2;records=points+14UL*npoints;
        for(i=0;i<nlines;++i){
            wp_line* l=&wl_lines[i];wp_vec end;unsigned int from,to;
            p=records+27UL*i;from=read16(p);to=read16(p+2);
            if(from>=npoints||to>=npoints)return 0;
            l->r=compact_point(points,from);end=compact_point(points,to);
            l->v=wp_sub_v(end,l->r);
            l->egyseg.x=compact_scalar(p+4,6,1);l->egyseg.y=compact_scalar(p+10,6,1);
            l->hossz=compact_scalar(p+16,7,0);
            l->wide_endpoint.x=wp_add(end.x,compact_scalar(p+23,2,1));
            l->wide_endpoint.y=wp_add(end.y,compact_scalar(p+25,2,1));
            l->wide_normal=wp_forgatas90fokkal(l->egyseg);
        }
    }
    wl_rows=parts[4];wl_runs=parts[5];wl_lists=parts[6];
    wl_pc_nobjs=nobjects;wl_Racsonkivul=0;wl_Single=1;wl_Tag=0;
    wl_pc_bump=wp_int(0);wl_pc_friction=wp_int(0);wl_pc_time=wp_int(0);wl_pc_eaten=0;
    wp_runtime_reset(apples);
    return 1;
}

/* The host trace fixtures retain their convenient contiguous file format. */
int wp_load_level(const unsigned char* blob){
    const unsigned char* parts[7];unsigned int i;
    for(i=0;i<7;++i)parts[i]=blob+read32(blob+20+4*i);
    return wp_load_level_parts(blob,parts);
}

/* Only the active cell needs linked nodes. No physics query nests another
 * grid enumeration; original order, duplicates and boundary rules survive. */
void wp_szakaszok_felsorolasreset(wp_segments* self,wp_vec r){
    unsigned int start,end,list=0,count,i;
    int x=0,y=0;
    const unsigned char* p;
    r=wp_scale(wp_sub_v(r,self->origo),wp_div(wp_int(1),self->cellameret));
    if(wp_gt(r.x,wp_int(0)))x=wp_to_int(r.x);
    if(wp_gt(r.y,wp_int(0)))y=wp_to_int(r.y);
    if(x>self->xdim){wl_Racsonkivul=1;x=self->xdim;}
    if(y>self->ydim){wl_Racsonkivul=1;y=self->ydim;}
    if(x==self->xdim)--x;if(y==self->ydim)--y;
    start=read16(wl_rows+2UL*y);end=read16(wl_rows+2UL*y+2);
    for(i=start;i<end;i+=3){
        p=wl_runs+i;if(p[0]>x)break;list=read16(p+1);
    }
    p=wl_lists+list;count=read16(p);p+=2;
    if(count>WL_MAX_CELL){wp_wide_fail("cell capacity");}
    for(i=0;i<count;++i){
        unsigned int id=read16(p+2UL*i);
        if(id>=self->szam){wp_wide_fail("segment index");}
        wl_nodes[i].pvonal=&wl_lines[id];
        wl_nodes[i].pnext=i+1<count?&wl_nodes[i+1]:0;
    }
    if(count)self->nextnode=&wl_nodes[0];else self->nextnode=0;
}
