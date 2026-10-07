#include	"w_all.h"

#define MINFREQ_TB              0
#define MAXFREQ_TB              100000
#define MINPAN_TB               0
#define MIDPAN_TB               400
#define MAXPAN_TB               800
#define SHIFTPAN_TB             (-400)
#define MULTPAN_TB              (10L)
#define MINPAN_VAL              (-400)
#define MIDPAN_VAL              0
#define MAXPAN_VAL              400
#define MINVOL_TB               0
#define MAXVOL_TB               400
#define SHIFTVOL_TB             (-400)
#define MULTVOL_TB              (10L)
#define MINVOL_VAL              -400
#define MAXVOL_VAL              0

static LPDIRECTSOUND		Pds = NULL;
//LPDIRECTSOUNDBUFFER	lpDSBStreamBuffer = NULL;

struct wavheader {
	char riff[4];
	long hossz1;
	char wave[4];
	// format:
	char fmt[4];
	long miez1;
	short mod; // 1 -> 8bit uncompressed
	short channel; // 1 -> mono, 2 -> stereo
	unsigned short frekvencia;
	short miez2, miez3, miez4;
	long nemkene;
	// audio data:
	char data[4];
	long hossz;
};

LPDIRECTSOUNDBUFFER loadsbuffer( char* nev ) {
	// Megnyitjuk file-t:
	FILE* h = qopen( nev, "rb" );
	if( !h )
		hiba( "loadsbuffer-ben file nem nyilik!: ", nev  );

	wavheader header;
	int negyvennegy = 44;
	if( sizeof( wavheader ) != negyvennegy )
		hiba( "sizeof( wavheader ) != 44!" );
	
	if( fread( &header, 1, 44, h ) != 44 )
		hiba( "Nem sikerult beolvasni wav-ot!" );

	if( header.channel != 1 )
		hiba( "Wav file nem mono!: ", nev );

	// 16 bites uncompressed:
	if( header.hossz%2 )
		hiba( "16 bites wav-nal nem paros byteszam!" );

	// Direct sound lefoglalas:	
	DSBUFFERDESC    dsbdesc;
    HRESULT         hr;
    BYTE            *pbData  = NULL;
    BYTE            *pbData2 = NULL;
    DWORD           dwLength;
    DWORD           dwLength2;
	LPDIRECTSOUNDBUFFER pdsb = NULL;

    memset( &dsbdesc, 0, sizeof(DSBUFFERDESC) );

    dsbdesc.dwSize          = sizeof(DSBUFFERDESC);
    dsbdesc.dwFlags         = 0;
    dsbdesc.dwFlags         |= DSBCAPS_STATIC;
    // Use new GetCurrentPosition() accuracy (DirectX 2 feature)
    dsbdesc.dwFlags         |= DSBCAPS_CTRLDEFAULT | DSBCAPS_GETCURRENTPOSITION2;
    //if (pFileInfo->fSticky)
    //    dsbdesc.dwFlags   |= DSBCAPS_STICKYFOCUS;
    dsbdesc.dwBufferBytes   = header.hossz; //*2;

	//char tmp[20];
	//sprintf( tmp, "%d", (int)dsbdesc.dwBufferBytes );
	//uzenet( tmp );
	
	// Beallitjuk formatumot:
	WAVEFORMATEX formatstruct;
	/*formatstruct.wFormatTag		 = 1;
	formatstruct.nChannels       = 1; 
	formatstruct.nSamplesPerSec  = 22000;
	formatstruct.nAvgBytesPerSec = 44000;
	formatstruct.nBlockAlign	 = 2;
	formatstruct.wBitsPerSample  = 16;
	formatstruct.cbSize			 = 0;*/
	formatstruct.wFormatTag		 = 1;
	formatstruct.nChannels       = 1; 
	formatstruct.nSamplesPerSec  = 11025;
	formatstruct.nAvgBytesPerSec = 22050;
	formatstruct.nBlockAlign	 = 2;
	formatstruct.wBitsPerSample  = 16;
	formatstruct.cbSize			 = 0;
	dsbdesc.lpwfxFormat			 = &formatstruct;

    hr = Pds->CreateSoundBuffer( &dsbdesc,
							&pdsb,
							NULL );
	if( hr != DS_OK )
		uzenet( "In DSound CreateSoundBuffer unsuccessfull!" );

    // Ok, lock the sucker down, and copy the memory to it.
    hr = pdsb->Lock( 
			0,
			header.hossz,//*2,
			(void**)&pbData,
			&dwLength,
			(void**)&pbData2,
			&dwLength2,
			0L );
    if( hr != 0 || pbData == NULL )
		uzenet( "In DSound Lock unsuccessfull!" );

    //memcpy(pbData, pFileInfo->pbData, pFileInfo->cbSize);
	fread( pbData, 1, header.hossz/**2*/, h );

	qclose( h );
	h = NULL;

	// Ok, now unlock the buffer, we don't need it anymore.
    hr = pdsb->Unlock( pbData, header.hossz*2, NULL, 0 );
    if( hr != 0 )
		uzenet( "In DSound Unlock unsuccessfull!" );

    pbData = NULL;

    hr = pdsb->SetVolume( MAXVOL_VAL );
	if( hr != 0 )
		uzenet( "In DSound SetVolume unsuccessfull!" );
    
	hr = pdsb->SetPan( MIDPAN_VAL );
	if( hr != 0 )
		uzenet( "In DSound SetPan unsuccessfull!" );

    return pdsb;

    /*ERROR_IN_ROUTINE:
    if (pbData != NULL)
    {
    hr = pFileInfo->pDSB->lpVtbl->Unlock(pFileInfo->pDSB, pbData,
						pFileInfo->cbSize, NULL, 0);
    pbData = NULL;
    }

    if (pFileInfo->pDSB != NULL)
    {
    pFileInfo->pDSB->lpVtbl->Release(pFileInfo->pDSB);
    pFileInfo->pDSB = NULL;
    }*/
}






