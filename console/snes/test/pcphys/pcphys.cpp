// The rest of the original game that its physics sources call, copied from
// ADATOK.CPP (initadatok, initmotor), TOPOL.CPP (killerekelore,
// setallaktiv), ECSET.CPP (kilogna), LOAD.CPP (the grid of the lines) and
// LEJATSZO.CPP (belsoresz, spritefeldolgoz), for one player.
#include "all.h"
#include "pcphys.h"

double K_pi = 3.141592653589793;
double K_pip2 = 3.141592653589793/2.0;

// ADATOK.CPP:
motorst Motorst1;
motorst* Pmot1 = &Motorst1;
motorst* Pmot2 = &Motorst1;
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

void hiba( const char* a, const char* b, const char* c ) {
	fprintf( stderr, "hiba: %s %s %s\n", a, b ? b : "", c ? c : "" );
	exit( 1 );
}

void uzenet( const char* a, const char* b, const char* c ) {
	hiba( a, b, c );
}

static void initmotor( motorst* pmot ) {
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

// TOPOL.CPP:
kerek* topol::getptrkerek( int index ) {
	if( index < 0 || index >= MAXKEREK || !kerektomb[index] )
		hiba( "getptrkerek" );
	return kerektomb[index];
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
				vekt2 diff = pker->r - pmot->kor2.r;
				pmot->kor1.r = pmot->kor1.r + diff;
				pmot->kor2.r = pmot->kor2.r + diff;
				pmot->kor4.r = pmot->kor4.r + diff;
				pmot->vezetor = pmot->vezetor + diff;
			}
		}
	}
	return kajaszam;
}

// ECSET.CPP:
static void meghelyez( double* pd, double arany ) {
	int pixel = *pd * arany;
	*pd = (pixel+0.5)/arany;
}

#define EREDETIARANY (48.0)
#define ECSETSZEL (20)

