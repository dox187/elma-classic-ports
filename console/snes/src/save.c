// The saved state in the SRAM (save.h). Two copies of 4 KB: a header,
// then the state (save_t) from byte 16. The header (written last) has the
// number of the write, the checksum of the state and the checksum
// inverted; the valid copy with the higher number is read.
#include <snes.h>
#include "core.h"
#include "levels.h"
#include "save.h"

#define SLOT_SIZE  0x1000
#define DATA_OFS   16
#define SAVE_VERSION 2
#define SUM_SEED   0x5A3C

typedef struct {
	char magic[4];              // "ELMS"
	u8 version;
	u8 levels;                  // LEVEL_COUNT of the ROM that wrote it
	u16 seq;                    // the number of the write
	u16 sum, nsum;              // checksum of the state, and inverted
	u8 pad[4];
} save_head_t;

void save_sram_write(u16 ofs, const void* src, u16 n);
void save_sram_read(u16 ofs, void* dst, u16 n);
u16 save_sum(const void* p, u16 n, u16 seed);
u16 save_sram_sum(u16 ofs, u16 n, u16 seed);

save_t save;
static save_head_t head;
static u16 save_seq;
static u8 save_slot;            // the copy written last

static u8 head_valid(u16 slot) {
	save_sram_read(slot * SLOT_SIZE, &head, sizeof(save_head_t));
	if( head.magic[0] != 'E' || head.magic[1] != 'L' || head.magic[2] != 'M' ||
		head.magic[3] != 'S' )
		return 0;
	if( head.version != SAVE_VERSION || head.levels != LEVEL_COUNT )
		return 0;
	if( (head.sum ^ head.nsum) != 0xFFFF )
		return 0;
	if( save_sram_sum(slot * SLOT_SIZE + DATA_OFS, sizeof(save_t),
					  SUM_SEED + head.seq) != head.sum )
		return 0;
	return 1;
}

// The buttons a level starts with:
static const u16 default_keys[SAVE_KEYS] = {
	JOY_B, JOY_A, JOY_LEFT, JOY_RIGHT, JOY_X, JOY_SELECT, JOY_L
};

void save_default_keys(void) {
	u16 i;
	for( i = 0; i < SAVE_KEYS; i++ )
		save.keys[i] = default_keys[i];
}

static void save_defaults(void) {
	u16 i;
	u8* p = (u8*)&save;
	for( i = 0; i < sizeof(save_t); i++ )
		p[i] = 0;
	save.sound = 1;
	save.anim_menus = 1;
	save.anim_objects = 1;
	save.detail = 1;
	save_default_keys();
}

static u8 name_char(char c) {
	return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9');
}

// Values out of their ranges (a state of another version that passed the
// checksum by chance) are made valid.
static void save_check(void) {
	u16 i, j;
	if( save.nplayers > SAVE_PLAYERS )
		save.nplayers = SAVE_PLAYERS;
	if( save.player >= save.nplayers )
		save.player = 0;
	for( i = 0; i < save.nplayers; i++ ) {
		save_player_t* p = &save.players[i];
		p->name[SAVE_NAME_LEN] = 0;
		if( !name_char(p->name[0]) ) {
			p->name[0] = 'A';
			p->name[1] = 0;
		}
		for( j = 1; j < SAVE_NAME_LEN && p->name[j]; j++ )
			if( !name_char(p->name[j]) )
				p->name[j] = 0;
		if( p->done > LEVEL_COUNT )
			p->done = LEVEL_COUNT;
		if( p->current >= LEVEL_COUNT )
			p->current = 0;
	}
	for( i = 0; i < SAVE_LEVELS; i++ ) {
		save_times_t* t = &save.times[i];
		if( i >= LEVEL_COUNT || t->count > SAVE_TIMES )
			t->count = 0;
		for( j = 0; j < t->count; j++ )
			if( t->player[j] >= save.nplayers )
				t->count = j;
	}
	save.sound = save.sound != 0;
	save.anim_menus = save.anim_menus != 0;
	save.anim_objects = save.anim_objects != 0;
	save.detail = save.detail != 0;
	// A button each, of those allowed, and none twice (and not none at
	// all):
	j = 0;
	for( i = 0; i < SAVE_KEYS; i++ )
		j |= save.keys[i];
	if( !j )
		save_default_keys();
	for( i = 0; i < SAVE_KEYS; i++ ) {
		u16 k = save.keys[i];
		if( (k & ~SAVE_KEYS_ALLOWED) || (k & (k - 1)) ) {
			save_default_keys();
			break;
		}
		for( j = 0; j < i; j++ )
			if( k && save.keys[j] == k ) {
				save_default_keys();
				break;
			}
	}
}

