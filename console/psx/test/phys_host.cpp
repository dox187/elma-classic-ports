// Host fidelity test of the fixed point physics of the PlayStation
// (src/phys/): runs the original double physics of the game (LEPTET.CPP,
// BEALLIT.CPP, UTKOZES.CPP, UTKOZES2.CPP, SZAKASZ.CPP, VEKT2.CPP, compiled
// unchanged) and the fixed point physics with the same keys on the same
// level, side by side, and tells how far apart the bikes get over time and
// when the events (apples, flower, death) come. Built and run by
// test/phys_test.py.
//
//   phys_host LEVEL.txt "SCRIPT" [options]      one run, a line every 0.25 s
//   phys_host -f CASES [options]                 a summary line for each case
//   phys_host LEVEL.txt --search [--dt D]        a script that finishes the level
//                                                with the original physics
//
// LEVEL.txt is written by test/phys_levels.py. A script is items of keys
// and a number of steps: G gas, B brake, R right volt, L left volt, N
// nothing, T turn (at the start of the item), e.g. "G200 NT1 G150 R1 G60".
// CASES has "LEVEL.txt SCRIPT" on each line (# comments).
//
// Options:
//   --script-dt D  game time of a step of the script (0.0055; the scripts of
//                  the SNES version have 0.4368/80)
//   --fps F        frames a second of the game loop: each frame ends with a
//                  shorter step, as LEJATSZO.CPP lejatszo; 0 (default) gives
//                  whole steps
//   --dt D         the step of the game loop (0.0055, as the game)
//   --every S      seconds between the lines of one run (0.25), -v all steps
//   --dump FROM N  the state of both bikes after N steps from step FROM
//   --sync STEP    the fixed bike takes the original's state before STEP
//   --sync-all     that before every step, printing one-step errors
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
#include <string>
#include <vector>
#include <algorithm>

#include "phys/phys_glue.h"

// ---------------------------------------------------------------------------
// What the physics sources need of the rest of the game: ADATOK.CPP,
// KOZOS.CPP, LEJATSZO.CPP, TOPOL.CPP, ECSET.CPP, RECORDER.CPP, as there.

double K_pi = 3.141592;
double K_pip2 = K_pi*0.5;
double K_2pi = K_pi*2.0;

motorst Motorst1, Motorst2;
motorst *Pmot1 = &Motorst1, *Pmot2 = &Motorst2;
double Elszakadasisebhat, Belsosav, G;
double Talppontegybeolvadasitav;
double Ugrassebesseg1, Ugrassebesseg2;
double Ugroturelem;
double Vegenvaras;
double Drsugar, Drtang, Sr;
double Fejsugar;
double Objektumsugar = 0.4;
double Spritemaxsugar, Ketmaxsugar;
double Fejkerektavnegyzet = 1.0;
double Fekegyutthato;
double Kord2x, Kord2y, Kord4x, Kord4y, Kord5y;
int Single = 1, Tag = 0;
topol* Ptop = NULL;
ecset* Pecsetalso = NULL;
vekt2 Kezdetihelydiff;

void hiba( char* a, char* b, char* c ) {
	fprintf( stderr, "hiba: %s %s %s\n", a, b ? b : "", c ? c : "" );
	exit( 3 );
}

void uzenet( char* a, char* b, char* c ) {
	hiba( a, b, c );
}

static void initmotor( motorst* pmot ) {
	memset( pmot, 0, sizeof( *pmot ) );
	pmot->hatra_f = 0;
	pmot->hatra_h = 0;
	pmot->gravirany = 1;
	pmot->voltfek = 0;
	pmot->kor1.alfa = 0.0;
	pmot->kor1.omega = 0.0;
	pmot->kor1.sugar = 0.3;
	pmot->kor1.m = 200;
	pmot->kor1.theta = 200.0*0.55*0.55;
	pmot->kor1.r = vekt2( 2.75, 3.6 );
	pmot->kor1.v = vekt2( 0, 0 );
	pmot->kor2.alfa = 0.0;
	pmot->kor2.omega = 0.0;
	pmot->kor2.sugar = 0.4;
	pmot->kor2.m = 10;
	pmot->kor2.theta = 0.32;
	pmot->kor2.r = vekt2( 1.9, 3.0 );
	pmot->kor2.v = vekt2( 0, 0 );
	pmot->kor4.alfa = 0.0;
	pmot->kor4.omega = 0.0;
	pmot->kor4.sugar = 0.4;
	pmot->kor4.m = 10;
	pmot->kor4.theta = 0.32;
	pmot->kor4.r = vekt2( 3.6, 3.0 );
	pmot->kor4.v = vekt2( 0, 0 );
	pmot->vezetor = vekt2( 2.75, 4.04 );
	pmot->vezetov = vekt2( 0.0, 0.0 );
}

