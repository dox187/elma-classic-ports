#include	"all.h"
#ifdef ELMA_PS3
#include "MEMORY_BUDGET.H"
#include "LGR_BUDGET.H"
#endif

int Volttopsave = 0;

static char Bentlevelnev[20] = "";

#ifdef ELMA_PSX
void psx_loading_stage( const char* level, const char* stage );
#endif

// True while the in-game zoom is changing (ujraepiteshang):
static int Ujraepites = 0;

void ujraepiteshang( void ) {
	if( Ujraepites )
		hang();
}

#ifdef ELMA_PS3
static uint64_t ps3_project_brushes(double effective,int same_level,const std::vector<elma_lgr_shape>& shapes) {
    double low=0,high=0,left=0,right=0,vertical=0,grass=0;int lines=0;bool first=true;
    for(int i=0;i<MAXGYURU;++i) {
        gyuru* g=Ptop->ptomb[i];if(!g || g->pontszam<1)continue;
        for(int j=0;j<g->pontszam;++j) {
            vekt2 a=g->ponttomb[j],b=g->ponttomb[(j+1)%g->pontszam];
            const double finite=std::numeric_limits<double>::max();
            if(!(a.x>=-finite && a.x<=finite && a.y>=-finite && a.y<=finite))return UINT64_C(1)<<60;
            if(first){low=high=a.y;left=right=a.x;first=false;}
            if(a.x<left)left=a.x;if(a.x>right)right=a.x;
            if(a.y<low)low=a.y;if(a.y>high)high=a.y;
            if(g->koveto)grass+=fabs(b.x-a.x)+fabs(b.y-a.y);
            else {vertical+=fabs(b.y-a.y);++lines;}
        }
    }
    double scale=Aranyalap*effective;
    double width=(right-left)*scale+20000*effective+16;
    if(!(width>=0) || width>INT_MAX)return UINT64_C(1)<<60;
    double rows=(high-low)*scale+2000*effective+16;
    if(!(rows>=0) || rows>MAXECSETSOR)return UINT64_C(1)<<60;
    double nodes=2*rows+vertical*scale+lines*2+grass*scale*4;
    for(int i=0;i<MAXSPRITE;++i)if(Ptop->spritetomb[i]) {
        sprite* s=Ptop->spritetomb[i];
        double height=same_level && s->ysize>0 ? s->ysize*scale : 20*effective;
        const char* name=s->kepnev[0]?s->kepnev:s->maszknev;
        for(size_t j=0;j<shapes.size();++j) {
            if(!strcmpi(const_cast<char*>(shapes[j].name),const_cast<char*>(name))) {
                height=shapes[j].height;break;
            }
        }
        // Each pass can split both ends of an existing fragment; the
        // three picture passes and front/back brushes coexist at the peak.
        nodes+=height*16;
    }
    if(!(nodes>=0) || nodes>1000000000)return UINT64_C(1)<<60;
    uint64_t projected=uint64_t(ceil(nodes))*(sizeof(mdarab)+sizeof(darab))
       +uint64_t(ceil(rows))*3*(4*sizeof(void*)+2*sizeof(int))
       +6*sizeof(mdarabtomb)+2u*1024*1024;
    if(same_level && ps3_brush_effective_zoom()>0) {
        double ratio=effective/ps3_brush_effective_zoom();
        // Observed peak includes masks, grass patches and compact arrays
        // coexisting with construction lists; never predict less than it.
        uint64_t observed=uint64_t(ceil(ps3_brush_peak_bytes()*ratio*ratio*1.15));
        if(observed>projected)projected=observed;
    }
    return projected;
}
static bool GraphicsMetadataOkay=true;
static int ps3_graphics_fit(double zoom,int same_level,int notify) {
    if(!Ptop)return 1;
    int w=640,h=480;backbuffersize(&w,&h);
    double fit=w/640.0<h/480.0?w/640.0:h/480.0;if(fit<1)fit=1;
    double effective=fit*zoom;
    char path[64];snprintf(path,sizeof(path),"lgr/%s.lgr",Ptop->lgrnev);
    FILE* f=fopen(path,"rb");if(!f)f=fopen("lgr/default.lgr","rb");
    elma_lgr_budget assets={};
    std::vector<elma_lgr_shape> shapes;
    bool valid=f && elma_estimate_lgr(f,effective,&assets,dd_zoom_textures()?effective:1,dd_zoom_grass()?effective:1,&shapes);if(f)fclose(f);
    GraphicsMetadataOkay=valid;
    uint64_t map=valid?ps3_project_brushes(effective,same_level,shapes):0;
    uint64_t available=ps3_memory_available()+ps3_lgr_memory_bytes();
    bool fits=valid && elma_graphics_memory_fits(assets.persistent,assets.temporary,map,
        ps3_memory_available(),ps3_lgr_memory_bytes(),ps3_brush_memory_bytes());
    printf("elma: graphics admission %.2fx %dx%d: LGR %llu + temporary %llu, brush peak %llu, available %llu: %s\n",
      zoom,w,h,(unsigned long long)assets.persistent,(unsigned long long)assets.temporary,
      (unsigned long long)map,(unsigned long long)available,fits?"accepted":"refused");
    if(!valid && notify)uzenet("Cannot inspect this LGR graphics file.","Check that the LGR file is complete and compatible.");
    else if(!fits && notify)uzenet("This zoom/resolution needs more PS3 memory than is available.",
        "The current graphics and zoom are kept. Choose a smaller zoom or Original resolution.");
    return fits;
}
int ps3_zoom_admissible(double zoom){return ps3_graphics_fit(zoom,1,1);}
static int ps3_prepare_level_graphics(int same_level) {
    if(ps3_graphics_fit(dd_zoom(),same_level,0))return 1;
    if(!GraphicsMetadataOkay) {
        uzenet("Cannot inspect this LGR graphics file.","Check that the LGR file is complete and compatible.");
        if(same_level)dd_set_zoom(Motornagyitas);
        Volttopsave=1;return 0;
    }
    if(same_level) {
        ps3_graphics_fit(dd_zoom(),1,1);
        dd_set_zoom(Motornagyitas);
        return 0;
    }
    if(dd_zoom()>1 && ps3_graphics_fit(1,0,0)) {
        uzenet("This level needs more memory at the selected zoom.","The level will use 1x zoom to fit safely in memory.");
        dd_set_zoom(1);return 1;
    }
    uzenet("This level cannot fit in PS3 memory at the selected resolution.",
           "Choose Original resolution or a smaller zoom, then try again.");
    Volttopsave=1;return 0;
}
#endif

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
#ifdef ELMA_PSX
	int loading_notice = 0;
