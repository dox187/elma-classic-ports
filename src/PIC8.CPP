#include    "all.h"
#include "LE_STRUCT.H"
#ifdef ELMA_PS3
#include "SPRITE_STREAM.H"
#endif
#include "MEMORY_BUDGET.H"
#ifdef ELMA_PS3
#include "ATOMIC_FILE.H"
#endif
#ifdef ELMA_PSX
#include "pcx_decode.h"
#endif

typedef unsigned char* puchar;

#ifndef W_95
	extern pic8* Pscr8;
#endif

/*class pic8 {
    friend blt8( pic8* pd, pic8* ps, int x = 0, int y = 0,
        int x1 = -10000, int y1 = -10000, int x2 = -1000, int y2 = -10000 );
    int fizkep;
    int lefoglal( xsize, ysize );
    int xsize, ysize, success;
    puchar* sormuttomb;
    puchar* szegmuttomb;
    int     szegnum;
public:
*/

// Ha igaz, akkor lefoglalt kepek minden masodik sora paratlan cimen
// kezdodik. LGR file beolvasas es betolthattereket alatt aktiv:
int Paratlankepsorok = 0;

int pic8::lefoglal( long xsizep, long ysizep ) {
    // nem szabad hasznalni size-eket, hanem sizep-eket!
    if( sormuttomb || szegmuttomb ) {
        hiba( "Bhiba pic8::lefoglalban!" );
        return 0;
    }
    // The sizes are stored in a short (getxsize, getysize):
    if( xsizep > 32767 || ysizep > 32767 ) {
        hiba( "pic8::lefoglal: a kep tul nagy!" );
        return 0;
    }
    xsize = short(xsizep);
    ysize = short(ysizep);
	// xsizep-ot 4-el oszthatova valtoztatjuk:
	if( Paratlankepsorok )
		xsizep++;
	if( xsizep % 4 ) {
        xsizep += 4-xsizep%4;
    }
    if( xsizep <= 0 || ysizep <= 0 )  {
        hiba( "sizep tul pici pic8::lefoglalban!" );
        return 0;
    }
#ifdef ELMA_PS3
    const uint64_t required=uint64_t(xsizep)*uint64_t(ysizep)+uint64_t(ysizep)*2*sizeof(void*)+65536;
    if(!elma_memory_fits(required,ps3_memory_available())) {
        hiba("Image exceeds available PS3 memory. Reduce resolution or zoom.");
        return 0;
    }
#endif
    long egyszegben = 0x0ff00l/long(xsizep); // Nehogy szegmens merete
                // megkozelitse 65536-ot
    if( egyszegben < 1 ) // a picture wider than 65280: one segment per row
        egyszegben = 1;
    // szegnum meg inkrementalva lesz a vegen, ha plussz is van!:
    szegnum = unsigned(ysizep)/egyszegben;
    long pluszszegbensorok = ysizep - szegnum*egyszegben;
    int vanplussz = pluszszegbensorok != 0;
    { sormuttomb = NEW(puchar*) puchar[unsigned(ysizep)]; }
    if( vanplussz ) {
        { szegmuttomb = NEW(puchar*) puchar[unsigned(szegnum+1)]; }
    }
    else {
        { szegmuttomb = NEW(puchar*) puchar[unsigned(szegnum)]; }
    }
	if( !sormuttomb || !szegmuttomb ) {
        uzenet( "pic8::alloc memory!" );
        return 0;
    }
    int i;
    for( i = 0; i < ysizep; i++ ) {
        sormuttomb[i] = NULL;
    }
    for( i = 0; i < szegnum; i++ ) {
        szegmuttomb[i] = NULL;
    }
    if( vanplussz )
        szegmuttomb[unsigned(szegnum)] = NULL;
    for( i = 0; i < szegnum; i++ ) {
        { szegmuttomb[i] = NEW(unsigned char*) unsigned char[unsigned(egyszegben*xsizep)]; }
        if( !szegmuttomb[i] ) {
            uzenet( "pic8::alloc memory!" );
            return 0;
        }
        for( int j = 0; j < egyszegben; j++ )
            sormuttomb[unsigned(i*egyszegben+j)] =
							&szegmuttomb[i][unsigned(j*xsizep)];
    }
    if( vanplussz ) {
        { szegmuttomb[unsigned(szegnum)] =
    NEW(unsigned char*) unsigned char[unsigned(pluszszegbensorok*xsizep)]; }
        if( !szegmuttomb[unsigned(szegnum)] ) {
            uzenet( "pic8::alloc memory!" );
            return 0;
        }
        for( int j = 0; j < pluszszegbensorok; j++ )
            sormuttomb[unsigned(szegnum*egyszegben+j)] =
                    &szegmuttomb[unsigned(szegnum)][unsigned(j*xsizep)];
    }

    if( vanplussz )
        szegnum++;

	for( int y = 0; y < ysizep; y++ ) {
		memset( sormuttomb[y], 0, unsigned(xsizep) ); // nullazunk
		if( Paratlankepsorok && (y % 2) )
			sormuttomb[y]++;
	}

	return 1;
}

