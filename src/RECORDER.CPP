#include	"all.h"
#include "LE_STRUCT.H"
#ifdef ELMA_PS3
#include "ATOMIC_FILE.H"
#include <cmath>
static bool RecWriteFailed=false;
static bool RecLoaded=false;
bool ps3_replay_loaded() { return RecLoaded; }
#endif

recorder *Prec1 = NULL, *Prec2 = NULL;
int Multirec = 0; // Ha multiplayer, akkor ez igaz

#ifdef ELMA_PSX
recorder::recorder( void ) : tag( 0 ) { memset(palyanev,0,sizeof(palyanev)); }
recorder::~recorder( void ) {}

void recorder::erase( char* name ) {
	if( strlen( name ) > 15 ) hiba( "Invalid recorder level name!" );
	memset(palyanev,0,sizeof(palyanev));
	strcpy( palyanev, name );
}

long loadrecek( char*, int ) { return 0; }
void saverecek( char*, long, int ) {}
#else
#define MAGICNUMBER (4796277l)

#define RECFREAD( t, n, h ) elma_read( (t), 1, (n), (h) )
#define RECFWRITE( t, n, h ) elma_write( (t), 1, (n), (h) )

//#define Darabszam (10000u)
//#define Hangdarabszam (3000u)

// Friss kikomentezes:
//static const int Darabszam = 14370;
//static const int Hangdarabszam = 3000;

static const int Darabszam = 8981; // Ot perc
static const int Hangdarabszam = 3900;

#ifdef ELMA_PS3
// Validate in bounded chunks before changing either live recorder. A zero
// level stamp is valid, so callers must use the separate loaded status.
static bool valid_replay_file(FILE* h) {
    const long begin=ftell(h);
    if(begin<0)return false;
    int riders=1, expected_multi=-1;
    for(int rider=0;rider<riders;++rider){
        int header[5]={};char name[16];
        if(elma_read(header,4,5,h)!=5 || fread(name,1,16,h)!=16)return false;
        const int frames=header[0], multi=header[2];
        // Preserve the shared loader's version warning for an otherwise
        // readable legacy layout instead of rejecting solely by its number.
        if(frames<=0 || frames>Darabszam || (multi!=0 && multi!=1)
           || (header[3]!=0 && header[3]!=1) || !name[0] || !memchr(name,0,sizeof(name)))return false;
        if(!rider){expected_multi=multi;riders=multi?2:1;}
        else if(multi!=expected_multi)return false;
        for(int array=0;array<2;++array){
            for(int left=frames;left;){
                float coordinates[64];const int count=left<64?left:64;
                if(elma_read(coordinates,4,count,h)!=size_t(count))return false;
                for(int i=0;i<count;++i)if(!std::isfinite(coordinates[i]))return false;
                left-=count;
            }
        }
        // Six short offsets, one short rotation and five byte channels.
        if(fseek(h,long(frames)*19,SEEK_CUR)!=0)return false;
        int sounds=0;if(elma_read(&sounds,4,1,h)!=1 || sounds<0 || sounds>Hangdarabszam)return false;
        for(int i=0;i<sounds;++i){
            egyhang sound={};
            if(elma_read(&sound,sizeof(sound),1,h)!=1 || !std::isfinite(sound.t)
               || !std::isfinite(sound.hangero) || sound.objszam>=MAXKEREK)return false;
            if(sound.objszam<0 && (sound.wavindex<WAV_UTODES || sound.wavindex>WAV_UGRAS2
               || sound.hangero<=0 || sound.hangero>=1))return false;
        }
        int magic=0;if(elma_read(&magic,4,1,h)!=1 || magic!=MAGICNUMBER)return false;
    }
    return fseek(h,begin,SEEK_SET)==0;
}
#endif

static double Valtrate = 30; //60;
static double Recorderszorzo = Valtrate/(182.0*0.0024);