static void initadatok( void ) {
	initmotor( Pmot1 );
	initmotor( Pmot2 );
	Fekegyutthato = 100.0;
	Elszakadasisebhat = 0.01;
	Belsosav = 0.005;
	G = 10.0;
	Talppontegybeolvadasitav = 0.1;
	Ugrassebesseg1 = 5;
	Ugrassebesseg2 = 5;
	Ugroturelem = 0.4;
	Vegenvaras = 1.0;
	Drsugar = 10000.0;
	Drtang = 10000.0;
	Sr = 1000.0;
	Fejsugar = 0.238;
	Spritemaxsugar = 0.5;
	Ketmaxsugar = Spritemaxsugar + Pmot1->kor4.sugar;
	Fejkerektavnegyzet = Pmot1->kor1.sugar + Pmot1->kor2.sugar;
	Fejkerektavnegyzet = Fejkerektavnegyzet * Fejkerektavnegyzet;
	vekt2 vtmp = Pmot1->kor2.r-Pmot1->kor1.r;
	Kord2x = vtmp.x;
	Kord2y = vtmp.y;
	vtmp = Pmot1->kor4.r-Pmot1->kor1.r;
	Kord4x = vtmp.x;
	Kord4y = vtmp.y;
	Kord5y = Pmot1->vezetor.y-Pmot1->kor1.r.y;
}

int topol::setallaktiv( motorst* pmot ) {
	int kajaszam = 0;
	for( int i = 0; i < MAXKEREK; i++ ) {
		kerek* pker = kerektomb[i];
		if( pker ) {
			pker->aktiv = 1;
			if( pker->tipus == T_KAJA )
				kajaszam++;
			if( pker->tipus == T_KEZDO ) {
				pker->aktiv = 0;
				Kezdetihelydiff = pker->r - pmot->kor2.r;
				pmot->kor1.r = pmot->kor1.r + Kezdetihelydiff;
				pmot->kor2.r = pmot->kor2.r + Kezdetihelydiff;
				pmot->kor4.r = pmot->kor4.r + Kezdetihelydiff;
				pmot->vezetor = pmot->vezetor + Kezdetihelydiff;
			}
		}
	}
	return kajaszam;
}

void topol::killerekelore( void ) {
	int szam = 0;
	for( int i = 0; i < MAXKEREK; i++ )
		if( kerektomb[i] )
			szam++;
	for( int j = 0; j < szam+4; j++ ) {
		for( int i = 0; i < szam-1; i++ ) {
			int tipus1 = kerektomb[i]->tipus;
			int tipus2 = kerektomb[i+1]->tipus;
			int tip1 = 10;
			if( tipus1 == T_HALALOS ) tip1 = 1;
			if( tipus1 == T_KAJA ) tip1 = 2;
			if( tipus1 == T_CEL ) tip1 = 3;
			int tip2 = 10;
			if( tipus2 == T_HALALOS ) tip2 = 1;
			if( tipus2 == T_KAJA ) tip2 = 2;
			if( tipus2 == T_CEL ) tip2 = 3;
			if( tip1 > tip2 ) {
				kerek tmpker = *kerektomb[i];
				*kerektomb[i] = *kerektomb[i+1];
				*kerektomb[i+1] = tmpker;
			}
		}
	}
}

kerek* topol::getptrkerek( int index ) {
	if( index < 0 || index >= MAXKEREK || !kerektomb[index] )
		hiba( "topol::getptrkerek" );
	return kerektomb[index];
}

#define EREDETIARANY (48.0)
#define ECSETSZEL (20)

static void meghelyez( double* pd, double arany ) {
	int pixel = *pd * arany;
	*pd = (pixel+0.5)/arany;
}

