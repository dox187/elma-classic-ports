; The sound driver of the SPC700 (wla-spc700). It plays the sounds of a
; level on the S-DSP as the mixer of the original game mixes them
; (SDL_HHIGH.CPP, after F_WIN/W_HHIGH.CPP):
;
; - The engine: its start (Pw1) runs into the idle loop (Pw2). With the gas
;   it fades into Pw3, which runs into the gas loop (Pw4), whose pitch
;   follows the wheel (1.0-2.0 times the rate) sliding over each buffer of
;   the mixer. Without the gas the gas loop fades into the idle loop. Two
;   voices take turns for the fades.
; - The friction loop, its volume sliding over each buffer; silent while it
;   is below 0.1.
; - Up to five effects at a time (MAXWAV of the original): a new one is
;   dropped while all five play.
;
; The original mixer works on buffers of 550 samples (49.9 ms) and looks at
; the game once for each. Here timer 2 ticks 1280 times a second (25
; samples of the DSP) and 64 ticks make a buffer.
;
; The 65816 talks through the ports:
;   $F4  the pitch index of the gas loop, 0-255 (1.0-2.0 times the rate)
;   $F5  bit 7 the gas, bits 0-6 the volume of the friction (127: 1.0)
;   $F6  the argument of a command
;   $F7  a command, written after $F6: a sequence number in bits 3-7, the
;        command in bits 0-2. The driver echoes $F7 when it took it.
;        0: argument 0 stops every sound, 1 starts the sounds of a level.
;        1-7: an effect (WAV_UTODES...WAV_UGRAS2), the argument its volume
;        (0-127).
;
; Memory: $00-$EF variables, $0100 the stack, $0200 this program, $0600 the
; image that the loader receives at the start: the sample directory, the
; parameters, the pitch table and the samples up to $FFFF (tools/gen_snd.py;
; no echo buffer: its writes are off).

.MEMORYMAP
DEFAULTSLOT 0
SLOT 0 $0200 $0400
.ENDME
.ROMBANKSIZE $0400
.ROMBANKS 1

; I/O
.DEFINE CONTROL  $F1
.DEFINE DSPADDR  $F2
.DEFINE DSPDATA  $F3
.DEFINE PORT0    $F4
.DEFINE PORT1    $F5
.DEFINE PORT2    $F6
.DEFINE PORT3    $F7
.DEFINE T2TARGET $FC
.DEFINE T2OUT    $FF

; Registers of the DSP
.DEFINE MVOLL $0C
.DEFINE MVOLR $1C
.DEFINE KON   $4C
.DEFINE KOF   $5C
.DEFINE FLG   $6C
.DEFINE ENDX  $7C
.DEFINE DIR   $5D
.DEFINE ESA   $6D
; of a voice (+ voice * 16):
.DEFINE V_VOLL  0
.DEFINE V_VOLR  1
.DEFINE V_PL    2
.DEFINE V_PH    3
.DEFINE V_SRCN  4
.DEFINE V_ADSR1 5
.DEFINE V_GAIN  7

; The image (tools/gen_snd.py):
.DEFINE IMAGE      $0600        ; the sample directory
.DEFINE DIRPAGE    $06
.DEFINE P_INTRO    $0628        ; ticks of the start of the engine (Pw1)
.DEFINE P_RISE     $062A        ; ticks of Pw3
.DEFINE P_PITCH1   $062C        ; the pitch of the original rate
.DEFINE P_EFFPITCH $062E        ; the pitch of each effect sample
.DEFINE PITCH_LO   $0640        ; the pitch of the gas loop by index
.DEFINE PITCH_HI   $0740

; Sample numbers:
.DEFINE SRCN_START 0            ; Pw1 into the idle loop
.DEFINE SRCN_IDLE  1            ; the idle loop
.DEFINE SRCN_GAS   2            ; Pw3 into the gas loop
.DEFINE SRCN_FRIC  3

