// m_dd.h
 
class pic8;
class palyaleiro;
class recorder;

class ddpal {
	friend void lassufizre( pic8* ppic, ddpal* ppal );
public:
	#ifdef W_95
		void* pddpal;
	#else
		unsigned char* tomb;
	#endif

	ddpal( unsigned char* tomb );
	~ddpal( void );
	void set( void );
};

// Ha igaz, alulrol indul y (kirajz320 allitja igazba):
extern int Locky0_alul; 

// The game's picture (kirajzol320) is its own xsize*ysize picture, lockbackbuffer
// returns ysize row pointers (reversed when Locky0_alul). The menus', dialogs'
// and the editor's picture (lockfrontbuffer) is always 640x480 and stays
// unchanged between draws.
unsigned char** lockbackbuffer( int fizikai );
void unlockbackbuffer( void ); // Also presents it
// The size of the picture given by the next lockbackbuffer, valid while
// locked. Can only change between two pictures, at least 640x480, at most
// MAXKEPXSIZE*MAXKEPYSIZE (kirajzol.h):
void backbuffersize( int* xsize, int* ysize );

unsigned char** lockfrontbuffer( void );
void unlockfrontbuffer( void );
// Size of the menus' picture (front buffer): dd_menumeret is the platform's
// suggestion for the window (at least 640x480, texts stay on 1:1 pixels),
// frontbuffermeret sets it, the next lockfrontbuffer already gives a picture
// this size (called by menukep.cpp menumeretbeallit):
void dd_menumeret( int* xsize, int* ysize );
void frontbuffermeret( int xsize, int ysize );

// How the picture is scaled in the window, settable in the Options menu.
// Returns NULL if not settable on the platform (terminal, SDL 1.2):
const char* dd_scale_name( void );
void dd_next_scale( void ); // Switches to the next mode and saves it

// Aspect ratio of the game picture (screen's or 4:3), settable in the
// Options menu, valid from the next picture. Returns NULL if not settable
// on the platform (terminal, SDL 1.2):
const char* dd_aspect_name( void );
void dd_next_aspect( void ); // Switches to the other one and saves it

// Resolution of the game picture (how many pixels for the same part),
// settable in the Options menu, valid from the next level. NULL if not
// settable:
const char* dd_resolution_name( void );
void dd_next_resolution( void ); // Switches to the next one and saves it


// Size of the bike on the screen (zoom): 1 is the original, NAGYITASMIN..
// NAGYITASMAX (adatok.h). Takes effect when the next level loads, and
// during the game immediately with the zoom keys (load.cpp). Always 1 in
// the terminal:
double dd_zoom( void );
void dd_set_zoom( double zoom ); // Saves it (in-game keys)
// True if the textures (both sky and ground) also scale when zooming,
// otherwise they stay original pixel size:
int dd_zoom_textures( void );
// True if the grass pictures (qup_, qdown_, qgrass) also scale when zooming:
int dd_zoom_grass( void );
// DIK code of the zoom-in (nagyit true) and zoom-out key during the game
// and replay, 0 if none:
int dd_zoom_key( int nagyit );
// Options menu rows (Zoom, Zoom Textures). Return NULL if not settable on
// the platform (terminal, SDL 1.2):
const char* dd_zoom_name( void );
void dd_next_zoom( void ); // Switches to the next zoom level and saves it
const char* dd_zoom_textures_name( void );
void dd_next_zoom_textures( void ); // Switches to the other one and saves it
// Filter of the scaled pictures (szuro.h: SZURO_HQX, SZURO_SIMA,
// SZURO_LEGKOZELEBBI) and its Options menu row (NULL if not settable):
int dd_texture_filter( void );
const char* dd_texture_filter_name( void );
void dd_next_texture_filter( void ); // Switches to the next one and saves it

