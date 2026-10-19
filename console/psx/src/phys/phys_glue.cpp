// The fixed point physics (fixphys.c) in the place of leptet, vizsgalat,
// resetleptet and kiszamolsurlodast of the original (LEPTET.CPP): it keeps
// a fixed point state for each motorst and, after each step, writes it back
// into the double fields of motorst, which the rest of the game (drawing,
// recorder, sounds, camera) reads. If something else changes those fields
// (initmotor in Flag Tag, the start of a game), the state is read from them
// again. The level is prepared at load on the PS1, or at the first step on
// the host; its compact cache can be evicted and rebuilt around the menus.
//
// The functions are named fxg_*; phys_api.cpp gives them the names of the
// original on the PlayStation, the host test calls them next to the
// original's.

// The grid and the edges of the level are private members of szakaszok and
// ecset: the system headers first, then the classes opened up for this file.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>
#include <ctype.h>
#include <stdint.h>
#define class struct
#define private public
#define protected public
#include "all.h"
#undef class
#undef private
#undef protected

#include "fixphys.h"
#include "phys_glue.h"

namespace {

// The double fields of motorst the physics writes (r, v, alfa, omega of
// the three circles, vezetor, vezetov), as the last step left them:
#define NEXPORT 22

struct slot {
	motorst* pmot;
	fx_bike b;
	int imported;
	double out[NEXPORT];
};

slot Slots[2];
fx_level Lev;
fx_param Param;
int Level_ready = 0;
double Maxsurlodas_last = 0.0;

void fields( motorst* pmot, double** f ) {
	kor* k[3] = { &pmot->kor1, &pmot->kor2, &pmot->kor4 };
	for( int i = 0; i < 3; i++ ) {
		f[i*6] = &k[i]->r.x;
		f[i*6+1] = &k[i]->r.y;
		f[i*6+2] = &k[i]->v.x;
		f[i*6+3] = &k[i]->v.y;
		f[i*6+4] = &k[i]->alfa;
		f[i*6+5] = &k[i]->omega;
	}
	f[18] = &pmot->vezetor.x;
	f[19] = &pmot->vezetor.y;
	f[20] = &pmot->vezetov.x;
	f[21] = &pmot->vezetov.y;
}

void values( const fx_bike* b, int64_t* v ) {
	for( int i = 0; i < 3; i++ ) {
		const fx_kor* k = &b->k[i];
		v[i*6] = k->r.x;
		v[i*6+1] = k->r.y;
		v[i*6+2] = k->v.x;
		v[i*6+3] = k->v.y;
		v[i*6+4] = k->a;
		v[i*6+5] = k->w;
	}
	v[18] = b->vr.x;
	v[19] = b->vr.y;
	v[20] = b->vv.x;
	v[21] = b->vv.y;
}

// The circles and the rider from the double fields; with all, the start of a
// game (resetleptet), also the brake and the volts, which only the physics
// changes during a game.
void import( slot* s, int all ) {
	motorst* pmot = s->pmot;
	fx_bike* b = &s->b;
	double* f[NEXPORT];
	fields( pmot, f );
	if( all )
		memset( b, 0, sizeof( *b ) );
	for( int i = 0; i < 3; i++ ) {
		fx_kor* k = &b->k[i];
		k->r.x = fx_d2q( *f[i*6], 40 );
		k->r.y = fx_d2q( *f[i*6+1], 40 );
		k->v.x = fx_d2q( *f[i*6+2], 40 );
		k->v.y = fx_d2q( *f[i*6+3], 40 );
		k->a = fx_d2q( *f[i*6+4], 40 );
		k->w = fx_d2q( *f[i*6+5], 40 );
	}
	b->aw = fx_wrap( b->k[0].a );
	b->vr.x = fx_d2q( *f[18], 40 );
	b->vr.y = fx_d2q( *f[19], 40 );
	b->vv.x = fx_d2q( *f[20], 40 );
	b->vv.y = fx_d2q( *f[21], 40 );
	b->fej.x = fx_d2q( pmot->fejr.x, 40 );
	b->fej.y = fx_d2q( pmot->fejr.y, 40 );
	if( all ) {
		b->voltfek = pmot->voltfek;
		b->dfek2 = fx_d2q( pmot->dfek2, 40 );
		b->dfek4 = fx_d2q( pmot->dfek4, 40 );
		b->ugrasban1 = pmot->ugrasban1;
		b->ugrasban2 = pmot->ugrasban2;
		b->ugras1kezd = pmot->ugras1kezd;
		b->ugras2kezd = pmot->ugras2kezd;
		b->kezdoomega1 = fx_d2q( pmot->kezdoomega1, 40 );
		b->kezdoomega2 = fx_d2q( pmot->kezdoomega2, 40 );
	}
	s->imported = 1;
}

// True if the game changed a field since the last step:
int changed( slot* s ) {
	double* f[NEXPORT];
	fields( s->pmot, f );
	for( int i = 0; i < NEXPORT; i++ ) {
		uint64_t now, before;
		__builtin_memcpy( &now, f[i], 8 );
		__builtin_memcpy( &before, &s->out[i], 8 );
		if( now != before )
			return 1;
	}
	return 0;
}

void export_state( slot* s ) {
	motorst* pmot = s->pmot;
	fx_bike* b = &s->b;
	double* f[NEXPORT];
	int64_t v[NEXPORT];
	fields( pmot, f );
	values( b, v );
	for( int i = 0; i < NEXPORT; i++ )
		*f[i] = s->out[i] = fx_q2d( v[i], 40 );
	pmot->fejr.x = fx_q2d( b->fej.x, 40 );
	pmot->fejr.y = fx_q2d( b->fej.y, 40 );
	// Only the physics reads these during a game; written for the look of
	// the state:
	pmot->voltfek = b->voltfek;
	pmot->ugrasban1 = b->ugrasban1;
	pmot->ugrasban2 = b->ugrasban2;
	pmot->ugras1kezd = b->ugras1kezd;
	pmot->ugras2kezd = b->ugras2kezd;
}

slot* find_slot( motorst* pmot ) {
	for( int i = 0; i < 2; i++ )
		if( Slots[i].pmot == pmot )
			return &Slots[i];
	for( int i = 0; i < 2; i++ )
		if( !Slots[i].pmot ) {
			Slots[i].pmot = pmot;
			Slots[i].imported = 0;
			return &Slots[i];
		}
	// More bikes than two: reuse the second slot.
	Slots[1].pmot = pmot;
	Slots[1].imported = 0;
	return &Slots[1];
}

void free_level( void ) {
#ifdef ELMA_PSX
	if( Lev.line_chunks ) {
		for( int c = 0; c < (Lev.nlines+FX_LINE_CHUNK-1)/FX_LINE_CHUNK; ++c )
			free( Lev.line_chunks[c] );
		free( Lev.line_chunks );
	}
	else
#endif
	free( Lev.lines );
	free( Lev.row );
	free( Lev.cell );
#ifdef ELMA_PSX
	if( Lev.list_rows ) {
		for( int y = 0; y < Lev.ydim; ++y )
			free( Lev.list_rows[y] );
		free( Lev.list_rows );
	}
	else
#endif
	free( Lev.list );
	free( Lev.objs );
	memset( &Lev, 0, sizeof( Lev ) );
}

// The lines of the level and their grid, from szakaszok.
void build_lines( szakaszok* psz ) {
	int n = psz->szam;
	Lev.nlines = n;

	// The grid, in the order of the lists of szakaszok:
	Lev.xdim = psz->xdim;
	Lev.ydim = psz->ydim;
	Lev.origo.x = fx_d2q( psz->origo.x, 40 );
	Lev.origo.y = fx_d2q( psz->origo.y, 40 );
	const int xdim = psz->xdim, ydim = psz->ydim;
	Lev.row = (uint32_t*)malloc( sizeof( uint32_t )*(ydim+1) );
	Lev.cell = (uint16_t*)malloc( sizeof( uint16_t )*(xdim+1)*(ydim > 0 ? ydim : 1) );
	if( !Lev.row || !Lev.cell )
		hiba( "Not enough memory for the collision grid!" );
	uint32_t total = 0;
	for( int y = 0; y < ydim; y++ ) {
		Lev.row[y] = total;
		uint32_t inrow = 0;
		for( int x = 0; x < xdim; x++ ) {
			Lev.cell[(xdim+1)*y+x] = (uint16_t)inrow;
			for( vonalnode* pn = psz->tertomb[xdim*y+x]; pn; pn = pn->pnext )
				inrow++;
		}
		if( inrow > 65535 )
			hiba( "fxg: too many lines in a row of the grid!" );
		Lev.cell[(xdim+1)*y+xdim] = (uint16_t)inrow;
		total += inrow;
	}
	Lev.row[ydim] = total;
	Lev.list = (uint16_t*)malloc( sizeof( uint16_t )*(total > 0 ? total : 1) );
#ifdef ELMA_PSX
	if( !Lev.list ) {
		// A warm sound bank can split the remaining space while the
		// original grid is still resident. Each row is independently
		// contiguous for the unchanged contact iterator below.
		Lev.list_rows = (uint16_t**)calloc( ydim > 0 ? ydim : 1, sizeof(uint16_t*) );
		if( !Lev.list_rows )
			hiba( "Not enough memory for collision list rows!" );
		for( int y = 0; y < ydim; ++y ) {
			const uint32_t count = Lev.row[y+1]-Lev.row[y];
			if( !count ) continue;
			Lev.list_rows[y] = (uint16_t*)malloc( sizeof(uint16_t)*count );
			if( !Lev.list_rows[y] )
				hiba( "Not enough memory for a collision list row!" );
		}
		printf( "elma: collision list uses separate rows (%u bytes)\n", (unsigned)(sizeof(uint16_t)*total) );
	}
#else
	if( !Lev.list ) {
		printf( "elma: collision cell lists need %u bytes\n", (unsigned)(sizeof(uint16_t)*total) );
		hiba( "Not enough memory for collision cell lists!" );
	}
#endif
	for( int y = 0; y < ydim; ++y ) {
		uint16_t* dest = (uint16_t*)fx_level_row( &Lev, y );
		uint32_t j = 0;
		for( int x = 0; x < xdim; ++x )
			for( vonalnode* pn = psz->tertomb[xdim*y+x]; pn; pn = pn->pnext )
				dest[j++] = (uint16_t)psz->getsorszam( pn->pvonal );
	}
#ifdef ELMA_PSX
	// Only the double physics searched the grid of szakaszok:
	delete[] psz->tertomb;
	psz->tertomb = NULL;
	psz->deleteallnodes();
#endif
	// Allocate the fixed lines after the original grid is released. A
	// dense level can have hundreds of KB of temporary grid nodes, which
	// need not overlap the second copy of all its line coordinates.
#ifdef ELMA_PSX
	const int chunks = (n+FX_LINE_CHUNK-1)/FX_LINE_CHUNK;
	Lev.line_chunks = (fx_line**)calloc( chunks > 0 ? chunks : 1, sizeof(fx_line*) );
	if( !Lev.line_chunks )
		hiba( "Not enough memory for collision line chunks!" );
	for( int c = 0; c < chunks; ++c ) {
		const int count = n-c*FX_LINE_CHUNK;
		Lev.line_chunks[c] = (fx_line*)malloc( sizeof(fx_line)*(count < FX_LINE_CHUNK ? count : FX_LINE_CHUNK) );
		if( !Lev.line_chunks[c] )
			hiba( "Not enough memory for collision lines!" );
	}
	Lev.lines = chunks > 0 ? Lev.line_chunks[0] : NULL;
#else
	Lev.lines = (fx_line*)malloc( sizeof( fx_line )*(n > 0 ? n : 1) );
	if( !Lev.lines )
		uzenet( "memory!" );
#endif
	for( int i = 0; i < n; i++ ) {
		vonal* pv = psz->getptrszakasz( i );
		fx_line* l = (fx_line*)fx_level_line( &Lev, i );
		l->p.x = fx_d2q( pv->r.x, 40 );
		l->p.y = fx_d2q( pv->r.y, 40 );
		vekt2 vege = pv->r+pv->egyseg*pv->hossz;
		l->e.x = fx_d2q( vege.x, 40 );
		l->e.y = fx_d2q( vege.y, 40 );
		l->len = fx_d2q( pv->hossz, 40 );
		l->ux = (int32_t)fx_d2q( pv->egyseg.x, 30 );
		l->uy = (int32_t)fx_d2q( pv->egyseg.y, 30 );
		l->lx = (int32_t)fx_d2q( pv->egyseg.x*1073741824.0-l->ux, 31 );
		l->ly = (int32_t)fx_d2q( pv->egyseg.y*1073741824.0-l->uy, 31 );
	}
}

void build_level( void ) {
	if( !Pszak || !Ptop || !Pecsetalso )
		hiba( "fxg: no level for the physics!" );
	fx_init();
	szakaszok* psz = Pszak;
#ifdef ELMA_PSX
	if( !Lev.lines && !psz->tertomb )
		fxg_prepare_lines();
	// The original grid is freed after conversion. A missing original grid
	// and resident fixed lines identify an already prepared cache.
	const int lines_ready = Lev.lines && !psz->tertomb;
#else
	const int lines_ready = 0;
#endif
	if( !lines_ready )
		free_level();
	else {
		free( Lev.objs );
		Lev.objs = NULL;
	}

	// The constants:
	fx_input in;
	in.drsugar = Drsugar;
	in.sr = Sr;
	in.g = G;
	in.belsosav = Belsosav;
	in.elszakad = Elszakadasisebhat;
	in.merge = Talppontegybeolvadasitav;
	in.fejsugar = Fejsugar;
	in.objsugar = Objektumsugar;
	in.ugroturelem = Ugroturelem;
	in.kord2x = Kord2x;
	in.kord2y = Kord2y;
	in.kord4x = Kord4x;
	in.kord4y = Kord4y;
	in.kord5y = Kord5y;
	in.pi = K_pi;
	const kor* k[3] = { &Pmot1->kor1, &Pmot1->kor2, &Pmot1->kor4 };
	for( int i = 0; i < 3; i++ ) {
		in.kor_m[i] = k[i]->m;
		in.kor_theta[i] = k[i]->theta;
		in.kor_sugar[i] = k[i]->sugar;
	}
	// avnormegys of vezeto_hatarolas:
	vekt2 av( 0.14-(-0.35), 0.36-(0.13) );
	vekt2 avnormegys = egys( vekt2( -av.y, av.x ) );
	in.avn_x = avnormegys.x;
	in.avn_y = avnormegys.y;
	fx_params( &Param, &in );

	if( !lines_ready )
		build_lines( psz );

	// The objects (utkozikesprite stops at the first empty place):
	int nobj = 0;
	while( nobj < MAXKEREK && Ptop->kerektomb[nobj] )
		nobj++;
	Lev.nobjs = nobj;
	Lev.objs = (fx_obj*)malloc( sizeof( fx_obj )*(nobj > 0 ? nobj : 1) );
	if( !Lev.objs )
		hiba( "Not enough memory for collision objects!" );
	for( int i = 0; i < nobj; i++ ) {
		kerek* pker = Ptop->kerektomb[i];
		Lev.objs[i].r.x = fx_d2q( pker->r.x, 40 );
		Lev.objs[i].r.y = fx_d2q( pker->r.y, 40 );
		Lev.objs[i].aktiv = &pker->aktiv;
		Lev.objs[i].tipus = pker->tipus;
	}

	// ecset::kilogna: x = (r.x - 320/48 - origo.x)*48 must be at least 20
	// and floor( x ) + 639 at most maxx - 20, the same for y with 240, 479:
	const double arany = 48.0;
	ecset* pe = Pecsetalso;
	Lev.kill_x1 = fx_d2q( pe->eredetiorigo.x+(320.0+20.0)/arany, 40 );
	Lev.kill_x2 = fx_d2q( pe->eredetiorigo.x+(pe->eredetimaxx-658+320.0)/arany, 40 );
	Lev.kill_y1 = fx_d2q( pe->eredetiorigo.y+(240.0+20.0)/arany, 40 );
	Lev.kill_y2 = fx_d2q( pe->eredetiorigo.y+(pe->eredetisorszam-498+240.0)/arany, 40 );
	Level_ready = 1;
}

} // namespace

