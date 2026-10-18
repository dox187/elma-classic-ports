/*
 * Elasto Mania PSX port: hello world smoke test.
 *
 * Initializes a 320x240 NTSC display with double buffering, draws a few
 * primitives and text, polls pad 1 and counts frames. The state lives in the
 * global `hello_state` so that the test harness can find it through the
 * symbol map (nm) and read it from emulator RAM.
 */

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <psxapi.h>
#include <psxgpu.h>
#include <psxpad.h>

#define HELLO_MAGIC 0x454C4D41u /* "ELMA" */

#define OT_LENGTH     16
#define BUFFER_LENGTH 8192
#define SCREEN_XRES   320
#define SCREEN_YRES   240

/* Read by the test harness. Keep the layout stable. */
typedef struct {
	volatile uint32_t magic;
	volatile uint32_t frames;
	volatile uint32_t pad;     /* pressed buttons, PAD_* bits of psxpad.h */
	volatile uint32_t pad_id;  /* pad type nibble, 0xf when no pad */
} HelloState;

HelloState hello_state;

typedef struct {
	DISPENV  disp_env;
	DRAWENV  draw_env;
	uint32_t ot[OT_LENGTH];
	uint8_t  buffer[BUFFER_LENGTH];
} RenderBuffer;

typedef struct {
	RenderBuffer buffers[2];
	uint8_t     *next_packet;
	int          active;
} RenderContext;

static uint8_t pad_buf[2][34];

static void setup_context(RenderContext *ctx)
{
	ResetGraph(0);
	/* Force NTSC regardless of the console region. */
	SetVideoMode(MODE_NTSC);

	SetDefDrawEnv(&ctx->buffers[0].draw_env, 0, 0, SCREEN_XRES, SCREEN_YRES);
	SetDefDispEnv(&ctx->buffers[0].disp_env, 0, 0, SCREEN_XRES, SCREEN_YRES);
	SetDefDrawEnv(&ctx->buffers[1].draw_env, 0, SCREEN_YRES, SCREEN_XRES, SCREEN_YRES);
	SetDefDispEnv(&ctx->buffers[1].disp_env, 0, SCREEN_YRES, SCREEN_XRES, SCREEN_YRES);
	for (int i = 0; i < 2; i++) {
		setRGB0(&ctx->buffers[i].draw_env, 32, 32, 96);
		ctx->buffers[i].draw_env.isbg = 1;
	}
	ctx->active = 0;
	ctx->next_packet = ctx->buffers[0].buffer;
	ClearOTagR(ctx->buffers[0].ot, OT_LENGTH);
	SetDispMask(1);
}

static void flip_buffers(RenderContext *ctx)
{
	DrawSync(0);
	VSync(0);
	RenderBuffer *draw = &ctx->buffers[ctx->active];
	RenderBuffer *disp = &ctx->buffers[ctx->active ^ 1];
	PutDispEnv(&disp->disp_env);
	DrawOTagEnv(&draw->ot[OT_LENGTH - 1], &draw->draw_env);
	ctx->active ^= 1;
	ctx->next_packet = disp->buffer;
	ClearOTagR(disp->ot, OT_LENGTH);
}

static void *new_primitive(RenderContext *ctx, int z, size_t size)
{
	RenderBuffer *buf = &ctx->buffers[ctx->active];
	uint8_t *prim = ctx->next_packet;
	addPrim(&buf->ot[z], prim);
	ctx->next_packet += size;
	return prim;
}

static void draw_text(RenderContext *ctx, int x, int y, int z, const char *text)
{
	RenderBuffer *buf = &ctx->buffers[ctx->active];
	ctx->next_packet = (uint8_t *)FntSort(&buf->ot[z], ctx->next_packet, x, y, text);
}

static void poll_pad(void)
{
	/* BIOS pad driver buffer: [0] status (0 = ok), [1] id, [2..3] buttons,
	 * active low. */
	if (pad_buf[0][0] == 0) {
		hello_state.pad_id = pad_buf[0][1] >> 4;
		hello_state.pad = (~(pad_buf[0][2] | (pad_buf[0][3] << 8))) & 0xffff;
	} else {
		hello_state.pad_id = 0xf;
		hello_state.pad = 0;
	}
}

int main(int argc, const char **argv)
{
	RenderContext ctx;
	char text[64];

	setup_context(&ctx);
	FntLoad(960, 0);

	InitPAD(pad_buf[0], 34, pad_buf[1], 34);
	StartPAD();
	ChangeClearPAD(0);

	hello_state.magic = HELLO_MAGIC;

	int x = 0, y = 0, dx = 2, dy = 1;
	for (;;) {
		poll_pad();
		if (x < 0 || x > SCREEN_XRES - 48)
			dx = -dx;
		if (y < 0 || y > SCREEN_YRES - 48)
			dy = -dy;
		x += dx;
		y += dy;

		TILE *tile = new_primitive(&ctx, 2, sizeof(TILE));
		setTile(tile);
		setXY0(tile, x, y);
		setWH(tile, 48, 48);
		setRGB0(tile, 255, 255, 0);

		POLY_G3 *tri = new_primitive(&ctx, 1, sizeof(POLY_G3));
		setPolyG3(tri);
		setXY3(tri, 160, 60, 100, 160, 220, 160);
		setRGB0(tri, 255, 0, 0);
		setRGB1(tri, 0, 255, 0);
		setRGB2(tri, 0, 0, 255);

		sprintf(text, "ELMA PSX HELLO\nframe %u\npad %04x",
			(unsigned)hello_state.frames, (unsigned)hello_state.pad);
		draw_text(&ctx, 8, 16, 0, text);

		flip_buffers(&ctx);
		hello_state.frames++;
	}
	return 0;
}
