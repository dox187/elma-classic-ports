// The machinery of the menus: the screen (BG2 background, BG3 text in
// front, sprites), the text (szoveglista), the helmet, the keys and the
// lists to choose from (valaszt2, VALASZT2.CPP).
#include "ui_int.h"
#include "save.h"

#define REG(a) (*(vuint8*)(a))

// Bytes of the text uploaded in a frame (the vertical blank takes about
// 5.5 KB with the OAM, the helmet and the balls; each transfer of a
// column costs the time of about 150 bytes more, 4096 loses some):
#define UI_TEXT_DMA 3072

char ui_items[UI_ITEMS][UI_ITEM_LEN];
char ui_tabs[UI_ITEMS][UI_TAB_LEN];
ui_extra_t ui_extra[UI_EXTRAS];
u8 ui_nextra;

u8 ui_ready;
u8 ui_balls_on;
u8 ui_pal;
static u8 ui_blank;             // forced blank: the VRAM is written at once
static s16 hel_x, hel_y;
static s16 hel_px, hel_py, hel_sx, hel_sy;  // the place on the screen of hel_px, hel_py
static u8 hel_on;
static u16 hel_acc;
static u8 hel_frame, hel_loaded;
static u16 last_frame;
static u16 rep_held, rep_start, rep_last;
static u8 ui_anim;              // the next frame starts with kirajzolanim
static u8 in_end;               // ui_end is uploading
static u8 buf_col[2][UI_COLS];  // columns of tiles that hold text in the VRAM
static u8 buf_lo[2], buf_end[2];  // rows of tiles that hold it: lo up to end - 1
static u8 buf_new_lo, buf_new_end;

// The balls: half of (0, 2, 0) and the background is about the darker
// background of the original (szoveg2.pcx against szoveg1.pcx).
static const u8 ball_pal[4] = { 0x00, 0x00, 0x40, 0x00 };

void ui_strcpy(char* d, const char* s) {
	while( *s )
		*d++ = *s++;
	*d = 0;
}

void ui_strcat(char* d, const char* s) {
	while( *d )
		d++;
	ui_strcpy(d, s);
}

void ui_itoa(u16 v, char* d) {
	char tmp[6];
	u16 n = 0;
	do {
		tmp[n++] = '0' + v % 10;
		v /= 10;
	} while( v );
	while( n )
		*d++ = tmp[--n];
	*d = 0;
}

// The state of the menus at the start (the RAM is not cleared).
void ui_reset(void) {
	ui_pal = (REG(0x213F) & 0x10) != 0;
	ui_ready = 0;
	ui_balls_on = 0;
	ui_blank = 0;
	hel_on = 0;
	hel_px = hel_py = -1000;
	hel_acc = 0;
	hel_frame = 0;
	hel_loaded = 0xFF;
	rep_held = rep_start = rep_last = 0;
	ui_anim = 0;
	in_end = 0;
	last_frame = core_frame_count;
}

// The registers of the menus' screen (forced blank).
static void ui_regs(void) {
	u16 i;
	REG(0x2105) = 0x09;         // mode 1, BG3 in front of everything
	REG(0x2106) = 0;
	REG(0x2107) = (UIV_INTRO_MAP >> 8) & 0xFC;
	REG(0x2108) = (UIV_BG_MAP >> 8) & 0xFC;
	REG(0x2109) = (UIV_TEXT_MAP >> 8) & 0xFC;
	REG(0x210B) = ((UIV_BG_CHR >> 12) << 4) | (UIV_INTRO_CHR >> 12);
	REG(0x210C) = UIV_TEXT_CHR >> 12;
	REG(0x2101) = 0xA0 | (UIV_OBJ >> 13);  // sprites of 32x32 and 64x64
	for( i = 0x2123; i <= 0x212B; i++ )
		REG(i) = 0;             // no windows
	REG(0x212E) = 0;
	REG(0x212F) = 0;
	REG(0x212C) = 0x16;         // BG2, BG3, sprites
	REG(0x212D) = 0x02;         // the sub screen: the background, for the balls
	REG(0x2130) = 0x02;         // color math with the sub screen
	REG(0x2131) = 0x50;         // half of the sum, on sprites of palettes 4-7
	// The fixed color, the sub screen where the background is not drawn
	// yet (the first menu scrolling in): the balls are dark green there,
	// as the original draws them over the black (Zoldsor).
	REG(0x2132) = 0xE0;
	REG(0x2132) = 0x40 | 2;
	REG(0x420C) = 0;            // no HDMA
	core_scroll[0] = 0;
	core_scroll[2] = 0;
	core_scroll[4] = 0;
	// The first line of the screen is line 1 of the backgrounds at 0:
	core_scroll[1] = 0xFFFF;
	core_scroll[3] = 0xFFFF;
	core_scroll[5] = 0xFFFF;
}

