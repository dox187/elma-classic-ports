#ifndef ELMA_LE_STRUCT_H
#define ELMA_LE_STRUCT_H
#include "LE_IO.H"
static_assert(sizeof(int)==4 && sizeof(short)==2 && sizeof(float)==4 && sizeof(double)==8,"Elma requires 16/32-bit integers and IEEE binary32/binary64 storage");
static_assert(sizeof(palyaegyfeleidok)==344 && sizeof(palyaidok)==688,"Legacy level time layout changed");
static_assert(sizeof(jatekos)==116 && sizeof(jatekosopciok)==32,"Legacy state layout changed");
static_assert(sizeof(egyhang)==16,"Legacy replay sound layout changed");
static_assert(sizeof(vekt2)==16,"Legacy polygon vertex layout changed");
inline void elma_swap(palyaegyfeleidok& p) { elma_swap(p.idokszama); for(int i=0;i<MAXIDOK;++i) elma_swap(p.idok[i]); }
inline void elma_swap(palyaidok& p) { elma_swap(p.singleidok);elma_swap(p.multiidok); }
inline void elma_swap(jatekos& p) { elma_swap(p.sikerespalyakszama);elma_swap(p.jelenlegipalya); }
inline void elma_swap(jatekosopciok& p) {
    elma_swap(p.billgaz);elma_swap(p.billfek);elma_swap(p.billugras1);elma_swap(p.billugras2);
    elma_swap(p.billfordul);elma_swap(p.billview);elma_swap(p.billtime);elma_swap(p.billshowkep);
}
inline void elma_swap(vekt2& p) { elma_swap(p.x);elma_swap(p.y); }
inline void elma_swap(egyhang& p) { elma_swap(p.t);elma_swap(p.objszam);elma_swap(p.hangero); }
#endif
