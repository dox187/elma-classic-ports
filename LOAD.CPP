#include	"all.h"

int Volttopsave = 0;

static char Bentlevelnev[20] = "";

// True while the in-game zoom is changing (ujraepiteshang):
static int Ujraepites = 0;

void ujraepiteshang( void ) {
	if( Ujraepites )
		hang();
}

// Reloads the LGR and rebuilds the brushes for a different zoom (Ptop and
// Pszak stay). Ptop's wheels must not be upside down:
static void ujranagyit( void ) {
	beallitarany( 1 );
	loadlgrfile( Ptop->lgrnev );
	Ptop->pic_selejtez( Plgr );
	betoltecseteket();
}

// Beolvas egy level-t ha kell (nev max 12 karakter).
// Torli es kitolti Ptop, Plgr, Pszak, ecset mutatokat.
// Ha belso file-ban is megvan palya onnan veszi:
// Hamissal ter vissza, ha hibas topologiaju level:
int floadlevel_p( char* nev ) {
	if( !nev )
		hiba( "floadlevel_p-ben !nev!" );
	// A collection's level names can be longer than 8.3 (tutorial01.lev):
	if( strlen( nev ) > 15 || !nev[0] )
		hiba( "floadlevel_p-ben strlen( nev ) > 15 || !nev[0]!: ", nev );
	if( Volttopsave || !Ptop || !Pszak || strcmpi( nev, Bentlevelnev ) != 0 ) {
		Volttopsave = 0;
		// Ujra be kell olvasni palyat:
		strcpy( Bentlevelnev, nev );
		if( Ptop )
			delete Ptop;
		Ptop = new topol( nev );
		if( Ptop->hibas ) {
			// Kiir hiba uzenetet:
			szoveglista szl;
			szl.addszoveg_kozep( "Level file has some topology errors!", 320, 190 );
			szl.addszoveg_kozep( "Use the editor to fix them!", 		320, 240 );
			mk_emptychar();
			while( 1 ) {
				if( mk_kbhit() ) {
					int c = mk_getextchar();
					if( c == MK_ESC || c == MK_ENTER )
						break;
				}
				szl.kirajzol();
			}

			delete Ptop;
			Ptop = NULL;
			return 0;
		}
		// The game runs at the desired zoom, with the LGR scaled to it:
		beallitarany( 1 );
		loadlgrfile( Ptop->lgrnev );
		Ptop->pic_selejtez( Plgr );

		if( Pszak )
			delete Pszak;
		Pszak = new szakaszok( Ptop );
		if( Fejsugar > Pmot1->kor2.sugar )
			Pszak->rendez( Fejsugar );
		else
			Pszak->rendez( Pmot1->kor2.sugar );

		betoltecseteket();
	}
	else {
		// Same level, but the zoom has changed since (Options), or the
		// editor loaded the LGR at its original size:
		if( maskellarany() || !lgrnagyitasjo() )
			ujranagyit();
	}
	return 1;
}

void nagyitasvaltas( void ) {
	if( !Ptop || !Pszak )
		hiba( "nagyitasvaltas !Ptop || !Pszak!" );
	if( !maskellarany() && lgrnagyitasjo() )
		return;
	// The time spent rebuilding does not count as game time:
	mv_pausestopper( 1 );
	Ujraepites = 1;
	hang();
	// We compute the food's whole coordinates (kitoltfoodkoordokat) with
	// upright wheels:
	int fejjellefele = Ptop->kerekekfejjellefele;
	Ptop->kerekjolalljon();
	ujranagyit();
	if( fejjellefele )
		Ptop->kereklefejjel();
	// kirajzol320 puts the frame back in place again:
	Kitoltestmegrak = Kitoltestmegrakkezd;
	hang();
	Ujraepites = 0;
	mv_pausestopper( 0 );
}

void editornagyitas( void ) {
	if( !Ptop )
		return;
	if( Arany == Aranyalap && Plgr && Plgr->megfelel( 1.0, 1.0, 1.0 ) )
		return;
	beallitarany( 0 );
	loadlgrfile( Ptop->lgrnev );
	Ptop->pic_selejtez( Plgr );
}


// Torli es kitolti Ptop, Plgr, mutatokat.
// Pszak, ecset mutatokat torli:
// Ha belso file-ban is megvan palya onnan veszi:
// Igaz ha file nem volt lezarva, kulonben new palya hamissal:
int floadlevel_e( char* nev, int forceload ) {
	int levoltzarva = 0;

	// The editor always works at the original size, with an unscaled LGR:
	beallitarany( 0 );

	if( !nev )
		hiba( "floadlevel_e-ben !nev!" );
	if( strlen( nev ) > 12 || !nev[0] )
		hiba( "floadlevel_e-ben strlen( nev ) > 12 || !nev[0]!: ", nev );
	if( forceload || Volttopsave || !Ptop || Ptop->lezart ||
							strcmpi( nev, Bentlevelnev ) != 0 ) {
		Volttopsave = 0;
		// Ujra be kell olvasni palyat:
		strcpy( Bentlevelnev, nev );
		if( Ptop )
			delete Ptop;
		if( strcmpi( nev, "_uj_topol_" ) == 0 ) {
			Ptop = new topol;
			Bentlevelnev[0] = 0;
		}
		else
			Ptop = new topol( nev );

		if( Ptop->lezart ) {
			levoltzarva = 1;

			char szoveg[80];
			sprintf( szoveg, "The file '%s' is locked, you cannot edit it!",
												State->editfilenev );

			dialog( szoveg );
			delete Ptop;
			Ptop = new topol;
		}

		loadlgrfile( Ptop->lgrnev );
		if( Ptop->pic_selejtez( Plgr ) )
			dialogselejtez();
	}
	else
		// The level stayed after the game, but the LGR may be scaled:
		editornagyitas();
	Ptop->checklevelforsarvari();

	if( Pszak ) // ervenytelenites
		delete Pszak;
	Pszak = NULL;

	// Ha vannak benne idok, figyelmeztetes:
	if( Ptop->idok.singleidok.idokszama > 0 ||
		Ptop->idok.multiidok.idokszama > 0 )
		dialog( "Warning!",
				"The level file you are opening has some best times.",
				"If you save this level file, these times will be erased!" );

	return !levoltzarva;
}


// Opciok minibike-ja hasznalja:
void invalidate_ptop( void ) {
	if( Ptop ) {
		delete Ptop;
		Ptop = 0;
	}
}

void dialogselejtez( void ) {
dialog( "The LGR file has changed since the last edition of this level and",
		"some parts (pictures, textures or border polygons) of the level",
		"must have been deleted!",
		"",
		"!!!!IMPORTANT!!!!",
		"If you do not want to loose these parts, do not save this level",
		"on its original name!" );
}