void ui_enter(void) {
	u16 i;
	if( ui_ready )
		return;
	core_screen_off();
	ui_blank = 1;
	ui_regs();
	core_cgram_now(0, ui_text_pal, 8);
	core_cgram_now(UI_BG_PAL * 16, ui_bg_pal, 32);
	core_cgram_now(UI_INTRO_PAL * 16, ui_intro_pal, UI_INTRO_PALS * 32);
	core_cgram_now(128, ui_helmet_pal, 32);
	core_cgram_now(192, ball_pal, 4);
	core_vram_now(UIV_BG_CHR, ui_bg_chr, UI_BG_TILES * 32);
	core_vram_now(UIV_BG_MAP, ui_bg_map, 2048);
	core_vram_now(UIV_INTRO_CHR, ui_intro_chr, UI_INTRO_TILES * 32);
	core_vram_now(UIV_INTRO_MAP, ui_intro_map, 2048);
	core_vram_fill_now(UIV_TEXT_CHR, 0, UI_ROWS * 32 * 8);
	core_vram_fill_now(UIV_OBJ, 0, 0x2000);
	// The map of the text: every cell its own tile of the canvas, in front.
	REG(0x2115) = 0x80;
	REG(0x2116) = UIV_TEXT_MAP & 0xFF;
	REG(0x2117) = UIV_TEXT_MAP >> 8;
	for( i = 0; i < 1024; i++ ) {
		u16 t = i < UI_ROWS * 32 ? (i & 31) * UI_ROWS + (i >> 5) : 0;
		REG(0x2118) = (u8)t;
		REG(0x2119) = (u8)((t >> 8) | 0x20);
	}
	ui_canvas_clear_all();
	for( i = 0; i < UI_COLS; i++ )
		buf_col[0][i] = 0;
	buf_lo[0] = UI_ROWS;
	buf_end[0] = 0;
	core_oam_clear();
	hel_loaded = 0xFF;
	hel_on = 0;
	ui_balls_vram_reset();
	ui_ready = 1;
	last_frame = core_frame_count;
	core_screen_on(15);
}

void ui_leave(void) {
	core_screen_off();
	REG(0x420C) = 0;
	core_oam_clear();
	ui_ready = 0;
}

void ui_invalidate(void) {
	ui_ready = 0;
}

// A new picture of texts: the canvas is cleared.
void ui_begin(void) {
	ui_canvas_clear();
}

// The texts drawn since ui_begin go to the screen (over a few frames). The
// canvas is stored by columns of tiles, so a column is one transfer; only
// the columns and the rows that hold text now or held it are sent.
void ui_end(void) {
	u16 c, lo = UI_ROWS, end = 0, r;
	for( r = 0; r < UI_ROWS; r++ ) {
		if( ui_row_used[r] ) {
			if( r < lo )
				lo = r;
			end = r + 1;
		}
	}
	buf_new_lo = lo;
	buf_new_end = end;
	if( buf_lo[0] < lo )
		lo = buf_lo[0];
	if( buf_end[0] > end )
		end = buf_end[0];
	in_end = 1;
	for( c = 0; c < UI_COLS; c++ ) {
		u16 off;
		u16 size;
		if( !ui_col_used[c] && !buf_col[0][c] )
			continue;
		off = c * UI_CANVAS_STRIDE + UI_CANVAS_PAD + lo * 16;
		size = (end - lo) * 16;
		if( size ) {
			if( ui_blank ) {
				core_vram_now(UIV_TEXT_CHR + c * (UI_ROWS * 8) + lo * 8, ui_canvas + off, size);
			}
			else {
				while( 1 ) {
					if( core_dmaq_bytes + size <= UI_TEXT_DMA ) {
						if( core_queue_vram(UIV_TEXT_CHR + c * (UI_ROWS * 8) + lo * 8, ui_canvas + off, size) )
							break;
					}
					ui_frame();
				}
			}
		}
	}
	for( c = 0; c < UI_COLS; c++ )
		buf_col[0][c] = ui_col_used[c];
	buf_lo[0] = buf_new_lo;
	buf_end[0] = buf_new_end;
	in_end = 0;
}