pic8::~pic8( void ) {
    if( nemdestrukt )
        return;
    if( sormuttomb )
        DELETE[] sormuttomb; }
    if( szegmuttomb )
        for( int i = 0; i < szegnum; i++ )
            DELETE[] szegmuttomb[i]; }
    DELETE[] szegmuttomb; }
    if( sprite )
        DELETE[] sprite; }
}

#ifdef ELMA_PSX
void pic8::discardpixels( void ) {
    if( nemdestrukt )
        return;
    delete[] sormuttomb;
    sormuttomb = NULL;
    if( szegmuttomb )
        for( int i = 0; i < szegnum; i++ )
            delete[] szegmuttomb[i];
    delete[] szegmuttomb;
    szegmuttomb = NULL;
    szegnum = 0;
    delete[] sprite;
    sprite = NULL;
    spritehossz = 0;
}
#endif

pic8::pic8( int xsizep, int ysizep ) {
    success = 0;
    nemdestrukt = 0;
    sormuttomb = NULL;
    szegmuttomb = NULL;
    fizkep = 0;
    sprite = NULL;
    spritehossz = NULL;
    success = lefoglal( xsizep, ysizep );
}

// Mar meglevo tombre epiti ra pic8-at, destruktor nem torli:
pic8::pic8( int xsizep, int ysizep, unsigned char** ppc ) {
    success = 0;
    nemdestrukt = 1;
    sormuttomb = NULL;
    szegmuttomb = NULL;
    fizkep = 0;
    sprite = NULL;
    spritehossz = NULL;
    if( xsizep == -12333 && ysizep == -12334 ) {
        hiba( "fizkep nemdestruktos pic8 konstruktorban!" );
        return;
    }
    xsize = short(xsizep);
    ysize = short(ysizep);
    if( !ppc )
        hiba( "!ppc nemdestruktos pic8 konstruktorban!" );
    sormuttomb = ppc;
    success = 1;
}

pic8::pic8( char* nev, FILE* h ) {
    nemdestrukt = 0;
    success = 0;
    sormuttomb = NULL;
    szegmuttomb = NULL;
    fizkep = 0;
    sprite = NULL;
    spritehossz = NULL;
	// Kiterjesztes megkeresese:
    int i = strlen( nev ) - 1;
    while( i >= 0 ) {
        if( nev[i] == '.' ) {
			if( strcmpi( nev+i, ".spr" ) == 0 ) {
                spritebeolvas( nev, h );
                return;
            }
            if( strcmpi( nev+i, ".pcx" ) == 0 ) {
                pcxbeolvas( nev, h );
                return;
            }
            hiba( "pic8 konstruktor nem ismeri kiterjesztest nevben!: ", nev );
            return;
        }
        i--;
    }
    hiba( "pic8 konstruktor nem talalt pontot nevben!: ", nev );
}



int pic8::save( char* nev, unsigned char* pal, FILE* h ) {
    if( !success ) {
        hiba( "pic8::save-ben nem success!" );
        return 0;
    }
    if( fizkep ) {
        hiba( "Fizikai kepernyore save hivasa!" );
        return 0;
    }
    // Kiterjesztes megkeresese:
    int i = 0;
    while( nev[i] ) {
        if( nev[i] == '.' ) {
			if( strcmpi( nev+i, ".spr" ) == 0 ) {
                return spritesave( nev, h );
            }
            if( strcmpi( nev+i, ".pcx" ) == 0 ) {
                return pcxsave( nev, pal );
            }
            //if( strcmpi( nev+i, ".mix" ) == 0 ) {
            //  return mixsave( nev );
            //}
            hiba( "pic8::save-ben nem ismeri kiterjesztest nevben!: ", nev );
            return 0;
        }
        i++;
    }
    hiba( "pic8::save-ben nem talalt pontot nevben!: ", nev );
    return 0;
}

int pic8::getxsize( void ) {
    return xsize;
}

int pic8::getysize( void ) {
    return ysize;
}