// The part of ecset::getorigoandsize for kilogna (view false):
static void ecset_eredeti( ecset* pe ) {
	Pszak->felsorolasresetszak();
	vonal* psz = Pszak->getnextszak();
	double minx = psz->r.x, maxx = psz->r.x, miny = psz->r.y, maxy = psz->r.y;
	while( psz ) {
		if( psz->r.x < minx ) minx = psz->r.x;
		if( psz->r.x > maxx ) maxx = psz->r.x;
		if( psz->r.y < miny ) miny = psz->r.y;
		if( psz->r.y > maxy ) maxy = psz->r.y;
		if( psz->r.x+psz->v.x < minx ) minx = psz->r.x+psz->v.x;
		if( psz->r.x+psz->v.x > maxx ) maxx = psz->r.x+psz->v.x;
		if( psz->r.y+psz->v.y < miny ) miny = psz->r.y+psz->v.y;
		if( psz->r.y+psz->v.y > maxy ) maxy = psz->r.y+psz->v.y;
		psz = Pszak->getnextszak();
	}
	pe->eredetiorigo = vekt2( minx-10000/EREDETIARANY, miny-1000/EREDETIARANY );
	meghelyez( &pe->eredetiorigo.x, EREDETIARANY );
	meghelyez( &pe->eredetiorigo.y, EREDETIARANY );
	pe->eredetimaxx = ((maxx+10000/EREDETIARANY)-pe->eredetiorigo.x)*EREDETIARANY;
	pe->eredetisorszam = ((maxy+1000/EREDETIARANY)-pe->eredetiorigo.y)*EREDETIARANY;
}

int ecset::kilogna( vekt2 r ) {
	double x = (r.x - 320.0/EREDETIARANY - eredetiorigo.x)*EREDETIARANY;
	double y = (r.y - 240.0/EREDETIARANY - eredetiorigo.y)*EREDETIARANY;
	if( x < ECSETSZEL || y < ECSETSZEL )
		return 1;
	if( floor( x ) + 639 > eredetimaxx-ECSETSZEL )
		return 1;
	if( floor( y ) + 479 > eredetisorszam-ECSETSZEL )
		return 1;
	return 0;
}

#define GYUJTODARAB (200)
static int Begyujtve = 0;
static int Azonosito[GYUJTODARAB];
static double Hangero[GYUJTODARAB];
static int Objszam[GYUJTODARAB];

void startwavegyujto( int wavazonosito, double hangero, int objszam ) {
	if( Begyujtve < GYUJTODARAB ) {
		Azonosito[Begyujtve] = wavazonosito;
		Hangero[Begyujtve] = hangero;
		Objszam[Begyujtve] = objszam;
		Begyujtve++;
	}
}

// ---------------------------------------------------------------------------
// The level

static topol* Top;
static ecset* Ecset;
static int Nobj, Kajakell;
static std::string Levname;

static int load( const char* path ) {
	FILE* f = fopen( path, "r" );
	if( !f ) {
		perror( path );
		return 0;
	}
	char line[256];
	Levname = "";
	if( !fgets( line, sizeof line, f ) )
		return 0;
	if( line[0] == '#' ) {
		line[strcspn( line, "\n" )] = 0;
		Levname = line+2;
	}
	else
		rewind( f );
	int npoly, nobj;
	if( fscanf( f, "%d %d", &npoly, &nobj ) != 2 || npoly > MAXGYURU || nobj > MAXKEREK )
		return 0;
	Top = (topol*)calloc( 1, sizeof( topol ) );
	for( int i = 0; i < npoly; i++ ) {
		gyuru* g = (gyuru*)calloc( 1, sizeof( gyuru ) );
		if( fscanf( f, "%d %d", &g->koveto, &g->pontszam ) != 2 )
			return 0;
		g->ponttomb = new vekt2[g->pontszam];
		for( int j = 0; j < g->pontszam; j++ )
			if( fscanf( f, "%lf %lf", &g->ponttomb[j].x, &g->ponttomb[j].y ) != 2 )
				return 0;
		Top->ptomb[i] = g;
	}
	for( int i = 0; i < nobj; i++ ) {
		kerek* k = (kerek*)calloc( 1, sizeof( kerek ) );
		if( fscanf( f, "%d %lf %lf %d %d", &k->tipus, &k->r.x, &k->r.y, &k->kajatipus,
					&k->foodsorszam ) != 5 )
			return 0;
		Top->kerektomb[i] = k;
	}
	fclose( f );
	Ptop = Top;
	Nobj = nobj;
	initadatok();
	Ptop->killerekelore();
	Pszak = new szakaszok( Ptop );
	if( Fejsugar > Pmot1->kor2.sugar )
		Pszak->rendez( Fejsugar );
	else
		Pszak->rendez( Pmot1->kor2.sugar );
	Ecset = (ecset*)calloc( 1, sizeof( ecset ) );
	Pecsetalso = Ecset;
	ecset_eredeti( Ecset );
	return 1;
}

