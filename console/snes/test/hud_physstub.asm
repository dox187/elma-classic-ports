; A stand-in of the variables of the physics (src/phys.h, SPEC 6) that the
; HUD reads, linked only while there is no physics (mk/hud.mk).

.include "hdr.asm"

.BASE $00
.RAMSECTION ".hud_physstub" BANK $7E SLOT 2
phys_view           dsb 64      ; bike_view_t
phys_objs           dsb 12*128  ; phys_obj_t
phys_nobjs          dw
phys_apples_left    dw
phys_eaten          dw
.ENDS
.BASE $80
