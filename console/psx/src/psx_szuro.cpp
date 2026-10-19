// The PS1 build shows the LGR's pictures at their own size, so the resizing
// filters of SZURO.CPP (with their 256 KB color table and the hqx scalers)
// are left out; the platform's dd_texture_filter is always
// SZURO_LEGKOZELEBBI, where SZURO.CPP also just calls atmeretez.
#include "all.h"

pic8* atmeretez_szurovel( pic8* ps, int ujxsize, int ujysize, int, unsigned char*, int, int ) {
	return atmeretez( ps, ujxsize, ujysize );
}
