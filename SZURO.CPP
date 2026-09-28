#include	"all.h"
#include	"third_party/hqx/hqx.h"
#include	<vector>

// Egy kep 8 bites RGB-ben es atlatszosaggal (0 vagy 255, szures utan koztes),
// soronkent, fentrol lefele:
struct szinkep {
	int xsize, ysize;
	std::vector<unsigned> rgb;   // 0x00RRGGBB
	std::vector<unsigned char> a;
};

static unsigned vgaszin( unsigned char c ) {
	return (unsigned( c ) << 2) | (c >> 4);
}

static void kepbolszinkep( pic8* ps, unsigned char* paltomb, int atlatszo,
						   szinkep* pk ) {
	pk->xsize = ps->getxsize();
	pk->ysize = ps->getysize();
	pk->rgb.assign( size_t( pk->xsize )*pk->ysize, 0 );
	pk->a.assign( size_t( pk->xsize )*pk->ysize, 255 );
	for( int y = 0; y < pk->ysize; y++ ) {
		unsigned char* sor = ps->getptr( y );
		for( int x = 0; x < pk->xsize; x++ ) {
			size_t i = size_t( y )*pk->xsize+x;
			if( atlatszo >= 0 && sor[x] == atlatszo ) {
				pk->a[i] = 0;
				continue;
			}
			unsigned char* c = &paltomb[sor[x]*3];
			pk->rgb[i] = vgaszin( c[0] ) << 16 | vgaszin( c[1] ) << 8 | vgaszin( c[2] );
		}
	}
	if( atlatszo < 0 )
		return;
	// Az atlatszo pixelek a szomszedaik szinet kapjak (nehany lepesben), hogy
	// a szures a kep szelen ne keverjen bele idegen szint:
	std::vector<unsigned char> van( pk->a );
	for( int lepes = 0; lepes < 4; lepes++ ) {
		std::vector<unsigned char> ujvan( van );
		for( int y = 0; y < pk->ysize; y++ ) {
			for( int x = 0; x < pk->xsize; x++ ) {
				size_t i = size_t( y )*pk->xsize+x;
				if( van[i] )
					continue;
				unsigned r = 0, g = 0, b = 0, db = 0;
				static const int dx[4] = { -1, 1, 0, 0 }, dy[4] = { 0, 0, -1, 1 };
				for( int k = 0; k < 4; k++ ) {
					int nx = x+dx[k], ny = y+dy[k];
					if( nx < 0 || ny < 0 || nx >= pk->xsize || ny >= pk->ysize )
						continue;
					size_t j = size_t( ny )*pk->xsize+nx;
					if( !van[j] )
						continue;
					r += pk->rgb[j] >> 16; g += (pk->rgb[j] >> 8) & 255; b += pk->rgb[j] & 255;
					db++;
				}
				if( db ) {
					pk->rgb[i] = (r/db) << 16 | (g/db) << 8 | (b/db);
					ujvan[i] = 1;
				}
			}
		}
		van.swap( ujvan );
	}
}

typedef void (*hqfuggveny)( const uint32_t*, uint32_t*, int, int );

// hqNx egy 32 bites kepre; ismetlodo kepnel a szelek korbe erik egymast
// (2 pixel keret a masik oldalrol, a vegen levagva):
static std::vector<unsigned> hqkep( const std::vector<unsigned>& forras, int xs, int ys,
									int n, int ismetlodo ) {
	static const hqfuggveny fuggvenyek[5] = { NULL, NULL, hq2x_32, hq3x_32, hq4x_32 };
	int k = ismetlodo ? 2 : 0;
	int pxs = xs+2*k, pys = ys+2*k;
	std::vector<uint32_t> be( size_t( pxs )*pys ), ki( size_t( pxs*n )*pys*n );
	for( int y = 0; y < pys; y++ ) {
		int sy = ((y-k) % ys + ys) % ys;
		for( int x = 0; x < pxs; x++ ) {
			int sx = ((x-k) % xs + xs) % xs;
			be[size_t( y )*pxs+x] = forras[size_t( sy )*xs+sx];
		}
	}
	fuggvenyek[n]( be.data(), ki.data(), pxs, pys );
	std::vector<unsigned> eredmeny( size_t( xs*n )*ys*n );
	for( int y = 0; y < ys*n; y++ )
		for( int x = 0; x < xs*n; x++ )
			eredmeny[size_t( y )*xs*n+x] = ki[size_t( y+k*n )*pxs*n+x+k*n];
	return eredmeny;
}