recorder::recorder( void ) {
	memset(palyanev,0,sizeof(palyanev));
	palyanev[0] = 0;
	pk1rx = NULL;
	pk1ry = NULL;
	pk2rx = NULL;
	pk2ry = NULL;
	pk4rx = NULL;
	pk4ry = NULL;
	pvezrx = NULL;
	pvezry = NULL;
	pk2alfa = NULL;
	pk1alfa = NULL;
	pk4alfa = NULL;
	pfrekvencia = NULL;
	psurlero = NULL;
	pgazhatra = NULL;

	phangok = NULL;

	betoltve = 0;
	hangbetoltve = 0;

	tag = 0;

	// Ellenorzes:
	long hossz = sizeof( float );
	if( hossz != 4 )
		hiba( "float hossz != 4!" );
	hossz = long(Darabszam)*sizeof( float );
	if( hossz > 64000l )
		hiba( "Darabszam*sizeof( float )!" );

	hossz = long(Hangdarabszam)*sizeof( egyhang );
	if( hossz > 64000l )
		hiba( "Hangdarabszam*sizeof( egyhang )!" );

	pk1rx = new float[Darabszam];
	pk1ry = new float[Darabszam];
	pk2rx = new short[Darabszam];
	pk2ry = new short[Darabszam];
	pk4rx = new short[Darabszam];
	pk4ry = new short[Darabszam];
	pvezrx = new short[Darabszam];
	pvezry = new short[Darabszam];
	pk2alfa = new unsigned char[Darabszam];
	pk1alfa = new short[Darabszam];
	pk4alfa = new unsigned char[Darabszam];
	pfrekvencia = new unsigned char[Darabszam];
	psurlero = new unsigned char[Darabszam];
	pgazhatra = new unsigned char[Darabszam];

	phangok = NEW(egyhang*) egyhang[Hangdarabszam];

	if( !pk1rx || !pk1ry || !pk2rx || !pk2ry || !pk4rx || !pk4ry ||
	!pvezrx || !pvezry ||
	!pk2alfa || !pk1alfa|| !pk4alfa || !pfrekvencia || !pgazhatra ||
	!phangok || !psurlero )
		uzenet( "memory" );
}

recorder::~recorder( void ) {
	// Ez most nincs megcsinalva!
}

void recorder::erase( char* palyanev_p ) {
	if( strlen( palyanev_p ) > 15 )
		hiba( "875h8uyf" );
	memset(palyanev,0,sizeof(palyanev));
	strcpy( palyanev, palyanev_p );
	betoltve = 0;
	hangbetoltve = 0;
	ucsokiadva = 0;
	hangkov = 0;
	legkozindex = 0;
}

void recorder::rewind( void ) {
	ucsokiadva = 0;
	hangkov = 0;
	legkozindex = 0;
}

int recorder::gettag( void ) {
	return tag;
}

void recorder::settag( int tag_p ) {
	tag = tag_p;
}

#ifdef ELMA_PS3
bool recorder::objects_exist(kerek* const* objects) const {
    for(long i=0;i<hangbetoltve;++i){
        const int object=phangok[i].objszam;
        if(object>=0 && (object>=MAXKEREK || !objects[object]))return false;
    }
    return true;
}
#endif

static double Korrszorzo = 1000.0, 		   Korrszorzo_rec = 1.0 / Korrszorzo;
static double Alfaszorzo = 250/(2.0*K_pi), Alfaszorzo_rec = 1.0 / Alfaszorzo;
static double Alfaszorzo_16 = 10000/(2.0*K_pi), Alfaszorzo_16_rec = 1.0 / Alfaszorzo_16;
static double Frekvszorzo = 250.0, 	   Frekvszorzo_rec = 1.0 / Frekvszorzo;
//static double Frekvszorzo = 250.0/2.0, 	   Frekvszorzo_rec = 1.0 / Frekvszorzo;
static double Surlszorzo = 250/2.0, 	   Surlszorzo_rec = 1.0 / Surlszorzo;

//int Mostirdki = 0;

/*static int Filebairsorszam = 0;

static void filebair( float d1, float d2, float d3 ) {
	FILE* h = fopen( "log.txt", "at" );
	if( !h )
		hiba( "filebair-ban nem nyilik!" );

	fprintf( h, "%d %f %f %f\n", Filebairsorszam, d1, d2, d3 );


	Filebairsorszam++;
	fclose( h );
}*/

