; ROM0 bounds for exact signed56 -> shifted/saturated32 conversion.
; Entry s is INT32_MAX >> (16-s), s=0..16; complement gives the
; corresponding negative middle-word bound. No operand bits are discarded
; before the signed range check in physics_math32.c.
    .module riding_math32_bounds
    .area _CODE
_riding_math32_positive_limit::
    .dw 0x7fff,0x0000
    .dw 0xffff,0x0000
    .dw 0xffff,0x0001
    .dw 0xffff,0x0003
    .dw 0xffff,0x0007
    .dw 0xffff,0x000f
    .dw 0xffff,0x001f
    .dw 0xffff,0x003f
    .dw 0xffff,0x007f
    .dw 0xffff,0x00ff
    .dw 0xffff,0x01ff
    .dw 0xffff,0x03ff
    .dw 0xffff,0x07ff
    .dw 0xffff,0x0fff
    .dw 0xffff,0x1fff
    .dw 0xffff,0x3fff
    .dw 0xffff,0x7fff
