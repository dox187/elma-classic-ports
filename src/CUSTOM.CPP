#include "all.h"

#ifdef ELMA_PSX
#include "psx_controls.h"

static const char* ControllerActions[PSX_CONTROL_COUNT] = {
	"Throttle", "Brake", "Rotate left", "Rotate right", "Change direction",
	"Toggle navigator", "Toggle time", "Show / hide view"
};

static void controller_button( int player, int action ) {
	valaszt2 val;
	val.egykepen = 11;
	val.x0 = 200;
	val.y0 = 85;
	val.dy = 32;
	val.escelheto = 1;
	sprintf( val.cim, "%s: choose button", ControllerActions[action] );
	const int count = psx_control_button_count();
	for( int i = 0; i < count; ++i ) {
		strcpy( Rubrikak[i], psx_control_button_name( i ) );
		if( psx_control_binding( player, action ) == psx_control_key( player, i ) )
			val.kur = i;
	}
	val.bead( count );
	const int choice = val.valassz();
	if( choice >= 0 )
		psx_control_assign( player, action, psx_control_key( player, choice ) );
}

static void controller_player( int player ) {
	int current = 0;
	while( 1 ) {
		valaszt2 val;
		val.kur = current;
		val.egykepen = 10;
		val.x0 = 56;
		val.x0_tab = 348;
		val.y0 = 96;
		val.dy = 36;
		val.escelheto = 1;
		sprintf( val.cim, "Customize Player %c (Pad %d)", 'A'+player, player+1 );
		for( int i = 0; i < PSX_CONTROL_COUNT; ++i ) {
			strcpy( Rubrikak[i], ControllerActions[i] );
			strncpy( Rubrikak_tab[i], psx_control_name( psx_control_binding( player, i ) ),
				MAXRUBRIKAHOSSZ );
			Rubrikak_tab[i][MAXRUBRIKAHOSSZ] = 0;
		}
		val.bead( PSX_CONTROL_COUNT, 1 );
		current = val.valassz();
		if( current < 0 )
			return;
		controller_button( player, current );
	}
}

int customize( void ) {
	int original[2][PSX_CONTROL_COUNT];
	for( int player = 0; player < 2; ++player )
		for( int action = 0; action < PSX_CONTROL_COUNT; ++action )
			original[player][action] = psx_control_binding( player, action );
	int current = 0;
	while( 1 ) {
		valaszt2 val;
		val.kur = current;
		val.egykepen = 10;
		val.x0 = 100;
		val.y0 = 160;
		val.dy = 50;
		val.escelheto = 1;
		strcpy( val.cim, "Customize Controls" );
		strcpy( Rubrikak[0], "Reset all controls to default" );
		strcpy( Rubrikak[1], "Customize Player A" );
		strcpy( Rubrikak[2], "Customize Player B" );
		val.bead( 3 );
		current = val.valassz();
		if( current < 0 ) {
			for( int player = 0; player < 2; ++player )
				for( int action = 0; action < PSX_CONTROL_COUNT; ++action )
					if( original[player][action] != psx_control_binding( player, action ) )
						return 1;
			return 0;
		}
		if( current == 0 )
			psx_controls_reset();
		else
			controller_player( current-1 );
	}
}

void controller_help( void ) {
	int player = 0;
	while( 1 ) {
		szoveglista layout;
		char title[64];
		sprintf( title, "Controller Layout: Player %c (Pad %d)", 'A'+player, player+1 );
		layout.addszoveg_kozep( title, 320, 16 );
		for( int i = 0; i < PSX_CONTROL_COUNT; ++i ) {
			layout.addszoveg( (char*)ControllerActions[i], 56, 86+i*34 );
			layout.addszoveg( (char*)psx_control_name( psx_control_binding( player, i ) ),
				348, 86+i*34 );
		}
		layout.addszoveg_kozep( "Select: leave level (both pads)", 320, 374 );
		layout.addszoveg_kozep( "Left/Right: switch player", 320, 408 );
		layout.addszoveg_kozep( "Cross/Start: OK; Circle/Select: Back", 320, 442 );
		mk_emptychar();
		while( 1 ) {
			if( mk_kbhit() ) {
				const int key = mk_getextchar();
				if( key == MK_ENTER || key == MK_ESC )
					return;
				if( key == MK_LEFT || key == MK_RIGHT ) {
					player = !player;
					break;
				}
			}
			layout.kirajzol();
		}
	}
}