// y of the 640x480 menus on the screen.
s16 ui_y(s16 y) {
	return (2 * (y + UI_SHIFT_Y) + 2) / 5;
}

void ui_text(s16 x, s16 y, const char* s) {
	if( x < 0 )
		x = 0;
	ui_text_draw(x, ui_y(y), s);
}

u16 ui_text_len(const char* s) {
	u16 n = 0;
	while( *s ) {
		u8 c = *s++;
		if( c == ' ' )
			n += UI_FONT_SPACE;
		else if( ui_font_pcw[c] )
			n += ui_font_pcw[c] + UI_FONT_TAV;
	}
	return n;
}

void ui_text_center(s16 x, s16 y, const char* s) {
	ui_text(x - (s16)(ui_text_len(s) / 2), y, s);
}

// The helmet at the place szoveglista::setsisak gets (x0-30, row).
void ui_helmet(s16 x, s16 y) {
	hel_x = x;
	hel_y = y;
	hel_on = 1;
}

void ui_helmet_off(void) {
	hel_on = 0;
}

// The helmet and the balls of a frame, moved down by dy lines (the menu
// scrolling in), then the frame is shown.
static void ui_show(s16 dy) {
	u16 n = core_frame_count - last_frame;
	u8 f;
	if( n > 30 )
		n = 30;
	last_frame = core_frame_count;
	// The helmet turns 31.2 frames a second (anim::getframe: 0.014 of 0.0024
	// at 182 ticks a second): 0.52 a frame of 60, 0.624 of 50.
	if( save.anim_menus ) {
		u16 step = ui_pal ? 40894 : 34079;
		while( n-- ) {
			u16 a = hel_acc + step;
			if( a < hel_acc ) {
				hel_frame++;
				if( hel_frame >= UI_HELMET_FRAMES )
					hel_frame = 0;
			}
			hel_acc = a;
		}
		f = hel_frame;
	}
	else
		f = 25;                 // getframebyindex( 25 )
	if( hel_on ) {
		s16 x, y;
		if( hel_x != hel_px || hel_y != hel_py ) {
			hel_px = hel_x;
			hel_py = hel_y;
			hel_sx = (2 * (hel_x - 20) + 2) / 5;   // blt8 at sisakx-20, sisaky-7
			hel_sy = ui_y(hel_y - 7);
		}
		x = hel_sx;
		y = hel_sy + dy;
		if( f != hel_loaded ) {
			const u8* src = ui_helmet_chr + f * 192;
			core_queue_vram(UIV_OBJ, src, 64);
			core_queue_vram(UIV_OBJ + 16 * 16, src + 64, 64);
			core_queue_vram(UIV_OBJ + 32 * 16, src + 128, 64);
			hel_loaded = f;
		}
		if( y <= -32 || y >= 224 ) {
			x = 0;
			y = 224;
		}
		core_oam[0] = (u8)x;
		core_oam[1] = (u8)y;
		core_oam[2] = 0;
		core_oam[3] = 0x20;     // priority 2, palette 0
		core_oam[512] = (core_oam[512] & 0xFC) | ((x >> 8) & 1);
	}
	else {
		core_oam[0] = 0;
		core_oam[1] = 224;
		core_oam[512] &= 0xFC;
	}
	if( ui_balls_on && save.anim_menus && !dy )
		ui_balls_step(core_frame_count);
	if( ui_balls_on && save.anim_menus )
		ui_balls_draw(dy);
	else
		ui_balls_hide();
	ui_balls_upload();
	core_frame_done();
	ui_blank = 0;
}

