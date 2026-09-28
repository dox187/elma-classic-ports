#include	"all.h"

// A gyujtemenyek nevei es sorrendje a Steam-es kiadaset koveti; palyaik
// elma.res-ben resnev01.lev, resnev02.lev, ... neven vannak, a jatekban
// pedig QWQ + kod + 001.LEV az azonositojuk:
struct gyujtemeny {
	char* nev;
	char* resnev;
	char* kod;
};

#define GYUJTEMENYSZAM (4)
static gyujtemeny Gyujtemenyek[GYUJTEMENYSZAM] = {
	{ "Tutorial", "tutorial", "TU" },
	{ "Stolen Internals by Sla", "stolen", "ST" },
	{ "Quick & Easy by Sla", "easy", "EA" },
	{ "Quick & Hard by Sla", "hard", "HA" },
};

// Menu sorai: gyujtemeny indexek, es a belso es kulso palyak:
#define EREDETI (-1)
#define KULSO (-2)
static int Sorrend[] = { 0, EREDETI, 1, 2, 3, KULSO };
#define SORSZAM (int(sizeof( Sorrend )/sizeof( Sorrend[0] )))

#define MAXGYUJTEMENYPALYA (99)
// Palya sorok hossza, hogy kiferjenek a kepre:
#define MAXPALYASORHOSSZ (28)

static void palyanev( int g, int i, char* nev ) {
	sprintf( nev, "QWQ%s%03d.LEV", Gyujtemenyek[g].kod, i+1 );
}

static void palyaresnev( int g, int i, char* nev ) {
	sprintf( nev, "%s%02d.lev", Gyujtemenyek[g].resnev, i+1 );
}

// elma.res-ben levo palyak szama gyujtemenyenkent (-1: meg nem szamoltuk):
static int Palyaszamok[GYUJTEMENYSZAM] = { -1, -1, -1, -1 };

static int gyujtemenypalyaszam( int g ) {
	if( Palyaszamok[g] < 0 ) {
		int szam = 0;
		while( szam < MAXGYUJTEMENYPALYA ) {
			char nev[30];
			palyaresnev( g, szam, nev );
			if( !qvan( nev ) )
				break;
			szam++;
		}
		Palyaszamok[g] = szam;
	}
	return Palyaszamok[g];
}

int vannakgyujtemenyek( void ) {
	for( int g = 0; g < GYUJTEMENYSZAM; g++ ) {
		if( gyujtemenypalyaszam( g ) > 0 )
			return 1;
	}
	return 0;
}

// QWQST001.LEV-bol gyujtemeny es palya index, hamis ha nem ilyen nev:
static int nevbol( char* nev, int* pg, int* pi ) {
	if( strlen( nev ) != 12 || _fstrnicmp( nev, "QWQ", 3 ) != 0 ||
		strcmpi( nev+8, ".LEV" ) != 0 )
		return 0;
	for( int k = 5; k < 8; k++ ) {
		if( !isdigit( (unsigned char)nev[k] ) )
			return 0;
	}
	for( int g = 0; g < GYUJTEMENYSZAM; g++ ) {
		if( _fstrnicmp( nev+3, Gyujtemenyek[g].kod, 2 ) != 0 )
			continue;
		int i = (nev[5]-'0')*100 + (nev[6]-'0')*10 + (nev[7]-'0') - 1;
		if( i < 0 || i >= gyujtemenypalyaszam( g ) )
			return 0;
		*pg = g;
		*pi = i;
		return 1;
	}
	return 0;
}

int gyujtemenypalya( char* nev ) {
	int g, i;
	return nevbol( nev, &g, &i );
}

void gyujtemenyresnev( char* nev, char* resnev ) {
	int g, i;
	if( !nevbol( nev, &g, &i ) )
		hiba( "gyujtemenyresnev-ben nem gyujtemeny palya!: ", nev );
	palyaresnev( g, i, resnev );
}

// GYUJTEMENYSTATE: azonosito, verzio, idok szama, titkositott idok,
// jatekosok szama, titkositott jatekosok, ellenorzo osszeg, azonosito.
struct gyujtemenyido {
	char nev[16];
	int32_t belyeg;
	palyaidok idok;
};

// Jatekosonkent es gyujtemenyenkent a teljesitett palyak. Ahogy belso
// palyaknal sikerespalyakszama, ez sem fugg attol, hogy ideje bent maradt-e
// a legjobb tiz kozott:
struct gyujtemenyjatekos {
	char nev[16];
	char gyujtemeny[16];
	char kesz[MAXGYUJTEMENYPALYA+1];
};

