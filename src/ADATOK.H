

extern double Elszakadasisebhat, Belsosav, G;
extern double  Talppontegybeolvadasitav;

extern double Ugrassebesseg1, Ugrassebesseg2;
extern double Ugroturelem;
extern double Vegenvaras;

extern double Drsugar, Drtang, Sr;

void initadatok( void );

extern double Magassag, Szelesseg;

extern vekt2 P_alap1, P_alap2, P_alap3, P_alap4, P_alap6;
extern double Fejsugar;

extern double Objektumsugar;

extern double Spritemaxsugar; // Targykereseshez!
extern double Ketmaxsugar; // Targykereseshez!

// Match-ben fej es kerek tavolsag vizsgalathoz:
extern double Fejkerektavnegyzet;

// Hajszalnyival kisebb kor.sugarnal, hogy kirajzolasnal ne logjon foldbe:
extern double Kerekrajzsugar;

// MCGA kirajzolasos:

// Pixel/meter: what the built-in LGR's pictures and the brushes were made
// with. Only changed by beallitarany, together with reloading the LGR and
// rebuilding the brushes (load.cpp):
extern double Arany, Aranyrec;
// The original game's Arany without zoom (initadatok: 100*0.48 = 48):
extern double Aranyalap, Aranyalaprec;
// The engine's zoom, which Arany was built with (1: original size):
extern double Motornagyitas;

// Zoom limits:
#define NAGYITASMIN (0.5)
#define NAGYITASMAX (4.0)

// Arany = Aranyalap * picture fit to the screen * zoom. For the game
// (jatekhoz true) sets it with the desired zoom, for the editor with the
// original:
void beallitarany( int jatekhoz );
// True if beallitarany( 1 ) for the game would give a different Arany than
// the current one:
int maskellarany( void );
// How many times bigger the LGR's pictures are scaled to the current Arany
// (Arany/Aranyalap):
double kepnagyitas( void );
// A size given in one pixel (belonging to the pictures), scaled, rounded,
// at least 1; exactly the pixel value at 1x zoom:
int nagyitpixel( int pixel, double nagyitas );


extern double Kord2x, Kord2y, Kord4x, Kord4y,
				Kord5y; // Ez az utolso vezeto helye

extern double Fekegyutthato;

// Half size of objects (40x40 pictures) without zoom, scaled it is
// Plgr->objektumsugar:
#define OBJEKTUMSUGAR_I (20)

// The view window (map) has this many times smaller a ratio than Aranyalap;
// the map is always Aranyalap/Viewzoom pixel/meter regardless of zoom:
extern int Viewzoom;

struct motorst {
	kor kor1, kor2, kor4;
	vekt2 fejr; // kor1-bol Kor12Fejr fuggveny allitja elo (leptet.h)!
	int hatra_f;
	int hatra_h;
	int gravirany; // 1 a normalis (0:UP 1:DOWN 2:LEFT 3:RIGHT)
	//double labalfa; Bicigli

	vekt2 vezetor, vezetov; // Motoros

	int kajaszam; // hanyat evett ez a motoros

	// Leptet ezeket is hasznalja:
	int voltfek;
	double dfek2, dfek4;

	int ugrasban1, ugrasban2;
	double ugras1kezd, ugras2kezd;
	double kezdoomega1, kezdoomega2;
};

extern motorst *Pmot1, *Pmot2;

// reorder.h-ban friend-kent mar deklaralva van:
// pgazhatra-ba beepiti betoltvet:
class recorder;
void berakrecbehosszat( recorder* prec );
// pgazhatra alapjan ellenorzi hosszt:
int jorechossza( recorder* prec );