void pic8::ppixel( int x, int y, unsigned char szin ) {
    #ifdef PIC8TEST
        if( !success ) {
            hiba( "pic8::ppixelben success = 0!" );
            return;
        }
    #endif
    if( x < 0 || x >= xsize || y < 0 || y >= ysize )
        return;

    if( !fizkep ) {
        sormuttomb[y][x] = szin;
        return;
    }
	// Fizikai:
	#ifdef W_95
		hiba( "ppixel fizikaira!" );
	#else
		putpixel8_l( x, y, szin );
	#endif
}

unsigned char pic8::gpixel( int x, int y ) {
    #ifdef PIC8TEST
        if( !success ) {
            hiba( "pic8::ppixelben success = 0!" );
            return 0;
        }
    #endif
    if( x < 0 || x >= xsize || y < 0 || y >= ysize )
        return 0;

    if( !fizkep )
        return sormuttomb[y][x];
    else {
        // Fizikai:
        hiba( "gpixel fizikaira!" );
        //return (unsigned char)gpixel_l( x, y );
		return 0;
	}
}

#ifdef TEST

// Egyebkent inline:

unsigned char* pic8::getptr( int y ) {
	#ifdef PIC8TEST
		if( !success ) {
			hiba( "pic8::getptr success = 0!" );
			return 0;
		}
		if( y < 0 || y >= ysize ) {
			hiba( "pic8::getptr y kint van!" );
			return 0;
		}
	#endif
	if( !fizkep ) {
		return sormuttomb[y];
	}
	else {
		// Fizikai:
		hiba( "pic8::getptr meghivasa fizikai kepernyore!" );
		return NULL;
	}
}

#endif

void pic8::fillbox( unsigned char szin ) {
	fillbox( 0, 0, getxsize()-1, getysize()-1, szin );
}

void pic8::fillbox( int x1, int y1, int x2, int y2, unsigned char szin ) {
    if( fizkep )
        hiba( "pic8::fillbox meghivasa fizikai kepernyore!" );
    if( x1 > x2 ) {
        int tmp = x1; x1 = x2; x2 = tmp;
    }
    if( y1 > y2 ) {
        int tmp = y1; y1 = y2; y2 = tmp;
    }
    if( x1 < 0 )
        x1 = 0;
    if( y1 < 0 )
        y1 = 0;
    if( x2 >= xsize )
        x2 = xsize-1;
    if( y2 >= ysize )
        y2 = ysize-1;
    int xhossz = x2-x1+1;
    for( int y = y1; y <= y2; y++ ) {
		memset( sormuttomb[y]+x1, szin, xhossz );
	}
}


void pic8::vizszegmens_look( int x, int y, int size, unsigned char* lookup ) {
	#ifdef PIC8TEST
		if( x < 0 || y < 0 || x+size-1 >= xsize || y >= ysize )
			hiba( "pic8::vizszegmens-ben x, y kilog!" );
	#endif
	unsigned char* psor = getptr( y );
	for( int i = 0; i < size; i++ ) {
		psor[x+i] = lookup[psor[x+i]];
	}
	//memset( &psor[x], szin, size );
}

void pic8::fuggszegmens_look( int x, int y, int size, unsigned char* lookup ) {
	#ifdef PIC8TEST
		if( x < 0 || y < 0 || x >= xsize || y+size-1 >= ysize )
			hiba( "pic8::vizszegmens-ben x, y kilog!" );
	#endif
	for( int i = 0; i < size; i++ ) {
		unsigned char* psor = getptr( y+i );
		psor[x] = lookup[psor[x]];
	}

	//for( int i = 0; i < size; i++ )
	//	ppixel( x, y+i, szin );
}


// SPRITE:

/*static void dummy( long l ) {
    l++;
} */