int recorder::recall( motorst* pmot, double dt, hanginfo* phinfo ) {
	if( betoltve <= 0 )
		hiba( "recall-ban betoltve <= 0!" );

	int index1 = Recorderszorzo*dt;
	double suly2 = Recorderszorzo*dt-index1;
	if( suly2 < 0.0 )
		suly2 = 0.0;
	if( suly2 > 1.0 )
		suly2 = 1.0;
	double suly1 = 1.0-suly2;
	int index2 = index1+1;

	if( index1 < 0 )
		index1 = 0;
	if( index2 < 0 )
		index2 = 0;
	if( ucsokiadva ) {
		phinfo->frekvencia = 1.0;
		phinfo->gaz = 0;
		phinfo->surlero = 0;
		return 0;
	}

	if( index1 >= betoltve-1 ) {
		index1 = betoltve-1;
		ucsokiadva = 1;
	}
	if( index2 >= betoltve-1 )
		index2 = betoltve-1;

	pmot->kor1.r.x = pk1rx[index1]*suly1 + pk1rx[index2]*suly2;
	pmot->kor1.r.y = pk1ry[index1]*suly1 + pk1ry[index2]*suly2;
	pmot->kor2.r.x = pmot->kor1.r.x + Korrszorzo_rec *
						(pk2rx[index1]*suly1 + pk2rx[index2]*suly2);
	pmot->kor2.r.y = pmot->kor1.r.y + Korrszorzo_rec *
						(pk2ry[index1]*suly1 + pk2ry[index2]*suly2);
	pmot->kor4.r.x = pmot->kor1.r.x + Korrszorzo_rec *
						(pk4rx[index1]*suly1 + pk4rx[index2]*suly2);
	pmot->kor4.r.y = pmot->kor1.r.y + Korrszorzo_rec *
						(pk4ry[index1]*suly1 + pk4ry[index2]*suly2);
	pmot->vezetor.x = pmot->kor1.r.x + Korrszorzo_rec *
						(pvezrx[index1]*suly1 + pvezrx[index2]*suly2);
	pmot->vezetor.y = pmot->kor1.r.y + Korrszorzo_rec *
						(pvezry[index1]*suly1 + pvezry[index2]*suly2);

	if( index1 >= 2 ) {
		// Motor:
		if( abs( pk1alfa[index1] - pk1alfa[index2] ) > 9000 ) { // 1000
			//pmot->kor1.alfa = Alfaszorzo_16_rec * pk1alfa[index2];			
			if( pk1alfa[index1] > pk1alfa[index2] ) {
				int fixedindex1 = pk1alfa[index1] - 10000;
				pmot->kor1.alfa = Alfaszorzo_16_rec *
					(fixedindex1*suly1 + pk1alfa[index2]*suly2);
			}
			else {
				int fixedindex2 = pk1alfa[index2] - 10000;
				pmot->kor1.alfa = Alfaszorzo_16_rec *
					(pk1alfa[index1]*suly1*suly1 + fixedindex2*suly2);
			}
		}
		else
			pmot->kor1.alfa = Alfaszorzo_16_rec *
				(pk1alfa[index1]*suly1 + pk1alfa[index2]*suly2);
		
		// Elso kerek:
		if( abs( pk2alfa[index1] - pk2alfa[index2] ) > 220 ) { // 50
			//pmot->kor2.alfa = Alfaszorzo_rec * pk2alfa[index2];
			if( pk2alfa[index1] > pk2alfa[index2] ) {
				int fixedindex1 = pk2alfa[index1] - 250;
				pmot->kor2.alfa = Alfaszorzo_rec *
					(fixedindex1*suly1 + pk2alfa[index2]*suly2);
			}
			else {
				int fixedindex2 = pk2alfa[index2] - 250;
				pmot->kor2.alfa = Alfaszorzo_rec *
					(pk2alfa[index1]*suly1*suly1 + fixedindex2*suly2);
			}
		}
		else
			pmot->kor2.alfa = Alfaszorzo_rec *
				(pk2alfa[index1]*suly1 + pk2alfa[index2]*suly2);

		// Hatso kerek:
		if( abs( pk4alfa[index1] - pk4alfa[index2] ) > 220 ) {
			//pmot->kor4.alfa = Alfaszorzo_rec * pk4alfa[index2];
			if( pk4alfa[index1] > pk4alfa[index2] ) {
				int fixedindex1 = pk4alfa[index1] - 250;
				pmot->kor4.alfa = Alfaszorzo_rec *
					(fixedindex1*suly1 + pk4alfa[index2]*suly2);
			}
			else {
				int fixedindex2 = pk4alfa[index2] - 250;
				pmot->kor4.alfa = Alfaszorzo_rec *
					(pk4alfa[index1]*suly1*suly1 + fixedindex2*suly2);
			}
		}
		else
			pmot->kor4.alfa = Alfaszorzo_rec * 
				(pk4alfa[index1]*suly1 + pk4alfa[index2]*suly2);
		
	}
	else {
		pmot->kor1.alfa = Alfaszorzo_16_rec * pk1alfa[index2];
		pmot->kor2.alfa = Alfaszorzo_rec * pk2alfa[index2];
		pmot->kor4.alfa = Alfaszorzo_rec * pk4alfa[index2];
	}

	//filebair( index2, pk2alfa[index2], pmot->kor2.alfa );
	phinfo->gaz = char(pgazhatra[index1] & 1);
	pmot->hatra_f = (pgazhatra[index1] & 2) >> 1;
	Aafogo 		= (pgazhatra[index1] & 4) >> 2;
	Kozelvannak = (pgazhatra[index1] & 8) >> 3;

	/*if( Mostirdki ) {
		char tmp[100];
		int tmpfreki = pfrekvencia[index1];
		sprintf( tmp, "f:%d, index1:%d", tmpfreki, index1 );
		hiba( "Itt van eredmeny:", tmp );
	}*/

	phinfo->frekvencia = Frekvszorzo_rec * pfrekvencia[index1]
							+ 1.0;
	phinfo->surlero    = Surlszorzo_rec  * psurlero[index1];

	return 1;
}

static const double Reclepesido = 1.0 / Recorderszorzo;