#else

#ifdef W_95
// W_DI.CPP-ben van definialva:
char* kodtobillnev( int billkod );
#else
static char* kodtobillnev( int billkod ) {
	static char egybetu[] = "A";
	if( billkod >= 'a' && billkod <= 'z' ) {
		egybetu[0] = (char)billkod;
		return egybetu;
	}
	switch( billkod ) {
		case MK_UP: 		return "Up";
		case MK_DOWN: 		return "Down";
		case MK_LEFT: 		return "Left";
		case MK_RIGHT: 		return "Right";
		case MK_PGUP:       return "PageUp";
		case MK_PGDOWN:     return "PageDown";
		case MK_BACKSPACE:  return "Backspace";

		default: return NULL;
	}
}
#endif

typedef int* billmuttomb[MAXRUBRIKASZAM_TAB+1];

static billmuttomb Pbilltomb0;
static billmuttomb Pbilltomb1;
static billmuttomb Pbilltomb2;

static int Rubrikaszam0 = 6;
static int Rubrikaszam12 = 8;

static void betolt( billmuttomb bmuttomb, int sorszam,
					char* szoveg, int* pbillkod ) {
	strcpy( Rubrikak[sorszam], szoveg );

	char* billnev = kodtobillnev( *pbillkod );
	char tmp[20] = "";
	if( !billnev ) {
		if( *pbillkod == 0 )
			sprintf( tmp, "???" );
		else
			sprintf( tmp, "Key code: %d", *pbillkod );
		billnev = tmp;
	}

	strcpy( Rubrikak_tab[sorszam], billnev );
	bmuttomb[sorszam] = pbillkod;
}

static void gombotvalaszt( int rubrikaszam, billmuttomb bmuttomb, int sorszam ) {
	strcpy( Rubrikak_tab[sorszam], "_" );
	valaszt2 val;
	val.kur = sorszam;
	val.egykepen = 10;
	val.x0 = 60;
	val.x0_tab = 400;
	val.y0 = 86;
	val.dy = 40;
	val.escelheto = 1;

	strcpy( val.cim, "Customize controls" );
	strcpy( Rubrikak_tab[sorszam], "_" );

	val.bead( rubrikaszam, 1 ); // tab-os kiiras

	val.valassz( NULL, 0, 1 ); // Csak kirajzolja kepet

	// Megvarjuk, hogy felengedje a kivalasztashoz hasznalt gombot (game pad
	// gombja nem csak ENTER-t kuld, hanem egy iranyitas billentyujet is):
	int nyomva = 1;
	while( nyomva ) {
		mv_check( /*"cust.cpp"*/ );
		nyomva = 0;
		for( int i = 1; i < 256; i++ ) {
			if( mk_getstate( i ) )
				nyomva = 1;
		}
	}

	// Megnezzuk milyen gombot nyomott le:
	while( 1 ) {
		mv_check( /*"cust.cpp"*/ );	
		for( int i = 1; i < 256; i++ ) {
			if( mk_getstate( MK_ESC ) )
				return;

			#ifdef W_95
				if( i == 28 || i == MK_ESC )
			#else
				if( i == MK_ENTER || i == MK_ESC )
			#endif
				continue;

			if( !mk_getstate( i ) )
				continue;

			// Ez a billentyu le van nyomva:

			//char tmp[10];
			//sprintf( tmp, "Bill: %d", i );
			//hiba( tmp );

			// Most meg van nyomva egy gomb:
			// Kiszedjuk mindenhonnan mashonnan ezt a billt:
			int j;
			for( j = 3; j < Rubrikaszam0; j++ ) { // 1-tol megy
				if( *Pbilltomb0[j] == i )
					*Pbilltomb0[j] = 0;
			}
			for( j = 0; j < Rubrikaszam12; j++ ) {    // 0-tol megy
				if( *Pbilltomb1[j] == i )
					*Pbilltomb1[j] = 0;
				if( *Pbilltomb2[j] == i )
					*Pbilltomb2[j] = 0;
			}
			*bmuttomb[sorszam] = i;
			return;
		}
		// Golyokat leptetjuk:
		val.kirajzol();
	}
}

