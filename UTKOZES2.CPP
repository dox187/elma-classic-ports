#include	"all.h"

// Eredetileg itt meg egy +-200 pixeles (ecset pixel) elozetes szures is volt
// az objektum kep bal also sarka (rxint, ryint) korul: nagyitva a pontos
// vizsgalat elott kiszurte volna a kozeli objektumokat is, nagyitas nelkul
// pedig sosem szurt ki olyat, ami a pontos vizsgalaton atment volna.
int utkozikesprite( vekt2 r, double sugar ) {
	if( !Pecsetalso )
		hiba( "uovruor" );

	for( int i = 0; i < MAXKEREK; i++ ) {
		kerek* pker = Ptop->kerektomb[i];
		if( !pker )
			break;

		if( !pker->aktiv )
			continue;

		if( pker->tipus == T_CEL && !Single && Tag )
			continue; // Flag Tag-ben nincsen cel

		vekt2 diff = r-pker->r;
		double maxtav = sugar + Objektumsugar;
		if( diff.x*diff.x+diff.y*diff.y < maxtav*maxtav )
			return i;
	}
	return -1;
}