void recorder::store( motorst* pmot, double ido, hanginfo* phinfo ) {
	if( !legkozindex ) {
		ucso_r = pmot->kor1.r;
		ucsot = -0.00000000001;
		legkozt = 0.0;
	}
	if( ido < legkozt ) {
		ucso_r = pmot->kor1.r;
		ucsot = ido;
		return;
	}

	while( 1 ) {
		#ifdef TEST
			if( ido-ucsot == 0.0 )
				hiba( "ido-ucsot == 0.0!" );
		#endif
		vekt2 kor1r = (pmot->kor1.r - ucso_r) *
					  ((legkozt-ucsot)/(ido-ucsot)) +
					  ucso_r;

		if( legkozindex >= Darabszam )
			// betelt:
			return;

		// Beirunk bejegyzesbe:
		int i = legkozindex;
		pk1rx[i] = kor1r.x;
		pk1ry[i] = kor1r.y;
		pk2rx[i] = (pmot->kor2.r.x-pmot->kor1.r.x)*Korrszorzo;
		pk2ry[i] = (pmot->kor2.r.y-pmot->kor1.r.y)*Korrszorzo;
		pk4rx[i] = (pmot->kor4.r.x-pmot->kor1.r.x)*Korrszorzo;
		pk4ry[i] = (pmot->kor4.r.y-pmot->kor1.r.y)*Korrszorzo;
		pvezrx[i] = (pmot->vezetor.x-pmot->kor1.r.x)*Korrszorzo;
		pvezry[i] = (pmot->vezetor.y-pmot->kor1.r.y)*Korrszorzo;

		// Alfak:
		double alfa1 = pmot->kor1.alfa;
		while( alfa1 <= 0 )
			alfa1 += K_2pi;
		while( alfa1 > K_2pi )
			alfa1 -= K_2pi;
		pk1alfa[i] = alfa1*Alfaszorzo_16;

		if( pmot->kor2.alfa <= 0 )
			pk2alfa[i] = (pmot->kor2.alfa + K_2pi)*Alfaszorzo;
		else
			pk2alfa[i] = pmot->kor2.alfa*Alfaszorzo;
		if( pmot->kor4.alfa <= 0 )
			pk4alfa[i] = (pmot->kor4.alfa + K_2pi)*Alfaszorzo;
		else
			pk4alfa[i] = pmot->kor4.alfa*Alfaszorzo;

		// Belerakunk egy veletlen szamot felso negy bitbe:
		double tmpb = pmot->kor4.alfa + i*5.752364;
		uint64_t tmpbits;
		memcpy( &tmpbits, &tmpb, sizeof(tmpbits) );
		pgazhatra[i] = static_cast<unsigned char>((tmpbits >> 32) & 0xf0);

		if( phinfo->gaz )
			pgazhatra[i] += 1;
		if( pmot->hatra_f )
			pgazhatra[i] += 2;
		if( Aafogo )
			pgazhatra[i] += 4;
		if( Kozelvannak )
			pgazhatra[i] += 8;

		//pgazhatra[i] = char( phinfo->gaz + (pmot->hatra<<1) );

		if( phinfo->frekvencia < 1.0 )
			phinfo->frekvencia = 1.0;
		pfrekvencia[i] = Frekvszorzo * 
							(phinfo->frekvencia-1.0);
		psurlero[i]    = Surlszorzo  * phinfo->surlero;

		legkozindex++;
		legkozt += Reclepesido;
		if( ido < legkozt ) {
			ucso_r = pmot->kor1.r;
			ucsot = ido;
			betoltve = legkozindex;
			return;
		}
	}
}