void dsoundfinish( void ) {
	if( Pds ) 
		IDirectSound_Release( Pds );	
		//Pds->lpVtbl->Release( Pds );
	Pds = NULL;
}


extern HWND GhWnd;

#define WAVBANKSZAM (20)
#define HANGREDUNDSZAM (4)
struct  hangmutokst {
	LPDIRECTSOUNDBUFFER mutok[HANGREDUNDSZAM];
	int kurrens;
};

static hangmutokst Hangoktomb[WAVBANKSZAM];

static void duplikal( int index ) {
	for( int i = 1; i < HANGREDUNDSZAM; i++ ) {
		HRESULT hr = Pds->DuplicateSoundBuffer(
							Hangoktomb[index].mutok[0],
							&Hangoktomb[index].mutok[i] );
		if( hr != DS_OK )
			uzenet( "Could not Create D DirectSound buffer!" );
	}
}

void initdsound( void ) {
	/*bEnumDrivers = GetProfileInt( "DSSTREAM", "EnumDrivers", FALSE );
    if( bEnumDrivers && !DoDSoundEnumerate( &guID ) ) {
		fUseGuid = TRUE;
	}
    dsRetVal = DirectSoundCreate( fUseGuid ? &guID : NULL, &lpDS, NULL );
	*/
 
	HRESULT sret = DirectSoundCreate( NULL, &Pds, NULL );

    if( sret != DS_OK ) 
        hiba( "Could not create DirectSound onject!" );
        
	sret = IDirectSound_SetCooperativeLevel( Pds,
									  GhWnd,
                                      DSSCL_NORMAL );	

    if( sret != DS_OK )
		hiba( "Could not set cooperative level",
			  "while initializing DirectSound!" );

	// Hangok betoltese:
	for( int i = 0; i < WAVBANKSZAM; i++ )
		for( int j = 0; j < HANGREDUNDSZAM; j++ ) {
			Hangoktomb[i].mutok[j] = NULL;
			Hangoktomb[i].kurrens = 0;
		}

	//loadsbuffer( "alap.wav" );
	//uzenet( "Ide nem johet!" );

	Hangoktomb[WAV_UTODES].mutok[0] = loadsbuffer( "utodes.wav" );
	Hangoktomb[WAV_TORES].mutok[0]  = loadsbuffer( "torik.wav" );
	Hangoktomb[WAV_SIKER].mutok[0]  = loadsbuffer( "siker.wav" );
	Hangoktomb[WAV_EVES].mutok[0]   = loadsbuffer( "eves.wav" );
	Hangoktomb[WAV_FORDULAS].mutok[0] = loadsbuffer( "fordul.wav" );
	Hangoktomb[WAV_UGRAS1].mutok[0] = loadsbuffer( "ugras.wav" );
	Hangoktomb[WAV_UGRAS2].mutok[0] = loadsbuffer( "ugras.wav" );
	Hangoktomb[WAV_DORZSOL].mutok[0] = loadsbuffer( "dorzsol.wav" );
	Hangoktomb[WAV_TURA].mutok[0] = loadsbuffer( "turaz.wav" );

	// Ezeket nem duplikaljuk meg:
	Hangoktomb[WAV_ALAP].mutok[0] = loadsbuffer( "harl.wav" );
	Hangoktomb[WAV_GAZ].mutok[0] = loadsbuffer( "gaz.wav" );


	duplikal( WAV_UTODES );
	duplikal( WAV_TORES );
	duplikal( WAV_SIKER );
	duplikal( WAV_EVES );
	duplikal( WAV_FORDULAS );
	duplikal( WAV_UGRAS1 );
	duplikal( WAV_UGRAS2 );
	duplikal( WAV_TURA );
	/*sret = IDirectSoundBuffer_Play( Hangoktomb[WAV_UTODES], 0, 0, 0 );
	if( !SUCCEEDED(sret) ) 
		hiba( "Nem jatszik le!" );
	hiba( "Hangon atment jol!" );*/
}

// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek
// PUBLIKUS FV.-ek PUBLIKUS FV.-ek PUBLIKUS FV.-ek



int Mute = 0;

int Hangenabled = 1;

void setvolume( double volume ) {
	volume++;
}

void starthanghigh( void ) {
}

void stophanghigh( void ) {
}

void stophang( void ) {
}

static int Alapban = 1;
static int Atmenetben = 0;
static int Berreg = 0;

void startmotor( void ) {
	// Elinditjuk motor hangjat:
	HRESULT hr; /* = IDirectSoundBuffer_Play( 
	Hangoktomb[WAV_ALAP].mutok[0], 0, 0, DSBPLAY_LOOPING  );

	if( !SUCCEEDED(hr) ) 
		hiba( "Nem indul motor hangja startmotor-ban!" );
	*/

	Alapban = 1;
	Atmenetben = 0;
	Berreg = 0;

	hr = IDirectSoundBuffer_Play( 
	Hangoktomb[WAV_DORZSOL].mutok[0], 0, 0, DSBPLAY_LOOPING  );

	if( !SUCCEEDED(hr) ) 
		hiba( "Nem indul dorzsol startmotor-ban!" );

	//setmotor( 1.0, 0 );
}

int Ucsosurlodas = 0;

static double Surlido = 0.0;
static double Surlero = 0.0;

void setsurlodas( double hangero, double ido ) {
	/*Tmpszam++;
	if( Tmpszam > 100 )
		uzenet( "setsurlodas-ban > 1000!" );*/

	hangero *= 1.5;

	if( hangero > 0.999 )
		hangero = 0.999;
	if( hangero < 0.001 )
		hangero = 0.001;

	/*if( ido > Surlido || hangero > Surlero-0.001 ) {
		// Uj surlodasi ciklus inditasa:
		Surlido = ido + 0.1;
		Surlero = hangero;
	}

	hangero = Surlero;*/

	Ucsosurlodas = hangero * 630;
	int volume = (DSBVOLUME_MAX - DSBVOLUME_MIN) * hangero +
					DSBVOLUME_MIN;
	HRESULT hr = IDirectSoundBuffer_SetVolume( 
	  Hangoktomb[WAV_DORZSOL].mutok[0], volume );

	if( !SUCCEEDED(hr) ) 
		hiba( "Nem tud allitani setsurlodas-ban!" );
}

//static int Setmszam = 0;

static double Legkoztura = 0.0;