static void hqnagyit( const szinkep& k, int n, int ismetlodo, szinkep* pk ) {
	pk->xsize = k.xsize*n;
	pk->ysize = k.ysize*n;
	pk->rgb = hqkep( k.rgb, k.xsize, k.ysize, n, ismetlodo );
	// Az atlatszosag kulon, fekete-feher kepkent, hogy a szele is simuljon:
	std::vector<unsigned> maszk( k.a.size() );
	for( size_t i = 0; i < k.a.size(); i++ )
		maszk[i] = k.a[i] ? 0xffffff : 0;
	std::vector<unsigned> nagymaszk = hqkep( maszk, k.xsize, k.ysize, n, ismetlodo );
	pk->a.resize( nagymaszk.size() );
	for( size_t i = 0; i < nagymaszk.size(); i++ )
		pk->a[i] = (unsigned char)( (nagymaszk[i] >> 8) & 255 );
}

// Teruletatlag: minden cel pixel a lefedett forras pixelek atlaga, a lefedett
// terulet aranyaban (az atlatszok szine nem szamit bele):
static void teruletatlag( const szinkep& k, int ujx, int ujy, szinkep* pk ) {
	pk->xsize = ujx;
	pk->ysize = ujy;
	pk->rgb.assign( size_t( ujx )*ujy, 0 );
	pk->a.assign( size_t( ujx )*ujy, 0 );
	double fx = double( k.xsize )/ujx, fy = double( k.ysize )/ujy;
	for( int y = 0; y < ujy; y++ ) {
		double y1 = y*fy, y2 = (y+1)*fy;
		for( int x = 0; x < ujx; x++ ) {
			double x1 = x*fx, x2 = (x+1)*fx;
			double r = 0, g = 0, b = 0, a = 0, osszes = 0;
			for( int sy = int( y1 ); sy < y2 && sy < k.ysize; sy++ ) {
				double wy = (sy+1 < y2 ? sy+1 : y2) - (sy > y1 ? sy : y1);
				for( int sx = int( x1 ); sx < x2 && sx < k.xsize; sx++ ) {
					double w = wy*((sx+1 < x2 ? sx+1 : x2) - (sx > x1 ? sx : x1));
					size_t i = size_t( sy )*k.xsize+sx;
					double wa = w*k.a[i];
					unsigned c = k.rgb[i];
					r += wa*(c >> 16); g += wa*((c >> 8) & 255); b += wa*(c & 255);
					a += wa;
					osszes += w;
				}
			}
			size_t i = size_t( y )*ujx+x;
			if( a > 0 )
				pk->rgb[i] = unsigned( r/a+0.5 ) << 16 | unsigned( g/a+0.5 ) << 8 |
							 unsigned( b/a+0.5 );
			pk->a[i] = osszes > 0 ? (unsigned char)( a/osszes+0.5 ) : 0;
		}
	}
}

// RGB -> legkozelebbi palettaszin tabla, 6 bit szinenkent, mint a paletta:
static unsigned char Szintabla[262144];
static unsigned char Szintablapal[768];
static int Vanszintabla = 0;

static int szintav( unsigned c, unsigned char* p ) {
	int dr = int( c >> 16 ) - int( vgaszin( p[0] ) );
	int dg = int( (c >> 8) & 255 ) - int( vgaszin( p[1] ) );
	int db = int( c & 255 ) - int( vgaszin( p[2] ) );
	return 2*dr*dr + 4*dg*dg + 3*db*db;
}

