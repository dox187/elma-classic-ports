#include "all.h"

// Regen a file vegen volt egy kikomentezett eget keszit nevu fuggveny is
// hegyekhez, de ezt 99.05.19-en kiszedtem.

//#define FFECSET // Ha definialva, fekete-feheren rajzol

//#define KIIRDARABOT

int Kisordarabszam = 0;

//static pic8* Egtmp = NULL;
//static pic8* Hegy1 = NULL;
//static pic8* Hegy2 = NULL;

ecset* Pecsetalso = NULL;
ecset* Pecsetfelso = NULL;
ecset* Pecsetview = NULL;

#define PIXELMASZK    (~(uintptr_t)0x7ff) // also 2048 hely ures


/*void vizsgal( ecset* pecset ) {

	mdarab* futo = pecset->msorok[1071];
	int xtomb[40];
	int muttomb[40];
	int kurx = 1;
	int i = 0;
	while( futo ) {
		if( i > 38 )
			hiba( "i > 38!" );

		xtomb[i] = kurx;
		muttomb[i] = (int)futo->pixelek;

		kurx += futo->xsize;

		i++;
		futo = futo->pkov;
	}

	semmi();
}*/

static void hibanincsmem( void ) {
	uzenet( "You do not have enough memory to load this level!",
			"Try to set the graphich detail to low at the options." );
}

mdarab* ecset::newmdarab( void ) {
	if( tombbenkov >= TOMBBENMDARAB ) {
		// Ez a tomb betelt:
		tombbenkov = 0;
		kurtomb->kovtomb = new mdarabtomb;
		if( !kurtomb->kovtomb )
			hibanincsmem();
		kurtomb = kurtomb->kovtomb;
		kurtomb->kovtomb = NULL;
		tombbenkov++;
		mdarab* ret = &kurtomb->tomb[tombbenkov-1];
		ret->tavolsag = 0;
		return ret;
	}
	tombbenkov++;
	mdarab* ret = &kurtomb->tomb[tombbenkov-1];
	ret->tavolsag = 0;
	return ret;
}

static void meghelyez( double* pd, double arany ) {
	int pixel = *pd * arany;
	*pd = (pixel+0.5)/arany;
}

// The original game's Arany (initadatok, 100.0*0.48):
#define EREDETIARANY (48.0)

void ecset::getorigoandsize( void ) {
	// Megkeresi burkolokat:
	Pszak->felsorolasresetszak();
	vonal* psz = Pszak->getnextszak();
	if( !psz )
		hiba( "Nincs egyetlen szakasz sem definialva!" );
	double minx = psz->r.x;
	double maxx = psz->r.x;
	double miny = psz->r.y;
	double maxy = psz->r.y;
	while( psz ) {
		if( psz->r.x < minx )
			minx = psz->r.x;
		if( psz->r.x > maxx )
			maxx = psz->r.x;
		if( psz->r.y < miny )
			miny = psz->r.y;
		if( psz->r.y > maxy )
			maxy = psz->r.y;

		if( psz->r.x+psz->v.x < minx )
			minx = psz->r.x+psz->v.x;
		if( psz->r.x+psz->v.x > maxx )
			maxx = psz->r.x+psz->v.x;
		if( psz->r.y+psz->v.y < miny )
			miny = psz->r.y+psz->v.y;
		if( psz->r.y+psz->v.y > maxy )
			maxy = psz->r.y+psz->v.y;

		psz = Pszak->getnextszak();
	}

	// The edges are the same size in meters at every zoom (10000, 4000 and
	// 1000 pixel with the original Arany), so the same pictures fall into
	// them, and the textures start at the same place in the world:
	if( view ) {
		// VIEW VIEW VIEW VIEW VIEW VIEW VIEW VIEW VIEW VIEW
		// x-re jol ra lehet hagyni, nem noveli memoria foglalast:
		origo = vekt2( minx-10000/Aranyalap, miny-4000/Aranyalap );
		xsizedb = (maxx+10000/Aranyalap)-origo.x;
		ysizedb = (maxy+4000/Aranyalap)-origo.y;
	}
	else {
		// x-re jol ra lehet hagyni, nem noveli memoria foglalast:
		origo = vekt2( minx-10000/Aranyalap, miny-1000/Aranyalap );
		// Beallitjuk ugy, hogy mindig pixel felezo helyen legyen origo:
		meghelyez( &origo.x, Arany );
		meghelyez( &origo.y, Arany );

		xsizedb = (maxx+10000/Aranyalap)-origo.x;
		ysizedb = (maxy+1000/Aranyalap)-origo.y;

		// The same with the original Arany, for kilogna (ecset::ecset
		// computes maxx and sorszam this way):
		eredetiorigo = vekt2( minx-10000/EREDETIARANY, miny-1000/EREDETIARANY );
		meghelyez( &eredetiorigo.x, EREDETIARANY );
		meghelyez( &eredetiorigo.y, EREDETIARANY );
		eredetimaxx = ((maxx+10000/EREDETIARANY)-eredetiorigo.x)*EREDETIARANY;
		eredetisorszam = ((maxy+1000/EREDETIARANY)-eredetiorigo.y)*EREDETIARANY;
	}
}

void ecset::addszakasz( vonal* psz ) {
	// The map (view) is not zoomed:
	double arany = Arany;
	if( view )
		arany = Aranyalap;
	vekt2 r, v;
	r = psz->r-origo;
	r.x *= arany;
	r.y *= arany;
	v.x = psz->v.x*arany;
	v.y = psz->v.y*arany;
	if( view ) {
		double szorzo = 1.0/Viewzoom;
		r.x *= szorzo;
		r.y *= szorzo;
		v.x *= szorzo;
		v.y *= szorzo;
	}

	// Egy kicsit modositjuk palyat, hogy motoros egyforman erintse talajt,
	// ha kulonbozo iranyokban all:
	r.x -= 0.5;
	r.y -= 0.5;

	int foldjon = v.y < 0;

	// Alulrol felfele mutasson:
	if( v.y < 0 ) {
		r = r+v;
		v = Vekt2null-v;
	}
	// Nem vizszintes-e?:
	if( v.y < 0.001 )
		return;
	int y1 = r.y+1;
	int y2 = r.y+v.y;

	/*double kozelseg = 0.000001;
	if( fabs( double( y1 )-(r.y+1) ) < kozelseg )
			hiba( "Nagyon kozeli pont!" );
	if( fabs( double( y2 )-(r.y+v.y) ) < kozelseg )
			hiba( "Nagyon kozeli pont!" );*/

	// Egyenes egyenletenek parameterei:
	double m = v.x/v.y;
	double dy1 = r.y;
	double dy2 = r.y+v.y;
	double dx1 = r.x;
	double dx2 = r.x+v.x;
	double a = (dx2*dy1-dx1*dy2)/(dy1-dy2);
	for( int y = y1; y <= y2; y++ ) {
		int x = m*y+a+1.0;
		//if( fabs( double(x)-m*y+a+1.0 ) < kozelseg )
		//	hiba( "Nagyon kozeli pont!" );

		// Hozzacsapjuk hatar pontot sorhoz:
		if( y < 10 || y >= sorszam )
			hiba( "ecset::addszakasz y < 10 || y >= sorszam!" );
		if( x < 10 || x > maxx )
			hiba( "ecset::addszakasz x < 10 || x > maxx!" );

		mdarab* pmd = newmdarab();
		pmd->pkov = NULL;
		pmd->xsize = x;
		if( foldjon )
			pmd->pixelek = (unsigned char*)PX_FOLD;
		else
			pmd->pixelek = (unsigned char*)PX_EG;

		mdarab* pfut = msorok[y];
		if( !pfut )
			hiba( "ecset::addszakasz !pfut!" );
		while( pfut->pkov )
			pfut = pfut->pkov;
		pfut->pkov = pmd;
	}
}

static int sizeraallit( mdarab* elso ) {
	int eleje = elso->xsize;
	mdarab* futo = elso;
	while( futo ) {
		if( futo->pkov )
			futo->xsize = futo->pkov->xsize - futo->xsize;
		else
			futo->xsize = 1000000;

		futo = futo->pkov;
	}
	return eleje;
}

static void rendez( mdarab* elso ) {
	// Megszamoljuk elemeket:
	int szam = 0;
	mdarab* futo = elso;
	while( futo ) {
		futo = futo->pkov;
		szam++;
	}
	if( szam <= 0 )
		hiba( "(ecset) rendez-ben szam <= 0!" );

	if( szam < 2 )
		return;

	// Sorba rendezunk:
	for( int j = 0; j < szam+2; j++ ) {
		futo = elso;
		futo = futo->pkov;
		while( futo->pkov ) {
			mdarab* pkov = futo->pkov;
			if( futo->xsize > pkov->xsize ) {
				// Csere:
				int tmp = futo->xsize;
				futo->xsize = pkov->xsize;
				pkov->xsize = tmp;
				unsigned char* ptmp = futo->pixelek;
				futo->pixelek = pkov->pixelek;
				pkov->pixelek = ptmp;
			}
			futo = pkov;
		}
	}
	// Kikuszoboljuk egy x-en fekvo mdarab-okat:
	mdarab* futoelozo = elso;
	futo = futoelozo->pkov;
	while( futo->pkov ) {
		mdarab* pkov = futo->pkov;
		if( futo->xsize == pkov->xsize ) {
			if( futo->pixelek == pkov->pixelek ) {
				// Azonosak, csak az egyiket vesszuk ki (pkov-et):
				futo->pkov = pkov->pkov;
			}
			else {
				// Kulonbozoek, mindkettot kiszedjuk:
				futoelozo->pkov = pkov->pkov;
			}
			// Visszaallunk lanc legelejere:
			futoelozo = elso;
			futo = futoelozo->pkov;
			if( !futo )
				return;
		}
		else {
			// Nem volt x-juk azonos, megyunk tovabb:
			futoelozo = futo;
			futo = pkov;
		}
	}

	// Kikuszoboljuk egymas utan fekvo, ugyanazt jelenot mdarab-okat:
	futo = elso;
	while( futo->pkov ) {
		mdarab* pkov = futo->pkov;
		if( futo->pixelek == pkov->pixelek ) {
			futo->pkov = pkov->pkov;
			// Visszaallunk lanc legelejere:
			futo = elso;
		}
		else {
			// Nem voltak azonosak, megyunk tovabb:
			futo = pkov;
		}
	}
}