static void bejegyez0( void ) {
	strcpy( Rubrikak[0], "Reset all controls to default" );
	Rubrikak_tab[0][0] = 0;
	strcpy( Rubrikak[1], "Customize Player A" );
	Rubrikak_tab[1][0] = 0;
	strcpy( Rubrikak[2], "Customize Player B" );
	Rubrikak_tab[2][0] = 0;
	betolt( Pbilltomb0, 3, "Inc. Screen Size", &State->billplussz );
	betolt( Pbilltomb0, 4, "Dec. Screen Size", &State->billminusz );
	betolt( Pbilltomb0, 5, "Make a Screenshot", &State->billsnap );
}

static void bejegyez12( billmuttomb bmuttomb, jatekosopciok* pjatopc ) {
	betolt( bmuttomb, 0, "Throttle", 			&pjatopc->billgaz );
	betolt( bmuttomb, 1, "Brake",    			&pjatopc->billfek );
	betolt( bmuttomb, 2, "Rotate left",    		&pjatopc->billugras2 );
	betolt( bmuttomb, 3, "Rotate right",   		&pjatopc->billugras1 );
	betolt( bmuttomb, 4, "Change direction",   	&pjatopc->billfordul );
	betolt( bmuttomb, 5, "Toggle Navigator",  	&pjatopc->billview );
	betolt( bmuttomb, 6, "Toggle Time",   		&pjatopc->billtime );
	betolt( bmuttomb, 7, "Toggle Show/Hide",   	&pjatopc->billshowkep );
}

static void customizeplayer( billmuttomb bmuttomb, 
				jatekosopciok* pjatopc, char* ABjel ) {
	int kurrens = 0;
	while( 1 ) {
		valaszt2 val;
		val.kur = kurrens;
		val.egykepen = 10;
		val.x0 = 60;
		val.x0_tab = 400;
		val.y0 = 86;
		val.dy = 40;
		val.escelheto = 1;

		strcpy( val.cim, "Customize Player " );
		strcat( val.cim, ABjel );

		bejegyez12( bmuttomb, pjatopc );

		val.bead( Rubrikaszam12, 1 ); // tab-os kiiras

		kurrens = val.valassz();

		if( kurrens < 0 )
			return;

		if( kurrens >= 0 && kurrens < Rubrikaszam12 )
			gombotvalaszt( Rubrikaszam12, bmuttomb, kurrens );
	}
}

void customize( void ) {
	bejegyez12( Pbilltomb1, &State->opciok1 );
	bejegyez12( Pbilltomb2, &State->opciok2 );

	int kurrens = 0;
	while( 1 ) {
		valaszt2 val;
		val.kur = kurrens;
		val.egykepen = 10;
		val.x0 = 60;
		val.x0_tab = 400;
		val.y0 = 86;
		val.dy = 40;
		val.escelheto = 1;

		strcpy( val.cim, "Customize controls" );

		bejegyez0();

		val.bead( Rubrikaszam0, 1 ); // tab-os kiiras

		kurrens = val.valassz();

		if( kurrens < 0 )
			return;

		if( kurrens == 0 ) {
			State->resetcontrols();
			bejegyez12( Pbilltomb1, &State->opciok1 );
			bejegyez12( Pbilltomb2, &State->opciok2 );
			bejegyez0();
		}

		if( kurrens == 1 )
			customizeplayer( Pbilltomb1, &State->opciok1, "A" );

		if( kurrens == 2 )
			customizeplayer( Pbilltomb2, &State->opciok2, "B" );

		if( kurrens >= 3 && kurrens < Rubrikaszam0 )
			gombotvalaszt( Rubrikaszam0, Pbilltomb0, kurrens );
	}
}

#endif