#define MAXGYUJTEMENYIDO (GYUJTEMENYSZAM*MAXGYUJTEMENYPALYA)
#define MAXGYUJTEMENYJATEKOS (GYUJTEMENYSZAM*MAXJATEKOS)
#define GYUJTEMENYAZON1 (5638247)
#define GYUJTEMENYAZON2 (2847563)
#define GYUJTEMENYVERZIO (2)

static gyujtemenyido* Idotabla = NULL;
static int Idoszam = 0;
static gyujtemenyjatekos* Jatekostabla = NULL;
static int Jatekosszam = 0;

static void titkosit( void* mut, int hossz ) {
	unsigned char* pc = (unsigned char*)mut;
	short a = 29, b = 8731, c = 3371;
	for( int i = 0; i < hossz; i++ ) {
		pc[i] ^= a;
		a %= c;
		b += a*c;
		a = 31*b+c;
	}
}

static uint32_t osszeg( void* mut, int hossz, uint32_t sum = 0 ) {
	unsigned char* pc = (unsigned char*)mut;
	for( int i = 0; i < hossz; i++ )
		sum = sum*31 + pc[i];
	return sum;
}

static void betoltallapot( void ) {
	if( Idotabla )
		return;
	Idotabla = new gyujtemenyido[MAXGYUJTEMENYIDO];
	Jatekostabla = new gyujtemenyjatekos[MAXGYUJTEMENYJATEKOS];
	if( !Idotabla || !Jatekostabla )
		hiba( "betoltallapot-ban memory!" );
	Idoszam = 0;
	Jatekosszam = 0;

	FILE* h = fopen( GYUJTEMENYSTATE, "rb" );
	if( !h )
		return; // Meg nem jatszott gyujtemeny palyan
	int32_t azon1 = 0, verzio = 0, idoszam = 0, jatekosszam = 0;
	int32_t ellenorzo = 0, azon2 = 0;
	int jo = fread( &azon1, 1, 4, h ) == 4 && azon1 == GYUJTEMENYAZON1 &&
			 fread( &verzio, 1, 4, h ) == 4 && verzio == GYUJTEMENYVERZIO &&
			 fread( &idoszam, 1, 4, h ) == 4 && idoszam >= 0 && idoszam <= MAXGYUJTEMENYIDO;
	int idohossz = jo ? int( idoszam*sizeof( gyujtemenyido ) ) : 0;
	jo = jo && fread( Idotabla, 1, idohossz, h ) == size_t(idohossz) &&
		 fread( &jatekosszam, 1, 4, h ) == 4 && jatekosszam >= 0 &&
		 jatekosszam <= MAXGYUJTEMENYJATEKOS;
	int jatekoshossz = jo ? int( jatekosszam*sizeof( gyujtemenyjatekos ) ) : 0;
	jo = jo && fread( Jatekostabla, 1, jatekoshossz, h ) == size_t(jatekoshossz) &&
		 fread( &ellenorzo, 1, 4, h ) == 4 &&
		 fread( &azon2, 1, 4, h ) == 4 && azon2 == GYUJTEMENYAZON2;
	fclose( h );
	if( jo ) {
		titkosit( Idotabla, idohossz );
		titkosit( Jatekostabla, jatekoshossz );
		uint32_t sum = osszeg( Jatekostabla, jatekoshossz, osszeg( Idotabla, idohossz ) );
		jo = ellenorzo == int32_t( sum & 0x7fffffff );
	}
	if( !jo ) {
		uzenet( "Corrupt file, please rename it!", GYUJTEMENYSTATE );
		idoszam = jatekosszam = 0;
	}
	Idoszam = idoszam;
	Jatekosszam = jatekosszam;
	for( int i = 0; i < Idoszam; i++ )
		Idotabla[i].nev[sizeof( Idotabla[i].nev )-1] = 0;
	for( int i = 0; i < Jatekosszam; i++ ) {
		Jatekostabla[i].nev[sizeof( Jatekostabla[i].nev )-1] = 0;
		Jatekostabla[i].gyujtemeny[sizeof( Jatekostabla[i].gyujtemeny )-1] = 0;
	}
}