/*void recorder::store( motorst* pmot, double dt, hanginfo* phinfo ) {
	int index = Recorderszorzo*dt;
	if( index < 0 )
		index = 0;
	if( index >= Darabszam )
		// betelt:
		return;
	if( index < betoltve-1 )
		hiba( "recorder::store-ban index < betoltve-1!" );

	for( int i = betoltve; i <= index; i++ ) {
		pk1rx[i] = pmot->kor1.r.x;
		pk1ry[i] = pmot->kor1.r.y;
		pk2rx[i] = (pmot->kor2.r.x-pmot->kor1.r.x)*Korrszorzo;
		pk2ry[i] = (pmot->kor2.r.y-pmot->kor1.r.y)*Korrszorzo;
		pk4rx[i] = (pmot->kor4.r.x-pmot->kor1.r.x)*Korrszorzo;
		pk4ry[i] = (pmot->kor4.r.y-pmot->kor1.r.y)*Korrszorzo;
		pvezrx[i] = (pmot->vezetor.x-pmot->kor1.r.x)*Korrszorzo;
		pvezry[i] = (pmot->vezetor.y-pmot->kor1.r.y)*Korrszorzo;

		// torlendo
		//int hatar = 2000;
		//if( pk2rx[i] > hatar || pk4rx[i] > hatar ||
		//	pk2ry[i] > hatar || pk4ry[i] > hatar )
		//	uzenet( "Nagyobb 5000-nel!" );
		//if( pk2rx[i] < -hatar || pk4rx[i] < -hatar ||
		//	pk2ry[i] < -hatar || pk4ry[i] < -hatar )
		//	uzenet( "Kisebb -5000-nel!" );

		// Alfak:
		double alfa1 = pmot->kor1.alfa;
		while( alfa1 <= 0 )
			alfa1 += K_2pi;
		while( alfa1 > K_2pi )
			alfa1 -= K_2pi;
		pk1alfa[i] = alfa1*Alfaszorzo_16;

		if( pmot->kor2.alfa <= 0 )
			pk2alfa[i] = (pmot->kor2.alfa + K_2pi)*Alfaszorzo;
		else
			pk2alfa[i] = pmot->kor2.alfa*Alfaszorzo;
		if( pmot->kor4.alfa <= 0 )
			pk4alfa[i] = (pmot->kor4.alfa + K_2pi)*Alfaszorzo;
		else
			pk4alfa[i] = pmot->kor4.alfa*Alfaszorzo;

		if( phinfo->gaz )
			pgazhatra[i] = 1;
		else
			pgazhatra[i] = 0;

		if( pmot->hatra )
			pgazhatra[i] += 2;
		if( Aafogo )
			pgazhatra[i] += 4;
		if( Kozelvannak )
			pgazhatra[i] += 8;

		//pgazhatra[i] = char( phinfo->gaz + (pmot->hatra<<1) );

		if( phinfo->frekvencia > 2.0 )
			phinfo->frekvencia = 2.0;
		pfrekvencia[i] = Frekvszorzo * phinfo->frekvencia;
		psurlero[i]    = Surlszorzo  * phinfo->surlero;
	}
	betoltve = index+1;
}*/

void recorder::addhang( double t, char wavindex, double hangero, int objszam ) {
	if( hangbetoltve >= Hangdarabszam )
		return;
	if( hangbetoltve > 0 ) {
		if( phangok[unsigned(hangbetoltve-1)].t > t+0.00001 ) {
			char tmp[50];
			double t2 = phangok[unsigned(hangbetoltve-1)].t;
			sprintf( tmp, "t1: kulonbseg: %f\n", float( t - t2 ) );
			hiba( tmp );
			//hiba( "recorder::addhang-ban ido forditott sorrendben!" );
		}
	}
	// The legacy 16-byte record includes padding after wavindex. Do not write
	// an uninitialized heap byte to disk; all meaningful fields stay unchanged.
	memset( &phangok[unsigned(hangbetoltve)], 0, sizeof(egyhang) );
	phangok[unsigned(hangbetoltve)].t = t;
	phangok[unsigned(hangbetoltve)].wavindex = wavindex;
	phangok[unsigned(hangbetoltve)].hangero = hangero;
	phangok[unsigned(hangbetoltve)].objszam = (short)objszam;
	hangbetoltve++;
}

// Ha van hang, akkor igazzal ter vissza:
int recorder::gethang( double t, char* pwavindex, double* phangero,
												int* pobjszam ) {
	if( hangkov < hangbetoltve ) {
		if( phangok[unsigned(hangkov)].t <= t ) {
			*pwavindex = phangok[unsigned(hangkov)].wavindex;
			*phangero = phangok[unsigned(hangkov)].hangero;
			*pobjszam = phangok[unsigned(hangkov)].objszam;
			hangkov++;
			return 1;
		}
	}
	return 0;
}

static void olvhiba( char* nev ) {
	hiba( "Nem sikerult olvasni recorded file-bol!: ", nev );
}

