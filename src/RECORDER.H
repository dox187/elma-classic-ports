
struct hanginfo {
	double frekvencia;
	char gaz;
	double surlero;
};

struct egyhang {
	double t;
	short objszam;
	char wavindex;
	float hangero;
};

#ifdef ELMA_PSX
// The PS1 version keeps a recording in pieces of DARAB elements, made when they
// are first used (the arrays of a whole five minute recording would take
// 300 KB): indexed as the arrays, read and written as them.
void* recorder_darab( unsigned meret );
template <typename ELEM, int DARAB, int MAXDB> class rectomb {
	ELEM* darabok[(MAXDB + DARAB - 1) / DARAB];
public:
	rectomb( void ) {
		for( int i = 0; i < (MAXDB + DARAB - 1) / DARAB; i++ )
			darabok[i] = 0;
	}
	ELEM& operator[]( long i ) {
		ELEM*& d = darabok[i / DARAB];
		if( !d )
			d = (ELEM*)recorder_darab( DARAB * sizeof( ELEM ) );
		return d[i % DARAB];
	}
	void torol( void ) {
		for( int i = 0; i < (MAXDB + DARAB - 1) / DARAB; i++ ) {
			delete[] (char*)darabok[i];
			darabok[i] = 0;
		}
	}
	// fread( tomb, 1, bajt, h ) and fwrite( tomb, 1, bajt, h ):
	long olvas( FILE* h, long bajt ) {
		long kesz = 0;
		for( long i = 0; kesz < bajt; i += DARAB ) {
			long db = bajt - kesz < long( DARAB * sizeof( ELEM ) ) ? bajt - kesz : long( DARAB * sizeof( ELEM ) );
			long olvasott = fread( &(*this)[i], 1, db, h );
			kesz += olvasott;
			if( olvasott != db )
				break;
		}
		return kesz;
	}
	long ir( FILE* h, long bajt ) {
		long kesz = 0;
		for( long i = 0; kesz < bajt; i += DARAB ) {
			long db = bajt - kesz < long( DARAB * sizeof( ELEM ) ) ? bajt - kesz : long( DARAB * sizeof( ELEM ) );
			long irt = fwrite( &(*this)[i], 1, db, h );
			kesz += irt;
			if( irt != db )
				break;
		}
		return kesz;
	}
};
#define RECTOMB_DB (8981)
#define RECHANG_DB (3900)
#endif

class recorder {
	// demo eseten resource file-bol nyit:
	// belyeg-et adja vissza, vagy 0-at:
	friend long loadrecek( char* nev, int demo );
	friend void saverecek( char* nev, long belyeg, int tag );
	// pgazhatra-ba beepitik es ellenorzik betoltvet:
	friend void berakrecbehosszat( recorder* prec );
	friend int jorechossza( recorder* prec );
	friend void replay( void ); // Hogy betolthoz hozzaferjen

#ifdef ELMA_PSX
	rectomb<float, 512, RECTOMB_DB> pk1rx, pk1ry;
	rectomb<short, 512, RECTOMB_DB> pk2rx, pk2ry, pk4rx, pk4ry;
	rectomb<short, 512, RECTOMB_DB> pvezrx, pvezry;
	rectomb<unsigned char, 512, RECTOMB_DB> pk2alfa, pk4alfa;
	rectomb<short, 512, RECTOMB_DB> pk1alfa;
	rectomb<unsigned char, 512, RECTOMB_DB> pfrekvencia, psurlero;
	rectomb<unsigned char, 512, RECTOMB_DB> pgazhatra;
#else
	float *pk1rx, *pk1ry;
	short   *pk2rx, *pk2ry, *pk4rx, *pk4ry;
	short   *pvezrx, *pvezry;
	unsigned char  *pk2alfa, *pk4alfa;
	short *pk1alfa;
	unsigned char  *pfrekvencia, *psurlero;
	unsigned char  *pgazhatra;
#endif

	long betoltve;
	int ucsokiadva;

#ifdef ELMA_PSX
	rectomb<egyhang, 128, RECHANG_DB> phangok;
#else
	egyhang* phangok;
#endif
	long hangbetoltve;
	long hangkov;

	vekt2 ucso_r;
	double ucsot, legkozt;
	int legkozindex;

	int tag;
	// demo eseten resource file-bol nyit:
	// belyeg-et adja vissza, vagy 0-at:
	long load( char* nev, FILE* h, int demo );
	void save( char* nev, FILE* h, long belyeg, int tag );
#ifdef ELMA_PSX
	// Makes the buffers at the first use:
	void lefoglal( void );
#endif
public:
	char palyanev[16];

	recorder( void );
	~recorder( void );
	void erase( char* palyanev );
	void rewind( void );
	// Ez a ket fuggveny  meg ezt a ket globalis valtozot is
	// beveszi es allitja: Aafogo Kozelvannak:
	int recall( motorst* pmot, double dt, hanginfo* phinfo );
	void store( motorst* pmot, double dt, hanginfo* phinfo );

	void addhang( double t, char wavindex, double hangero, int objszam );
	// Ha van hang, akkor igazzal ter vissza:
	int gethang( double t, char* pwavindex, double* phangero, int* pobjszam );

	int gettag( void );
	void settag( int tag_p );
};

extern recorder *Prec1, *Prec2;
// Ha multiplayer a bentlevo rec, akkor ez igaz:
// long lejatszo( void ) allithatja, vagy loadrecek:
extern int Multirec;
long loadrecek( char* nev, int demo );
void saverecek( char* nev, long belyeg, int tag );

void startwavegyujto( int wavazonosito, double hangero, int objszam );
void resetwavegyujto( void );
// Igaz, ha van bent wav:
int getwavegyujto( int* pwavazonosito, double* phangero, int* pobjszam );
