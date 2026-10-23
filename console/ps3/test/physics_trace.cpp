// Original double engine trajectory fixture. No fixed point implementation.
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
// Fixtures use explicit absolute paths and do not link the game filesystem.
#ifdef fopen
#undef fopen
#endif
#include <string>
#include <vector>
#include <algorithm>



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

void initadatok( void ) {
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
	leptet( pmot, eddig, dt, gaz, fek, ugrik1, ugrik2 );
	eredmeny = vizsgalat( pmot );
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

// Canonical integer representations make a trace independent of native byte
// order, structure padding, printf rounding and the width of long.
static FILE* Trace;
static void number(double d) { uint64_t bits; memcpy(&bits,&d,8); fprintf(Trace," %016llx",(unsigned long long)bits); }
static void vec(const vekt2& v) { number(v.x);number(v.y); }
static void trace(engine& e,int step,double t) {
    motorst& m=*e.pmot;
    fprintf(Trace,"%d",step);number(t);
    const kor* circles[]={&m.kor1,&m.kor2,&m.kor4};
    for(int i=0;i<3;++i) { const kor& k=*circles[i];number(k.alfa);number(k.omega);number(k.sugar);number(k.m);number(k.theta);vec(k.r);vec(k.v); }
    vec(m.fejr);vec(m.vezetor);vec(m.vezetov);
    number(m.dfek2);number(m.dfek4);number(m.ugras1kezd);number(m.ugras2kezd);number(m.kezdoomega1);number(m.kezdoomega2);number(e.utolsougras);
    fprintf(Trace," %d %d %d %d %d %d %d %d %d %ld",m.hatra_f,m.hatra_h,m.gravirany,m.kajaszam,m.voltfek,m.ugrasban1,m.ugrasban2,e.dead,e.finished,e.megvanido);
    for(int i=0;i<Nobj;++i) fprintf(Trace," %d",e.aktiv[i]);
    fprintf(Trace,"\n");
}
static int run_case(const char* level,const char* script,double fps) {
    if(!load(level)) return 0;
    engine e={};e.name="original";e.pmot=Pmot1;
    Kajakell=Ptop->setallaktiv(e.pmot);eng_reset(&e);
    std::vector<item> items=parse(script);
    std::vector<double> starts;double total=0;
    for(size_t i=0;i<items.size();++i) { starts.push_back(total);total+=items[i].n*0.0055; }
    double t=0,cel=0;size_t cur=0,turned=0;int step=0;
    trace(e,step++,t);
    while(t<total && !e.dead && !e.finished) {
        cel=fps>0 ? cel+0.4368/fps : t+0.0055;
        while(t<=cel-0.000001) {
            double dt=std::min(0.0055,cel-t);
            while(cur+1<items.size() && starts[cur+1]<=t+1e-12) ++cur;
            eng_step(&e,items[cur].in,t,dt);t+=dt;trace(e,step++,t);
            if(e.dead || e.finished) break;
        }
        // Match LEJATSZO.CPP: turn is processed after all physics steps
        // of the frame, including when a script boundary falls mid-frame.
        while(turned<items.size() && starts[turned]<=t+1e-12) {
            if(items[turned].turn) eng_turn(&e);
            ++turned;
        }
    }
    fprintf(Trace,"result %d %d %ld\n",e.dead,e.finished,e.megvanido);
    for(size_t i=0;i<e.events.size();++i) { fprintf(Trace,"event %d %d",e.events[i].type,e.events[i].obj);number(e.events[i].t);fprintf(Trace,"\n"); }
    delete Pszak;Pszak=NULL;
    for(int i=0;i<MAXGYURU;++i) if(Top->ptomb[i]) { delete[] Top->ptomb[i]->ponttomb;free(Top->ptomb[i]); }
    for(int i=0;i<MAXKEREK;++i) free(Top->kerektomb[i]);
    free(Top);free(Ecset);return 1;
}
int main(int argc,char** argv) {
#ifdef ELMA_PS3
    const char* cases="/dev_hdd0/game/ELMAC0001/USRDIR/physics-cases.txt";
    const char* output="/dev_hdd0/game/ELMAC0001/USRDIR/physics-trace.txt";
#else
    if(argc!=3) { fprintf(stderr,"usage: physics-trace CASES OUTPUT\n");return 2; }
    const char* cases=argv[1];const char* output=argv[2];
#endif
    FILE* f=fopen(cases,"r");Trace=fopen(output,"w");if(!f || !Trace) return 2;
    char line[32768],level[1024];double fps;int n,index=0;
    while(fgets(line,sizeof(line),f)) {
        if(line[0]=='#' || line[0]=='\n') continue;
        if(sscanf(line,"%1023s %lf %n",level,&fps,&n)!=2) return 3;
        fprintf(Trace,"case %d\n",index++);
        if(!run_case(level,line+n,fps)) return 4;
        fflush(Trace);
    }
    fprintf(Trace,"complete %d\n",index);fclose(Trace);fclose(f);return 0;
}