void pic8::spritebeolvas( char* nev, FILE* h ) {
    int volth = 1;
    if( !h ) {
        volth = 0;
        h = qopen( nev, "rb" );
        if( !h ) {
            hiba( "pic8 spritebeolvaso nem tudta megnyitni file-t!: ", nev );
            return;
        }
    }
    unsigned char c = 0;
    if( elma_read( &c, 1, 1, h ) != 1 ) {
        hiba( "Nem tudott olvasni file-bol!: ", nev );
        if( !volth ) qclose( h );
        return;
    }
    if( c != 0x2d ) {
        hiba( "SPRITE file elso karaktere nem 0x2d!: ", nev );
        if( !volth ) qclose( h );
        return;
    }

	unsigned short xsize_s = -1, ysize_s = -1;
	if( elma_read( &xsize_s, 2, 1, h ) != 1 || elma_read( &ysize_s, 2, 1, h ) != 1 ) {
        hiba( "Nem tudott olvasni SPRITE file-bol!: ", nev );
        if( !volth ) qclose( h );
        return;
	}
	xsize = xsize_s;
	ysize = ysize_s;
    if( xsize < 1 || ysize < 1 ) {
        hiba( "Meretek kicsik SPRITE file-ban!: ", nev );
        if( !volth ) qclose( h );
        return;
    }
    if( !lefoglal( xsize, ysize ) )
        return;

    for( int y = 0; y < ysize; y++ ) {
        // Egy sor beolvasasa:
        if( elma_read( sormuttomb[y], xsize, 1, h ) != 1 ) {
            hiba( "Nem tudott olvasni SPRITE file-bol!: ", nev );
            if( !volth ) qclose( h );
            return;
        }
    }

    // SPRITE reszek beolvasasa:
    char tmp[10] = "";
    if( elma_read( tmp, 7, 1, h ) != 1 ) {
        hiba( "Nem tudott olvasni SPRITE file-bol!: ", nev );
        if( !volth ) qclose( h );
        return;
    }
    if( strcmp( tmp, "SPRITE" ) != 0 ) {
        hiba( "Sprite kulcsszo nem stimmel SPRITE file-ban!: ", nev );
        if( !volth ) qclose( h );
        return;
    }

    spritehossz = -1;
    if( elma_read( &spritehossz, 2, 1, h ) != 1 ) {
        hiba( "Nem tudott olvasni SPRITE file-bol!: ", nev );
        if( !volth ) qclose( h );
        return;
    }
    if( spritehossz < 1 ) {
        hiba( "Sprite hossza tul rovid SPRITE file-ban!: ", nev );
        if( !volth ) qclose( h );
        return;
    }

    //long l = farcoreleft();
    //dummy( l );
    { sprite = NEW(unsigned char*) unsigned char[spritehossz]; }
    if( !sprite ) {
        hiba( "Nincs eleg hely SPRITE beolvasoban!: ", nev );
        if( !volth ) qclose( h );
        return;
    }
    if( elma_read( sprite, spritehossz, 1, h ) != 1 ) {
        hiba( "Nem tudott olvasni SPRITE file-bol sprite-ot!: ", nev );
        if( !volth ) qclose( h );
        return;
    }
#ifdef ELMA_PS3
    if(!elma_sprite_stream_valid(sprite,spritehossz,xsize,ysize)) {
        success=0;
        hiba("Invalid SPRITE command stream!",nev);
        if(!volth)qclose(h);
        return;
    }
#endif
    if( !volth )
        qclose( h );
    success = 1;
}

int pic8::spritesave( char* nev, FILE* h ) {
    int volth = 1;
    if( !h ) {
        volth = 0;
        h = fopen( nev, "wb" );
        if( !h ) {
            hiba( "pic8::spritesave-ben nem tudta megnyitni file-t!: ", nev );
            return 0;
        }
    }
    unsigned char c = 0x2d;
    if( elma_write( &c, 1, 1, h ) != 1 ||
        elma_write( &xsize, 2, 1, h ) != 1 ||
        elma_write( &ysize, 2, 1, h ) != 1 ) {
        hiba( "pic8::spritesave-ben nem tud irni file-ba!: ", nev );
        if( !volth ) fclose( h );
        return 0;
    }

    for( int y = 0; y < ysize; y++ ) {
        // Egy sor kiirasa:
        if( elma_write( sormuttomb[y], xsize, 1, h ) != 1 ) {
            hiba( "Nem tudott irni SPRITE file-ba!: ", nev );
			if( !volth ) fclose( h );
			return 0;
		}
	}

	// Sprite resz kiirasa:
	if( elma_write( "SPRITE", 7, 1, h ) != 1 ||
		elma_write( &spritehossz, 2, 1, h ) != 1 ||
		elma_write( sprite, spritehossz, 1, h ) != 1 ) {
		hiba( "Nem tudott irni SPRITE file-ba!: ", nev );
		if( !volth ) fclose( h );
		return 0;
	}
	if( !volth )
		fclose( h );
	return 1;
}

// PCX:
struct  pcxdescriptor {
	unsigned char   ManufactId,
					VersionNum,
					EncodingTech,
					BitsPerPlane;
	short           Xmin, Ymin, Xmax, Ymax;
	short           HorRes, VertRes;
	unsigned char   ColorMap[48],
					Reserved,
					NumberOfBitPlanes;
	short           BytesPerScanLine,
					PaletteInf;
	unsigned char   Padding[127-70+1];
};

static_assert(sizeof(pcxdescriptor)==128,"Legacy PCX header layout changed");
inline void elma_swap(pcxdescriptor& p) { elma_swap(p.Xmin);elma_swap(p.Ymin);elma_swap(p.Xmax);elma_swap(p.Ymax);elma_swap(p.HorRes);elma_swap(p.VertRes);elma_swap(p.BytesPerScanLine);elma_swap(p.PaletteInf); }