// Rovid folddarabokat atalakitja konkret mutatova:
void ecset::foldmutatocsere( void ) {
	for( int i = 0; i < sorszam; i++ ) {
		mdarab* fut = msorok[i];
		int xpos = kurxposok_A[i];
		if( xpos > 100 )
			hiba( "ecset::foldmutatocsere xpos > 100!" );
		while( fut ) {
			if( (uintptr_t)fut->pixelek == PX_FOLD && fut->xsize < 640 ) {
				int x = xpos%Plgr->foldxmodulus;
				int y = i%Plgr->pfold->getysize();
				fut->pixelek = Plgr->pfold->getptr( y ) + x;
				//fut->pixelek = Plgr->pfold->getptr( 0 ); igy latszik
			}

			xpos += fut->xsize;
			fut = fut->pkov;
		}
	}
}

// Egymas utani azonos texturakat es ureseket lecsereli egy hosszabbra:
void ecset::duplaeliminacio( void ) {
	for( int i = 0; i < sorszam; i++ ) {
		int voltvaltozas = 1;
		while( voltvaltozas ) {
			voltvaltozas = 0;
			mdarab* fut = msorok[i];
			while( fut && fut->pkov) {
				mdarab* kov = fut->pkov;
				if( ((uintptr_t)fut->pixelek & PIXELMASZK) == 0 &&
					fut->pixelek == kov->pixelek ) {
					fut->pkov = kov->pkov;
					fut->xsize += kov->xsize;
					voltvaltozas = 1;
				}

				fut = fut->pkov;
			}
		}
	}
}

void ecset::textura2mutato( void ) {
	for( int y = 0; y < sorszam; y++ ) {
		if( y == 992 )
			semmi();
		mdarab* fut = msorok[y];
		int xpos = kurxposok_A[y];
		if( xpos > 100 )
			hiba( "9865fd" );
		while( fut ) {
			mdarab* kov = fut->pkov;
			int hozzaad = fut->xsize;

			intptr_t kepindex = (intptr_t)fut->pixelek;
			if( ((kepindex & PIXELMASZK) == 0) && (kepindex >= 10) ) {
				kepindex -= 10;
				// Itt van maszk, le kell cserelni:
				#ifdef TEST
					if( kepindex >= Plgr->texturaszam )
						hiba( "ecset::maszkokkitoltese kepindex >= Plgr->kepszam!" );
					if( Plgr->texturak[kepindex].origxsize <= 0 )
						hiba( "7ywijohg!" );
				#endif
				textura* pt = &Plgr->texturak[kepindex];
				pic8* ppic = pt->ppic;
				int megvan = fut->xsize;
				int x = xpos;
				int elso = 1;
				while( megvan > 0 ) {
					if( !elso ) {
						// Beillesztunk egy uj mdarab-ot:
						mdarab* ujdarab = newmdarab();
						ujdarab->pkov = fut->pkov;
						fut->pkov = ujdarab;
						fut = ujdarab;
					}
					elso = 0;

					x %= pt->origxsize;
					int size = megvan;
					if( x + size > ppic->getxsize() )
						size = ppic->getxsize() - x;

					fut->xsize = size;
					fut->pixelek = ppic->getptr( y%ppic->getysize() ) + x;
					if( ((uintptr_t)fut->pixelek & PIXELMASZK) == 0 )
						uzenet( "Memory address is less than 2048 (723)!" );

					x += size;
					megvan -= size;
				}
			}
			xpos += hozzaad;
			fut = fut->pkov;
		}
	}
}

static int megszamol( mdarab* elso ) {
	// Megszamoljuk elemeket:
	int szam = 0;
	mdarab* futo = elso;
	while( futo ) {
		futo = futo->pkov;
		szam++;
	}
	if( szam <= 0 )
		hiba( "(ecset) megszamol-ban szam <= 0!" );
	return szam;
}

int Osszegszam = 0;

void ecset::mutatotlanit( void ) {
	// Megszamoljuk osszes mdarab-ot:
	int szam = 0;
	int i;
	for( i = 0; i < sorszam; i++ )
		szam += megszamol( msorok[i] );
	Osszegszam += szam;
	// Most lefoglaljuk uj egybefuggo tombot:
	nagydarabtomb = new darab[szam+10];
	if( !nagydarabtomb )
		hibanincsmem();
	int szammost = 0;
	for( i = 0; i < sorszam; i++ ) {
		if( i == 1000 )
			semmi();
		if( i == 7792 )
			semmi();
		mdarab* futo = msorok[i];
		sorok[i] = &nagydarabtomb[szammost];
		curdarabok_A[i] = sorok[i];
		curdarabok_B[i] = sorok[i];
		while( futo ) {
			nagydarabtomb[szammost].xsize = futo->xsize;
			nagydarabtomb[szammost].pixelek = futo->pixelek;

			futo = futo->pkov;
			szammost++;
		}
	}
}

// Ptop kerek-jeinek egesz koordinatait kitolti:
void ecset::kitoltfoodkoordokat( void ) {
	for( int i = 0; i < MAXKEREK; i++ ) {
		kerek* pker = Ptop->kerektomb[i];
		if( !pker )
			continue;
		if( view ) {
			pker->rxint_v = (pker->r.x-origo.x)*Aranyalap/Viewzoom;
			pker->ryint_v = (-pker->r.y-origo.y)*Aranyalap/Viewzoom;
		}
		else {
			// Bottom left corner of the zoomed object picture:
			pker->rxint = (pker->r.x-origo.x)*Arany-Plgr->objektumsugar;
			pker->ryint = (-pker->r.y-origo.y)*Arany-Plgr->objektumsugar;
		}
	}
}

enum { FAZIS_FOLD, FAZIS_EG, FAZIS_NEMFOLDEG, FAZIS_URESRE };

mdarab* ecset::beepitegymadarabnyit( mdarab* pmd, unsigned char* ujpixelek,
			int x1, int ujx1, int ujx2,
			int ujtavolsag, mdarab* vege, int* pujavege, int fazis ) {

	if( (uintptr_t)ujpixelek == PX_URES )
		hiba( "ecset::beepitegymadarabnyit-ban nem lehet ureset rarakni!" );

	if( (uintptr_t)pmd->pixelek == PX_URES && fazis != FAZIS_URESRE )
		hiba( "ecset::beepitegymadarabnyit-ban",
			  "(uintptr_t)ujpixelek == PX_URES && fazis != FAZIS_URESRE!" );

	// Eldontjuk, hogy ki kell-e egyaltalan rakni:
	int regitav = pmd->tavolsag;
	int nemrakjaki = 0;
	if( fazis == FAZIS_FOLD ) {
		if( (uintptr_t)pmd->pixelek == PX_FOLD )
			regitav = 1000000;
		if( (uintptr_t)pmd->pixelek == PX_EG )
			nemrakjaki = 1;
	}
	if( fazis == FAZIS_EG ) {
		ujtavolsag += 10000;
		if( (uintptr_t)pmd->pixelek == PX_FOLD )
			nemrakjaki = 1;
		if( (uintptr_t)pmd->pixelek == PX_EG ) {
			regitav = 1000000;
		}
	}
	if( fazis == FAZIS_NEMFOLDEG )
		if( (uintptr_t)pmd->pixelek == PX_FOLD || (uintptr_t)pmd->pixelek == PX_EG )
			regitav = 1000000;

	if( fazis == FAZIS_URESRE ) {
		if( (uintptr_t)pmd->pixelek == PX_FOLD || (uintptr_t)pmd->pixelek == PX_EG )
			hiba( "ecset::beepitegymadarabnyit fazis == FAZIS_LYUKRA, megis fold vagy eg!" );
		if( (uintptr_t)pmd->pixelek == PX_URES )
			regitav = 1000000;
	}

	if( nemrakjaki || ujtavolsag >= regitav ) {
		*pujavege = 0;
		return pmd;
	}

	// Most mar biztos, hogy kirakjuk:
	int x2 = x1 + pmd->xsize-1;
	// Levagdossuk ujx1, ujx2-t:
	if( ujx1 < x1 )
		ujx1 = x1;
	if( ujx2 > x2 )
		ujx2 = x2;
	if( ujx2 < x1 || ujx1 > x2 )
		hiba( "ecset::beepitegymadarabnyit ujx2 < x1 || ujx1 > x2!" );

	// Most kivalasztjuk melyik esettel allunk szemben:

	//  ------------------------------------
	//  I              XXXXXXXXXXXXXXXXXXXXI
	//  ------------------------------------

	if( x1 != ujx1 && x2 == ujx2 ) {
		mdarab* puj = newmdarab();
		puj->xsize = ujx2-ujx1+1;
		puj->pixelek = ujpixelek;
		puj->tavolsag = ujtavolsag;
		puj->pkov = pmd->pkov;

		pmd->xsize -= puj->xsize;
		pmd->pkov = puj;

		*pujavege = 1;
		return puj;
	}

	//  ------------------------------------
	//  IXXXXXXXXXXXXXXXXXXXX              I
	//  ------------------------------------

	if( x1 == ujx1 && x2 != ujx2 ) {
		if( !vege )
			hiba( "8796kuyg76" );
		// Ha minden megfelel, atallitjuk *pujavege-t:
		if( !(*pujavege) &&
			vege->tavolsag == ujtavolsag &&
			!((uintptr_t)vege->pixelek & PIXELMASZK) &&
			vege->pixelek == ujpixelek )
			*pujavege = 1;
		if( *pujavege ) {
			int ujsize = ujx2-ujx1+1;

			vege->xsize += ujsize;
			pmd->xsize  -= ujsize;
			if( (uintptr_t)pmd->pixelek & PIXELMASZK )
				pmd->pixelek += ujsize;

			*pujavege = 0;
			return pmd;
		}
		else {
			mdarab* puj = newmdarab();
			vege->pkov = puj;

			puj->xsize = ujx2-ujx1+1;
			puj->pixelek = ujpixelek;
			puj->tavolsag = ujtavolsag;
			puj->pkov = pmd;

			pmd->xsize -= puj->xsize;
			if( (uintptr_t)pmd->pixelek & PIXELMASZK )
				pmd->pixelek += puj->xsize;

			*pujavege = 0;
			return pmd;
		}
	}

	//  ------------------------------------
	//  IXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXI
	//  ------------------------------------

	if( x1 == ujx1 && x2 == ujx2 ) {
		if( !vege )
			hiba( "6fg67r57fu6t" );
		// Ha minden megfelel, atallitjuk *pujavege-t:
		if( !(*pujavege) &&
			vege->tavolsag == ujtavolsag &&
			!((uintptr_t)vege->pixelek & PIXELMASZK) &&
			vege->pixelek == ujpixelek )
			*pujavege = 1;
		if( *pujavege ) {
			vege->xsize += pmd->xsize;
			vege->pkov = pmd->pkov;

			*pujavege = 1;
			return vege;
		}
		else {
			pmd->pixelek = ujpixelek;
			pmd->tavolsag = ujtavolsag;

			*pujavege = 1;
			return pmd;
		}
	}

	//  ------------------------------------
	//  I             XXXXXXXXXXXX         I
	//  ------------------------------------

	if( x1 != ujx1 && x2 != ujx2 ) {
		mdarab* puj1 = newmdarab();
		mdarab* puj2 = newmdarab();

		puj1->xsize = ujx2-ujx1+1;
		puj1->pixelek = ujpixelek;
		puj1->tavolsag = ujtavolsag;
		puj1->pkov = puj2;

		puj2->xsize = x2-ujx2;
		if( (uintptr_t)pmd->pixelek & PIXELMASZK )
			puj2->pixelek = pmd->pixelek + (ujx2+1 - x1);
		else
			puj2->pixelek = pmd->pixelek;
		puj2->tavolsag = pmd->tavolsag;
		puj2->pkov = pmd->pkov;

		pmd->xsize -= puj1->xsize + puj2->xsize;
		pmd->pkov = puj1;

		*pujavege = 0;
		return puj2;
	}

	hiba( "ecset::beepitegymadarabnyit nem talalta meg esetet!" );
	return NULL;
}

