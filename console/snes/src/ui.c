// The screens of the menus as the original game shows them (ui.h).
#include "ui_int.h"
#include "ui.h"
#include "save.h"
#include "levels.h"

// Skips allowed (SKIP.CPP):
#define SKIPS_MAX (LEVEL_SHAREWARE ? 3 : 5)
// The original's Palyaszam: the levels with the last one that is not a
// real level ("More Levels" of the registered game, which is not among the
// levels here; "Please Register" of the shareware).
#define PC_PALYASZAM (LEVEL_COUNT + 1 - LEVEL_SHAREWARE)

// The rows of the original's lists (VALASZT2.CPP: LISTegykepen...):
#define LIST_EGYKEPEN 11
#define LIST_X0 200
#define LIST_Y0 90
#define LIST_DY 33

// The keys of Help (OPTIONS.CPP), the buttons of the SNES.
static const char* const help_keys[] = {
	"B", "A", "LEFT", "RIGHT", "X", "SELECT"
};
static const char* const help_what[] = {
	"- Accelerate", "- Block Wheels", "- Rotate AntiClockwise",
	"- Rotate Clockwise", "- Turn Around", "- View Box Toggle"
};
#define HELP_ROWS 6

static ui_list_t list;
static s16 main_kur;
static char text[64];

void ui_time_string(u32 hs, char* t) {
	u16 szazad = (u16)(hs % 100);
	u32 s = hs / 100;
	u16 masodperc = (u16)(s % 60);
	u16 perc = (u16)((s / 60) % 60);
	if( s >= 3600 ) {
		// ido2string: an hour or more is shown as 59:59:99.
		szazad = 99;
		masodperc = 59;
		perc = 59;
	}
	t[0] = '0' + perc / 10;
	t[1] = '0' + perc % 10;
	t[2] = ':';
	t[3] = '0' + masodperc / 10;
	t[4] = '0' + masodperc % 10;
	t[5] = ':';
	t[6] = '0' + szazad / 10;
	t[7] = '0' + szazad % 10;
	t[8] = 0;
}

static void add_extra(s16 x, s16 y, u8 center, const char* s) {
	ui_extra_t* e = &ui_extra[ui_nextra++];
	e->x = x;
	e->y = y;
	e->center = center;
	ui_strcpy(e->text, s);
}

// A screen of texts until a key (a szoveglista with no helmet).
static void text_screen_begin(void) {
	ui_enter();
	ui_balls_on = 1;
	ui_helmet_off();
	ui_begin();
}

// "Loading" (kiirloading, no balls), then the screen is given to the game,
// which loads the level in forced blank: the text stays a few frames to be
// seen, as long as the original takes to load a level.
static void loading(void) {
	u16 i;
	ui_enter();
	ui_balls_on = 0;
	ui_helmet_off();
	ui_begin();
	ui_text_center(320, 230, "Loading");
	ui_end();
	for( i = 0; i < 8; i++ )
		ui_frame();
	ui_leave();
}

// Entering a name (JATEKOS.CPP bevesznevet, with the keys of nyilasbetu):
// 1 with the name, 0 for Esc where esc allows it.
static u8 enter_name(char* nev, u8 esc) {
	u16 i = 0;
	u8 redraw = 1;
	u16 k, key;
	nev[0] = 0;
	ui_enter();
	ui_balls_on = 1;
	ui_helmet_off();
	core_pad_take();
	while( 1 ) {
		if( redraw ) {
			redraw = 0;
			ui_begin();
			nev[i] = '_';
			nev[i + 1] = 0;
			ui_text_center(320, 240, nev);
			nev[i] = 0;
			ui_text_center(320, 180, "Please enter your name:");
			ui_end();
		}
		ui_frame();
		k = ui_keys();
		if( (k & K_ESC) && esc )
			return 0;
		if( (k & K_ENTER) && i > 0 )
			return 1;
		for( key = K_UP; key <= K_RIGHT; key <<= 1 ) {
			if( !(k & key) )
				continue;
			if( key == K_LEFT ) {
				if( i > 0 )
					i--;
			}
			else if( i == 0 || key == K_RIGHT ) {
				// A new letter:
				if( i < SAVE_NAME_LEN ) {
					nev[i] = 'A';
					i++;
				}
			}
			else {
				// The last letter steps in A-Z, 0-9:
				char c = nev[i - 1];
				if( key == K_UP )
					c = c == 'Z' ? '0' : c == '9' ? 'A' : c + 1;
				else
					c = c == 'A' ? '9' : c == '0' ? 'Z' : c - 1;
				nev[i - 1] = c;
			}
			nev[i] = 0;
			redraw = 1;
		}
	}
}