static void mentallapot( void ) {
	int idohossz = int( Idoszam*sizeof( gyujtemenyido ) );
	int jatekoshossz = int( Jatekosszam*sizeof( gyujtemenyjatekos ) );
	int32_t fej[3] = { GYUJTEMENYAZON1, GYUJTEMENYVERZIO, Idoszam };
	int32_t jatekosszam = Jatekosszam;
	uint32_t sum = osszeg( Jatekostabla, jatekoshossz, osszeg( Idotabla, idohossz ) );
	int32_t ellenorzo = int32_t( sum & 0x7fffffff );
	int32_t azon2 = GYUJTEMENYAZON2;

	FILE* h = fopen( GYUJTEMENYSTATE, "wb" );
	if( !h ) {
		uzenet( "Could not open file!", GYUJTEMENYSTATE );
		return;
	}
	titkosit( Idotabla, idohossz );
	titkosit( Jatekostabla, jatekoshossz );
	int jo = fwrite( fej, 1, sizeof( fej ), h ) == sizeof( fej ) &&
			 fwrite( Idotabla, 1, idohossz, h ) == size_t(idohossz) &&
			 fwrite( &jatekosszam, 1, 4, h ) == 4 &&
			 fwrite( Jatekostabla, 1, jatekoshossz, h ) == size_t(jatekoshossz) &&
			 fwrite( &ellenorzo, 1, 4, h ) == 4 &&
			 fwrite( &azon2, 1, 4, h ) == 4;
	titkosit( Idotabla, idohossz );
	titkosit( Jatekostabla, jatekoshossz );
	if( fclose( h ) != 0 )
		jo = 0;
	if( !jo )
		uzenet( "Could not write file:", GYUJTEMENYSTATE );
}

static gyujtemenyido* keresidot( char* nev ) {
	betoltallapot();
	for( int i = 0; i < Idoszam; i++ ) {
		if( strcmpi( Idotabla[i].nev, nev ) == 0 )
			return &Idotabla[i];
	}
	return NULL;
}

void gyujtemenyidok( char* nev, long belyeg, palyaidok* pidok ) {
	gyujtemenyido* pido = keresidot( nev );
	if( pido && pido->belyeg == int32_t(belyeg) )
		*pidok = pido->idok;
	else
		memset( pidok, 0, sizeof( palyaidok ) );
}

void mentgyujtemenyidok( char* nev, long belyeg, palyaidok* pidok ) {
	gyujtemenyido* pido = keresidot( nev );
	if( !pido ) {
		if( Idoszam >= MAXGYUJTEMENYIDO || strlen( nev ) >= sizeof( pido->nev ) )
			hiba( "mentgyujtemenyidok-ben nincs hely!: ", nev );
		pido = &Idotabla[Idoszam++];
		memset( pido, 0, sizeof( gyujtemenyido ) );
		strcpy( pido->nev, nev );
	}
	pido->belyeg = int32_t(belyeg);
	pido->idok = *pidok;
	mentallapot();
}

static gyujtemenyjatekos* keresjatekost( int g, char* jatekosnev, int letrehoz ) {
	betoltallapot();
	for( int i = 0; i < Jatekosszam; i++ ) {
		if( strcmp( Jatekostabla[i].nev, jatekosnev ) == 0 &&
			strcmpi( Jatekostabla[i].gyujtemeny, Gyujtemenyek[g].resnev ) == 0 )
			return &Jatekostabla[i];
	}
	if( !letrehoz )
		return NULL;
	if( Jatekosszam >= MAXGYUJTEMENYJATEKOS )
		hiba( "keresjatekost-ban nincs hely!" );
	gyujtemenyjatekos* pj = &Jatekostabla[Jatekosszam++];
	memset( pj, 0, sizeof( gyujtemenyjatekos ) );
	strncpy( pj->nev, jatekosnev, sizeof( pj->nev )-1 );
	strncpy( pj->gyujtemeny, Gyujtemenyek[g].resnev, sizeof( pj->gyujtemeny )-1 );
	return pj;
}

// Igaz, ha jatekosnev egyedul mar teljesitette a gyujtemeny i-edik palyajat:
static int teljesitette( int g, int i, char* jatekosnev ) {
	gyujtemenyjatekos* pj = keresjatekost( g, jatekosnev, 0 );
	return pj && pj->kesz[i];
}

static void teljesitettnek( int g, int i, char* jatekosnev ) {
	gyujtemenyjatekos* pj = keresjatekost( g, jatekosnev, 1 );
	if( pj->kesz[i] )
		return;
	pj->kesz[i] = 1;
	mentallapot();
}

static int teljesitettek( int g ) {
	int db = 0;
	for( int i = 0; i < gyujtemenypalyaszam( g ); i++ ) {
		if( teljesitette( g, i, State->jatekosa ) )
			db++;
	}
	return db;
}

// Ennyi palya van meg az elejetol kezdve megszakitas nelkul:
static int elejenkeszek( int g ) {
	int db = 0;
	while( db < gyujtemenypalyaszam( g ) && teljesitette( g, db, State->jatekosa ) )
		db++;
	return db;
}