void fxg_unload_level( void ) {
	free_level();
	Level_ready = 0;
}

#ifdef ELMA_PSX
void fxg_prepare_lines( void ) {
	// Compact the temporary double-precision collision grid before the
	// renderer allocates the level's instances and sprites.
	if( !Pszak ) return;
	if( !Lev.lines && !Pszak->tertomb ) {
		void gv_menu_picture_free();
		void gv_menu_images_free();
		gv_menu_picture_free();
		gv_menu_images_free();
		Pszak->rendez( Fejsugar > Pmot1->kor2.sugar ? Fejsugar : Pmot1->kor2.sugar );
	}
	if( Pszak->tertomb ) {
		free_level();
		build_lines( Pszak );
		Level_ready = 0;
	}
}
#endif

void fxg_resetleptet( motorst* pmot ) {
#ifdef ELMA_PSX
	// Play and replay restart their stopwatch after resetleptet, so any
	// collision cache evicted for the menus is rebuilt outside playing time.
	if( Pszak && !Lev.lines && !Pszak->tertomb )
		fxg_prepare_lines();
#endif
	Racsonkivul = 0;
	pmot->voltfek = 0;
	pmot->dfek2 = pmot->dfek4 = 0;
	pmot->ugrasban1 = pmot->ugrasban2 = 0;
	pmot->ugras1kezd = pmot->ugras2kezd = -1.0;
	pmot->kezdoomega1 = pmot->kezdoomega2 = -1.0;
	slot* s = find_slot( pmot );
	s->imported = 0;
	// The level may be new:
	Level_ready = 0;
}