// ---------------------------------------------------------------------------
// The two engines, each with the game loop's part around the physics
// (LEJATSZO.CPP belsoresz, spritefeldolgoz, kulsoresz's turn).

enum { IN_GAS = 1, IN_BRAKE = 2, IN_VOLT_R = 4, IN_VOLT_L = 8 };

struct event {
	int type;      // 'a' apple, 'f' finish, 'd' death
	int obj;
	double t;      // game time (eddig)
};

struct engine {
	const char* name;
	int fixed;
	motorst* pmot;
	int aktiv[MAXKEREK];
	double utolsougras;
	int dead, finished;
	long megvanido;
	std::vector<event> events;
};

static void eng_reset( engine* e ) {
	e->pmot->kajaszam = 0;
	e->utolsougras = -100.0;
	e->dead = e->finished = 0;
	e->megvanido = 0;
	e->events.clear();
	if( e->fixed )
		fxg_resetleptet( e->pmot );
	else
		resetleptet( e->pmot );
	szamitfejr( e->pmot );
	for( int i = 0; i < Nobj; i++ )
		e->aktiv[i] = Ptop->kerektomb[i]->aktiv;
}

static void eng_step( engine* e, int in, double eddig, double dt ) {
	if( e->dead || e->finished )
		return;
	for( int i = 0; i < Nobj; i++ )
		Ptop->kerektomb[i]->aktiv = e->aktiv[i];
	Begyujtve = 0;
	motorst* pmot = e->pmot;
	int ugrik1 = 0, ugrik2 = 0;
	if( eddig > e->utolsougras + Ugroturelem ) {
		if( in & IN_VOLT_R ) {
			ugrik1 = 1;
			e->utolsougras = eddig;
		}
		if( in & IN_VOLT_L ) {
			ugrik2 = 1;
			e->utolsougras = eddig;
		}
	}
	int gaz = (in & IN_GAS) != 0, fek = (in & IN_BRAKE) != 0;
	int eredmeny;
	if( e->fixed ) {
		fxg_leptet( pmot, eddig, dt, gaz, fek, ugrik1, ugrik2 );
		eredmeny = fxg_vizsgalat( pmot );
	}
	else {
		leptet( pmot, eddig, dt, gaz, fek, ugrik1, ugrik2 );
		eredmeny = vizsgalat( pmot );
	}
	if( eredmeny == 0 ) {
		e->dead = 1;
		event ev = { 'd', -1, eddig };
		e->events.push_back( ev );
	}
	else {
		for( int j = 0; j < Begyujtve; j++ ) {
			int o = Objszam[j];
			if( o < 0 )
				continue;
			kerek* pker = Ptop->kerektomb[o];
			if( pker->tipus == T_HALALOS ) {
				if( !e->dead ) {
					e->dead = 1;
					event ev = { 'd', o, eddig };
					e->events.push_back( ev );
				}
			}
			else if( pker->tipus == T_KAJA ) {
				pker->aktiv = 0;
				pmot->kajaszam++;
				switch( pker->kajatipus ) {
					case KT_UP: pmot->gravirany = 0; break;
					case KT_DOWN: pmot->gravirany = 1; break;
					case KT_LEFT: pmot->gravirany = 2; break;
					case KT_RIGHT: pmot->gravirany = 3; break;
				}
				event ev = { 'a', o, eddig };
				e->events.push_back( ev );
			}
			else if( pker->tipus == T_CEL && pmot->kajaszam >= Kajakell ) {
				e->megvanido = eddig*100.0/(182.0*0.0024);
				if( !e->finished ) {
					e->finished = 1;
					event ev = { 'f', o, eddig };
					e->events.push_back( ev );
				}
			}
		}
		// The flower counts even with a killer in the same step:
		if( e->finished )
			e->dead = 0;
	}
	for( int i = 0; i < Nobj; i++ )
		e->aktiv[i] = Ptop->kerektomb[i]->aktiv;
}

static void eng_turn( engine* e ) {
	if( e->dead || e->finished )
		return;
	e->pmot->hatra_f = !e->pmot->hatra_f;
	szamitfejr( e->pmot );
}

