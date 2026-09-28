
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

// Jatek es visszajatszas kozben, ket kep kozott: ha a kivant nagyitas (vagy a
// texturak, fu nagyitasa) mas, mint amivel az LGR es az ecsetek keszultek,
// ujratolti es ujraepiti oket (az objektumok allapota marad, az ido nem
// szamit jatekidonek):
void nagyitasvaltas( void );
// Editorba visszateresre (editplay): Arany es az LGR ujra az eredeti meretu,
// a palya sprite-jainak merete is ahhoz igazodik:
void editornagyitas( void );
// Jatek kozbeni nagyitas ujraepitese kozben hang()-ot hiv (LGR betoltes,
// ecset epites), hogy ne szakadjon meg a hang, kulonben semmit:
void ujraepiteshang( void );

void dialogselejtez( void );