// The first menu after the intro picture comes in (szoveglista::
// kirajzolanim): the intro moves down, the background of the menu rises
// from the bottom, its texts, helmet and balls come down from the top, 2.3
// pixels of the original a tick of 182 a second: 2.79 lines a frame. An
// HDMA of TM and TS shows each part where it is.
static u8 hdma_tab[2][32];

static void hdma_line(u8* t, u16* i, u16 lines, u8 tm, u8 ts) {
	while( lines ) {
		u16 c = lines > 127 ? 127 : lines;
		t[(*i)++] = (u8)c;
		t[(*i)++] = tm;
		t[(*i)++] = ts;
		lines -= c;
	}
}

static void intro_scroll(void) {
	u16 d16 = 0, buf = 0, first = 1;
	REG(0x4370) = 0x01;         // two registers: TM, TS
	REG(0x4371) = 0x2C;
	REG(0x4374) = 0x7E;
	while( 1 ) {
		u16 d = d16 >> 8;
		u16 a, b, c, l, next, i = 0;
		u8* t = hdma_tab[buf];
		if( d >= 224 )
			break;
		a = 16 + d;             // the intro from this line
		b = 224 - d;            // the background from this line
		c = d;                  // the texts and the sprites to this line
		// Line 0 of the frame is not shown: the first entry has it too.
		l = 0;
		while( l < 224 ) {
			u8 tm = 0, ts = 0;
			next = 224;
			if( l >= a )
				tm |= 0x01;
			else if( a < next )
				next = a;
			if( l >= b ) {
				tm |= 0x02;
				ts = 0x02;
			}
			else if( b < next )
				next = b;
			if( l < c ) {
				tm |= 0x14;
				if( c < next )
					next = c;
			}
			hdma_line(t, &i, next - l + (l == 0), tm, ts);
			l = next;
		}
		t[i] = 0;
		core_queue_reg(0x4372, (u16)t & 0xFF);
		core_queue_reg(0x4373, (u16)t >> 8);
		if( first )
			core_queue_reg(0x420C, 0x80);
		first = 0;
		core_scroll[1] = (u16)(-(s16)a - 1);
		core_scroll[3] = (u16)((s16)d - 225);
		core_scroll[5] = (u16)(223 - (s16)d);
		ui_show((s16)d - 224);
		d16 += ui_pal ? 857 : 714;
		buf ^= 1;
	}
	core_queue_reg(0x420C, 0);
	core_queue_reg(0x212C, 0x16);
	core_queue_reg(0x212D, 0x02);
	core_scroll[1] = 0xFFFF;
	core_scroll[3] = 0xFFFF;
	core_scroll[5] = 0xFFFF;
}

// The intro picture (teljes) until a button; the first menu then comes in.
void ui_intro_screen(void) {
	ui_enter();
	REG(0x212C) = 0x01;         // the intro picture only
	REG(0x212D) = 0;
	core_scroll[1] = (u16)(-17);  // 16 lines down
	core_pad_take();
	while( 1 ) {
		core_frame_done();
		if( core_pad_take() )
			break;
	}
	ui_blank = 0;
	ui_balls_init(core_frame_count);
	last_frame = core_frame_count;
	ui_anim = 1;
}

// Shows the frame: the helmet and the balls move, the queued uploads go.
void ui_frame(void) {
	if( ui_anim && !in_end ) {
		ui_anim = 0;
		intro_scroll();
	}
	ui_show(0);
}

// The keys of the menus pressed since the last call, Up, Down, Left,
// Right, L and R repeating while held.
u16 ui_keys(void) {
	u16 p = core_pad_take();
	u16 held = core_pad & (JOY_UP | JOY_DOWN | JOY_LEFT | JOY_RIGHT | JOY_L | JOY_R);
	u16 k = 0;
	u16 now = core_frame_count;
	if( held != rep_held || (p & held) ) {
		rep_held = held;
		rep_start = now;
		rep_last = now;
	}
	else if( held && now - rep_start >= 20 && now - rep_last >= 4 ) {
		rep_last = now;
		p |= held;
	}
	if( p & JOY_UP )
		k |= K_UP;
	if( p & JOY_DOWN )
		k |= K_DOWN;
	if( p & JOY_LEFT )
		k |= K_LEFT;
	if( p & JOY_RIGHT )
		k |= K_RIGHT;
	if( p & JOY_L )
		k |= K_PGUP;
	if( p & JOY_R )
		k |= K_PGDN;
	if( p & (JOY_A | JOY_START) )
		k |= K_ENTER;
	if( p & JOY_B )
		k |= K_ESC;
	if( p & (JOY_X | JOY_Y | JOY_SELECT) )
		k |= 0x100;             // other buttons: only "a key"
	return k;
}