// newjatekos: 1 if a player was made.
static u8 new_player(void) {
	char nev[SAVE_NAME_LEN + 2];
	if( save.nplayers >= SAVE_PLAYERS ) {
		text_screen_begin();
		ui_text_center(320, 200, "Sorry, no more players can");
		ui_text_center(320, 250, "get onto the list!");
		ui_end();
		ui_wait(K_ANY);
		return 0;
	}
	if( !enter_name(nev, 1) )
		return 0;
	save_add_player(nev);
	save_write();
	return 1;
}

// jatekosvalasztas: 1 if a player was chosen or made, 0 for Esc.
static u8 choose_player(u8 esc) {
	u16 i;
	s16 r;
	while( 1 ) {
		ui_list_init(&list, "Choose Player", LIST_X0, LIST_Y0, LIST_DY, LIST_EGYKEPEN);
		list.esc = esc;
		ui_strcpy(ui_items[0], "Create New Player");
		for( i = 0; i < save.nplayers; i++ )
			ui_strcpy(ui_items[i + 1], save.players[i].name);
		list.n = save.nplayers + 1;
		if( save.nplayers )
			list.kur = save.player + 1;
		r = ui_choose(&list);
		if( r < 0 )
			return 0;
		if( r == 0 ) {
			if( new_player() )
				return 1;
			continue;
		}
		if( save.player != r - 1 ) {
			save.player = r - 1;
			save_write();
		}
		return 1;
	}
}

void ui_intro(void) {
	char nev[SAVE_NAME_LEN + 2];
	ui_reset();
	main_kur = 0;
	save_load();
	ui_intro_screen();
	if( !save.nplayers ) {
		// The first start: the name of the first player (Esc does nothing
		// here; the original quits).
		enter_name(nev, 0);
		save_add_player(nev);
		save_write();
	}
	else
		choose_player(0);
}

// Help: the controls.
static void help(void) {
	// The second column a little more to the right than the original's 220:
	// SELECT is longer than the keys of the PC.
	s16 x1 = 90, x2 = 236, yo = 80, dy = 32;
	u16 i;
	text_screen_begin();
	ui_text_center(320, 20, "Default controls:");
	for( i = 0; i < HELP_ROWS; i++ ) {
		ui_text(x1, yo + dy * i, help_keys[i]);
		ui_text(x2, yo + dy * i, help_what[i]);
	}
	ui_text_center(320, yo + dy * 9, "After you have eaten all the fruits,");
	ui_text_center(320, yo + dy * 10, "touch the flower!");
	ui_end();
	ui_wait(K_ENTER | K_ESC);
}

static void level_title(u16 level, char* t, u8 prefix) {
	t[0] = 0;
	if( prefix )
		ui_strcpy(t, "Level ");
	ui_itoa(level + 1, t + (prefix ? 6 : 0));
	ui_strcat(t, ": ");
	ui_strcat(t, level_names[level].name);
}

// The best times of a level (levelbesttimes, elemibesttimes): nothing if
// it has none.
static void level_best_times(u16 level) {
	save_times_t* t = &save.times[level];
	u16 i, j;
	char tm[10];
	if( !t->count )
		return;
	text_screen_begin();
	level_title(level, text, 0);
	ui_text_center(320, 37, text);
	for( i = 0; i < t->count; i++ ) {
		ui_strcpy(text, save.players[t->player[i]].name);
		// Cut so that it does not reach the time:
		j = 0;
		while( text[j] )
			j++;
		while( j && ui_text_len(text) > 360 - 120 - 4 )
			text[--j] = 0;
		ui_text(120, 110 + i * 34, text);
		ui_time_string(save_time(level, i), tm);
		ui_text(360, 110 + i * 34, tm);
	}
	ui_end();
	ui_wait(K_ENTER | K_ESC);
}