//static mdarab* Pmddd = NULL;

void ecset::addbytesor( unsigned char* ujpixelek, int ujtavolsag,
								int ujx1, int ujx2, int y, int fazis ) {
	//if( y != 1039 )
	//	return;

	// Rows outside the ecset and pieces sticking out to the left are left
	// out (grass polygons are not in Pszak, so they can stick out of it):
	if( y < 0 || y >= sorszam )
		return;
	if( ujx2 < kurxposok_A[y] )
		return;

	// Beallunk pmd, xpos-sal elso szoba jovo madarab-ra:
	// Visszalepunk amig kell:
	mdarab* pmd = msorok[y];
	//Pmddd = pmd;
	int xpos = kurxposok_A[y];
	if( xpos > 10 )
		hiba( "ecset::addbytesor xpos > 10!" );
	// Elorelepunk amig kell:
	mdarab* vege = NULL;
	while( xpos + pmd->xsize - 1 < ujx1 ) {
		xpos += pmd->xsize;
		vege = pmd;
		pmd = pmd->pkov;
		if( !pmd )
			hiba( "ecset::addbytesor !pmd (1)!" );
	}
	// Most rajta allunk elso mdarabon:
	int ujavege = 0;
	while( 1 ) {
		if( !pmd )
			hiba( "ecset::addbytesor !pmd (2)!" );
		int x1 = xpos;
		int x2 = xpos+pmd->xsize-1;
		if( ujx2 < x1 )
			hiba( "ecset::addbytesor ujx2 < x1!" );

		// Beallitjuk kovetkezo ertekeket:
		int kovmarnincs = 0;
		if( x2+1 > ujx2 )
			kovmarnincs = 1;

		unsigned char* kovujpixelek = ujpixelek;
		if( (uintptr_t)kovujpixelek & PIXELMASZK ) {
			int kimaradxsize = 0; // Elso mdarab eseteben lehetseges csak
			if( ujx1 > x1 )
				kimaradxsize = ujx1 - x1;
			kovujpixelek = ujpixelek + (pmd->xsize-kimaradxsize);
		}

		int kovxpos = xpos+pmd->xsize;
		mdarab* kovpmd = pmd->pkov;

		vege = beepitegymadarabnyit( pmd, ujpixelek, xpos, ujx1, ujx2,
						ujtavolsag, vege, &ujavege, fazis );

		if( kovmarnincs )
			return;
		ujpixelek = kovujpixelek;
		xpos = kovxpos;
		pmd = kovpmd;
	}
}

// Visszaadja hany pixel lyuk szinu x-tol kezdve:
int uresszam( int x, int xsize, unsigned char* sor, unsigned char lyuk ) {
	int szam = 0;
	while( x < xsize && sor[x] == lyuk ) {
		x++;
		szam++;
	}
	return szam;
}

// Visszaadja hany pixel nem lyuk szinu x-tol kezdve:
int teliszam( int x, int xsize, unsigned char* sor, unsigned char lyuk ) {
	int szam = 0;
	while( x < xsize && sor[x] != lyuk ) {
		x++;
		szam++;
	}
	return szam;
}

// The left edge of pictures and masks must be at least this far, the right
// edge at least this far, from the ecset's edge (originally 120 and 50
// pixel, the same in meters when zoomed), addspriteok sets it:
static int Kepszelbal = 120, Kepszeljobb = 50;

// addspriteok hivja:
void ecset::addegymaszk( sprite* psp, int index_t, int index_m, int fazis ) {
	// Egy kep berakasa:
	int x1 = (psp->r.x-origo.x)*Arany;
	int y1 = (-psp->r.y-origo.y)*Arany;

	textura* pt = &Plgr->texturak[index_t];
	maszk*   pm = &Plgr->maszkok[index_m];

	int tavolsag = psp->tavolsag;

	int xsize = pm->xsize;
	int ysize = pm->ysize;

	if( x1 < Kepszelbal || x1+xsize >= maxx-Kepszeljobb )
		return;

	int i = 0;
	for( int y = 0; y < ysize; y++ ) {
		// Kep egy soranak elintezese:
		int x = 0;
		// Maszkos eljaras:
		while( pm->adatok[i].tipus != ME_SOREMELES ) {
			// We go in the negative direction on y (y1-y):
			if( pm->adatok[i].tipus == ME_TELI && y1-y >= 0 && y1-y < sorszam ) {
				addbytesor( (unsigned char*)(index_t+10), tavolsag,
					x1+x, x1+x+pm->adatok[i].hossz-1,
					y1-y, fazis );
			}
			x += pm->adatok[i].hossz;
			i++;
		}
		i++;
	}
}

void ecset::addspriteok( int fazis ) {
	Kepszelbal = nagyitpixel( 120, kepnagyitas() );
	Kepszeljobb = nagyitpixel( 50, kepnagyitas() );
	for( int j = 0; j < MAXSPRITE; j++ ) {
		sprite* psp = Ptop->spritetomb[j];
		if( !psp )
			return;
		if( j % 16 == 0 )
			ujraepiteshang();

		// Fazis fuggvenyeben csak bizonyos kepeket rakunk be:
		if( fazis == FAZIS_FOLD && psp->hatarol != HATAROL_G )
			continue;
		if( fazis == FAZIS_EG && psp->hatarol != HATAROL_S )
			continue;
		if( fazis == FAZIS_NEMFOLDEG && psp->hatarol )
			continue;

		if( psp->kepnev[0] == 0 ) {
			// Csak maszkos textura lehet, kulon intezzuk:
			if( !psp->texturanev[0] || !psp->maszknev[0] )
				continue;
			int index_t = Plgr->gettexturaindex( psp->texturanev );
			if( index_t < 0 )
				hiba( "tgferg" );
			int index_m = Plgr->getmaszkindex( psp->maszknev );
			if( index_m < 0 )
				hiba( "6t7ffrge" );

			// Ez egy maszk, innentol teljesen kulon intezzuk el:
			addegymaszk( psp, index_t, index_m, fazis );
			continue;
		}

		// Ez egy kep:
		if( psp->texturanev[0] || psp->maszknev[0] )
			hiba( "gkuhlij" );

		int index = Plgr->getkepindex( psp->kepnev );
		if( index < 0 )
			hiba( "kjhhgfchg" );
		kep* pkep = &Plgr->kepek[index];

		// Egy kep berakasa:
		int x1 = (psp->r.x-origo.x)*Arany;
		int y1 = (-psp->r.y-origo.y)*Arany;

		int ujtavolsag = psp->tavolsag;


		int xsize = pkep->xsize;
		int ysize = pkep->ysize;

		// From here on all further pictures are left out too (as originally):
		if( x1 < Kepszelbal || x1+xsize >= maxx-Kepszeljobb )
			return;

		unsigned char* tomb = pkep->adatok;

		if( ((uintptr_t)tomb & PIXELMASZK) == 0 )
			uzenet( "Memory address is less than 2048 (987)!" );

		// Vegigmegyunk kepen:
		int i = 0; // byte index tombben
		for( int y = 0; y < ysize; y++ ) {
			// Kep egy soranak elintezese:
			int x = 0;
			while( 1 ) {
				// Ures elintezes:
				int uresszam = tomb[i]*256+tomb[i+1];
				i += 2;

				if( uresszam > 60000 )
					break;

				x += uresszam;

				// Teli elintezes:
				int teliszam = tomb[i]*256+tomb[i+1];
				i += 2;

				// Negativ iranyban haladunk y-on (y1-y):
				if( y1-y >= 0 && y1-y < sorszam )
					addbytesor( &tomb[i], ujtavolsag, x1+x, x1+x+teliszam-1,
														y1-y, fazis );

				x += teliszam;
				i += teliszam;
			}
		}
	}
}

// Kovetok beillesztese:

static int getatlaatszoszam( unsigned char* sor, int x, int xsize,
									unsigned char atlatszo ) {
	int sum = 0;
	for( int i = x; i < xsize; i++ ) {
		if( sor[i] == atlatszo )
			sum++;
		else
			return sum;
	}
	return sum;
}

static int getanyagszam( unsigned char* sor, int x, int xsize,
									unsigned char atlatszo ) {
	int sum = 0;
	for( int i = x; i < xsize; i++ ) {
		if( sor[i] != atlatszo )
			sum++;
		else
			return sum;
	}
	return sum;
}


// A grass line can be this long (in ecset pixels, the same in meters when zoomed):
#define KOVVONALHOSSZ (10000)

// The grass picture's own helper picture (originally the menus' Buffsima):
static pic8* Kovetosegedkep = NULL;