void fxg_reimport( motorst* pmot ) {
	find_slot( pmot )->imported = 0;
}

void fxg_leptet( motorst* pmot, double most, double dt, int gaz, int fek,
				 int ugrik1, int ugrik2 ) {
	if( !Level_ready )
		build_level();
	slot* s = find_slot( pmot );
	if( !s->imported )
		import( s, 1 );
	else if( changed( s ) )
		// The game moved the bike (Flag Tag):
		import( s, 0 );
	fx_bike* b = &s->b;
	b->racs = 0;
	fx_leptet( b, &Lev, &Param, most, dt, gaz, fek, ugrik1, ugrik2,
			   pmot->hatra_f, pmot->gravirany );
	if( b->racs )
		Racsonkivul = 1;
	export_state( s );
	Maxsurlodas_last = fx_q2d( b->maxsurl, 40 );
	// The bumps of the wheels (talppontigazitas):
	for( int i = 0; i < b->nbump; i++ ) {
		double ero = fx_q2d( b->bump[i], 40 );
		ero = ero/0.8*0.1;
		if( ero >= 0.99 )
			ero = 0.99;
		startwavegyujto( WAV_UTODES, ero, -1 );
	}
}

int fxg_vizsgalat( motorst* pmot ) {
	if( !Level_ready )
		build_level();
	slot* s = find_slot( pmot );
	fx_bike* b = &s->b;
	b->racs = 0;
	int fejutkozik = fx_fejutkozik( b, &Lev, &Param );
	int racsonkivul = Racsonkivul || b->racs;
	Racsonkivul = 0;
	if( fejutkozik )
		return 0;
	if( racsonkivul || fx_kilogna( &Lev, b->k[0].r ) )
		return 0;

	// The objects (as LEPTET.CPP):
	int skipcel = !Single && Tag;
	int voltkaja = 1;
	while( voltkaja ) {
		voltkaja = 0;
		int sorszamtomb[3];
		sorszamtomb[0] = fx_utkozikesprite( &Lev, &Param, b->k[1].r, Param.sugar[1], skipcel );
		sorszamtomb[1] = fx_utkozikesprite( &Lev, &Param, b->k[2].r, Param.sugar[2], skipcel );
		sorszamtomb[2] = fx_utkozikesprite( &Lev, &Param, b->fej, Param.fejsugar, skipcel );
		for( int i = 0; i < 3; i++ ) {
			if( sorszamtomb[i] >= 0 ) {
				startwavegyujto( 0, 0.0, sorszamtomb[i] );
				kerek* pker = Ptop->getptrkerek( sorszamtomb[i] );
				if( pker->tipus == T_KAJA ) {
					pker->aktiv = 0;
					voltkaja = 1;
				}
			}
		}
	}
	return 2;
}

double fxg_kiszamolsurlodast( void ) {
	return Maxsurlodas_last;
}