#endif
	if( !nev )
		hiba( "floadlevel_p-ben !nev!" );
	// A collection's level names can be longer than 8.3 (tutorial01.lev):
	if( strlen( nev ) > 15 || !nev[0] )
		hiba( "floadlevel_p-ben strlen( nev ) > 15 || !nev[0]!: ", nev );
#ifdef ELMA_PSX
	// Menu-only image caches must leave before any level allocation,
	// including a retained level whose physics or GPU data needs rebuilding.
	void gv_menu_images_free( void );
	gv_menu_images_free();
#endif
	if( Volttopsave || !Ptop || !Pszak || strcmpi( nev, Bentlevelnev ) != 0 ) {
#ifdef ELMA_PSX
		loading_notice = 1;
		psx_loading_stage( NULL, "Reading level..." );
#endif
		Volttopsave = 0;
		// Ujra be kell olvasni palyat:
		strcpy( Bentlevelnev, nev );
		if( Ptop )
			delete Ptop;
#if defined(ELMA_PSX) || defined(ELMA_PS3)
        // Never leave the previous level's collision map paired with the
        // new topology if graphics admission refuses this load.
		if( Pszak )
			delete Pszak;
		Pszak = NULL;
#ifdef ELMA_PSX
		void fxg_unload_level( void );
		fxg_unload_level();
#endif
#endif
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
#ifdef ELMA_PS3
        if(!ps3_prepare_level_graphics(0))return 0;
#endif
		// The game runs at the desired zoom, with the LGR scaled to it:
		beallitarany( 1 );
#ifdef ELMA_PSX
		psx_loading_stage( Ptop->levelname, "Loading graphics..." );
#endif
		loadlgrfile( Ptop->lgrnev );
		Ptop->pic_selejtez( Plgr );

#ifdef ELMA_PSX
		psx_loading_stage( Ptop->levelname, "Preparing level..." );
#endif
		if( Pszak )
			delete Pszak;
		Pszak = new szakaszok( Ptop );
		if( Fejsugar > Pmot1->kor2.sugar )
			Pszak->rendez( Fejsugar );
		else
			Pszak->rendez( Pmot1->kor2.sugar );

#ifdef ELMA_PSX
		void fxg_prepare_lines( void );
		fxg_prepare_lines();
		// Sound decoding and compression need temporary buffers; finish
		// them before allocating the GPU's scenery instances and sprites.
		void psx_prepare_sound( void );
		psx_loading_stage( Ptop->levelname, "Loading sounds..." );
		psx_prepare_sound();
		psx_loading_stage( Ptop->levelname, "Preparing graphics..." );
#endif
		betoltecseteket();
	}
	else {
		// Same level, but the zoom has changed since (Options), or the
		// editor loaded the LGR at its original size:
		if( maskellarany() || !lgrnagyitasjo() ) {
#ifdef ELMA_PSX
			loading_notice = 1;
			psx_loading_stage( Ptop->levelname, "Loading graphics..." );
#endif
#ifdef ELMA_PS3
            if(!ps3_prepare_level_graphics(1))return 0;
#endif
			ujranagyit();
		}
#ifdef ELMA_PSX
		void psx_prepare_sound( void );
		if( State->soundon && !Hangmarmegy ) {
			loading_notice = 1;
			psx_loading_stage( Ptop->levelname, "Loading sounds..." );
		}
		psx_prepare_sound();
#endif
	}
#ifdef ELMA_PSX
	if( loading_notice )
		psx_loading_stage( Ptop->levelname, "Starting level..." );
#endif
#ifdef ELMA_PS3
    printf("elma: level ready %s zoom %.2fx effective %.2fx RAM available %u KiB, LGR %llu KiB, brushes %llu KiB, brush construction peak %llu KiB\n",
      nev,dd_zoom(),kepnagyitas(),ps3_memory_available()/1024,
      ps3_lgr_memory_bytes()/1024,ps3_brush_memory_bytes()/1024,ps3_brush_peak_bytes()/1024);
#endif
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