void ecset::kovetotextura( koveto* pkov, int index, int xo, int yo, int fazis ) {
	// Most mindig felso:
	int felso = 1;
	int tavolsag = 600;

	char texturanev[20];
	strcpy( texturanev, "qgrass" );

	// Kikeressuk textura indexet:
	int textindex = Plgr->gettexturaindex( texturanev );
	if( textindex < 0 )
		hiba( "iygtyrt" );

	pic8* ppic = pkov->pkeptomb[index];
	int xsize = ppic->getxsize();
	int ysize = ppic->getysize();
	int y;
	unsigned char atlatszo = pkov->atlatszotomb[index];

	if( !Kovetosegedkep || Kovetosegedkep->getxsize() < xsize ||
		Kovetosegedkep->getysize() < ysize ) {
		int segedx = 640, segedy = 480;
		if( Kovetosegedkep ) {
			segedx = Kovetosegedkep->getxsize();
			segedy = Kovetosegedkep->getysize();
			delete Kovetosegedkep;
		}
		if( segedx < xsize )
			segedx = xsize;
		if( segedy < ysize )
			segedy = ysize;
		Kovetosegedkep = new pic8( segedx, segedy );
	}
	pic8* pseged = Kovetosegedkep;

	// Clear the helper picture (with row pointers, because of zoomed pictures):
	// pseged: 0 -> transparent, 1 -> has texture:
	for( y = 0; y < ysize; y++ )
		memset( pseged->getptr( y ), 0, xsize );
	// Feltoltjuk segedkepet:
	for( int x = 0; x < xsize; x++ ) {
		// Minden oszlopot kitoltunk:
		if( felso ) {
			for( int y = 0; y < ysize; y++ ) {
				if( ppic->getptr( y )[x] == atlatszo )
					pseged->getptr( y )[x] = 1;
				else
					break;
			}
		}
		else {
			for( int y = ysize-1; y >= 0; y-- ) {
				if( ppic->getptr( y )[x] == atlatszo )
					pseged->getptr( y )[x] = 1;
				else
					break;
			}
		}
	}

	// Beadjuk textura darabokat ecset-be:
	for( y = 0; y < ysize; y++ ) {
		int x = 0;
		unsigned char* sor = pseged->getptr( ysize-1-y );
		while( x < xsize ) {
			x += getatlaatszoszam( sor, x, xsize, 0 );
			if( x >= xsize )
				break;
			int anyagszam = getanyagszam( sor, x, xsize, 0 );
			if( anyagszam <= 0 ) 		hiba( "8toiurtg" );
			addbytesor( (unsigned char*)(textindex+10), tavolsag,
						xo+x, xo+x+anyagszam-1, yo+y, fazis );
			x += anyagszam;
		}
	}
	// Most beadjuk alul vagy felul megtoldott reszt is:
	int fuggtoldas = Plgr->fuggtoldas;
	if( felso ) {
		// Felso:
		for( y = 0; y < fuggtoldas; y++ ) {
			addbytesor( (unsigned char*)(textindex+10), tavolsag,
							xo, xo+xsize-1, yo+ysize+y, fazis );
		}
	}
	else {
		// Also:
		for( y = 0; y < fuggtoldas; y++ ) {
			addbytesor( (unsigned char*)(textindex+10), tavolsag,
							xo, xo+xsize-1, yo-1-y, fazis );
		}
	}
}

void ecset::kiegykovetokep( koveto* pkov, int index, int xo, int yo, int fazis ) {

	int tavolsag = 600;

	pic8* ppic = pkov->pkeptomb[index];
	int xsize = ppic->getxsize();
	int ysize = ppic->getysize();
	unsigned char atlatszo = pkov->atlatszotomb[index];
	int keltolas = Plgr->keltolas;

	// Kiszamoljuk kep tetejenek helyet:
	// (A picture going downward enters the line on its right side, where its
	// top is higher by keltolas+lejtes; without zoom, ysize-1-keltolas.)
	if( pkov->feltomb[index] )
		yo -= keltolas;
	else
		yo -= keltolas + pkov->lejtestomb[index];

	for( int y = 0; y < ysize; y++ ) {
		int x = 0;
		unsigned char* sor = ppic->getptr( ysize-1-y );
		while( x < xsize ) {
			x += getatlaatszoszam( sor, x, xsize, atlatszo );
			if( x >= xsize )
				break;
			int anyagszam = getanyagszam( sor, x, xsize, atlatszo );
			if( anyagszam <= 0 ) 		hiba( "8toiurtg" );
			addbytesor( &sor[x], tavolsag, xo+x, xo+x+anyagszam-1,
														yo+y, fazis );
			x += anyagszam;
		}
	}

	// Originally it had to fit in the 640x480 Buffsima (zoomed, the same
	// pictures get a texture):
	if( xsize > Plgr->kovetomaxx || ysize > Plgr->kovetomaxy ) {
		#ifdef TEST
			hiba( "7yfg4" );
		#endif
		return;
	}

	kovetotextura( pkov, index, xo, yo, fazis );
	//kovetotextura( 0, pkov, pgy, index, xo, yo, fazis );
}

void ecset::kikovetokepek( koveto* pkov, int* ytomb, int hossz,
													int x0, int fazis ) {
	#ifdef TEST
		if( hossz < 1 )
			hiba( "dd387d3e" );
	#else
		if( hossz < 1 )
			return;
	#endif
	int curx = x0;
	int cury = ytomb[0];
	while( 1 ) {
		if( curx >= x0+hossz )
			return; // Befejezte

		// Megkeressuk legjobb kepet:
		int elteres = 10000;
		int joindex = -1;
		int jody = 0;
		for( int i = 0; i < pkov->kepszam; i++ ) {
			int dy = pkov->lejtestomb[i];
			if( dy < 0 ) {
				char tmp[60];
				sprintf( tmp, "picture's y size is less than %d!",
							2*20+1 );
				uzenet( "In grass picture ", tmp );
			}
			if( !pkov->feltomb[i] )
				dy = -dy;

			int ujx = curx + pkov->pkeptomb[i]->getxsize();
			int vonaly;
			if( ujx >= x0+hossz )
				vonaly = ytomb[hossz-1];
			else
				vonaly = ytomb[ujx-x0];

			int ujelteres = abs( cury+dy - vonaly );

			if( ujelteres < elteres ) {
				elteres = ujelteres;
				joindex = i;
				jody = dy;
			}
		}

		// Megvan legjobb kep:
		if( joindex < 0 )
			hiba( "7f908ur5tg" );

		kiegykovetokep( pkov, joindex, curx, cury, fazis );

		curx += pkov->pkeptomb[joindex]->getxsize();
		cury += jody;
	}
}

void ecset::addkovetok( int fazis ) {
	if( !Plgr->vanfu )
		return;
	int kovvonalhossz = nagyitpixel( KOVVONALHOSSZ, kepnagyitas() );
	int* Kovetoytomb = new int[kovvonalhossz+10];
	for( int i = 0; i < MAXGYURU; i++ ) {
		gyuru* pgy = Ptop->ptomb[i];
		if( !pgy )
			break;
		if( !pgy->koveto )
			continue;
		ujraepiteshang();

		int hatarol = HATAROL_G;

		// Fazis fuggvenyeben csak bizonyos kepeket rakunk be:
		if( fazis == FAZIS_FOLD && hatarol != HATAROL_G )
			continue;
		if( fazis == FAZIS_EG && hatarol != HATAROL_S )
			continue;
		if( fazis == FAZIS_NEMFOLDEG && hatarol )
			continue;

		koveto* pkov = Plgr->pkoveto;

		int vonalhossz = 0, x0 = 0;
		if( !makevonal( pgy, Kovetoytomb, &vonalhossz, &x0,
					kovvonalhossz, &origo ) )
			continue;
		if( vonalhossz > kovvonalhossz )
			hiba( "uh9fdw" );

		// Kirajzolunk egy minta vonalat kepre:
		/*static unsigned char kovetchar = 0;
		for( int x = x0; x < x0 + vonalhossz; x++ ) {
			addbytesor( &kovetchar, 100, x, x,
						Kovetoytomb[x-x0], fazis );
		}*/

		kikovetokepek( pkov, Kovetoytomb, vonalhossz, x0, fazis );
	}
	delete[] Kovetoytomb;
}

void ecset::addobjektumok( void ) {
	if( !view )
		return;

	for( int i = 0; i < MAXKEREK; i++ ) {
		kerek* pk = Ptop->kerektomb[i];
		if( !pk )
			return;

		if( pk->tipus == T_KAJA || pk->tipus == T_KEZDO ||
				pk->tipus == T_CEL )
			continue;

		// Egy kep berakasa:
		if( view ) {
			unsigned char* mut = Plgr->viewexit;
			int ujtavolsag = 498;
			if( pk->tipus == T_HALALOS ) {
				mut = Plgr->viewkiller;
				ujtavolsag = 499;
			}
			int x1 = (pk->r.x-origo.x)*(Aranyalap/Viewzoom);
			int y1 = (-pk->r.y-origo.y)*(Aranyalap/Viewzoom);
			// Kirakja kis 3x3-as gyurut:
			addbytesor( mut, ujtavolsag, x1-1, x1+1, y1-1, FAZIS_NEMFOLDEG );
			addbytesor( mut, ujtavolsag, x1-1, x1-1, y1,   FAZIS_NEMFOLDEG );
			addbytesor( mut, ujtavolsag, x1+1, x1+1, y1,   FAZIS_NEMFOLDEG );
			addbytesor( mut, ujtavolsag, x1-1, x1+1, y1+1, FAZIS_NEMFOLDEG );

			continue;
		}


		/* Ez a resz csak nagy objektumokhoz kellene, de most csak view-val
		   foglalkozunk:
		int x1 = (pk->r.x-origo.x)*Arany;
		int y1 = (-pk->r.y-origo.y)*Arany;
		x1 -= OBJEKTUMSUGAR_I;
		y1 += OBJEKTUMSUGAR_I;

		pic8* ppic = Plgr->pexit;
		int ujtavolsag = 498;
		if( pk->tipus == T_HALALOS ) {
			ppic = Plgr->pkiller;
			ujtavolsag = 499;
		}

		int xsize = ppic->getxsize();
		int ysize = ppic->getysize();

		if( x1 < 120 || x1+xsize >= maxx-50 )
			return;

		// Van atlatszosag:
		unsigned char atlatszo = ppic->gpixel( 0, 0 );
		for( int y = 0; y < ysize; y++ ) {
			// Kep egy soranak elintezese:
			unsigned char* sor = ppic->getptr( ysize - 1 - y );
			if( ((uintptr_t)sor & PIXELMASZK) == 0 )
				uzenet( "Memory address is less than 2048 (654)!" );

			// Atugorja elso ures pixeleket:
			int x = uresszam( 0, xsize, sor, atlatszo );
			while( x <= xsize-1 ) {
				// Keresi kis szakaszokat:
				int size = teliszam( x, xsize, sor, atlatszo );
				if( size <= 0 )
					hiba( "ecset::addspriteok teliszam utan size <= 0!" );

				// Negativ iranyban haladunk y-on (y1-y):
				if( y1-y >= 0 && y1-y < sorszam )
					addbytesor( &sor[x], ujtavolsag, x1+x, x1+x+size-1,
													y1-y, FAZIS_NEMFOLDEG );
				x += size;

				// Atugorja ures pixeleket:
				x += uresszam( x, xsize, sor, atlatszo );
			}
		}*/
	}
}