// Az utolso belso palya (Visit, sharewareben End) nem szamit bele, mint a
// Steam-es kiadasban:
static int belsopalyaszam( void ) {
	return Palyaszam-1;
}

static int belsoteljesitettek( void ) {
	jatekos* pjatekos = &State->jatekosok[getjatekosindex( State->jatekosa )];
	int db = 0;
	for( int i = 0; i < pjatekos->sikerespalyakszama && i < belsopalyaszam(); i++ ) {
		if( !pjatekos->skippedtomb[i] )
			db++;
	}
	return db;
}

// Palya neve elma.res-bol (cim legalabb LEVELNAMEHOSSZ+1 byte), hiba
// eseten ures:
static void palyacim( int g, int i, char* cim ) {
	cim[0] = 0;
	char nev[30];
	palyaresnev( g, i, nev );
	FILE* h = qopen( nev, "rb" );
	char tmp[10] = "AAAAA";
	if( fread( tmp, 1, 5, h ) == 5 && strncmp( tmp, "POT", 3 ) == 0 ) {
		// Nev elott (13-as verziotol 2 byte,) belyeg es negy double all,
		// ld. topol::loadkulso:
		int verzio = tmp[4] - '0' + 10*(tmp[3] - '0');
		long hely = 5 + (verzio >= 13 ? 2 : 0) + 4 + 4*sizeof( double );
		int hossz = verzio >= 14 ? LEVELNAMEHOSSZ : 14;
		if( qseek( h, hely, SEEK_SET ) == 0 &&
			fread( cim, 1, hossz+1, h ) == size_t(hossz+1) )
			cim[hossz] = 0;
		else
			cim[0] = 0;
	}
	qclose( h );
}

// Ha a sorok nem ferenek ki, levagjuk a palyanevek kozos elejet (utolso
// szava kivetelevel) es kozos veget, szohatarnal, pl.
// "Elastomania Pack - Level #001 by Sla"-bol "Level #001" lesz:
static void rovidit( char cimek[][LEVELNAMEHOSSZ+1], int szam ) {
	int tulhosszu = 0;
	for( int i = 0; i < szam; i++ ) {
		if( int(strlen( cimek[i] )) + 3 > MAXPALYASORHOSSZ )
			tulhosszu = 1;
	}
	if( !tulhosszu || szam < 2 )
		return;

	int hossz0 = strlen( cimek[0] );
	int eleje = hossz0;
	int vege = hossz0;
	for( int i = 1; i < szam; i++ ) {
		int j = 0;
		while( j < eleje && cimek[i][j] == cimek[0][j] )
			j++;
		eleje = j;
		int hossz = strlen( cimek[i] );
		j = 0;
		while( j < vege && j < hossz && cimek[i][hossz-1-j] == cimek[0][hossz0-1-j] )
			j++;
		vege = j;
	}
	// Eleje szohatarra, utolso szavat meghagyva:
	int szavak = 0;
	while( eleje > 0 && szavak < 2 ) {
		eleje--;
		if( cimek[0][eleje] == ' ' )
			szavak++;
	}
	if( szavak == 2 )
		eleje++;
	else
		eleje = 0;
	// Vege szohatarra (szokozzel kezdodjon):
	while( vege > 0 && cimek[0][hossz0-vege] != ' ' )
		vege--;

	for( int i = 0; i < szam; i++ ) {
		if( int(strlen( cimek[i] ))-eleje-vege <= 0 )
			return; // Semmi nem maradna belole
	}
	for( int i = 0; i < szam; i++ ) {
		int hossz = strlen( cimek[i] );
		memmove( cimek[i], cimek[i]+eleje, hossz-eleje-vege );
		cimek[i][hossz-eleje-vege] = 0;
	}
}

// Igaz, ha a palya neve a sorszamaval kezdodik vagy vegzodik
// (pl. "01 Worm Up", "Tutorial 1"), ilyenkor nem irjuk ele meg egyszer:
static int cimbensorszam( char* cim, int sorszam ) {
	if( isdigit( (unsigned char)cim[0] ) && atoi( cim ) == sorszam )
		return 1;
	char* szokoz = strrchr( cim, ' ' );
	return szokoz && isdigit( (unsigned char)szokoz[1] ) && atoi( szokoz+1 ) == sorszam;
}