// Shows frames until one of the keys.
u16 ui_wait(u16 keys) {
	u16 k;
	core_pad_take();            // mk_emptychar
	while( 1 ) {
		ui_frame();
		k = ui_keys();
		if( keys == K_ANY ? k != 0 : (k & keys) != 0 )
			return k;
	}
}

void ui_list_init(ui_list_t* l, const char* title, s16 x0, s16 y0, s16 dy, u8 egykepen) {
	ui_strcpy(l->title, title);
	l->x0 = x0;
	l->y0 = y0;
	l->dy = dy;
	l->egykepen = egykepen;
	l->x0_tab = 0;
	l->cimy = 30;
	l->esc = 1;
	l->tabs = 0;
	l->kur = 0;
	l->n = 0;
	ui_nextra = 0;
}

// valaszt2::valassz: the title, the rows from ui_items (and ui_tabs) and
// the texts of ui_extra; returns the row chosen, -1 for Esc.
s16 ui_choose(ui_list_t* l) {
	s16 n = l->n;
	s16 eredeti = l->egykepen;
	s16 egykepen = eredeti + 2 * (UI_SHIFT_Y / l->dy);
	s16 lathato0 = eredeti < n ? eredeti : n;
	s16 lathato = egykepen < n ? egykepen : n;
	s16 fel = (lathato - lathato0) * l->dy / 2;
	s16 kur = l->kur;
	s16 felso, i;
	u8 redraw = 1;
	u16 k;
	if( kur > n - 1 )
		kur = n - 1;
	if( kur < 0 )
		kur = 0;
	felso = kur - egykepen / 2;
	if( felso > n - egykepen )
		felso = n - egykepen;
	if( felso < 0 )
		felso = 0;
	ui_enter();
	ui_balls_on = 1;
	core_pad_take();            // mk_emptychar
	while( 1 ) {
		if( redraw ) {
			redraw = 0;
			ui_begin();
			for( i = 0; i < ui_nextra; i++ ) {
				if( ui_extra[i].center )
					ui_text_center(ui_extra[i].x, ui_extra[i].y - fel, ui_extra[i].text);
				else
					ui_text(ui_extra[i].x, ui_extra[i].y - fel, ui_extra[i].text);
			}
			ui_text_center(320, l->cimy - fel, l->title);
			for( i = 0; i < egykepen && i < n - felso; i++ ) {
				ui_text(l->x0, l->y0 - fel + i * l->dy, ui_items[felso + i]);
				if( l->tabs )
					ui_text(l->x0_tab, l->y0 - fel + i * l->dy, ui_tabs[felso + i]);
			}
			ui_end();
		}
		ui_helmet(l->x0 - 30, l->y0 - fel + (kur - felso) * l->dy);
		ui_frame();
		k = ui_keys();
		if( (k & K_ESC) && l->esc ) {
			l->kur = kur;
			return -1;
		}
		if( k & K_ENTER ) {
			l->kur = kur;
			return kur;
		}
		if( (k & K_UP) && kur > 0 ) {
			kur--;
			if( kur < felso ) {
				felso--;
				redraw = 1;
			}
		}
		if( (k & K_PGUP) && kur > 0 ) {
			kur -= egykepen;
			if( kur < 0 )
				kur = 0;
			if( kur < felso ) {
				felso = kur;
				redraw = 1;
			}
		}
		if( (k & K_DOWN) && kur < n - 1 ) {
			kur++;
			if( kur > felso + egykepen - 1 ) {
				felso++;
				redraw = 1;
			}
		}
		if( (k & K_PGDN) && kur < n - 1 ) {
			kur += egykepen;
			if( kur >= n )
				kur = n - 1;
			if( kur > felso + egykepen - 1 ) {
				felso = kur - egykepen + 1;
				redraw = 1;
			}
		}
	}
}