void ecset::levon10000t( void ) {
	for( int i = 0; i < sorszam; i++ ) {
		mdarab* pmd = msorok[i];
		while( pmd ) {
			if( pmd->tavolsag >= 10000 )
				pmd->tavolsag -= 10000;

			pmd = pmd->pkov;
		}
	}
};

// Based on sorszam, cleared:
void ecset::lefoglalsortomboket( void ) {
	if( sorszam < 0 || sorszam > MAXECSETSOR )
		hibanincsmem();
	sortombmeret = sorszam+10;
	msorok = new mdarab*[sortombmeret];
	sorok = new darab*[sortombmeret];
	kurxposok_A = new int[sortombmeret];
	curdarabok_A = new darab*[sortombmeret];
	kurxposok_B = new int[sortombmeret];
	curdarabok_B = new darab*[sortombmeret];
	if( !msorok || !sorok || !kurxposok_A || !curdarabok_A || !kurxposok_B ||
		!curdarabok_B )
		hibanincsmem();
	for( int i = 0; i < sortombmeret; i++ ) {
		msorok[i] = NULL;
		sorok[i] = NULL;
		kurxposok_A[i] = 0;
		kurxposok_B[i] = 0;
		curdarabok_A[i] = NULL;
		curdarabok_B[i] = NULL;
	}
}

// Ptop es Pszak alapjan:
ecset::ecset( int view_p ) {
	view = view_p;

	int i;
	sortombmeret = 0;
	msorok = NULL;
	sorok = NULL;
	kurxposok_A = kurxposok_B = NULL;
	curdarabok_A = curdarabok_B = NULL;

	// Inicializaljuk elso node tombot:
	elsotomb = kurtomb = NULL;
	tombbenkov = 0;

	nagydarabtomb = NULL;

	xsizedb = ysizedb = 0.0;
	maxx = sorszam = 0;
	eredetimaxx = eredetisorszam = 0;

	if( !Ptop || !Pszak )
		hiba( "ecset::ecset !Ptop || !Pszak!" );

	elsotomb = new mdarabtomb;
	if( !elsotomb )
		hiba( "Nincs eleg memoria ecset::ecset!" );
	elsotomb->kovtomb = NULL;
	kurtomb = elsotomb;

	getorigoandsize();

	if( view ) {
		// VIEW VIEW VIEW:
		maxx = xsizedb*(Aranyalap/Viewzoom);
		sorszam = ysizedb*(Aranyalap/Viewzoom);
	}
	else {
		maxx = xsizedb*Arany;
		sorszam = ysizedb*Arany;
	}

	// The row arrays adjust to the level's height (originally they were
	// fixed 12000-row arrays, with hiba):
	lefoglalsortomboket();

	// Inicializaljuk minden sor elejet foldre:
	for( i = 0; i < sorszam; i++ ) {
		msorok[i] = newmdarab();
		msorok[i]->pkov = NULL;
		msorok[i]->xsize = 1;
		msorok[i]->tavolsag = 0;
		msorok[i]->pixelek = (unsigned char*)PX_FOLD;
	}

	// Vegigmegyunk osszes szakaszon:
	Pszak->felsorolasresetszak();
	vonal* psz = Pszak->getnextszak();
	if( !psz )
		hiba( "Nincs egyetlen szakasz sem definialva!" );
	int szakaszszam = 0;
	while( psz ) {
		addszakasz( psz );
		psz = Pszak->getnextszak();
		if( ++szakaszszam % 256 == 0 )
			ujraepiteshang();
	}

	// Sorrendbe rendezzuk egy sor elemeit:
	for( i = 0; i < sorszam; i++ ) {
		if( i % 1024 == 0 )
			ujraepiteshang();
		rendez( msorok[i] );
		kurxposok_A[i] = kurxposok_B[i] = sizeraallit( msorok[i] );
	}

	// Spriteok beadasa:
	if( !view && State->highquality ) {
		addspriteok( FAZIS_FOLD );
		addkovetok( FAZIS_FOLD );
		addspriteok( FAZIS_EG );
		addkovetok( FAZIS_EG );
		levon10000t();
		addspriteok( FAZIS_NEMFOLDEG );
		addkovetok( FAZIS_NEMFOLDEG );
	}

	// Itt adtuk be objektumokat:
	addobjektumok(); // Ez most nem view eseten visszater

	// Ezeket vegen kivulrol hivja loadecsetek:

	// Rovid folddarabokat atalakitjuk konkret mutatova:
	//foldmutatocsere();

	//mutatotlanit();
	//deletemdarabok();
}

// URES sorokat tesz bele:
// Ptop es Pszak alapjan:
ecset::ecset( ecset* pold ) {
	int i;
	sortombmeret = 0;
	msorok = NULL;
	sorok = NULL;
	kurxposok_A = kurxposok_B = NULL;
	curdarabok_A = curdarabok_B = NULL;

	// Inicializaljuk elso node tombot:
	elsotomb = kurtomb = NULL;
	tombbenkov = 0;

	nagydarabtomb = NULL;

	view = 0;
	xsizedb = ysizedb = 0.0;
	maxx = sorszam = 0;

	if( !Ptop || !Pszak )
		hiba( "ecset::ecset !Ptop || !Pszak!" );

	elsotomb = new mdarabtomb;
	if( !elsotomb )
		hiba( "Nincs eleg memoria ecset::ecset!" );
	elsotomb->kovtomb = NULL;
	kurtomb = elsotomb;

	//getorigoandsize(); ehelyett:
	origo = pold->origo;
	xsizedb = pold->xsizedb;
	ysizedb = pold->ysizedb;

	maxx = pold->maxx;
	sorszam = pold->sorszam;

	eredetiorigo = pold->eredetiorigo;
	eredetimaxx = pold->eredetimaxx;
	eredetisorszam = pold->eredetisorszam;

	lefoglalsortomboket();

	// Inicializaljuk minden sor elejet uresre:
	for( i = 0; i < sorszam; i++ ) {
		kurxposok_A[i] = 1;
		kurxposok_B[i] = 1;

		msorok[i] = newmdarab();
		msorok[i]->pkov = NULL;
		msorok[i]->xsize = 1000000;
		msorok[i]->tavolsag = 0;
		msorok[i]->pixelek = (unsigned char*)PX_URES;
	}
}

ecset::~ecset( void ) {
	if( elsotomb )
		hiba( "ecset::~ecset elsotomb" );
	if( !nagydarabtomb )
		hiba( "ecset::~ecset !nagydarabtomb!" );
	delete nagydarabtomb;
	nagydarabtomb = NULL;
	delete[] msorok;
	delete[] sorok;
	delete[] kurxposok_A;
	delete[] curdarabok_A;
	delete[] kurxposok_B;
	delete[] curdarabok_B;
	msorok = NULL;
	sorok = NULL;
	kurxposok_A = kurxposok_B = NULL;
	curdarabok_A = curdarabok_B = NULL;
	sortombmeret = 0;
}

void ecset::deletemdarabok( void ) {
	if( !elsotomb )
		hiba( "ecset::deletemdarabok !elsotomb!" );
	mdarabtomb* cur = elsotomb;
	while( cur ) {
		mdarabtomb* kov = cur->kovtomb;
		delete cur;
		cur = kov;
	}
	elsotomb = NULL;
	for( int i = 0; i < sortombmeret; i++ )
		msorok[i] = NULL;
}

static int Xe1, Xe2, Xe2plussz1;

unsigned char *Foldsor = NULL, *Egsor = NULL;

void ecset::kiegysor_A( unsigned char* pc, int ye ) {
	// Visszalepunk amig kell:
	darab* pda = curdarabok_A[ye];
	int xpos = kurxposok_A[ye];
	while( xpos > Xe1 ) {
		pda--;
		xpos -= pda->xsize;
	}
	// Elorelepunk amig kell:
	while( xpos + pda->xsize <= Xe1 ) {
		xpos += pda->xsize;
		pda++;

	}
	// Elmentjuk kurrens darabot:
	curdarabok_A[ye] = pda;
	kurxposok_A[ye] = xpos;


	// ELSO SZAKASZ      ELSO SZAKASZ       ELSO SZAKASZ
	// ELSO SZAKASZ      ELSO SZAKASZ       ELSO SZAKASZ
	// ELSO SZAKASZ      ELSO SZAKASZ       ELSO SZAKASZ
	// ELSO SZAKASZ      ELSO SZAKASZ       ELSO SZAKASZ
	int ures = Xe1-xpos;
	if( xpos + pda->xsize > Xe2 ) {
		// ATLOG VEGIG:
		int ujpdaxsize = Xe2-xpos+1;
		// Ha eppen vegeig log, akkor is ide jon
		if( (uintptr_t)pda->pixelek & PIXELMASZK ) {
			// Normal kep copi:
			BYTECOPY( pc, &pda->pixelek[Xe1-xpos], ujpdaxsize-ures );
		}
		else {
			// Eg, Fold, vagy ures:
			if( !pda->pixelek ) { // Eg
				BYTECOPY( pc, Egsor, ujpdaxsize-ures );
				return;
			}
			if( (uintptr_t)pda->pixelek == PX_FOLD )
				BYTECOPY( pc, Foldsor, ujpdaxsize-ures );
			else {
				#ifdef TEST
					if( (uintptr_t)pda->pixelek != PX_URES ) hiba( "(uintptr_t)pda->pixelek != PX_URES iueghyreg!" );
				#endif
			}
		}
		return;
	}

	// Elso szakasz nem log at vegig:
	int size = pda->xsize-ures;
	if( (uintptr_t)pda->pixelek & PIXELMASZK ) {
		// Normal kep copi:
		BYTECOPY( pc, &pda->pixelek[Xe1-xpos], size );
	}
	else {
		// Eg, Fold, vagy ures:
		if( !pda->pixelek )  // Eg
			BYTECOPY( pc, Egsor, size );
		else {
			if( (uintptr_t)pda->pixelek == PX_FOLD )
				BYTECOPY( pc, Foldsor, size );
			else {
				#ifdef TEST
					if( (uintptr_t)pda->pixelek != PX_URES )
						hiba( "(uintptr_t)pda->pixelek != PX_URES iygvfrgiyvr!" );
				#endif
			}
		}
	}
	// Atugrunk kovetkezore:
	xpos += pda->xsize;
	pda++;
	pc += size;

	// BENT KEZDODO SZAKASZOK          BENT KEZDODO SZAKASZOK
	// BENT KEZDODO SZAKASZOK          BENT KEZDODO SZAKASZOK
	// BENT KEZDODO SZAKASZOK          BENT KEZDODO SZAKASZOK
	// BENT KEZDODO SZAKASZOK          BENT KEZDODO SZAKASZOK
	while( xpos <= Xe2 ) {
		#ifdef KIIRDARABOT
			Kisordarabszam++;
		#endif
		if( ye == 1071 && xpos == 12020 /*12055*/ ) {
			semmi();
		}

		if( xpos + pda->xsize > Xe2 ) {
			// Ez az utolso darab, ki is loghat:
			if( (uintptr_t)pda->pixelek & PIXELMASZK ) {
				// Normal kep copi:
				BYTECOPY( pc, pda->pixelek, Xe2-xpos+1 );
				return;
			}
			if( !pda->pixelek ) {
				BYTECOPY( pc, Egsor + (xpos-Xe1), Xe2-xpos+1 );
				return;
			}
			if( (uintptr_t)pda->pixelek == PX_FOLD ) {
				BYTECOPY( pc, Foldsor + (xpos-Xe1), Xe2-xpos+1 );
				return;
			}
			#ifdef TEST
				if( (uintptr_t)pda->pixelek != PX_URES )
					hiba( "(uintptr_t)pda->pixelek != PX_URES 653wetgki!" );
			#endif
		}

		// Ez a darab nem log ki:
		if( (uintptr_t)pda->pixelek & PIXELMASZK ) {
			// Normal kep copi:
			BYTECOPY( pc, pda->pixelek, pda->xsize );
		}
		else {
			if( !pda->pixelek ) {
				BYTECOPY( pc, Egsor + (xpos-Xe1), pda->xsize );
			}
			else {
				if( (uintptr_t)pda->pixelek == PX_FOLD ) {
					BYTECOPY( pc, Foldsor + (xpos-Xe1), pda->xsize );
				}
				else {
					#ifdef TEST
						if( (uintptr_t)pda->pixelek != PX_URES )
							hiba( "(uintptr_t)pda->pixelek != PX_URES 653wetgki!" );
					#endif
				}
			}
		}

		xpos += pda->xsize;
		pc += pda->xsize;
		pda++;
	}
}