static int legkozelebbi( unsigned c, unsigned char* paltomb, int kiveve ) {
	int jo = 0, jotav = 0x7fffffff;
	for( int i = 0; i < 256; i++ ) {
		if( i == kiveve )
			continue;
		int tav = szintav( c, &paltomb[i*3] );
		if( tav < jotav ) {
			jotav = tav;
			jo = i;
		}
	}
	return jo;
}

static void szintablakell( unsigned char* paltomb ) {
	if( Vanszintabla && memcmp( Szintablapal, paltomb, 768 ) == 0 )
		return;
	for( int i = 0; i < 262144; i++ ) {
		unsigned r = (i >> 12) & 63, g = (i >> 6) & 63, b = i & 63;
		unsigned c = vgaszin( (unsigned char)r ) << 16 | vgaszin( (unsigned char)g ) << 8 |
					 vgaszin( (unsigned char)b );
		Szintabla[i] = (unsigned char)legkozelebbi( c, paltomb, -1 );
	}
	memcpy( Szintablapal, paltomb, 768 );
	Vanszintabla = 1;
}

pic8* atmeretez_szurovel( pic8* ps, int ujxsize, int ujysize, int szuro,
						  unsigned char* paltomb, int atlatszo, int ismetlodo ) {
	int xs = ps->getxsize(), ys = ps->getysize();
	// Egesz szorzonal sima szurovel is a pixelek pontos ismetlese:
	int egesz = ujxsize % xs == 0 && ujysize % ys == 0 && ujxsize/xs == ujysize/ys;
	if( szuro == SZURO_LEGKOZELEBBI || !paltomb || (szuro == SZURO_SIMA && egesz) )
		return atmeretez( ps, ujxsize, ujysize );

	szinkep k;
	kepbolszinkep( ps, paltomb, atlatszo, &k );

	// HQx-szel nagyitaskor eloszor egesz szorosra (legfeljebb 4x), onnan
	// teruletatlaggal a meretre (az nagyitani is tud: egesz szorzonal a
	// pixelek ismetlese, kulonben a szomszedos pixelek aranyos keverese):
	if( szuro == SZURO_HQX && (xs < ujxsize || ys < ujysize) ) {
		int n = 1;
		while( n < 4 && (xs*n < ujxsize || ys*n < ujysize) )
			n++;
		szinkep nagy;
		hqnagyit( k, n, ismetlodo, &nagy );
		k.xsize = nagy.xsize; k.ysize = nagy.ysize;
		k.rgb.swap( nagy.rgb ); k.a.swap( nagy.a );
	}
	szinkep cel;
	if( k.xsize == ujxsize && k.ysize == ujysize ) {
		cel.xsize = k.xsize; cel.ysize = k.ysize;
		cel.rgb.swap( k.rgb ); cel.a.swap( k.a );
	}
	else
		teruletatlag( k, ujxsize, ujysize, &cel );

	// Vissza a palettara:
	szintablakell( paltomb );
	pic8* pd = new pic8( ujxsize, ujysize );
	for( int y = 0; y < ujysize; y++ ) {
		unsigned char* sor = pd->getptr( y );
		for( int x = 0; x < ujxsize; x++ ) {
			size_t i = size_t( y )*ujxsize+x;
			if( atlatszo >= 0 && cel.a[i] < 128 ) {
				sor[x] = (unsigned char)atlatszo;
				continue;
			}
			unsigned c = cel.rgb[i];
			int index = Szintabla[(c >> 18 & 63) << 12 | (c >> 10 & 63) << 6 | (c >> 2 & 63)];
			if( index == atlatszo )
				index = legkozelebbi( c, paltomb, atlatszo );
			sor[x] = (unsigned char)index;
		}
	}
	return pd;
}
