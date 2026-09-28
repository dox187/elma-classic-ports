// Kepek atmeretezese szurovel (az LGR kepei nagyitaskor, lgrfile.cpp):
//   SZURO_LEGKOZELEBBI: legkozelebbi szomszed (atmeretez, pic8.cpp),
//   SZURO_SIMA: teruletatlag, kicsinyiteskor a lefedett pixelek atlaga,
//               nagyitaskor a szomszedos pixelek aranyos keverese,
//   SZURO_HQX: nagyitaskor eloszor hq2x, hq3x vagy hq4x (third_party/hqx),
//              onnan teruletatlaggal a meretre; kicsinyiteskor mint SZURO_SIMA.
// Egesz szorzonal SZURO_SIMA a pixelek pontos ismetlese. A szinek a paletta
// legkozelebbi szinere kerekitodnek, az atlatszo szin csak ott marad, ahol a
// kep tobb mint fele atlatszo volt.
#define SZURO_LEGKOZELEBBI (0)
#define SZURO_SIMA (1)
#define SZURO_HQX (2)

// paltomb: az LGR 6 bites palettaja (768 byte). atlatszo < 0: nincs atlatszo
// szin; ismetlodo: textura, a kep szelen tuli pixelek a masik oldalrol jonnek.
// A regi kepet nem torli.
pic8* atmeretez_szurovel( pic8* ps, int ujxsize, int ujysize, int szuro,
						  unsigned char* paltomb, int atlatszo, int ismetlodo );