void ecset::kiegysor_B( unsigned char* pc, int ye ) {
	// Visszalepunk amig kell:
	darab* pda = curdarabok_B[ye];
	int xpos = kurxposok_B[ye];
	while( xpos > Xe1 ) {
		pda--;
		xpos -= pda->xsize;
	}
	// Elorelepunk amig kell:
	while( xpos + pda->xsize <= Xe1 ) {
		xpos += pda->xsize;
		pda++;

	}
	// Elmentjuk kurrens darabot:
	curdarabok_B[ye] = pda;
	kurxposok_B[ye] = xpos;


	// ELSO SZAKASZ      ELSO SZAKASZ       ELSO SZAKASZ
	// ELSO SZAKASZ      ELSO SZAKASZ       ELSO SZAKASZ
	// ELSO SZAKASZ      ELSO SZAKASZ       ELSO SZAKASZ
	// ELSO SZAKASZ      ELSO SZAKASZ       ELSO SZAKASZ
	int ures = Xe1-xpos;
	if( xpos + pda->xsize > Xe2 ) {
		// ATLOG VEGIG:
		int ujpdaxsize = Xe2-xpos+1;
		// Ha eppen vegeig log, akkor is ide jon
		if( (uintptr_t)pda->pixelek & PIXELMASZK ) {
			// Normal kep copi:
			BYTECOPY( pc, &pda->pixelek[Xe1-xpos], ujpdaxsize-ures );
		}
		else {
			// Eg, Fold, vagy ures:
			if( !pda->pixelek ) { // Eg
				BYTECOPY( pc, Egsor, ujpdaxsize-ures );
				return;
			}
			if( (uintptr_t)pda->pixelek == PX_FOLD )
				BYTECOPY( pc, Foldsor, ujpdaxsize-ures );
			else {
				#ifdef TEST
					if( (uintptr_t)pda->pixelek != PX_URES ) hiba( "(uintptr_t)pda->pixelek != PX_URES iueghyreg!" );
				#endif
			}
		}
		return;
	}

	// Elso szakasz nem log at vegig:
	int size = pda->xsize-ures;
	if( (uintptr_t)pda->pixelek & PIXELMASZK ) {
		// Normal kep copi:
		BYTECOPY( pc, &pda->pixelek[Xe1-xpos], size );
	}
	else {
		// Eg, Fold, vagy ures:
		if( !pda->pixelek )  // Eg
			BYTECOPY( pc, Egsor, size );
		else {
			if( (uintptr_t)pda->pixelek == PX_FOLD )
				BYTECOPY( pc, Foldsor, size );
			else {
				#ifdef TEST
					if( (uintptr_t)pda->pixelek != PX_URES )
						hiba( "(uintptr_t)pda->pixelek != PX_URES iygvfrgiyvr!" );
				#endif
			}
		}
	}
	// Atugrunk kovetkezore:
	xpos += pda->xsize;
	pda++;
	pc += size;

	// BENT KEZDODO SZAKASZOK          BENT KEZDODO SZAKASZOK
	// BENT KEZDODO SZAKASZOK          BENT KEZDODO SZAKASZOK
	// BENT KEZDODO SZAKASZOK          BENT KEZDODO SZAKASZOK
	// BENT KEZDODO SZAKASZOK          BENT KEZDODO SZAKASZOK
	while( xpos <= Xe2 ) {
		#ifdef KIIRDARABOT
			Kisordarabszam++;
		#endif

		if( xpos + pda->xsize > Xe2 ) {
			// Ez az utolso darab, ki is loghat:
			if( (uintptr_t)pda->pixelek & PIXELMASZK ) {
				// Normal kep copi:
				BYTECOPY( pc, pda->pixelek, Xe2-xpos+1 );
				return;
			}
			if( !pda->pixelek ) {
				BYTECOPY( pc, Egsor + (xpos-Xe1), Xe2-xpos+1 );
				return;
			}
			if( (uintptr_t)pda->pixelek == PX_FOLD ) {
				BYTECOPY( pc, Foldsor + (xpos-Xe1), Xe2-xpos+1 );
				return;
			}
			#ifdef TEST
				if( (uintptr_t)pda->pixelek != PX_URES )
					hiba( "(uintptr_t)pda->pixelek != PX_URES 653wetgki!" );
			#endif
		}

		// Ez a darab nem log ki:
		if( (uintptr_t)pda->pixelek & PIXELMASZK ) {
			// Normal kep copi:
			BYTECOPY( pc, pda->pixelek, pda->xsize );
		}
		else {
			if( !pda->pixelek ) {
				BYTECOPY( pc, Egsor + (xpos-Xe1), pda->xsize );
			}
			else {
				if( (uintptr_t)pda->pixelek == PX_FOLD ) {
					BYTECOPY( pc, Foldsor + (xpos-Xe1), pda->xsize );
				}
				else {
					#ifdef TEST
						if( (uintptr_t)pda->pixelek != PX_URES )
							hiba( "(uintptr_t)pda->pixelek != PX_URES 653wetgki!" );
					#endif
				}
			}
		}

		xpos += pda->xsize;
		pc += pda->xsize;
		pda++;
	}
}

#ifdef FFECSET

static unsigned char Feketesor[MAXKEPXSIZE+10], Fehersor[MAXKEPXSIZE+10];
static unsigned char* FFsor = Feketesor;
static int FFallapot = 0, FFinited = 0;
static void ffmutvalt( void ) {
	FFallapot = !FFallapot;
	if( FFallapot )
		FFsor = Feketesor;
	else
		FFsor = Fehersor;
}