void pic8::pcxbeolvas( char* nev, FILE* h ) {
	// Gany:
	success = 1;

	int zarando = 0;
	if( !h ) {
		zarando = 1;
		h = qopen( nev, "rb" );
		if( !h )
			hiba( "Nem nyilik PCX file!: ", nev );
	}
	pcxdescriptor   desc;
	if( elma_read( &desc, sizeof( desc ), 1, h ) != 1 )
		hiba( "Nem olvas PCX file-bol!: ", nev );
	if( (desc.VersionNum != 5)    ||
		(desc.ManufactId != 10)   ||
		(desc.EncodingTech != 1)  ||
		(desc.BitsPerPlane != 8 ) ||
		(desc.NumberOfBitPlanes != 1 ) )
			hiba( "\nNem megfelelo PCX file header!", nev );
	if(desc.BytesPerScanLine<=0 || desc.BytesPerScanLine<desc.Xmax-desc.Xmin+1)
		hiba("Invalid PCX row length!",nev);
	//if( !lefoglal( desc.Xmax-desc.Xmin+1, desc.Ymax-desc.Ymin+1 ) ) {
	if( !lefoglal( desc.Xmax-desc.Xmin+1, desc.Ymax-desc.Ymin+1 ) )
		hiba( "pcx !lefoglal!" );
#ifdef ELMA_PSX
	if( psx_pcx_decode( h, sormuttomb, xsize, ysize, desc.BytesPerScanLine ) != 0 )
		hiba( "Invalid or truncated PCX data!", nev );
#else
	for( int y = 0; y < ysize; y++ ) {
		// Egy sor beolvasasa:
		int nnn = 0, ccc, iii;

		do {
			unsigned char szin;
			long l = elma_read( &szin, 1, 1, h );
			ccc = szin;
			if( l != 1 )
				hiba( "\nNem tud olvasni PCX-ben", nev );

			if( (ccc & 0xc0) == 0xc0 ) {
				iii = ccc & (short)0x3f;
				l = elma_read( &szin, 1, 1, h );
				ccc = szin;
				if( l != 1 )
					hiba( "\nNem tud olvasni PCX-ben", nev );

				while( iii-- ) {
					if( nnn < xsize )
						ppixel( nnn, y, (unsigned char)ccc );
					nnn++;
				}
			}
			else {
				if( nnn < xsize )
					ppixel( nnn, y, (unsigned char)ccc );
				nnn++;
			}
		} while( nnn < desc.BytesPerScanLine );
	}
#endif

	// success az elejen mar 1-re van allitva!
	if( zarando )
		qclose( h );
}

// Stream a bounded run at a time; no second full-size screenshot is allocated.
static bool write_pcx(pic8* image, unsigned char* pal, FILE* h) {
    const int width=image->getxsize(), height=image->getysize();
    pcxdescriptor desc={};
    desc.ManufactId=10; desc.VersionNum=5; desc.EncodingTech=1; desc.BitsPerPlane=8;
    desc.Xmax=short(width-1); desc.Ymax=short(height-1);
    desc.HorRes=10; desc.VertRes=10; desc.NumberOfBitPlanes=1;
    // PCX scanlines must have an even byte count, independently of image width.
    desc.BytesPerScanLine=static_cast<unsigned short>((width+1)&~1);
    desc.PaletteInf=1;
    if(elma_write(&desc,sizeof(desc),1,h)!=1)return false;
    for(int y=0;y<height;++y) {
        for(int x=0;x<width;) {
            const unsigned char color=image->gpixel(x,y);
            int count=1;
            while(count<63 && x+count<width && image->gpixel(x+count,y)==color)++count;
            if(count>1 || color>=0xc0) {
                const unsigned char marker=static_cast<unsigned char>(0xc0|count);
                if(elma_write(&marker,1,1,h)!=1)return false;
            }
            if(elma_write(&color,1,1,h)!=1)return false;
            x+=count;
        }
        if(width&1) {const unsigned char padding=0;if(elma_write(&padding,1,1,h)!=1)return false;}
    }
    const unsigned char palette_marker=0x0c;
    if(elma_write(&palette_marker,1,1,h)!=1)return false;
    for(int i=0;i<768;++i) {
        const unsigned char color=pal?static_cast<unsigned char>(pal[i]<<2):static_cast<unsigned char>(i/3);
        if(elma_write(&color,1,1,h)!=1)return false;
    }
    return true;
}