// demo eseten resource file-bol nyit:
// belyeg-et adja vissza, vagy 0-at:
long recorder::load( char* nev, FILE* h, int demo ) {
	int megvoltnyitva = 0;
	if( h )
		megvoltnyitva = 1;

	if( !h ) {
		if( demo ) {
			h = qopen( nev, "rb" );
			if( !h )
				hiba( "Nem sikerult megnyitni recorded file-t!: ", nev );
		}
		else {
			char tmpnev[40];
			sprintf( tmpnev, "rec\\%s", nev );
			#ifdef ELMA_PS3
            elma_restore_save(tmpnev);
#endif
			h = fopen( tmpnev, "rb" );
			if( !h )
				uzenet( "Could not open for reading record file!:", tmpnev );
		}
	}

#ifdef ELMA_PS3
    if(!h)return 0;
#endif
	betoltve = 0;
	if( elma_read( &betoltve, 1, 4, h ) != 4 )
		olvhiba( nev );
	if( betoltve <= 0 )
		hiba( "Nem stimmel betoltve recorded file-ban!: ", nev );

	if( betoltve > Darabszam ) {
		hiba( "recorder load-ban betoltve > Darabszam!" );
	}

	long verzio = 0;
	if( elma_read( &verzio, 1, 4, h ) != 4 )
		hiba( "Nem sikerult olvasni recorded file-bol!: ", nev );

	// Ezt loadrecekben is igazitani kell:
	if( verzio < 131 )
		uzenet( "Recorded file version is too old!", nev );

	if( verzio > 131 )
		uzenet( "Recorded file version is too new!", nev );

	int tmp = 0; // Multirec, de ezt mar elintezte loadrecek, aki ezt hivta
	if( elma_read( &tmp, 1, 4, h ) != 4 )
		hiba( "Nem sikerult olvasni recorded file-bol!: ", nev );

	if( elma_read( &tag, 1, 4, h ) != 4 )
		hiba( "Nem sikerult olvasni recorded file-bol!: ", nev );

	long belyeg = 0;
	if( elma_read( &belyeg, 1, 4, h ) != 4 )
		olvhiba( nev );
	if( elma_read( palyanev, 1, 16, h ) != 16 )
		olvhiba( nev );
	palyanev[sizeof(palyanev)-1]=0;

	// Ehelyett lehet hogy kene valami hasonlo:
	//if( Sarvari && !belyeg && (level > 15 && level != 22) )
	//	uzenet( "This REC file can only be replayed with a registered version of the game!",
	//				nev );

	int hosszf = betoltve*sizeof( float );
	//int hosszi = betoltve*sizeof( int );
	int hosszc = betoltve*sizeof( char );
	int hosszs = betoltve*sizeof( short );

	if( RECFREAD( pk1rx, hosszf, h ) != hosszf )
		olvhiba( nev );
	if( RECFREAD( pk1ry, hosszf, h ) != hosszf )
		olvhiba( nev );
	if( RECFREAD( pk2rx, hosszs, h ) != hosszs )
		olvhiba( nev );
	if( RECFREAD( pk2ry, hosszs, h ) != hosszs )
		olvhiba( nev );
	if( RECFREAD( pk4rx, hosszs, h ) != hosszs )
		olvhiba( nev );
	if( RECFREAD( pk4ry, hosszs, h ) != hosszs )
		olvhiba( nev );
	if( RECFREAD( pvezrx, hosszs, h ) != hosszs )
		olvhiba( nev );
	if( RECFREAD( pvezry, hosszs, h ) != hosszs )
		olvhiba( nev );

	if( RECFREAD( pk1alfa, hosszs, h ) != hosszs )
		olvhiba( nev );
	if( RECFREAD( pk2alfa, hosszc, h ) != hosszc )
		olvhiba( nev );
	if( RECFREAD( pk4alfa, hosszc, h ) != hosszc )
		olvhiba( nev );
	if( RECFREAD( pgazhatra, hosszc, h ) != hosszc ) // karakter
		olvhiba( nev );

	if( RECFREAD( pfrekvencia, hosszc, h ) != hosszc )
		olvhiba( nev );
	if( RECFREAD( psurlero, hosszc, h ) != hosszc )
		olvhiba( nev );

	// Hangok:
	if( elma_read( &hangbetoltve, 1, 4, h ) != 4 )
		olvhiba( nev );
	if( hangbetoltve < 0 )
		hiba( "hangbetoltve nem stimmel loadban!" );
	if( hangbetoltve > Hangdarabszam )
		hiba( "rec load-ban hangbetoltve > Hangdarabszam!" );

	/*static int elsoszam = 0;
	if( elsoszam ) {
		char tmp11[50];
		sprintf( tmp11, "1.: %d, 2.: %d", hangbetoltve, elsoszam );
		uzenet( tmp11 );
	}
	elsoszam = hangbetoltve;*/

	int hossz = hangbetoltve*sizeof( egyhang );
	if( RECFREAD( phangok, hossz, h ) != hossz )
		olvhiba( nev );

	long magic = 0;
	if( elma_read( &magic, 1, 4, h ) != 4 )
		olvhiba( nev );
	if( magic != MAGICNUMBER )
		hiba( "magic != MAGICNUMBER" );

	if( !megvoltnyitva ) {
		if( demo )
			qclose( h );
		else
			fclose( h );
	}

	//if( !jorechossza( this ) )
	//	hiba( "recorder::load-ban !jorechossza( this )!" );
	return belyeg;
}

/* 1.0 es 1.1 eseten ez volt:
	h = fopen( nev, "wb" );
	if( !h )
		hiba( "Nem sikerult megnyitni irasra recorded file-t!: ", nev );

	if( elma_write( &betoltve, 1, 4, h ) != 4 )
		hiba( "Nem sikerult irni recorded file-ba!: ", nev );
	if( elma_write( &level, 1, 4, h ) != 4 )
		hiba( "Nem sikerult irni recorded file-ba!: ", nev );


	long hossz = betoltve*sizeof( float );

	if( elma_write( pk1rx, 1, unsigned(hossz), h ) != hossz )
		hiba( "Nem sikerult irni recorded file-ba!: ", nev );
*/