static void write_slot(u8 slot) {
	head.magic[0] = 'E';
	head.magic[1] = 'L';
	head.magic[2] = 'M';
	head.magic[3] = 'S';
	head.version = SAVE_VERSION;
	head.levels = LEVEL_COUNT;
	head.seq = save_seq;
	head.sum = save_sum(&save, sizeof(save_t), SUM_SEED + save_seq);
	head.nsum = head.sum ^ 0xFFFF;
	head.pad[0] = head.pad[1] = head.pad[2] = head.pad[3] = 0;
	save_sram_write(slot * SLOT_SIZE + DATA_OFS, &save, sizeof(save_t));
	save_sram_write(slot * SLOT_SIZE, &head, sizeof(save_head_t));
}

void save_load(void) {
	u8 a, b;
	u16 seq_a, seq_b;
	a = head_valid(0);
	seq_a = head.seq;
	b = head_valid(1);
	seq_b = head.seq;
	if( !a && !b ) {
		// First start, or both copies broken: an empty state in both.
		save_defaults();
		save_seq = 0;
		write_slot(0);
		save_seq = 1;
		write_slot(1);
		save_slot = 1;
		return;
	}
	// The valid copy written last:
	save_slot = a ? 0 : 1;
	if( a && b ) {
		if( (s16)(seq_b - seq_a) > 0 )
			save_slot = 1;
	}
	save_seq = save_slot ? seq_b : seq_a;
	save_sram_read(save_slot * SLOT_SIZE + DATA_OFS, &save, sizeof(save_t));
	save_check();
}

void save_write(void) {
	save_seq++;
	save_slot ^= 1;
	write_slot(save_slot);
}

u32 save_time(u16 level, u16 i) {
	u8* t = save.times[level].time[i];
	return (u32)t[0] | ((u32)t[1] << 8) | ((u32)t[2] << 16);
}

u32 save_best(u16 level) {
	if( level >= LEVEL_COUNT || !save.times[level].count )
		return SAVE_NO_TIME;
	return save_time(level, 0);
}

static void set_time(save_times_t* t, u16 i, u32 v, u8 player) {
	t->time[i][0] = (u8)v;
	t->time[i][1] = (u8)(v >> 8);
	t->time[i][2] = (u8)(v >> 16);
	t->player[i] = player;
}

u8 save_record(u16 level, u32 time_hs, u16 player) {
	save_times_t* t;
	u16 i, n;
	u8 result;
	// (816-tcc miscompiles && and || with a comparison of 32 bits: the
	// conditions here are one comparison each.)
	if( level >= LEVEL_COUNT )
		return SAVE_REC_NONE;
	if( !time_hs )
		return SAVE_REC_NONE;
	if( time_hs > 0xFFFFFF )
		time_hs = 0xFFFFFF;
	t = &save.times[level];
	n = t->count;
	if( n == SAVE_TIMES ) {
		if( save_time(level, SAVE_TIMES - 1) < time_hs )
			return SAVE_REC_NONE;
	}
	if( n == 0 ) {
		set_time(t, 0, time_hs, player);
		t->count = 1;
		return SAVE_REC_BEST;
	}
	result = SAVE_REC_ADDED;
	if( save_time(level, n - 1) > time_hs )
		result = SAVE_REC_TOP10;
	if( save_time(level, 0) > time_hs )
		result = SAVE_REC_BEST;
	// At the end, then into its place (the order of equal times stays):
	if( n == SAVE_TIMES )
		n--;
	else
		t->count++;
	set_time(t, n, time_hs, player);
	for( i = n; i > 0; i-- ) {
		u32 a = save_time(level, i - 1);
		if( a <= time_hs )
			break;
		set_time(t, i, a, t->player[i - 1]);
		set_time(t, i - 1, time_hs, player);
	}
	return result;
}

save_player_t* save_player(void) {
	return &save.players[save.player];
}

u16 save_levels_done(void) {
	if( !save.nplayers )
		return 0;
	return save.players[save.player].done;
}

u8 save_add_player(const char* name) {
	save_player_t* p;
	u16 i;
	if( save.nplayers >= SAVE_PLAYERS )
		return 0;
	p = &save.players[save.nplayers];
	for( i = 0; i < sizeof(save_player_t); i++ )
		((u8*)p)[i] = 0;
	for( i = 0; i < SAVE_NAME_LEN && name[i]; i++ )
		p->name[i] = name[i];
	save.player = save.nplayers;
	save.nplayers++;
	return 1;
}

u8 save_skipped(u16 level) {
	return (save.players[save.player].skipped[level >> 3] >> (level & 7)) & 1;
}

void save_set_skipped(u16 level, u8 on) {
	u8* b = &save.players[save.player].skipped[level >> 3];
	if( on )
		*b |= 1 << (level & 7);
	else
		*b &= ~(1 << (level & 7));
}