int pic8::pcxsave(char* nev, unsigned char* pal) {
#ifdef ELMA_PS3
    elma_atomic_file output(nev);
    FILE* h=output.file();
    if(!h || !output.commit(write_pcx(this,pal,h))) {
        uzenet("Could not save screenshot: ",nev);
        return 0;
    }
#else
    FILE* h=fopen(nev,"wb");
    if(!h) {hiba("pcxsave-ben nem nyilik file!: ",nev);return 0;}
    bool ok=write_pcx(this,pal,h);
    if(fclose(h)!=0)ok=false;
    if(!ok) {hiba("pcxsave-ben sikertelen iras!: ",nev);return 0;}
#endif
    return 1;
}

//int Debugblt = 0;
void blt8( pic8* pd, pic8* ps, int x, int y,
                int x1, int y1, int x2, int y2 ) {
    #ifdef PIC8TEST
        if( y2 == -10000 && (x1 != -10000 || y1 != -10000 || x2 != -10000 ) ) {
            hiba( "blt8 hivasa y2 == -10000 (default), de elotte nem mind!" );
            return;
        }
	  #ifndef W_95
		if( pd == Pscr8 && ps == Pscr8 ) {
			hiba( "blt8 hivasa, dest es source is fizikai kepernyo!" );
			return;
		}
	  #endif
		if( !pd || !ps ) {
			hiba( "blt8 hivasa, dest vagy source NULL!" );
			return;
		}
	#endif

	//if( Debugblt ) idejott
	//	hiba( "Itt van 17!" );

	if( pd->sprite ) {
		hiba( "blt8 hivasa, de dest sprite!" );
		return;
	}
	if( x1 == -10000 ) {
		x1 = y1 = 0;
		x2 = ps->xsize-1;
		y2 = ps->ysize-1;
	}
	else {
		// Sorrend beallitasa:
		if( x2 < x1 ) {
			int tmp = x1;
			x1 = x2;
			x2 = tmp;
		}
		if( y2 < y1 ) {
			int tmp = y1;
			y1 = y2;
			y2 = tmp;
		}
	}
	// Levagdosasa reszeknek x iranyban:
	// Eloszor source kepnek megfeleloen:
	if( x1 < 0 ) {
		x += -x1;
		x1 = 0;
	}
	if( x2 >= ps->xsize ) {
		x -= x2-(ps->xsize-1);
		x2 = ps->xsize-1;
	}
	// Most destinacionak megfeleloen:
	if( x < 0 ) {
		x1 += -x;
		x = 0;
	}
	if( x+(x2-x1) >= pd->xsize ) {
		x2 -= x+(x2-x1)-(pd->xsize-1);
	}
	if( x1 > x2 )
		return;

	// Levagdosasa reszeknek y iranyban:
	// Eloszor source kepnek megfeleloen:
	if( y1 < 0 ) {
		y += -y1;
		y1 = 0;
	}
	if( y2 >= ps->ysize ) {
		y -= y2-(ps->ysize-1);
		y2 = ps->ysize-1;
	}
	// Most destinacionak megfeleloen:
	if( y < 0 ) {
		y1 += -y;
		y = 0;
	}
	if( y+(y2-y1) >= pd->ysize ) {
		y2 -= y+(y2-y1)-(pd->ysize-1);
	}
	if( y1 > y2 )
		return;

	if( ps->sprite ) {
		// sprite lejatszas:
		// Itt vegig kell futni teljes sprite kepet es kozben vagni!
		unsigned buf = 0;
		unsigned char* buffer = ps->sprite;
		int desty = y-y1;
		for( int sy = 0; sy < ps->ysize; sy++ ) {
			int ybentvan = 1;
			if( sy < y1 || sy > y2 )
				ybentvan = 0;
			int sx = 0;
			while( sx < ps->xsize ) {
				switch( buffer[buf++] ) {
					case 'K':
						if( ybentvan ) {
							if( sx < x1 || sx+buffer[buf]-1 > x2 ) {
								if( !(sx > x2 || sx+buffer[buf]-1 < x1) ) {
									// Kilog, de van bent resze:
									int xkezd = sx;
									int xveg = sx+buffer[buf]-1;
									if( xkezd < x1 )
										xkezd = x1;
									if( xveg > x2 )
										xveg = x2;
									if( pd->fizkep )
										hiba( "t4ruh5t" );
										//putline8_l( x+xkezd-x1, desty,
										//&ps->sormuttomb[sy][xkezd],
										//xveg-xkezd+1 );
									else
										BYTECOPY( &pd->sormuttomb[desty][x+xkezd-x1],
										&ps->sormuttomb[sy][xkezd],
										xveg-xkezd+1 );
								}
							}
							else {
								// Nem log ki:
								if( pd->fizkep )
									hiba( "68464" );
                                    //putline8_l( x+sx-x1, desty,
                                    //&ps->sormuttomb[sy][sx],
                                    //buffer[buf] );
                                else
									BYTECOPY( &pd->sormuttomb[desty][x+sx-x1],
                                    &ps->sormuttomb[sy][sx],
                                    buffer[buf] );
                            }
                        }
                        sx += buffer[buf++];
                        break;
                    case 'N':
                        sx += buffer[buf++];
                        break;
                    default:

                        hiba( "Sprite blt-ban default parancsertelmezoben!" );
                        return;
                }
			}
            desty++;
        }

        return;
	}

	// Most mar tuti jok koordok!
	if( pd->fizkep ) {
		// Fizikai kepernyore iras:
		#ifdef W_95
			hiba( "0895t" );
		#else
			int xmeret = x2-x1+1;
			int dfy = y;
			for( int fy = y1; fy <= y2; fy++ ) {
				putline8_l( x, dfy++, &ps->sormuttomb[fy][x1], xmeret );
			}
			return;
		#endif
	}
	if( ps->fizkep ) {
		// Fizikai kepernyorol olvasas:
		#ifdef W_95
			hiba( "8795t" );
		#else
			int xmeret = x2-x1+1;
			int dfy = y;
			for( int fy = y1; fy <= y2; fy++ ) {
				getline8_l( x1, fy, &pd->sormuttomb[dfy++][x], xmeret );
			}
			return;
		#endif
	}
	// Memoria-memoria atvitel!
	int xmeret = x2-x1+1;
	int dfy = y;

	// if( Debugblt )	idejott
	//	hiba( "Itt van 18!" );

    for( int fy = y1; fy <= y2; fy++ ) {
		BYTECOPY( &pd->sormuttomb[dfy++][x], &ps->sormuttomb[fy][x1], xmeret );
    }
	//if( Debugblt )	
	//	hiba( "Itt van 19!" ); idejott
}