// Fekete-feher-ben rak ki (csak tesztre):
void ecset::kiegysor_FF( unsigned char* pc, int ye ) {
	if( !FFinited ) {
		FFinited = 1;
		for( int i = 0; i < MAXKEPXSIZE; i++) {
			Feketesor[i] = 10;
			Fehersor[i] = 120;
		}
	}

	FFsor = Feketesor;
	FFallapot = 0;
	ffmutvalt();

	// Visszalepunk amig kell:
	darab* pda = curdarabok_A[ye];
	int xpos = kurxposok_A[ye];
	while( xpos > Xe1 ) {
		pda--;
		xpos -= pda->xsize;
	}
	// Elorelepunk amig kell:
	while( xpos + pda->xsize <= Xe1 ) {
		xpos += pda->xsize;
		pda++;

	}
	// Elmentjuk kurrens darabot:
	curdarabok_A[ye] = pda;
	kurxposok_A[ye] = xpos;


	// ELSO SZAKASZ      ELSO SZAKASZ       ELSO SZAKASZ
	// ELSO SZAKASZ      ELSO SZAKASZ       ELSO SZAKASZ
	// ELSO SZAKASZ      ELSO SZAKASZ       ELSO SZAKASZ
	// ELSO SZAKASZ      ELSO SZAKASZ       ELSO SZAKASZ
	int ures = Xe1-xpos;
	if( xpos + pda->xsize > Xe2 ) {
		// ATLOG VEGIG:
		int ujpdaxsize = Xe2-xpos+1;
		// Ha eppen vegeig log, akkor is ide jon
		if( (uintptr_t)pda->pixelek & PIXELMASZK ) {
			// Normal kep copi:
			BYTECOPY( pc, FFsor, ujpdaxsize-ures );
			ffmutvalt();
		}
		else {
			// Eg, Fold, vagy ures:
			if( !pda->pixelek ) { // Eg
				BYTECOPY( pc, FFsor, ujpdaxsize-ures );
				ffmutvalt();
				return;
			}
			if( (uintptr_t)pda->pixelek == PX_FOLD ) {
				BYTECOPY( pc, FFsor, ujpdaxsize-ures );
				ffmutvalt();
			}
			else {
				#ifdef TEST
					if( (uintptr_t)pda->pixelek != PX_URES ) hiba( "(uintptr_t)pda->pixelek != PX_URES iueghyreg!" );
				#endif
			}
		}
		return;
	}

	// Elso szakasz nem log at vegig:
	int size = pda->xsize-ures;
	if( (uintptr_t)pda->pixelek & PIXELMASZK ) {
		// Normal kep copi:
		BYTECOPY( pc, FFsor, size );
		ffmutvalt();
	}
	else {
		// Eg, Fold, vagy ures:
		if( !pda->pixelek ) {
			// Eg:
			BYTECOPY( pc, FFsor, size );
			ffmutvalt();
		}
		else {
			if( (uintptr_t)pda->pixelek == PX_FOLD ) {
				BYTECOPY( pc, FFsor, size );
				ffmutvalt();
			}
			else {
				#ifdef TEST
					if( (uintptr_t)pda->pixelek != PX_URES )
						hiba( "(uintptr_t)pda->pixelek != PX_URES iygvfrgiyvr!" );
				#endif
			}
		}
	}
	// Atugrunk kovetkezore:
	xpos += pda->xsize;
	pda++;
	pc += size;

	// BENT KEZDODO SZAKASZOK          BENT KEZDODO SZAKASZOK
	// BENT KEZDODO SZAKASZOK          BENT KEZDODO SZAKASZOK
	// BENT KEZDODO SZAKASZOK          BENT KEZDODO SZAKASZOK
	// BENT KEZDODO SZAKASZOK          BENT KEZDODO SZAKASZOK
	while( xpos <= Xe2 ) {
		if( xpos + pda->xsize > Xe2 ) {
			// Ez az utolso darab, ki is loghat:
			if( (uintptr_t)pda->pixelek & PIXELMASZK ) {
				// Normal kep copi:
				BYTECOPY( pc, FFsor, Xe2-xpos+1 );
				ffmutvalt();
				return;
			}
			if( !pda->pixelek ) {
				BYTECOPY( pc, FFsor, Xe2-xpos+1 );
				ffmutvalt();
				return;
			}
			if( (uintptr_t)pda->pixelek == PX_FOLD ) {
				BYTECOPY( pc, FFsor, Xe2-xpos+1 );
				ffmutvalt();
				return;
			}
			#ifdef TEST
				if( (uintptr_t)pda->pixelek != PX_URES )
					hiba( "(uintptr_t)pda->pixelek != PX_URES 653wetgki!" );
			#endif
		}

		// Ez a darab nem log ki:
		if( (uintptr_t)pda->pixelek & PIXELMASZK ) {
			// Normal kep copi:
			BYTECOPY( pc, FFsor, pda->xsize );
			ffmutvalt();
		}
		else {
			if( !pda->pixelek ) {
				BYTECOPY( pc, FFsor, pda->xsize );
				ffmutvalt();
			}
			else {
				if( (uintptr_t)pda->pixelek == PX_FOLD ) {
					BYTECOPY( pc, FFsor, pda->xsize );
					ffmutvalt();
				}
				else {
					#ifdef TEST
						if( (uintptr_t)pda->pixelek != PX_URES )
							hiba( "(uintptr_t)pda->pixelek != PX_URES 653wetgki!" );
					#endif
				}
			}
		}

		xpos += pda->xsize;
		pc += pda->xsize;
		pda++;
	}
}

#endif

void ecset::getbalalso_int( vekt2 balalso, int* px, int* py ) {
	vekt2 relat = balalso-origo;
	if( view ) {
		*px = relat.x*(Aranyalap/Viewzoom); // Ecset egesz koordinatak
		*py = relat.y*(Aranyalap/Viewzoom); // Ecset egesz koordinatak
	}
	else {
		*px = relat.x*Arany; // Ecset egesz koordinatak
		*py = relat.y*Arany; // Ecset egesz koordinatak
	}
}

/*static int Elsoegkeszit = 1;
static pic8* Pegbuffer = NULL;
static pic8* Felho = NULL;
static pic8* Felho2 = NULL;

static void egetkeszit( pic8* peg, int xhely, int xkezd, int xmodulus ) {
	if( Elsoegkeszit ) {
		Elsoegkeszit = 0;
		Pegbuffer = new pic8( peg->getxsize(), peg->getysize() );
		blt8( Pegbuffer, peg );

		Felho = new pic8( "felho.pcx" );
		forditkepet( Felho );
		spriteosit( Felho );

		Felho2 = new pic8( "felho2.pcx" );
		forditkepet( Felho2 );
		spriteosit( Felho2 );
	}

	// Resetaljuk eget:
	blt8( peg, Pegbuffer );

	// Felho2:
	double lassitas = 2.5;
	int modulus = 1000;
	int dx = -xhely/lassitas;
	while( dx < 0 )
		dx += modulus;
	dx -= modulus;
	int x = xkezd+dx;
	blt8( peg, Felho2, x, -80 );
	x += modulus;
	blt8( peg, Felho2, x, -80 );

	// Felho1:
	lassitas = 1.5;
	modulus = 1000;
	dx = -xhely/lassitas;
	while( dx < 0 )
		dx += modulus;
	dx -= modulus;
	x = xkezd+dx;
	blt8( peg, Felho, x, 0 );
	x += modulus;
	blt8( peg, Felho, x, 0 );
} */

// A band of this many pixels along the edge of the ecset is not drawn
// (originally the picture could not come closer, or the game quit with hiba):
#define ECSETSZEL (20)

// Non-negative remainder, also for negative ecset coordinates:
static int pozmaradek( int a, int m ) {
	int maradek = a % m;
	if( maradek < 0 )
		maradek += m;
	return maradek;
}

// Division rounded down (also for negative ecset coordinates):
static int lefeleoszt( int a, int b ) {
	if( a >= 0 )
		return a/b;
	return -((b-1-a)/b);
}

// The sky does not scroll vertically, it is aligned to the bottom row of the
// picture. Sky pictures lower than 480 were repeated already in the original
// (they are made for it) and go on repeating. A picture at least 480 high
// (e.g. sky.pcx) was never repeated in the original: on a taller picture it
// continues mirrored above its top, so that there is no seam:
// A sky lower than 480 (at its original size) is repeated as in the original,
// a taller one is mirrored above; for a zoomed sky the zoomed 480 is the
// limit, otherwise a shrunk 640x480 sky would be repeated as well:
static int egkepsor( int sor, int egymodulus ) {
	if( egymodulus < nagyitpixel( 480, Plgr->texturanagyitas ) )
		return sor % egymodulus;
	sor %= 2*egymodulus;
	if( sor >= egymodulus )
		sor = 2*egymodulus-1-sor;
	return sor;
}

// Where the picture falls outside the ecset, draws ground (bottom and view
// ecset) or nothing (top ecset) there, and the same as before inside:
void ecset::kitesz( int ajatekos, pic8* ppic, vekt2 balalso, int x1, int y1, int x2, int y2 ) {
	if( x1 >= x2 || y1 >= y2 )
		hiba( "ecset::kitesz x1 >= x2 || y1 >= y2!" );

	Kisordarabszam = 0;

	int ye1 = 0;
	int kepxe1 = 0; // Left edge of the picture in the ecset
	getbalalso_int( balalso, &kepxe1, &ye1 );
	int kepxe2 = kepxe1 + x2-x1;

	// This many columns of the ecset are visible (without the part sticking out):
	Xe1 = kepxe1;
	Xe2 = kepxe2;
	if( Xe1 < ECSETSZEL )
		Xe1 = ECSETSZEL;
	if( Xe2 > maxx-ECSETSZEL )
		Xe2 = maxx-ECSETSZEL;
	Xe2plussz1 = Xe2+1;
	int balra = Xe1-kepxe1; // Columns sticking out to the left
	int jobbra = kepxe2-Xe2; // Columns sticking out to the right
	int sorhossz = kepxe2-kepxe1+1;
	int kilogofold = this != Pecsetfelso;

	int foldymodulus = Plgr->pfold->getysize();
	int egymodulus = Plgr->peg->getysize();

	int folddx = pozmaradek( kepxe1, Plgr->foldxmodulus );
	//int eglassitas = 100;
	int eglassitas = 2;
	int egdx = pozmaradek( lefeleoszt( kepxe1, eglassitas ), Plgr->egxmodulus );
	//int egdy = ye1/eglassitas;

	//egetkeszit( Plgr->peg, Xe1, egdx, Plgr->egxmodulus );

	int yadd = ye1-y1;
	for( int y = y1; y <= y2; y++ ) {
		int ye = y + yadd;
		unsigned char* pc = ppic->getptr(y)+x1;
		Foldsor = Plgr->pfold->getptr( pozmaradek( ye, foldymodulus ) ) +
						folddx;
		// Eg fol-le is scrollozodik:
		//Egsor = Plgr->peg->getptr( (y-y1+egdy) % egymodulus ) + egdx;

		// Eg fol-le nem scrollozodik:
		Egsor = Plgr->peg->getptr( egkepsor( y-y1, egymodulus ) ) + egdx;

		if( ye < ECSETSZEL || ye > sorszam-ECSETSZEL || Xe1 > Xe2 ) {
			// The whole row sticks out:
			if( kilogofold )
				BYTECOPY( pc, Foldsor, sorhossz );
			continue;
		}
		if( kilogofold ) {
			if( balra > 0 )
				BYTECOPY( pc, Foldsor, balra );
			if( jobbra > 0 )
				BYTECOPY( pc+sorhossz-jobbra, Foldsor+sorhossz-jobbra, jobbra );
		}
		// kiegysor takes the start of Foldsor and Egsor at Xe1:
		Foldsor += balra;
		Egsor += balra;
		pc += balra;

		#ifdef FFECSET
			kiegysor_FF( pc, ye );
		#else
			if( ajatekos )
				kiegysor_A( pc, ye );
			else
				kiegysor_B( pc, ye );
		#endif
	}
}

