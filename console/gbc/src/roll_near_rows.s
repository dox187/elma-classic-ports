; Exact digit planes for the near-horizontal rolling solver.
.module roll_near_rows
.area _CODE_13
; U[i] = i*m for positive m and i*m+65280 for negative m. For a
; signed20 input only sixteen signed top digits occur. S[j] removes
; the upper bias. The product retains a -256 bias only for negative m.
.macro near_rows where,m,bias
where::
 .irp shift,0,8
 digit = 0
 .rept 256
 .db ((bias+digit*m)>>shift)&255
 digit=digit+1
 .endm
 .endm
.endm
.macro near_upper m,bias
 .irp shift,0,8
 digit = -8
 .rept 16
 .db ((digit*m-bias)>>shift)&255
 digit=digit+1
 .endm
 .endm
.endm
 .bndry 256
 near_rows near_rows_positive_134,134,0
 near_rows near_rows_negative_169,-169,65280
 near_rows near_rows_negative_170,-170,65280
 near_rows near_rows_negative_163,-163,65280
 near_rows near_rows_negative_123,-123,65280
 near_rows near_rows_negative_120,-120,65280
near_upper_digits::
 near_upper 134,0
 near_upper -169,256
 near_upper -170,256
 near_upper -163,256
 near_upper -123,256
 near_upper -120,256