/*void blt8fizrefejjelle( pic8* ps ) {
    int fizxsize = Pscr8->getxsize();
    int fizysize = Pscr8->getysize();
    #ifdef PIC8TEST
        if( ps == Pscr8 ) {
            hiba( "blt8fizrefejjelle hivasa, fizikai kepernyo parral!" );
            return;
        }
        if( ps->sprite ) {
            hiba( "blt8fizrefejjelle hivasa, sprite parral!" );
            return;
        }
        if( fizxsize != ps->getxsize() || fizysize != ps->getysize() ) {
            hiba( "blt8fizrefejjelle: par size != fizikai size!" );
            return;
        }
    #endif
    for( int y = 0; y < fizysize; y++ ) {
        putbytes_l( 0, y, ps->sormuttomb[fizysize-y-1], fizxsize );
    }
} */

int pcxtopal( char* nev, unsigned char* pal ) {
    // Paletta beolvasasa:
    FILE* h = qopen( nev, "rb" );
    if( !h ) {
        hiba( "pcxtopal-ban nem tudta megnyitni file-t!: ", nev );
        return 0;
    }
    long l = -769;
    if( qseek( h, l, SEEK_END ) != 0 ) {
        hiba( "Nem tud visszalepni palettahoz 768-at PCX-ben!: ", nev );
        qclose( h );
        return 0;
    }
    char c;
    l = elma_read( &c, 1, 1, h );
    if( l != 1 ) {
        hiba( "Nem tud olvasni PCX-ben!:", nev );
        qclose( h );
        return 0;
    }
    if( c != 0x0c ) {
        hiba( "Nem 0x0C a paletta elotti byte PCX-ben!: ", nev );
        qclose( h );
        return 0;
    }
    if( elma_read( pal, 768, 1, h ) != 1 ) {
        hiba( "Nem tud olvasni PCX-ben!: ", nev );
        qclose( h );
        return 0;
    }
    for( int i = 0; i < 768; i++ )
        pal[i] = (unsigned char)(pal[i] >> 2);
    qclose( h );
    return 1;
}

