// Loading the sprites of the bike and the objects of a level (the drawing
// is in bike.asm and objects.asm).
#include <snes.h>
#include "core.h"
#include "bike.h"
#include "levels.h"
#include "bike_data.h"

// The objects of the physics (phys.h, phys_obj_t):
typedef struct {
	u8 type, anim, gravity, active;
	s32 x, y;
} bike_obj_t;
extern bike_obj_t phys_objs[];
extern u16 phys_nobjs;

bike_anim_t bike_anim;

// bike.asm, objects.asm:
void bike_reset(void);
void obj_reset(void);
extern s32 bike_org_x, bike_org_y;
extern u16 obj_count, obj_used;
extern s16 obj_x[], obj_y[];
extern u16 obj_ta[], obj_kbit[], obj_poff[], obj_phase[];

static const u16 Bits[8] = { 1, 2, 4, 8, 16, 32, 64, 128 };

void bike_load(void) {
	// The 32 pictures of the wheel: tiles 0-127; the rest of the bike's
	// and the objects' tiles empty.
	core_vram_now(VRAM_OBJ, bike_wheel_tiles, 128 * 32);
	core_vram_fill_now(VRAM_OBJ + 128 * 16, 0, 128 * 16);
	core_cgram_now(128, bike_palettes, 4 * 32);
	REG_OBSEL = 0x63;
	bike_reset();
	bike_anim.turn = 65535;
	bike_anim.volt = 0;
	bike_anim.volt1 = 0;
}

// Level pixels of a distance from the origin (16.16 meters), rounded.
static s16 lpx(s32 d) {
	if( d < 0 )
		d = 0;
	return (s16)(((d >> 8) * 4915 + 32768) >> 16);
}

void objects_load(u16 level) {
	u16 i, n, k;
	bike_obj_t* o;
	bike_org_x = level_geom[level].org_x;
	bike_org_y = level_geom[level].org_y;
	obj_used = 0;
	n = 0;
	for( i = 0; i < phys_nobjs && n < 64; i++ ) {
		o = &phys_objs[i];
		if( o->type == 4 )
			continue;
		if( o->type == 1 )
			k = 0;
		else if( o->type == 3 )
			k = 1;
		else
			k = 2 + o->anim % OBJ_FOODS;
		obj_x[n] = lpx(o->x - bike_org_x);
		obj_y[n] = lpx(bike_org_y - o->y);
		// Tile 192 + 2k, palette 3, priority 2:
		obj_ta[n] = 192 + 2 * k + 0x2600;
		obj_kbit[n] = Bits[k];
		obj_poff[n] = o->type == 2 ? i * 12 : 0xFFFF;
		// The phase of the bobbing (s_random of the original), killers
		// do not bob:
		obj_phase[n] = o->type == 3 ? 0xFFFF : (i * 151 + 71) & 255;
		obj_used |= Bits[k];
		n++;
	}
	obj_count = n;
	obj_reset();
}