// ---------------------------------------------------------------------------
// Scripts

struct item { int in, turn, n; };

static std::vector<item> parse( const char* p ) {
	std::vector<item> out;
	while( *p ) {
		while( *p == ' ' || *p == '\t' )
			p++;
		if( !*p || *p == '\n' || *p == '#' )
			break;
		item it = { 0, 0, 0 };
		while( *p && strchr( "GBRLTN", *p ) ) {
			switch( *p ) {
				case 'G': it.in |= IN_GAS; break;
				case 'B': it.in |= IN_BRAKE; break;
				case 'R': it.in |= IN_VOLT_R; break;
				case 'L': it.in |= IN_VOLT_L; break;
				case 'T': it.turn = 1; break;
			}
			p++;
		}
		it.n = (int)strtol( p, (char**)&p, 10 );
		if( it.n <= 0 )
			it.n = 1;
		out.push_back( it );
	}
	return out;
}

static std::string fmt_time( long hs ) {
	char buf[32];
	snprintf( buf, sizeof buf, "%02ld:%02ld:%02ld", hs/6000, (hs/100)%60, hs%100 );
	return buf;
}

static std::string events_str( const engine* e ) {
	std::string s;
	char buf[64];
	for( const event& ev : e->events ) {
		double sec = ev.t/0.4368;
		if( ev.type == 'a' )
			snprintf( buf, sizeof buf, "apple%d@%.2fs ", ev.obj, sec );
		else if( ev.type == 'f' )
			snprintf( buf, sizeof buf, "finish@%s ", fmt_time( e->megvanido ).c_str() );
		else
			snprintf( buf, sizeof buf, "dead%s@%.2fs ", ev.obj >= 0 ? "(killer)" : "", sec );
		s += buf;
	}
	if( s.empty() )
		s = "- ";
	return s;
}

struct result {
	double t1mm, t1cm, t10cm;     // seconds when the bodies got that far apart (-1 never)
	double max1, max5, maxall;    // the largest distance in the first 1 s, 5 s, all
	double within1cm;             // share of the samples within 1 cm
	int same_events;              // the same events in the same order
	double event_dt;              // the largest time difference of matching events (s)
	int steps;
};

static double dist( const vekt2& a, const vekt2& b ) {
	return hypot( a.x-b.x, a.y-b.y );
}

static double Step = 0.0055;   // the step of the game loop (LEJATSZO.CPP)

// --dump FROM N: the whole state of both bikes after these steps.
static int Dump_from = -1, Dump_n = 1;
// --sync STEP: before this step the fixed bike takes the original's state.
static int Sync_at = -1;
// --sync-all: the same before every step, and the largest change of a
// velocity in one step is printed when above 1e-6 m/s (the one-step error).
static int Sync_all = 0;

static void dump_step( int step, engine* A, engine* B ) {
	printf( "step %d\n", step );
	for( int e = 0; e < 2; e++ ) {
		motorst* m = (e ? B : A)->pmot;
		const kor* k[3] = { &m->kor1, &m->kor2, &m->kor4 };
		for( int i = 0; i < 3; i++ )
			printf( "  %s k%d r %.12f %.12f v %.12f %.12f a %.12f w %.12f\n", e ? "fixed" : "orig ",
					i, k[i]->r.x, k[i]->r.y, k[i]->v.x, k[i]->v.y, k[i]->alfa, k[i]->omega );
		printf( "  %s rider %.12f %.12f v %.12f %.12f head %.12f %.12f\n", e ? "fixed" : "orig ",
				m->vezetor.x, m->vezetor.y, m->vezetov.x, m->vezetov.y, m->fejr.x, m->fejr.y );
	}
}