void ecset::getorigoandsize( void ) {
	Pszak->felsorolasresetszak();
	vonal* psz = Pszak->getnextszak();
	double minx = psz->r.x;
	double maxx = psz->r.x;
	double miny = psz->r.y;
	double maxy = psz->r.y;
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
	eredetiorigo = vekt2( minx-10000/EREDETIARANY, miny-1000/EREDETIARANY );
	meghelyez( &eredetiorigo.x, EREDETIARANY );
	meghelyez( &eredetiorigo.y, EREDETIARANY );
	eredetimaxx = ((maxx+10000/EREDETIARANY)-eredetiorigo.x)*EREDETIARANY;
	eredetisorszam = ((maxy+1000/EREDETIARANY)-eredetiorigo.y)*EREDETIARANY;
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

// RECORDER.CPP: the sounds and objects of a step, in order.
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

static int getwavegyujto( int* pw, double* ph, int* po ) {
	if( Begyujtve == 0 )
		return 0;
	*pw = Azonosito[0];
	*ph = Hangero[0];
	*po = Objszam[0];
	Begyujtve--;
	for( int i = 0; i < Begyujtve; i++ ) {
		Azonosito[i] = Azonosito[i+1];
		Hangero[i] = Hangero[i+1];
		Objszam[i] = Objszam[i+1];
	}
	return 1;
}

// The level, as levdump.py wrote it:
static topol Top;
static ecset Ecset;
static kerek Kerekek[MAXKEREK];
static gyuru Gyuruk[MAXGYURU];
static int Kajakell;
static double Eddig, Utolsougras;
static int Meghalt;

double pc_friction, pc_bump, pc_time;
int pc_eaten, pc_nobjs;
int pc_obj_type[52], pc_obj_active[52];

int pc_load( const char* path ) {
	FILE* f = fopen( path, "r" );
	if( !f )
		return 0;
	int npoly, nobj;
	if( fscanf( f, "%d %d", &npoly, &nobj ) != 2 || npoly > MAXGYURU || nobj > MAXKEREK )
		return 0;
	memset( &Top, 0, sizeof( Top ) );
	for( int i = 0; i < npoly; i++ ) {
		gyuru* g = &Gyuruk[i];
		if( fscanf( f, "%d %d", &g->koveto, &g->pontszam ) != 2 )
			return 0;
		g->ponttomb = new vekt2[g->pontszam];
		for( int j = 0; j < g->pontszam; j++ )
			// The file has y pointing down, as the game's polygons:
			if( fscanf( f, "%lf %lf", &g->ponttomb[j].x, &g->ponttomb[j].y ) != 2 )
				return 0;
		Top.ptomb[i] = g;
	}
	for( int i = 0; i < nobj; i++ ) {
		kerek* k = &Kerekek[i];
		// Objects with y pointing up (after kereklefejjel):
		if( fscanf( f, "%d %lf %lf %d %d", &k->tipus, &k->r.x, &k->r.y,
					&k->kajatipus, &k->foodsorszam ) != 5 )
			return 0;
		Top.kerektomb[i] = k;
	}
	fclose( f );
	Ptop = &Top;
	initadatok();
	Ptop->killerekelore();
	if( Pszak )
		delete Pszak;
	Pszak = new szakaszok( Ptop );
	if( Fejsugar > Pmot1->kor2.sugar )
		Pszak->rendez( Fejsugar );
	else
		Pszak->rendez( Pmot1->kor2.sugar );
	Pecsetalso = &Ecset;
	Ecset.getorigoandsize();
	pc_nobjs = nobj;
	pc_reset();
	return 1;
}

void pc_reset( void ) {
	initadatok();
	Kajakell = Ptop->setallaktiv( Pmot1 );
	resetleptet( Pmot1 );
	szamitfejr( Pmot1 );
	Pmot1->kajaszam = 0;
	Begyujtve = 0;
	Eddig = 0.0;
	Utolsougras = -100.0;
	Meghalt = 0;
	pc_time = 0;
	for( int i = 0; i < pc_nobjs; i++ ) {
		pc_obj_type[i] = Ptop->kerektomb[i]->tipus;
		pc_obj_active[i] = Ptop->kerektomb[i]->aktiv;
	}
}

// LEJATSZO.CPP spritefeldolgoz: 0 dead, 1 finished, 2 nothing.
static int spritefeldolgoz( int sorszam, int* pkajaszam, motorst* pmot ) {
	int tipus = Ptop->kerektomb[sorszam]->tipus;
	if( tipus == T_HALALOS )
		return 0;
	if( tipus == T_KAJA ) {
		Ptop->kerektomb[sorszam]->aktiv = 0;
		(*pkajaszam)++;
		switch( Ptop->kerektomb[sorszam]->kajatipus ) {
			case KT_UP: pmot->gravirany = 0; break;
			case KT_DOWN: pmot->gravirany = 1; break;
			case KT_LEFT: pmot->gravirany = 2; break;
			case KT_RIGHT: pmot->gravirany = 3; break;
		}
		pc_eaten = sorszam;
		return 3;
	}
	if( tipus == T_CEL ) {
		if( Pmot1->kajaszam >= Kajakell )
			return 1;
	}
	return 2;
}

// LEJATSZO.CPP belsoresz:
int pc_step( int input, double dt ) {
	int ev = 0;
	int ugrik1 = 0, ugrik2 = 0;
	if( Eddig > Utolsougras + Ugroturelem ) {
		if( input & 4 ) {
			ugrik1 = 1;
			Utolsougras = Eddig;
		}
		if( input & 8 ) {
			ugrik2 = 1;
			Utolsougras = Eddig;
		}
	}
	pc_bump = 0;
	Begyujtve = 0;
	leptet( Pmot1, Eddig, dt, input & 1, (input & 2) != 0, ugrik1, ugrik2 );
	int eredmeny = vizsgalat( Pmot1 );
	pc_friction = kiszamolsurlodast();
	if( eredmeny == 0 ) {
		Eddig += dt;
		pc_time = Eddig;
		return 1;
	}
	int meghalt = 0, megvan = 0;
	int w;
	double h;
	int o;
	while( getwavegyujto( &w, &h, &o ) ) {
		if( o >= 0 ) {
			int e = spritefeldolgoz( o, &Pmot1->kajaszam, Pmot1 );
			if( e == 0 )
				meghalt = 1;
			if( e == 1 )
				megvan = 1;
			if( e == 3 )
				ev |= 4;
		}
		else if( w == WAV_UTODES ) {
			ev |= 8;
			if( h > pc_bump )
				pc_bump = h;
		}
	}
	for( int i = 0; i < pc_nobjs; i++ )
		pc_obj_active[i] = Ptop->kerektomb[i]->aktiv;
	Eddig += dt;
	pc_time = Eddig;
	// The game ends with the time if the flower was reached, even if a
	// killer was touched in the same step:
	if( megvan )
		return ev | 2;
	if( meghalt )
		return ev | 1;
	return ev;
}

void pc_turn( void ) {
	Pmot1->hatra_f = !Pmot1->hatra_f;
	szamitfejr( Pmot1 );
}

static void getc( const kor* k, pc_circle* c ) {
	c->r.x = k->r.x; c->r.y = k->r.y;
	c->v.x = k->v.x; c->v.y = k->v.y;
	c->alfa = k->alfa; c->omega = k->omega;
}

static void setc( kor* k, const pc_circle* c ) {
	k->r = vekt2( c->r.x, c->r.y );
	k->v = vekt2( c->v.x, c->v.y );
	k->alfa = c->alfa; k->omega = c->omega;
}

void pc_get( pc_state* s ) {
	getc( &Pmot1->kor1, &s->c[0] );
	getc( &Pmot1->kor2, &s->c[1] );
	getc( &Pmot1->kor4, &s->c[2] );
	s->rider_r.x = Pmot1->vezetor.x; s->rider_r.y = Pmot1->vezetor.y;
	s->rider_v.x = Pmot1->vezetov.x; s->rider_v.y = Pmot1->vezetov.y;
	s->head.x = Pmot1->fejr.x; s->head.y = Pmot1->fejr.y;
	s->turned = Pmot1->hatra_f;
	s->gravity = Pmot1->gravirany;
	s->apples = Pmot1->kajaszam;
}

void pc_set( const pc_state* s ) {
	setc( &Pmot1->kor1, &s->c[0] );
	setc( &Pmot1->kor2, &s->c[1] );
	setc( &Pmot1->kor4, &s->c[2] );
	Pmot1->vezetor = vekt2( s->rider_r.x, s->rider_r.y );
	Pmot1->vezetov = vekt2( s->rider_v.x, s->rider_v.y );
	Pmot1->hatra_f = s->turned;
	Pmot1->gravirany = s->gravity;
	szamitfejr( Pmot1 );
}