// A gyujtemeny level-edik palyajan jatszik (ld. playlevel es playextmenu),
// Play next-tel tovabb is lephet. Az utoljara jatszott palyat adja vissza:
static int gyujtemenyjatek( int g, int level ) {
	int szam = gyujtemenypalyaszam( g );
	while( 1 ) {
		char nev[30];
		palyanev( g, level, nev );
		kiirloading();
		if( !floadlevel_p( nev ) )
			return level;
		Prec1->erase( nev );
		Prec2->erase( nev );
		int eddigkesz = teljesitette( g, level, State->jatekosa );
		long ido = lejatszo( nev );
		Pmenupal->set();
		char valasz[100] = "";
		// Kulso palyakent intezi, saveidok GYUJTEMENYSTATE-be menti:
		idoelintezes( ido, valasz, 0, nev );
		int ujpalya = 0;
		if( ido > 0 && Single ) {
			// Csak SINGLE jatek alatt teljesitheto, mint belso palyaknal:
			teljesitettnek( g, level, State->jatekosa );
			if( !eddigkesz && level < szam-1 )
				ujpalya = 1;
		}
		int kovetkezovan = level < szam-1 && teljesitette( g, level, State->jatekosa );
		int eredmeny = afterplay( 0, ujpalya, valasz, nev, kovetkezovan );
		Prec1->erase( nev );
		Prec2->erase( nev );
		if( eredmeny == 0 )
			return level;
		if( eredmeny == 2 )
			level++;
	}
}

// Mint belso palyaknal, a teljesitett palyak es az utanuk kovetkezo latszik;
// ha meg egy sincs meg, rogton az elsovel kezd:
static void gyujtemenypalyai( int g ) {
	static int Kurzorok[GYUJTEMENYSZAM] = { -1, -1, -1, -1 };

	int szam = gyujtemenypalyaszam( g );
	static char cimek[MAXGYUJTEMENYPALYA][LEVELNAMEHOSSZ+1];
	for( int i = 0; i < szam; i++ )
		palyacim( g, i, cimek[i] );
	rovidit( cimek, szam );

	int valasztott = -1;
	if( elejenkeszek( g ) == 0 )
		valasztott = 0;
	while( 1 ) {
		if( valasztott < 0 ) {
			int lathato = elejenkeszek( g )+1;
			if( lathato > szam )
				lathato = szam;
			for( int i = 0; i < lathato; i++ ) {
				char sor[MAXRUBRIKAHOSSZ+LEVELNAMEHOSSZ+10];
				if( cimbensorszam( cimek[i], i+1 ) )
					strcpy( sor, cimek[i] );
				else
					sprintf( sor, "%d %s", i+1, cimek[i] );
				sor[MAXPALYASORHOSSZ] = 0;
				strcpy( Rubrikak[i], sor );
			}

			valaszt2 val;
			val.kur = Kurzorok[g];
			if( val.kur < 0 || val.kur >= lathato )
				val.kur = lathato-1;
			val.egykepen = LISTegykepen;
			val.x0 = 120;
			val.y0 = LISTy0;
			val.dy = LISTdy;
			val.escelheto = 1;
			strcpy( val.cim, Gyujtemenyek[g].nev );
			val.bead( lathato );
			valasztott = val.valassz();
			if( valasztott < 0 )
				return;
		}
		Kurzorok[g] = gyujtemenyjatek( g, valasztott );
		valasztott = -1;
	}
}

void gyujtemenymenu( void ) {
	static int Kurzor = 0;
	while( 1 ) {
		int sorok[SORSZAM];
		int szam = 0;
		for( int i = 0; i < SORSZAM; i++ ) {
			int g = Sorrend[i];
			char* sor = Rubrikak[szam];
			if( g == EREDETI )
				sprintf( sor, "Original Levels (%d/%d)", belsoteljesitettek(),
						 belsopalyaszam() );
			else if( g == KULSO )
				strcpy( sor, "External Levels" );
			else if( gyujtemenypalyaszam( g ) > 0 )
				sprintf( sor, "%s (%d/%d)", Gyujtemenyek[g].nev, teljesitettek( g ),
						 gyujtemenypalyaszam( g ) );
			else
				continue;
			sorok[szam++] = g;
		}

		valaszt2 val;
		val.kur = Kurzor;
		val.egykepen = LISTegykepen;
		val.x0 = 90;
		val.y0 = LISTy0;
		val.dy = LISTdy;
		val.escelheto = 1;
		strcpy( val.cim, "Select collection!" );
		val.bead( szam );

		int eredmeny = val.valassz();
		if( eredmeny < 0 )
			return;
		Kurzor = eredmeny;

		int g = sorok[eredmeny];
		if( g == EREDETI ) {
			belsopalyak( 0 );
		}
		else if( g == KULSO ) {
			void playextmenu( void );
			playextmenu();
		}
		else {
			gyujtemenypalyai( g );
		}
	}
}