static result run( const char* script, double script_dt, double fps, int verbose,
				   double every, engine* A, engine* B ) {
	std::vector<item> items = parse( script );
	// The script's timeline in game time:
	std::vector<double> start;
	double total = 0;
	for( const item& it : items ) {
		start.push_back( total );
		total += it.n*script_dt;
	}
	Kajakell = Ptop->setallaktiv( A->pmot );
	Ptop->setallaktiv( B->pmot );
	eng_reset( A );
	eng_reset( B );
	result r = { -1, -1, -1, 0, 0, 0, 0, 1, 0, 0 };
	int samples = 0, near = 0;
	double eddig = 0.0;
	double frame = fps > 0 ? 0.4368/fps : Step;
	double cel = 0.0;
	size_t cur = 0, turned = 0;
	double next_line = every;
	if( verbose )
		printf( "   time  body x orig/fixed       body y orig/fixed     body d   wheel d   angle d\n" );
	while( eddig < total ) {
		if( fps > 0 )
			cel += frame;
		else
			cel = eddig+Step;
		if( cel < 0.000001 )
			cel = 0.000001;
		while( eddig <= cel-0.000001 ) {
			double dt = Step;
			if( eddig+dt > cel )
				dt = cel-eddig;
			while( cur+1 < items.size() && start[cur+1] <= eddig+1e-12 )
				cur++;
			int in = items[cur].in;
			if( r.steps == Sync_at || Sync_all ) {
				// The fixed bike from the state of the original (it is read
				// again because the fields changed):
				*B->pmot = *A->pmot;
				memcpy( B->aktiv, A->aktiv, sizeof( B->aktiv ) );
				fxg_reimport( B->pmot );
			}
			eng_step( A, in, eddig, dt );
			eng_step( B, in, eddig, dt );
			if( Sync_all ) {
				const kor* ka[3] = { &A->pmot->kor1, &A->pmot->kor2, &A->pmot->kor4 };
				const kor* kb[3] = { &B->pmot->kor1, &B->pmot->kor2, &B->pmot->kor4 };
				double worst = 0;
				int wi = 0;
				for( int i = 0; i < 3; i++ ) {
					double d = dist( ka[i]->v, kb[i]->v );
					if( d > worst ) {
						worst = d;
						wi = i;
					}
				}
				if( worst > 1e-6 )
					printf( "step %d: one-step velocity error %.3g m/s of circle %d\n", r.steps,
							worst, wi );
			}
			if( Dump_from >= 0 && r.steps >= Dump_from && r.steps < Dump_from+Dump_n )
				dump_step( r.steps, A, B );
			r.steps++;
			eddig += dt;
			if( !A->dead && !A->finished && !B->dead && !B->finished ) {
				double d = dist( A->pmot->kor1.r, B->pmot->kor1.r );
				double sec = eddig/0.4368;
				samples++;
				if( d < 0.01 )
					near++;
				if( d >= 0.001 && r.t1mm < 0 ) r.t1mm = sec;
				if( d >= 0.01 && r.t1cm < 0 ) r.t1cm = sec;
				if( d >= 0.1 && r.t10cm < 0 ) r.t10cm = sec;
				if( sec <= 1.0 && d > r.max1 ) r.max1 = d;
				if( sec <= 5.0 && d > r.max5 ) r.max5 = d;
				if( d > r.maxall ) r.maxall = d;
				if( verbose > 1 || (verbose && sec >= next_line) ) {
					next_line += every;
					double wd = fmax( dist( A->pmot->kor2.r, B->pmot->kor2.r ),
									  dist( A->pmot->kor4.r, B->pmot->kor4.r ) );
					double ad = A->pmot->kor1.alfa-B->pmot->kor1.alfa;
					printf( "%7.2f %9.4f %9.4f  %9.4f %9.4f  %9.6f %9.6f %9.6f\n", sec,
							A->pmot->kor1.r.x, B->pmot->kor1.r.x, A->pmot->kor1.r.y,
							B->pmot->kor1.r.y, d, wd, ad );
				}
			}
			if( (A->dead || A->finished) && (B->dead || B->finished) )
				break;
		}
		if( (A->dead || A->finished) && (B->dead || B->finished) )
			break;
		// The turn key (kulsoresz, after the steps of the frame):
		while( turned < items.size() && start[turned] <= eddig+1e-12 ) {
			if( items[turned].turn ) {
				eng_turn( A );
				eng_turn( B );
			}
			turned++;
		}
	}
	r.within1cm = samples ? (double)near/samples : 1.0;
	if( A->events.size() != B->events.size() )
		r.same_events = 0;
	for( size_t i = 0; i < A->events.size() && i < B->events.size(); i++ ) {
		const event& a = A->events[i];
		const event& b = B->events[i];
		if( a.type != b.type || a.obj != b.obj )
			r.same_events = 0;
		double dt = fabs( a.t-b.t )/0.4368;
		if( dt > r.event_dt )
			r.event_dt = dt;
	}
	return r;
}