static void irhiba( char* nev ) {
#ifdef ELMA_PS3
    RecWriteFailed=true;
#else
	hiba( "Nem sikerult irni recorded file-ba!: ", nev );
#endif
}

void recorder::save( char* nev, FILE* h, long belyeg, int tag_p ) {
	tag = tag_p;

	int megvoltnyitva = 0;
	if( h )
		megvoltnyitva = 1;

	if( betoltve == 0 )
		hiba( "save-ben betoltve == 0!" );

	if( !h ) {
		// Itt meg kell hagyni fopen-t!:
		char tmpnev[40];
		sprintf( tmpnev, "rec\\%s", nev );
		h = fopen( tmpnev, "wb" );
		if( !h )
			hiba( "Could not open for writing record file!: ", tmpnev );
	}

	if( elma_write( &betoltve, 1, 4, h ) != 4 )
		irhiba( nev );

	// Verzio csak 1.2-tol kezdodoen jon bele:
	// Elozoleg itt level volt, ami biztos hogy kisebb volt 120-nal:
	long verzio = 131;
	if( elma_write( &verzio, 1, 4, h ) != 4 )
		irhiba( nev );

	// Ezt loadrecekben is olvassa, ugyhogy ennek verzio utan kell maradnia:
	if( elma_write( &Multirec, 1, 4, h ) != 4 )
		irhiba( nev );

	if( elma_write( &tag, 1, 4, h ) != 4 )
		irhiba( nev );

	if( elma_write( &belyeg, 1, 4, h ) != 4 )
		irhiba( nev );

	if( elma_write( palyanev, 1, 16, h ) != 16 )
		irhiba( nev );

	int hosszf = betoltve*sizeof( float );
	//int hosszi = betoltve*sizeof( int );
	int hosszc = betoltve*sizeof( char );
	int hosszs = betoltve*sizeof( short );

	if( RECFWRITE( pk1rx, hosszf, h ) != hosszf )
		irhiba( nev );
	if( RECFWRITE( pk1ry, hosszf, h ) != hosszf )
		irhiba( nev );
	if( RECFWRITE( pk2rx, hosszs, h ) != hosszs )
		irhiba( nev );
	if( RECFWRITE( pk2ry, hosszs, h ) != hosszs )
		irhiba( nev );
	if( RECFWRITE( pk4rx, hosszs, h ) != hosszs )
		irhiba( nev );
	if( RECFWRITE( pk4ry, hosszs, h ) != hosszs )
		irhiba( nev );

	if( RECFWRITE( pvezrx, hosszs, h ) != hosszs )
		irhiba( nev );
	if( RECFWRITE( pvezry, hosszs, h ) != hosszs )
		irhiba( nev );

	if( RECFWRITE( pk1alfa, hosszs, h ) != hosszs )
		irhiba( nev );
	if( RECFWRITE( pk2alfa, hosszc, h ) != hosszc )
		irhiba( nev );
	if( RECFWRITE( pk4alfa, hosszc, h ) != hosszc )
		irhiba( nev );
	if( RECFWRITE( pgazhatra, hosszc, h ) != hosszc )
		irhiba( nev );

	if( RECFWRITE( pfrekvencia, hosszc, h ) != hosszc )
		irhiba( nev );
	if( RECFWRITE( psurlero, hosszc, h ) != hosszc )
		irhiba( nev );

	// Hangok:
	if( elma_write( &hangbetoltve, 1, 4, h ) != 4 )
		irhiba( nev );
	int hossz = hangbetoltve*sizeof( egyhang );
	if( RECFWRITE( phangok, hossz, h ) != hossz )
		irhiba( nev );

	long magic = MAGICNUMBER;
	if( elma_write( &magic, 1, 4, h ) != 4 )
		irhiba( nev );

	if( !megvoltnyitva )
		fclose( h );
}