// Single Player Best Times (besttimes_egytipus): the levels with the name
// of the best; the original asks Single or Multi first.
static void best_times(void) {
	u16 i, n = 0;
	s16 r;
	for( i = 0; i < save.nplayers; i++ )
		if( save.players[i].done > n )
			n = save.players[i].done;
	n++;
	if( n >= PC_PALYASZAM )
		n = PC_PALYASZAM - 1;
	ui_list_init(&list, "Single Player Best Times", 61, LIST_Y0, LIST_DY, LIST_EGYKEPEN);
	list.x0_tab = 380;
	list.tabs = 1;
	list.n = n;
	for( i = 0; i < n; i++ ) {
		ui_itoa(i + 1, ui_items[i]);
		ui_strcat(ui_items[i], " ");
		ui_strcat(ui_items[i], level_names[i].name);
		if( save.times[i].count )
			ui_strcpy(ui_tabs[i], save.players[save.times[i].player[0]].name);
		else
			ui_strcpy(ui_tabs[i], "-");
	}
	while( 1 ) {
		r = ui_choose(&list);
		if( r < 0 )
			return;
		level_best_times(r);
	}
}

// Options: the rows of the original that the SNES has.
static void options(void) {
	s16 kur = 0, r;
	u8 changed = 0;
	while( 1 ) {
		ui_list_init(&list, "Options", 72, 77, 36, 11);
		list.x0_tab = 390;
		list.tabs = 1;
		list.kur = kur;
		ui_strcpy(ui_items[0], "Player A:");
		ui_strcpy(ui_tabs[0], save.nplayers ? save_player()->name : "");
		ui_strcpy(ui_items[1], "Sound:");
		ui_strcpy(ui_tabs[1], save.sound ? "Enabled" : "Disabled");
		ui_strcpy(ui_items[2], "Animated Menus:");
		ui_strcpy(ui_tabs[2], save.anim_menus ? "Yes" : "No");
		ui_strcpy(ui_items[3], "Video Detail:");
		ui_strcpy(ui_tabs[3], save.detail ? "High" : "Low");
		ui_strcpy(ui_items[4], "Animated Objects:");
		ui_strcpy(ui_tabs[4], save.anim_objects ? "Yes" : "No");
		list.n = 5;
		r = ui_choose(&list);
		if( r < 0 ) {
			if( changed )
				save_write();
			return;
		}
		kur = r;
		if( r == 0 )
			choose_player(1);
		else {
			changed = 1;
			if( r == 1 )
				save.sound = !save.sound;
			if( r == 2 )
				save.anim_menus = !save.anim_menus;
			if( r == 3 )
				save.detail = !save.detail;
			if( r == 4 )
				save.anim_objects = !save.anim_objects;
		}
	}
}

u16 ui_main_menu(void) {
	s16 r;
	while( 1 ) {
		ui_list_init(&list, "Main Menu", 200, 100, 50, 7);
		list.esc = 0;           // the original asks "Do you want to quit?"
		list.kur = main_kur;
		ui_strcpy(ui_items[0], "Play");
		ui_strcpy(ui_items[1], "Options");
		ui_strcpy(ui_items[2], "Help");
		ui_strcpy(ui_items[3], "Best Times");
		list.n = 4;
		r = ui_choose(&list);
		main_kur = list.kur;
		if( r == 0 )
			return UI_PLAY;
		if( r == 1 )
			options();
		if( r == 2 )
			help();
		if( r == 3 )
			best_times();
	}
}

s16 ui_level_menu(void) {
	save_player_t* pl = save_player();
	u16 n = pl->done + 1, i;
	s16 r;
	if( n > LEVEL_COUNT )
		n = LEVEL_COUNT;
	ui_list_init(&list, "Select Level!", LIST_X0, LIST_Y0, LIST_DY, LIST_EGYKEPEN);
	list.kur = pl->current;
	list.n = n;
	for( i = 0; i < n; i++ ) {
		ui_itoa(i + 1, ui_items[i]);
		ui_strcat(ui_items[i], " ");
		ui_strcat(ui_items[i], save_skipped(i) ? "SKIPPED!" : level_names[i].name);
	}
	r = ui_choose(&list);
	if( r < 0 )
		return -1;
	loading();
	return r;
}