static void summary( const char* lev, const char* script, const result& r, engine* A,
					 engine* B ) {
	printf( "%s (%s): %s\n", lev, Levname.c_str(), script );
	printf( "   orig:  %s\n   fixed: %s\n", events_str( A ).c_str(), events_str( B ).c_str() );
	printf( "   events %s (largest time difference %.3f s); apart 1 mm %.2f s, 1 cm %.2f s, "
			"10 cm %.2f s; largest %.4f/%.4f/%.4f m (1 s/5 s/all); %.1f%% within 1 cm\n",
			r.same_events ? "SAME" : "DIFFERENT", r.event_dt, r.t1mm, r.t1cm, r.t10cm, r.max1,
			r.max5, r.maxall, 100.0*r.within1cm );
}

// ---------------------------------------------------------------------------
// Search of a script that finishes the level with the original physics in
// whole steps (--search): a beam search over segments of keys, each run from
// the saved state of its parent. The score is the apples eaten and the
// distance of the body to the nearest apple, then to the flower.

struct snode {
	motorst mot;
	int aktiv[MAXKEREK];
	double utolsougras, eddig;
	int steps, turns;
	std::string script;
	double score;
};

static double target_dist( const engine* e ) {
	double best = 1e9;
	int apples_left = 0;
	for( int i = 0; i < Nobj; i++ )
		if( e->aktiv[i] && Ptop->kerektomb[i]->tipus == T_KAJA )
			apples_left++;
	for( int i = 0; i < Nobj; i++ ) {
		kerek* k = Ptop->kerektomb[i];
		if( !e->aktiv[i] )
			continue;
		if( (apples_left && k->tipus == T_KAJA) || (!apples_left && k->tipus == T_CEL) )
			best = fmin( best, dist( e->pmot->kor1.r, k->r ) );
	}
	return best;
}

static int search( int width, int maxsteps ) {
	static const int acts[] = { 0, IN_GAS, IN_GAS | IN_VOLT_R, IN_GAS | IN_VOLT_L,
								IN_VOLT_R, IN_VOLT_L, IN_BRAKE };
	static const int durs[] = { 32, 64 };
	engine E = { "orig", 0, &Motorst1 };
	Kajakell = Ptop->setallaktiv( E.pmot );
	eng_reset( &E );
	std::vector<snode> beam( 1 );
	snode& s0 = beam[0];
	s0.mot = *E.pmot;
	memcpy( s0.aktiv, E.aktiv, sizeof( s0.aktiv ) );
	s0.utolsougras = E.utolsougras;
	s0.eddig = 0.0;
	s0.steps = 0;
	s0.turns = 0;
	s0.score = 0;
	while( !beam.empty() ) {
		std::vector<snode> next;
		for( const snode& n : beam ) {
			for( int turn = 0; turn < 2; turn++ )
			for( int a = 0; a < (int)(sizeof acts/sizeof acts[0]); a++ )
			for( int d = 0; d < (int)(sizeof durs/sizeof durs[0]); d++ ) {
				*E.pmot = n.mot;
				memcpy( E.aktiv, n.aktiv, sizeof( E.aktiv ) );
				E.utolsougras = n.utolsougras;
				E.dead = E.finished = 0;
				E.events.clear();
				double eddig = n.eddig;
				// As run: the turn of a later item comes before its first
				// step, of the first item after its first step.
				if( turn && n.steps > 0 )
					eng_turn( &E );
				for( int i = 0; i < durs[d] && !E.dead && !E.finished; i++ ) {
					eng_step( &E, acts[a], eddig, Step );
					eddig += Step;
					if( turn && n.steps == 0 && i == 0 )
						eng_turn( &E );
				}
				if( E.dead )
					continue;
				char buf[32];
				static const char* names[] = { "N", "G", "GR", "GL", "R", "L", "B" };
				snprintf( buf, sizeof buf, "%s%s%d ", names[a], turn ? "T" : "", durs[d] );
				std::string script = n.script+buf;
				if( E.finished ) {
					printf( "found %s in %s\nscript %s\n", events_str( &E ).c_str(),
							fmt_time( E.megvanido ).c_str(), script.c_str() );
					return 0;
				}
				snode c;
				c.mot = *E.pmot;
				memcpy( c.aktiv, E.aktiv, sizeof( c.aktiv ) );
				c.utolsougras = E.utolsougras;
				c.eddig = eddig;
				c.steps = n.steps+durs[d];
				c.turns = n.turns+turn;
				c.script = script;
				int eaten = 0;
				for( int i = 0; i < Nobj; i++ )
					if( !c.aktiv[i] && Ptop->kerektomb[i]->tipus == T_KAJA )
						eaten++;
				// Progress, a little against long scripts and turns:
				c.score = eaten*1000.0-target_dist( &E )-0.001*c.steps-0.5*c.turns;
				if( c.steps < maxsteps )
					next.push_back( c );
			}
		}
		std::sort( next.begin(), next.end(),
				   []( const snode& a, const snode& b ) { return a.score > b.score; } );
		// One node a cell of 0.5 m and a direction:
		beam.clear();
		std::vector<long> seen;
		for( const snode& c : next ) {
			long key = (long)floor( c.mot.kor1.r.x*2 )*100000+(long)floor( c.mot.kor1.r.y*2 )*10+
					   c.mot.hatra_f*2+(c.mot.kor1.v.x > 0);
			if( std::find( seen.begin(), seen.end(), key ) != seen.end() )
				continue;
			seen.push_back( key );
			beam.push_back( c );
			if( (int)beam.size() >= width )
				break;
		}
		if( !beam.empty() )
			fprintf( stderr, "steps %d best %.3f (%zu nodes)\n", beam[0].steps, beam[0].score,
					 beam.size() );
	}
	printf( "not found\n" );
	return 1;
}