// Szinte ugyanaz, mint kiteszalso:
void ecset::kiteszview( int ajatekos, pic8* ppic, vekt2 balalso, int x1, int y1, int x2, int y2 ) {
	if( x1 >= x2 || y1 >= y2 )
		hiba( "ecset::kitesz x1 >= x2 || y1 >= y2!" );

	int ye1 = 0;
	int kepxe1 = 0;
	getbalalso_int( balalso, &kepxe1, &ye1 );
	// Draws one more column (a frame covers it later):
	int kepxe2 = kepxe1 + x2-x1+1;

	Xe1 = kepxe1;
	Xe2 = kepxe2;
	if( Xe1 < ECSETSZEL )
		Xe1 = ECSETSZEL;
	if( Xe2 > maxx-ECSETSZEL )
		Xe2 = maxx-ECSETSZEL;
	Xe2plussz1 = Xe2+1;
	int balra = Xe1-kepxe1;
	int jobbra = kepxe2-Xe2;
	int sorhossz = kepxe2-kepxe1+1;

	int yadd = ye1-y1;
	for( int y = y1; y <= y2; y++ ) {
		int ye = y + yadd;
		unsigned char* pc = ppic->getptr(y)+x1;
		Foldsor = Plgr->viewfoldsor;
		Egsor = Plgr->viewegsor;
		if( ye < ECSETSZEL || ye > sorszam-ECSETSZEL || Xe1 > Xe2 ) {
			BYTECOPY( pc, Foldsor, sorhossz );
			continue;
		}
		if( balra > 0 )
			BYTECOPY( pc, Foldsor, balra );
		if( jobbra > 0 )
			BYTECOPY( pc+sorhossz-jobbra, Foldsor+sorhossz-jobbra, jobbra );
		Foldsor += balra;
		Egsor += balra;
		pc += balra;
		if( ajatekos )
			kiegysor_A( pc, ye );
		else
			kiegysor_B( pc, ye );
	}
}

// The original game's (1.11a) picture was 640x480, Arany was 48, and the
// level was seen around the motorbike's center (halved between the two
// extreme positions horizontally); if this picture got closer than
// ECSETSZEL to the ecset's edge, kitesz exited with hiba. This checks the
// same thing, independent of the picture's actual size and of Arany:
int ecset::kilogna( vekt2 r ) {
	// Bottom left corner of the picture in ecset pixels (getbalalso_int truncates to integer):
	double x = (r.x - 320.0/EREDETIARANY - eredetiorigo.x)*EREDETIARANY;
	double y = (r.y - 240.0/EREDETIARANY - eredetiorigo.y)*EREDETIARANY;
	if( x < ECSETSZEL || y < ECSETSZEL )
		return 1;
	// kitesz: Xe2 = Xe1 + 639 > maxx-20 || ye2 = ye1 + 479 > sorszam-20:
	if( floor( x ) + 639 > eredetimaxx-ECSETSZEL )
		return 1;
	if( floor( y ) + 479 > eredetisorszam-ECSETSZEL )
		return 1;
	return 0;
}

static mdarab* Glb_pfoltdarab = NULL;

// About one mdarab of the row above (ezfolt depends only on this):
static int ezfoltdarab( mdarab* pmd ) {
	if( !Glb_pfoltdarab )
		hiba( "65rw5r7twe" );

	intptr_t kepindex = (intptr_t)pmd->pixelek;
	if( kepindex < 10 )
		// Ha fold, eg, vagy ures:
		return 0;

	if( pmd->pixelek == Glb_pfoltdarab->pixelek )
		// Ha meg ez is koveto textura:
		return 0;

	if( pmd->tavolsag > 500 )
		// Ha nem takarja el motorost:
		return 0;

	return 1;
}

// How many consecutive pixels from x1 to xkov are folt (spot, if folt is
// true) or not folt: it steps over the mdarab pieces of the row above in one
// go (originally it checked pixel by pixel, with the same result):
static int getazonosszam( int x1, int xkov, int y, mdbiter* piter1, int folt ) {
	int szam = 0;
	int x = x1;
	while( x < xkov ) {
		// We check the row above:
		mdarab* pmd = piter1->getpmd( x, y+1 );
		if( ezfoltdarab( pmd ) != folt )
			return szam;
		int vege = piter1->getxpos() + pmd->xsize;
		if( vege > xkov )
			vege = xkov;
		szam += vege-x;
		x = vege;
	}
	return szam;
}

static int getnemfoltszam( int x1, int xkov, int y, mdbiter* piter1 ) {
	return getazonosszam( x1, xkov, y, piter1, 0 );
}

static int getfoltszam( int x1, int xkov, int y, mdbiter* piter1 ) {
	return getazonosszam( x1, xkov, y, piter1, 1 );
}

// Meg akkor kell hivni, amig nincsenek kettevalasztva also-ra es felsore es
// meg kis folddarabok sincsenek lecserelve:
void ecset::foltoz( void ) {
	mdbiter* piter1 = new mdbiter( this );
	// addbyte-ban tavolsagot valtakozva adjuk meg, nehogy osszeadja:
	int valtakozo = 0;

	// Vegigmegyunk osszes soron alulrol felfele:
	// Azert noveljuk megis y-t, mert fejjel lefele vannak y koordinatak:
	for( int y = 10; y < sorszam-10; y++ ) {
		// Vegigmegyunk osszes mdarabon:
		mdarab* pmd = msorok[y];
		int xpos = kurxposok_A[y];
		if( xpos > 10 )
			hiba( "uih67f" );

		while( pmd ) {
			int pmdorigxsize = pmd->xsize;
			mdarab* pmdorigkov = pmd->pkov;

			Glb_pfoltdarab = pmd;
			// Egy madarab-ot elintezunk:
			intptr_t kepindex = (intptr_t)pmd->pixelek;
			if( ((kepindex & PIXELMASZK) == 0) && (kepindex >= 10) ) {
				kepindex -= 10;
				// Itt van maszk, le kell cserelni:
				#ifdef TEST
					if( kepindex >= Plgr->texturaszam )
						hiba( "egryiegr" );
				#endif
				textura* pt = &Plgr->texturak[kepindex];

				if( pt->foltos && pmd->tavolsag > 500 ) {
					// Ha egy foltos, 500-nal tavolabbi textura mdarabja:
					// Vegigmegyunk mdarab-on:
					int x = xpos;
					// Ez mar kov mdarab elso pixele:
					int xkov = xpos+pmd->xsize;
					while( x < xkov ) {
						int nfszam = getnemfoltszam( x, xkov, y, piter1 );
						x += nfszam;
						int foltszam = getfoltszam( x, xkov, y, piter1 );
						if( foltszam > 0 ) {
							valtakozo = !valtakozo;
							if( valtakozo )
								addbytesor( //(unsigned char*)10,
											pmd->pixelek,
											223,
											x, x+foltszam-1,
											y, FAZIS_NEMFOLDEG );
							else
								addbytesor( //(unsigned char*)10,
											pmd->pixelek,
											224,
											x, x+foltszam-1,
											y, FAZIS_NEMFOLDEG );
						}
						x += foltszam;
					}
				}
			}

			// Ugrunk kovetkezo mdarab-ra:
			xpos += pmdorigxsize;
			pmd = pmdorigkov;
		}
	}
	delete piter1; piter1 = NULL;
}


void betoltecseteket( void ) {
	Plgr->betolthattereket();

	Osszegszam = 0; // Ide osszegezzuk osszes lefoglalt szakaszt

	if( Pecsetalso )
		delete Pecsetalso;
	Pecsetalso = NULL;
	if( Pecsetfelso )
		delete Pecsetfelso;
	Pecsetfelso = NULL;
	if( Pecsetview )
		delete Pecsetview;
	Pecsetview = NULL;

	Pecsetalso = new ecset( 0 );
	if( !Pecsetalso )
		hiba( "Nincs eleg memoria Pecsetalso-nak!" );

	Pecsetalso->foltoz();

	Pecsetfelso = new ecset( Pecsetalso );
	if( !Pecsetfelso )
		hiba( "Nincs eleg memoria Pecsetfelso-nak!" );

	// Most betesszuk felsobe is 500-nal kozelebbi madarabokat:
	// Es egyben uresse tesszuk alsoban helyuket:
	for( int i = 0; i < Pecsetalso->sorszam; i++ ) {
		if( i % 1024 == 0 )
			ujraepiteshang();
		mdarab* pmd = Pecsetalso->msorok[i];
		int xpos = Pecsetalso->kurxposok_A[i];
		if( xpos > 100 )
			hiba( "betoltecseteket xpos > 100!" );
		while( pmd ) {
			if( pmd->tavolsag < 500 ) {
				if( (uintptr_t)pmd->pixelek >= 10 ) {
					Pecsetfelso->addbytesor( pmd->pixelek, pmd->tavolsag,
									xpos, xpos+pmd->xsize-1, i, FAZIS_URESRE );
					pmd->pixelek = (unsigned char*)PX_URES;
				}
			}
			xpos += pmd->xsize;
			pmd = pmd->pkov;
		}
	}

	// Rovid folddarabokat atalakitja konkret mutatova:
	Pecsetalso->foldmutatocsere();
	// Egymas utani ket azonos texturat
	// lecsereli egyre (mar beepiteskor is megtortenik nemileg):
	Pecsetalso->duplaeliminacio();
	Pecsetalso->textura2mutato(); // Lecsereli textura indexeket mutatokka
	Pecsetalso->mutatotlanit();   // mdarab lancolt listabol tombot csinal
	Pecsetalso->deletemdarabok(); // Torli lancolt listat:

	Pecsetfelso->duplaeliminacio();
	Pecsetfelso->textura2mutato();
	Pecsetfelso->mutatotlanit();
	Pecsetfelso->deletemdarabok();

	// View ecset:
	Pecsetview = new ecset( 1 );
	if( !Pecsetview )
		hiba( "Nincs eleg memoria Pecsetview-nak!" );
	Pecsetview->mutatotlanit();
	Pecsetview->deletemdarabok();

	// Kajak egesz koordjainak kitoltese:
	Pecsetalso->kitoltfoodkoordokat();
	Pecsetview->kitoltfoodkoordokat(); // View koordok
}


void segedfv( void ) {
	ecset* pe = NULL;
	pe->kiegysor_A( NULL, 0 );
}


// Egy iterator class (inkabb cache) ecsethez (foltoz hasznalja oket):
mdbiter::mdbiter( ecset* pecset_p ) {
	xposbent = -1;
	ybent = -1;
	pmd = NULL;

	pecset = pecset_p;
}

mdarab* mdbiter::getpmd( int x, int y ) {
	if( y == ybent && x >= xposbent ) {
		while( x >= xposbent + pmd->xsize ) {
			xposbent += pmd->xsize;
			pmd = pmd->pkov;
		}
	}
	else {
		// We need to read again (we also remember the row; originally ybent
		// never changed, so every call started from the beginning of the row):
		if( y < 0 || y >= pecset->sorszam )
			hiba( "789eygrq" );
		ybent = y;
		pmd = pecset->msorok[y];
		xposbent = pecset->kurxposok_A[y];
		if( xposbent > 10 )
			hiba( "y7fjksd" );
		while( x >= xposbent + pmd->xsize ) {
			xposbent += pmd->xsize;
			pmd = pmd->pkov;
		}
	}
	return pmd;
}
