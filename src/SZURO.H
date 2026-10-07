// Resizing pictures with a filter (the LGR's pictures when zoomed, lgrfile.cpp):
//   SZURO_LEGKOZELEBBI: nearest neighbor (atmeretez, pic8.cpp),
//   SZURO_SIMA: area average, on shrinking the average of the covered
//               pixels, on zooming the proportional blend of neighboring
//               pixels,
//   SZURO_HQX: on zooming first hq2x, hq3x or hq4x (third_party/hqx),
//              then area average to the final size; on shrinking same as
//              SZURO_SIMA.
// At a whole-number factor SZURO_SIMA repeats pixels exactly. Colors are
// rounded to the nearest palette color; the transparent color only stays
// where the picture was more than half transparent.
#define SZURO_LEGKOZELEBBI (0)
#define SZURO_SIMA (1)
#define SZURO_HQX (2)

// paltomb: the LGR's 6-bit palette (768 bytes). atlatszo < 0: no transparent
// color; ismetlodo: a texture, pixels past the picture's edge come from the
// other side. Does not delete the old picture.
pic8* atmeretez_szurovel( pic8* ps, int ujxsize, int ujysize, int szuro,
						  unsigned char* paltomb, int atlatszo, int ismetlodo );