int main( int argc, char** argv ) {
	if( argc < 3 ) {
		fprintf( stderr, "usage: phys_host LEVEL.txt SCRIPT [options] | -f CASES [options]\n" );
		return 2;
	}
	double script_dt = 0.0055, fps = 0, every = 0.25;
	int verbose = 1;
	for( int i = 3; i < argc; i++ ) {
		if( !strcmp( argv[2], "--search" ) && strcmp( argv[i], "--dt" ) ) {
			fprintf( stderr, "--search takes only --dt\n" );
			return 2;
		}
		if( !strcmp( argv[i], "--script-dt" ) && i+1 < argc ) script_dt = atof( argv[++i] );
		else if( !strcmp( argv[i], "--fps" ) && i+1 < argc ) fps = atof( argv[++i] );
		else if( !strcmp( argv[i], "--dt" ) && i+1 < argc ) Step = atof( argv[++i] );
		else if( !strcmp( argv[i], "--every" ) && i+1 < argc ) every = atof( argv[++i] );
		else if( !strcmp( argv[i], "-v" ) ) verbose = 2;
		else if( !strcmp( argv[i], "--sync" ) && i+1 < argc ) Sync_at = atoi( argv[++i] );
		else if( !strcmp( argv[i], "--sync-all" ) ) Sync_all = 1;
		else if( !strcmp( argv[i], "--dump" ) && i+2 < argc ) {
			Dump_from = atoi( argv[++i] );
			Dump_n = atoi( argv[++i] );
		}
		else {
			fprintf( stderr, "unknown option %s\n", argv[i] );
			return 2;
		}
	}
	engine A = { "orig", 0, &Motorst1 };
	engine B = { "fixed", 1, &Motorst2 };
	if( !strcmp( argv[1], "-f" ) ) {
		FILE* f = fopen( argv[2], "r" );
		if( !f ) {
			perror( argv[2] );
			return 2;
		}
		char line[4096];
		int cases = 0, same = 0;
		while( fgets( line, sizeof line, f ) ) {
			char* p = line;
			while( *p == ' ' ) p++;
			if( *p == '#' || *p == '\n' || !*p )
				continue;
			p[strcspn( p, "\n" )] = 0;
			char* sp = strchr( p, ' ' );
			if( !sp )
				continue;
			*sp = 0;
			if( !load( p ) )
				return 2;
			result r = run( sp+1, script_dt, fps, 0, every, &A, &B );
			summary( p, sp+1, r, &A, &B );
			cases++;
			same += r.same_events;
		}
		fclose( f );
		printf( "%d cases, %d with the same events\n", cases, same );
		return 0;
	}
	if( !load( argv[1] ) )
		return 2;
	if( !strcmp( argv[2], "--search" ) )
		return search( 60, 6000 );
	result r = run( argv[2], script_dt, fps, verbose, every, &A, &B );
	summary( argv[1], argv[2], r, &A, &B );
	return 0;
}
