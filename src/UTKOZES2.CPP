#include	"all.h"

// Originally there was also a +-200 pixel (brush pixel) preliminary filter
// here around the object picture's bottom-left corner (rxint, ryint): when
// scaled it would have filtered out nearby objects too before the exact
// check, and without scaling it never filtered out anything that would have
// passed the exact check anyway.
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