void setmotor( double frekvencia, int gaz, double ido ) {
	//if( gaz )
	//	hiba( "setmotor-ban gaz igaz!" );

	if( ido < Legkoztura )
		return;

	if( gaz ) {
		startwave( WAV_TURA, 1.0 );					
		Legkoztura = ido + 0.2;
	}

	return;

	if( Alapban ) {
		// Eddig alapjaraton volt:
		if( gaz ) {
			// Eddig alapjarat volt, de most meghuzta gazt:
			// Leallitjuk alapjarat hangot:
			HRESULT hr = IDirectSoundBuffer_Stop(
				Hangoktomb[WAV_ALAP].mutok[0] );
			if( hr != DS_OK )
				hiba( "setmotor-ban Stop es hr != DS_OK! (uhf)" );
			// Elinditjuk berreges hangot:
			hr = IDirectSoundBuffer_Play( 
						Hangoktomb[WAV_GAZ].mutok[0], 
						0, 0, DSBPLAY_LOOPING  );
			if( hr != DS_OK )
				hiba( "setmotor-ban Play hr != DS_OK! (67tf)" );
			Alapban = 0;
			Berreg = 1;
		}
	}
	else {
		// Eddig berregett:
		if( !gaz ) {
			// Eddig berreges volt, de most alapjarat jon:
			// Leallitjuk berreges hangot:
			HRESULT hr = IDirectSoundBuffer_Stop(
				Hangoktomb[WAV_GAZ].mutok[0] );
			if( hr != DS_OK )
				hiba( "setmotor-ban Stop es hr != DS_OK! (hjg)" );
			// Elinditjuk alapjarat hangot:
			hr = IDirectSoundBuffer_Play( 
						Hangoktomb[WAV_ALAP].mutok[0], 
						0, 0, DSBPLAY_LOOPING  );
			if( hr != DS_OK )
				hiba( "setmotor-ban Play hr != DS_OK! (kljs)" );
			Alapban = 1;
			Berreg = 0;
		}
		else {
			// Eddig es mostantol fogva is berreg:
			// Frekvencia:
			if( frekvencia < 1.0 )
				frekvencia = 1.0;
			if( frekvencia > 2.0 )
				frekvencia = 2.0;

			HRESULT hr = Hangoktomb[WAV_GAZ].mutok[0]->
						SetFrequency( int(frekvencia*8000 /*11005*/ ) );
			if( hr != DS_OK )
				hiba( "setmotor-ban SetFrequency hr != DS_OK!" );
		}
	}

	/*Setmszam++;
	if( Setmszam > 100 ) {
		if( hangero )
			uzenet( "Setmszam elerte megadott szamot, 1!" );
		else
			uzenet( "Setmszam elerte megadott szamot, 0!" );
	}*/
}

void startwave( int wavindex, double hangero ) {
	//uzenet( "startwave-ben van!" );

	if( !Hangoktomb[wavindex].mutok[0] )
		hiba( "startwave-ben !Hangoktomb[wavindex].mutok[0]!" );

	HRESULT hr = IDirectSoundBuffer_Play( 
	  Hangoktomb[wavindex].mutok[Hangoktomb[wavindex].kurrens], 
	  0, 0, 0 );

	if( !SUCCEEDED(hr) ) 
		hiba( "Nem jatszik le! (hjgjhg)" );

	int volume = (DSBVOLUME_MAX - DSBVOLUME_MIN) * hangero +
					DSBVOLUME_MIN;
	hr = IDirectSoundBuffer_SetVolume( 
	  Hangoktomb[wavindex].mutok[Hangoktomb[wavindex].kurrens], 
	  volume );

	if( !SUCCEEDED(hr) ) 
		hiba( "Nem allit volume-ot! (hgvdc)" );

	Hangoktomb[wavindex].kurrens++;
	if( Hangoktomb[wavindex].kurrens >= HANGREDUNDSZAM ) 
		Hangoktomb[wavindex].kurrens = 0;

}

int vanmegwav( void ) {
	return 0;
}

void hang( void ) {
}

void nullazhangot( void ) {
}

void hangosdelay( long t ) {
	// 182*sec-et adja vissza idot tortresszel egyutt!
	double kezdo = mv_stopperido();
	while( mv_stopperido()/182.0 < kezdo/182.0+t/1000.0 )
		mv_check();
}







