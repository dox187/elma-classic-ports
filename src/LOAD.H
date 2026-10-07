
extern int Volttopsave;

// Beolvas egy level-t ha kell.
// Torli es kitolti Ptop, Plgr, Pszak, ecsetek mutatokat:
// Ha belso file-ban is megvan palya onnan veszi:
// Hamissal ter vissza, ha hibas topologiaju level:
int floadlevel_p( char* nev );

// Beolvas egy level-t ha kell.
// Torli es kitolti Ptop, Plgr, mutatokat:
// Pszak es ecseteket torli:
// Ha belso file-ban is megvan palya onnan veszi:
// Igaz ha file nem volt lezarva, kulonben new palya hamissal:
int floadlevel_e( char* nev, int forceload = 0 );
// Ha nevnek _uj_topol_-t adunk meg, ujat csinal

// Opciok minibike-ja hasznalja:
void invalidate_ptop( void );

// During the game and replay, between two pictures: if the desired zoom (or
// the texture/grass scaling) differs from what the LGR and the brushes were
// built with, reloads and rebuilds them (the objects' state stays, the time
// does not count as game time):
void nagyitasvaltas( void );
// For returning to the editor (editplay): Arany and the LGR are back at the
// original size, the level's sprite sizes follow that too:
void editornagyitas( void );
// Calls hang() while rebuilding the in-game zoom (LGR loading, brush
// building), so the sound does not break, otherwise does nothing:
void ujraepiteshang( void );

void dialogselejtez( void );