// demo eseten resource file-bol nyit:
long loadrecek( char* nev, int demo ) {
#ifdef ELMA_PS3
    RecLoaded=false;
#endif
	// Eloszor megvizsgaljuk, hogy multirec vagy nem:
	FILE* h;
	if( demo ) {
		h = qopen( nev, "rb" );
		if( !h )
			uzenet( "Could not open for reading record file!: !: ", nev );
	}
	else {
		char tmpnev[40];
		sprintf( tmpnev, "rec\\%s", nev );
		#ifdef ELMA_PS3
            elma_restore_save(tmpnev);
#endif
			h = fopen( tmpnev, "rb" );
		if( !h )
			uzenet( "Could not open for reading record file!:", tmpnev );
	}
#ifdef ELMA_PS3
    if(!h)return 0;
    if(!valid_replay_file(h)){
        if(demo)qclose(h);else fclose(h);
        uzenet("This replay is damaged or uses an unsupported format.",nev);
        return 0;
    }
#endif
	int tmp = 0; // betoltve (bejegyzes darabszam)
	if( elma_read( &tmp, 1, 4, h ) != 4 )
		hiba( "Nem sikerult olvasni recorded file-bol!: ", nev );

	long verzio = 0;
	if( elma_read( &verzio, 1, 4, h ) != 4 )
		hiba( "Nem sikerult olvasni recorded file-bol!: ", nev );

	if( verzio < 131 )
		uzenet( "Recorded file version is too old!", nev );

	if( verzio > 131 )
		uzenet( "Recorded file version is too new!", nev );

	// Betoltjuk Multirec-et:
	if( elma_read( &Multirec, 1, 4, h ) != 4 )
		hiba( "Nem sikerult olvasni recorded file-bol!: ", nev );

	if( demo )
		qclose( h );
	else
		fclose( h );


	// Most jon tenyleges beolvasas:
	long belyeg = 0;
	if( Multirec ) {
		FILE* h;
		if( demo ) {
			h = qopen( nev, "rb" );
			if( !h )
				uzenet( "Could not open for reading demo record file!:", nev );
		}
		else {
			char tmpnev[40];
			sprintf( tmpnev, "rec\\%s", nev );
			#ifdef ELMA_PS3
            elma_restore_save(tmpnev);
#endif
			h = fopen( tmpnev, "rb" );
			if( !h )
				uzenet( "Could not open for reading record file!:", tmpnev );
		}

#ifdef ELMA_PS3
        if(!h)return 0;
#endif
		belyeg = Prec1->load( nev, h, demo );
		Prec2->load( nev, h, demo );

		if( demo )
			qclose( h );
		else
			fclose( h );
	}
	else {
		belyeg = Prec1->load( nev, NULL, demo );
	}

	if( Sarvari ) {
		char ctmp = Prec1->palyanev[5];
		Prec1->palyanev[5] = 0;
		char tmpnev[10];
		strcpy( tmpnev, Prec1->palyanev );
		Prec1->palyanev[5] = ctmp;
		if( strcmpi( tmpnev, "QWQUU" ) == 0 ) {
			int belsopalyaszam = nevanalizis( Prec1->palyanev );
			if( belsopalyaszam < 1 ||
				(
					belsopalyaszam > Palyaszam-1 &&
					belsopalyaszam != 34
				) ) // utolso palya mar nem mehet, de demo igen
				uzenet(
"This rec file can only be played in the registered version!:", nev );
		}
	}

#ifdef ELMA_PS3
    RecLoaded=true;
#endif
	return belyeg;
}

// belyeg-et adja vissza, vagy 0-at:
void saverecek( char* nev, long belyeg, int tag ) {
#ifdef ELMA_PS3
    char path[64];int length=snprintf(path,sizeof(path),"rec/%s",nev);
    if(length<0 || size_t(length)>=sizeof(path)){uzenet("Replay filename is too long.");return;}
    elma_atomic_file transaction(path);FILE* h=transaction.file();
    if(!h){uzenet("Could not open replay for writing. The previous file is kept.",path);return;}
    RecWriteFailed=false;
    Prec1->save(nev,h,belyeg,tag);
    if(Multirec)Prec2->save(nev,h,belyeg,tag);
    if(!transaction.commit(!RecWriteFailed))uzenet("Could not save replay. The previous file is kept.",path);
#else
	if( Multirec ) {
		char tmpnev[40];
		sprintf( tmpnev, "rec\\%s", nev );
		FILE* h = fopen( tmpnev, "wb" );
		if( !h )
			uzenet( "Could not open for writing record file!: !: ", tmpnev );

		// Multirec alapjan tudjak, hogy mit kell rec file multirec
		// rubrikajaba irni:
		Prec1->save( nev, h, belyeg, tag );
		Prec2->save( nev, h, belyeg, tag );

		fclose( h );
	}
	else {
		Prec1->save( nev, NULL, belyeg, tag );
	}
#endif
}

#endif

// WAV GYUJTO:

static int Begyujtve = 0;

#define GYUJTODARAB (200)

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

void resetwavegyujto( void ) {
	Begyujtve = 0;
}

// Igaz, ha van bent wav:
int getwavegyujto( int* pwavazonosito, double* phangero, int* pobjszam ) {
	if( Begyujtve == 0 )
		return 0;
	*pwavazonosito = Azonosito[0];
	*phangero = Hangero[0];
	*pobjszam = Objszam[0];
	Begyujtve--;
	for( int i = 0; i < Begyujtve; i++ ) {
		Azonosito[i] = Azonosito[i+1];
		Hangero[i] =   Hangero[i+1];
		Objszam[i] = Objszam[i+1];
	}
	return 1;
}