; Voices: 0 and 1 the engine, 2 the friction, 3-7 the effects.
.DEFINE FRIC_VOICE $20

; The fades of the engine: GAIN linear, 32/2048 every 5 samples, 10 ms
; (the original's 100 samples are 9.1 ms).
.DEFINE FADE_RATE 27
; The friction is silent below 0.1 of its full volume (127):
.DEFINE FRIC_MIN 13

; States of the engine (allapot of the original):
.DEFINE ST_OFF   0
.DEFINE ST_INTRO 1              ; A_INDIT
.DEFINE ST_IDLE  2              ; A_ALACSONY
.DEFINE ST_RISE  3              ; A_ATMENETBE, A_ATMENET
.DEFINE ST_GAS   4              ; A_MAGAS

.ENUM $00
ptr       dw                    ; the loader: where the chunk goes
chunks    dw                    ; chunks still to come
c255      dw                    ; 255
last_cmd  db                    ; the last command seen in $F7
nticks    db
fifo_id   dsb 8                 ; commands taken, not yet done
fifo_arg  dsb 8
fifo_head db
fifo_tail db
c_id      db                    ; the command being done
c_arg     db
running   db                    ; between the start and the stop of a level
kof_pend  db                    ; 1: the key-off of a stop is let go next tick
kon       db                    ; voices to key on at the end of the tick
buf_count db                    ; ticks left of the buffer
boundary  db                    ; 1 in the tick that starts a buffer
in_pitch  db                    ; the ports at the start of the buffer
in_gas    db                    ; bit 7 the gas, bits 0-6 the friction
eng_state db
eng_timer dw
eng_voice db                    ; the register base of the engine's voice heard now
pitch_f   db                    ; the pitch of the gas loop, 16.8
pitch     dw
pitch_d   dw                    ; its slide in a tick, 8.8, and the sign
pitch_ds  db
fric      dw                    ; the volume of the friction, 8.8
fric_d    dw
slot      dsb 5                 ; 1 while the voice of the effect slot plays
busy      db                    ; slots playing
vtmp      db
w         dw
.ENDE

.BANK 0 SLOT 0
.ORGA $0200

; The loader, run by the IPL: the number of chunks, then the image in
; chunks of 255 bytes, 3 bytes a step ($F5-$F7, $F4 counts the steps from
; 1 and is echoed), then one more step to start. The three stores of a step
; get the address of the next chunk written into them.
loader:
	clrp
	mov x, #$EF
	mov sp, x
	mov ptr, #<IMAGE
	mov ptr+1, #>IMAGE
	mov c255, #255
	mov c255+1, #0
	mov y, #1
-	cmp y, PORT0
	bne -
	mov a, PORT1
	mov chunks, a
	mov a, PORT2
	mov chunks+1, a
	mov PORT0, y
	inc y
load_chunk:
	mov x, #0
load_step:
	cmp y, PORT0
	bne load_step
	mov a, PORT1
load_st0:
	mov !IMAGE+x, a
	mov a, PORT2
load_st1:
	mov !IMAGE+1+x, a
	mov a, PORT3
	mov PORT0, y
load_st2:
	mov !IMAGE+2+x, a
	inc y
	inc x
	inc x
	inc x
	cmp x, #255
	bne load_step
	mov vtmp, y
	movw ya, ptr
	addw ya, c255
	movw ptr, ya
	movw w, ya
	mov !load_st0+1, a
	mov !load_st0+2, y
	incw w
	movw ya, w
	mov !load_st1+1, a
	mov !load_st1+2, y
	incw w
	movw ya, w
	mov !load_st2+1, a
	mov !load_st2+2, y
	mov y, vtmp
	decw chunks
	bne load_chunk
-	cmp y, PORT0
	bne -
	mov chunks, y
	call !init
	mov PORT3, #0
	mov PORT2, #0
	mov PORT1, #0
	mov PORT0, chunks           ; ready

; The main loop: takes the commands as they come, runs the ticks.
main:
	call !poll
	mov a, T2OUT
	beq main
	mov nticks, a
-	call !tick
	dbnz nticks, -
	bra main

; Takes a new command of the 65816 into the queue (done in the next tick)
; and echoes it. Also called during a tick, so that the 65816 hardly waits.
poll:
	mov a, PORT3
	cmp a, last_cmd
	beq poll_ret
	cmp a, PORT3                ; read it again: it may have been changing
	bne poll_ret
	mov last_cmd, a
	mov x, fifo_tail
	mov a, x
	inc a
	and a, #7
	cmp a, fifo_head
	beq +                       ; full: dropped
	mov w, a
	mov a, last_cmd
	and a, #7
	mov fifo_id+x, a
	mov a, PORT2
	mov fifo_arg+x, a
	mov fifo_tail, w
+	mov PORT3, last_cmd
poll_ret:
	ret

; The DSP and the variables.
init:
	mov a, #FLG
	mov y, #$E0                 ; reset, mute, no echo writes
	movw DSPADDR, ya
	mov x, #0
-	cmp x, #FLG
	beq +
	mov DSPADDR, x
	mov DSPDATA, #0
+	inc x
	bpl -
	mov a, #DIR
	mov y, #DIRPAGE
	movw DSPADDR, ya
	mov a, #ESA
	mov y, #$FF
	movw DSPADDR, ya
	mov a, #MVOLL
	mov y, #127
	movw DSPADDR, ya
	mov a, #MVOLR
	movw DSPADDR, ya
	mov a, #FLG
	mov y, #$20                 ; no echo writes
	movw DSPADDR, ya
	mov a, #0
	mov x, #last_cmd
-	mov (x)+, a
	cmp x, #w+2
	bne -
	mov buf_count, #64
	mov T2TARGET, #50           ; 64 kHz / 50
	mov CONTROL, #$04           ; timer 2 only
	mov a, T2OUT
	ret

; A tick: the effects that ended, the commands, the engine, the friction,
; then the key-ons of the tick at once.
tick:
	mov a, kof_pend
	beq +
	mov kof_pend, #0
	mov a, #KOF
	mov y, #0
	movw DSPADDR, ya
+	mov kon, #0
	call !ends
	call !commands
	call !poll
	mov a, running
	beq +
	call !buffer
	call !engine
	call !poll
	call !friction
+	mov a, kon
	beq +
	mov y, a
	mov a, #KON
	movw DSPADDR, ya
+	ret

; The commands taken since the last tick. After a stop the rest wait for
; the next tick (the key-off has to be seen before a key-on).
commands:
	mov x, fifo_head
	cmp x, fifo_tail
	beq cmd_done
	mov a, fifo_id+x
	mov c_id, a
	mov a, fifo_arg+x
	mov c_arg, a
	mov a, x
	inc a
	and a, #7
	mov fifo_head, a
	mov a, c_id
	bne cmd_effect
	mov a, c_arg
	bne +
	jmp !stop
+	call !start
	bra commands
cmd_effect:
	call !effect
	bra commands
cmd_done:
	ret

; Every sound off (the original's Mute).
stop:
	mov running, #0
	mov eng_state, #ST_OFF
	mov a, #KOF
	mov y, #$FF
	movw DSPADDR, ya
	mov kof_pend, #1
	mov kon, #0
	mov a, #0
	mov busy, a
	mov x, #4
-	mov slot+x, a
	dec x
	bpl -
	ret

; The sounds of a level: the start of the engine (startmotor) and the
; friction, silent.
start:
	mov a, running
	beq +
	ret
+	mov running, #1
	mov eng_voice, #$00
	mov x, #$00
	mov a, #SRCN_START
	mov y, #$7F
	call !vkey
	or kon, #$01
	mov eng_state, #ST_INTRO
	mov a, !P_INTRO
	mov eng_timer, a
	mov a, !P_INTRO+1
	mov eng_timer+1, a
	mov x, #FRIC_VOICE
	mov a, #SRCN_FRIC
	mov y, #$7F
	call !vkey
	mov a, #FRIC_VOICE+V_VOLL
	mov y, #0
	movw DSPADDR, ya
	inc a
	movw DSPADDR, ya
	or kon, #$04
	mov a, #0
	mov fric, a
	mov fric+1, a
	mov fric_d, a
	mov fric_d+1, a
	mov buf_count, #1           ; a buffer starts now
	ret

; Sets up voice X (its register base) to be keyed on: sample A, gain Y, the
; original rate, full volume.
vkey:
	mov vtmp, y
	mov y, a
	mov a, x
	or a, #V_SRCN
	movw DSPADDR, ya
	mov a, x
	or a, #V_ADSR1
	mov y, #0
	movw DSPADDR, ya
	mov a, x
	or a, #V_GAIN
	mov y, vtmp
	movw DSPADDR, ya
	mov a, x
	or a, #V_PL
	mov y, !P_PITCH1
	movw DSPADDR, ya
	inc a
	mov y, !P_PITCH1+1
	movw DSPADDR, ya
	mov a, x
	mov y, #127
	movw DSPADDR, ya
	inc a
	movw DSPADDR, ya
	ret

; An effect (c_id 1-7) at volume c_arg in the first free slot.
effect:
	mov a, running
	beq eff_ret                 ; the original plays none while muted
	mov x, #0
-	mov a, slot+x
	beq +
	inc x
	cmp x, #5
	bne -
eff_ret:
	ret                         ; all five play
+	mov a, #1
	mov slot+x, a
	inc busy
	mov a, !slot_bit+x
	or a, kon
	mov kon, a
	mov a, !slot_base+x
	mov x, a
	mov y, c_id
	mov a, !eff_srcn-1+y
	push a
	mov y, #$7F
	call !vkey
	pop a                       ; its own rate
	asl a
	mov y, a
	mov a, !P_EFFPITCH-2*4+1+y
	mov vtmp, a
	mov a, !P_EFFPITCH-2*4+y
	push a
	mov a, x
	or a, #V_PL
	pop y
	movw DSPADDR, ya
	inc a
	mov y, vtmp
	movw DSPADDR, ya
	mov a, x
	mov y, c_arg
	movw DSPADDR, ya
	inc a
	movw DSPADDR, ya
	ret

; The slots whose sample reached its end are free.
ends:
	mov a, busy
	beq ends_ret
	mov DSPADDR, #ENDX
	mov a, DSPDATA
	mov w, a
	mov x, #4
-	mov a, slot+x
	beq +
	mov a, !slot_bit+x
	and a, w
	beq +
	mov a, #0
	mov slot+x, a
	dec busy
+	dec x
	bpl -
ends_ret:
	ret

; Counts the ticks of a buffer; at the start of one reads the ports.
buffer:
	mov boundary, #0
	dbnz buf_count, +
	mov buf_count, #64
	mov boundary, #1
-	mov a, PORT0
	cmp a, PORT0
	bne -
	mov in_pitch, a
-	mov a, PORT1
	cmp a, PORT1
	bne -
	mov in_gas, a
+	ret

; The engine (motorelintezes of the original).
engine:
	mov a, eng_state
	asl a
	mov x, a
	jmp [!eng_states+x]

eng_off:
	ret

; Pw1 plays to its end, then the idle loop.
eng_intro:
	decw eng_timer
	bne eng_off
	mov eng_state, #ST_IDLE
	bra eng_idle_now

; The idle loop; with the gas (looked at with each buffer) it fades into
; Pw3.
eng_idle:
	mov a, boundary
	beq eng_off
eng_idle_now:
	mov a, in_gas
	bpl eng_off
	mov a, #SRCN_GAS
	call !eng_fade
	mov eng_state, #ST_RISE
	mov a, !P_RISE
	mov eng_timer, a
	mov a, !P_RISE+1
	mov eng_timer+1, a
	ret

; Pw3 plays to its end, then the gas loop from the original rate. A
; buffer starts here.
eng_rise:
	decw eng_timer
	bne eng_off
	mov eng_state, #ST_GAS
	mov a, !P_PITCH1
	mov y, !P_PITCH1+1
	movw pitch, ya
	mov pitch_f, #0
	mov buf_count, #64
	bra eng_gas_now

; The gas loop: without the gas it fades into the idle loop, otherwise its
; pitch slides to that of the wheel over the buffer.
eng_gas:
	mov a, boundary
	beq eng_slide
eng_gas_now:
	mov a, in_gas
	bmi +
	mov a, #SRCN_IDLE
	call !eng_fade
	mov eng_state, #ST_IDLE
	ret
+	mov x, in_pitch
	mov a, !PITCH_HI+x
	mov y, a
	mov a, !PITCH_LO+x
	subw ya, pitch
	movw w, ya
	asl w
	rol w+1
	asl w
	rol w+1
	movw ya, w
	movw pitch_d, ya
	mov pitch_ds, #0
	mov a, y
	bpl eng_slide
	mov pitch_ds, #$FF
eng_slide:
	clrc
	mov a, pitch_f
	adc a, pitch_d
	mov pitch_f, a
	mov a, pitch
	adc a, pitch_d+1
	mov pitch, a
	mov a, pitch+1
	adc a, pitch_ds
	mov pitch+1, a
	mov a, eng_voice
	or a, #V_PL
	mov y, pitch
	movw DSPADDR, ya
	inc a
	mov y, pitch+1
	movw DSPADDR, ya
	ret

; Fades the engine's voice out and the other one in, playing sample A
; from its start.
eng_fade:
	push a
	mov a, eng_voice
	or a, #V_GAIN
	mov y, #$80|FADE_RATE       ; linear decrease
	movw DSPADDR, ya
	mov a, eng_voice
	eor a, #$10
	mov eng_voice, a
	mov x, a
	pop a
	mov y, #$C0|FADE_RATE       ; linear increase
	call !vkey
	mov a, eng_voice
	xcn a
	inc a                       ; voice 0: bit 1, voice 1: bit 2
	or a, kon
	mov kon, a
	ret

; The friction (surlodaselintezes): at the start of a buffer its slide to
; the volume of the game, or silence below 0.1.
friction:
	mov a, boundary
	beq fric_step
	mov a, in_gas
	and a, #$7F
	cmp a, #FRIC_MIN
	bcs +
	mov y, fric+1
	cmp y, #FRIC_MIN
	bcs +
	mov a, #0
	mov fric, a
	mov fric+1, a
	mov fric_d, a
	mov fric_d+1, a
	bra fric_write
+	mov y, a                    ; (the volume << 8 - fric) / 64
	mov a, #0
	subw ya, fric
	movw w, ya
	mov x, #6
-	mov a, w+1
	asl a
	ror w+1
	ror w
	dec x
	bne -
	movw ya, w
	movw fric_d, ya
fric_step:
	movw ya, fric_d
	beq fric_ret                ; no change
	movw ya, fric
	addw ya, fric_d
	movw fric, ya
fric_write:
	mov a, #FRIC_VOICE+V_VOLL
	mov y, fric+1
	movw DSPADDR, ya
	inc a
	movw DSPADDR, ya
fric_ret:
	ret

eng_states:
	.dw eng_off, eng_intro, eng_idle, eng_rise, eng_gas
; The effect slots: the bit and the register base of their voice.
slot_bit:
	.db $08, $10, $20, $40, $80
slot_base:
	.db $30, $40, $50, $60, $70
; The sample of each effect (WAV_UTODES...WAV_UGRAS2):
eff_srcn:
	.db 4, 5, 6, 7, 8, 9, 9
