#include	"all.h"
#ifdef ELMA_PS3
#include "PS3_PLATFORM.H"
#endif

void editplay( void ) {
	invalidateegesz();
	if( Valtozott || State->editfilenev[0] == 0 || Ptop->hibas )
		if( !tolt_save( 0 ) )
			return;

	if( Ptop->hibas )
		return;

#ifdef ELMA_PS3
    Ps3DiagnosticScope diagnostics("editor-play");
    if(!floadlevel_p(State->editfilenev)){
        // The play loader may have replaced/deleted topology before refusing
        // its graphics. Reopen the saved editor copy and restore 1x assets;
        // returning directly could leave the editor with NULL/stale pointers.
        Pgy=NULL;Pker=NULL;Psp=NULL;
        if(!floadlevel_e(State->editfilenev,1))State->editfilenev[0]=0;
        invalidateegesz();mk_emptychar();Pal_editor->set();return;
    }
#else
	floadlevel_p( State->editfilenev );
#endif

	Prec1->erase( State->editfilenev );
	Prec2->erase( State->editfilenev );
	lejatszo( State->editfilenev );

	// The editor keeps working with the original-size LGR:
	editornagyitas();

	mk_emptychar();

	// Visszaallitjuk eredeti allapotot:
	Pal_editor->set();

	/*initmou( 640, 480 );

	// Megprobaljuk kozepre hozni egeret:
	for( int i = 0; i < 1000; i++ )
		getmou( &Moux, &Mouy );
	int mmx = 300;
	int mmy = 255;
	Moux = mmx;
	Mouy = mmy;
	setmou( mmx, mmy );
	Moux = mmx;
	Mouy = mmy;*/
}