// skippelheto: the skips allowed and so far; 1 if the level can be skipped.
static u8 skippable(u16 level) {
	u16 n = 0, i;
	u8 ok;
	for( i = 0; i < level; i++ )
		n += save_skipped(i);
	ok = n < SKIPS_MAX;
	text_screen_begin();
	if( ok ) {
		ui_strcpy(text, "Number of skips allowed: ");
		ui_itoa(SKIPS_MAX, text + 25);
		ui_text_center(320, 150, text);
		ui_strcpy(text, "Number of skips so far:   ");
		ui_itoa(n, text + 26);
		ui_text_center(320, 200, text);
		ui_text_center(320, 300, "Press a key to continue!");
	}
	else {
		ui_text_center(320, 100, "You already have reached");
		ui_text_center(320, 150, "the maximum number of");
		ui_strcpy(text, "skips allowed (");
		ui_itoa(SKIPS_MAX, text + 15);
		ui_strcat(text, ")!");
		ui_text_center(320, 200, text);
		ui_text_center(320, 250, "Fullfill a previously skipped");
		ui_text_center(320, 300, "level to skip this level!");
		ui_text_center(320, 400, "Press a key to continue!");
	}
	ui_end();
	ui_wait(K_ANY);
	return ok;
}

u16 ui_after_play(u16 level, u8 finished, u32 time_hs) {
	save_player_t* pl = save_player();
	u8 ujpalya = 0, nextisvan, skipisvan;
	char valasz[48], tm[10];
	s16 r, kur;
	u8 rec;
	ui_enter();
	// idoelintezes and the rest of playlevel:
	if( !time_hs )
		finished = 0;
	if( finished ) {
		ui_time_string(time_hs, tm);
		ui_strcpy(valasz, tm);
		rec = save_record(level, time_hs, save.player);
		if( rec == SAVE_REC_BEST )
			ui_strcat(valasz, "     Best Time!");
		if( rec == SAVE_REC_TOP10 )
			ui_strcat(valasz, "     You Made the Top Ten");
		save_set_skipped(level, 0);
		if( pl->done == level ) {
			pl->done++;
			if( pl->done < LEVEL_COUNT )
				ujpalya = 1;
		}
		save_write();
	}
	else
		ui_strcpy(valasz, "You Failed to Finish!");
	nextisvan = pl->done > level && level < LEVEL_COUNT - 1;
	skipisvan = !nextisvan && level < LEVEL_COUNT - 1;
	kur = ujpalya;
	while( 1 ) {
		level_title(level, text, 1);
		ui_list_init(&list, text, 230, 110, 42, 6);
		list.kur = kur;
		add_extra(320, 370, 1, valasz);
		ui_strcpy(ui_items[0], "Play again");
		if( nextisvan || skipisvan ) {
			ui_strcpy(ui_items[1], nextisvan ? "Play next" : "Skip level");
			ui_strcpy(ui_items[2], "Best times");
			list.n = 3;
		}
		else {
			ui_strcpy(ui_items[1], "Best times");
			list.n = 2;
		}
		r = ui_choose(&list);
		kur = list.kur;
		if( r > 0 && !nextisvan && !skipisvan )
			r++;
		if( r < 0 ) {
			if( pl->current != level + ujpalya ) {
				pl->current = level + ujpalya;
				save_write();
			}
			return UI_BACK;
		}
		if( r == 0 ) {
			loading();
			return UI_PLAY_AGAIN;
		}
		if( r == 1 ) {
			if( nextisvan ) {
				pl->current = level + 1;
				save_write();
				loading();
				return UI_PLAY_NEXT;
			}
			if( skippable(level) ) {
				save_set_skipped(level, 1);
				pl->done++;
				pl->current = level + 1;
				save_write();
				loading();
				return UI_PLAY_NEXT;
			}
		}
		if( r == 2 )
			level_best_times(level);
	}
}

u16 ui_pause_menu(void) {
	return UI_QUIT;
}