int pcxtopal( char* nev, ddpal** ppddpal ) {
    unsigned char pal[768];
	pcxtopal( nev, pal );
	if( strcmp( nev, "intro.pcx" ) == 0 ) {
		// Egy kicsit gany, teljes.cpp-bol hivodik ilyen parameterrel.
		pal[0] = pal[1] = pal[2] = 0;
	}
    { *ppddpal = NEW(ddpal*) ddpal( pal ); }
    return 1;
}
void mintavetel8( pic8* pdest, pic8* psour, int x1, int y1, int x2, int y2 ) {
    // Ellenorzesek:
    #ifdef PIC8TEST
        if( !pdest || !psour )
        hiba( "mintavetel8-ban !pdest || !psour!" );
    #endif

    if( x1 > x2 ) {
        int tmp = x1; x1 = x2; x2 = tmp;
    }
    if( y1 > y2 ) {
        int tmp = y1; y1 = y2; y2 = tmp;
    }

    #ifdef PIC8TEST
        if( x1 < 0 || y1 < 0 || x2 >= pdest->getxsize() ||
                                            y2 >= pdest->getysize() )
            hiba( "pic8::mintavetel8-ban x1 < 0 || y1 < 0 || x2 >= xsize || y2 >= ysize!" );
    #endif

    int xsd = x2-x1+1;
    int ysd = y2-y1+1;
    int xss = psour->getxsize();
    int yss = psour->getysize();
    double s_per_d_y = (double)yss/ysd;
    double s_per_d_x = (double)xss/xsd;
    for( int y = 0; y < ysd; y++ ) {
        double sy = (y+0.5)*s_per_d_y;
        for( int x = 0; x < xsd; x++ ) {
            double sx = (x+0.5)*s_per_d_x;
            unsigned char c = psour->gpixel( sx, sy );
            pdest->ppixel( x1+x, y1+y, c );
        }
    }
}

void mintavetel8( pic8* pdest, pic8* psour ) {
    mintavetel8( pdest, psour, 0, 0, pdest->getxsize()-1, pdest->getysize()-1 );
}

// Kirakja fizikaira lock es unlockkal (Ez most mindenkeppen 320x200-ba valt):
/*void lassufizre( pic8* ppic, ddpal* ppal ) {
	if( ppic->getxsize() != 320 || ppic->getysize() != 200 )
		hiba( "lassufizre-ben ppic->getxsize != 320 || ppic->getysize != 200!" );

	unsigned char** ppc = lockbackbuffer();
	for( int y = 0; y < 200; y++ )
		memcpy( ppc[y+120]+160, ppic->getptr( 199-y ), 320 );

	unlockbackbuffer();
	if( ppal )
		ppal->set();
} */

// Egyenlore csak vizszintes es fuggoleges vonalak:
void pic8::line( int x1, int y1, int x2, int y2, unsigned char szin ) {
    // Sorrend:
    if( x2 < x1 ) {
        int tmp = x1;
        x1 = x2;
        x2 = tmp;
    }
    if( y2 < y1 ) {
        int tmp = y1;
		y1 = y2;
        y2 = tmp;
    }
    if( x1 == x2 ) {
        // Fuggoleges:
        for( int y = y1; y <= y2; y++ )
            ppixel( x1, y, szin  );
        return;
    }
    if( y1 == y2 ) {
        // Vizszintes:
        for( int x = x1; x <= x2; x++ )
            ppixel( x, y1, szin  );
        return;
    }
    hiba( "pic8::line egyenlore csak vizszintes es fuggoleges vonalakat tud!" );
}


void pic8::keszitbelsot( int x1, int y1, int x2, int y2, pic8* ppic ) {
	xsize = x2-x1+1;
	ysize = y2-y1+1;
	#ifdef TEST
	if( x1 < 0 || x2 >= ppic->getxsize() || y1 < 0 || y2 >= ppic->getysize() )
		hiba( "pic8::keszitbelsot!" );
	#endif
	for( int y = 0; y < ysize; y++ )
		sormuttomb[y] = ppic->getptr( y+y1 ) + x1;
}

// New picture resized with the nearest neighbor, does not delete the old one.
// Each target pixel gets the color index of the source pixel below its
// center (the transparent index too); at a whole-number factor this repeats
// the source pixels exactly:
pic8* atmeretez( pic8* ps, int ujxsize, int ujysize ) {
	if( ujxsize < 1 || ujysize < 1 )
		hiba( "atmeretez ujxsize < 1 || ujysize < 1!" );
	long long xs = ps->getxsize();
	long long ys = ps->getysize();
	pic8* pd = new pic8( ujxsize, ujysize );
	int* oszlopok = new int[ujxsize];
	for( int x = 0; x < ujxsize; x++ )
		oszlopok[x] = int( ((2*x+1)*xs)/(2ll*ujxsize) );
	for( int y = 0; y < ujysize; y++ ) {
		unsigned char* forras = ps->getptr( int( ((2*y+1)*ys)/(2ll*ujysize) ) );
		unsigned char* cel = pd->getptr( y );
		for( int x = 0; x < ujxsize; x++ )
			cel[x] = forras[oszlopok[x]];
	}
	delete[] oszlopok;
	return pd;
}
