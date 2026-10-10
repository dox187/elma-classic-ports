"""Generate exact unsigned Q48 products for the proven original-trig domains.

The entire bounded64/80/96-bit product is accumulated, including all discarded low48 bits.
One half-away rounding uses bit47 after carry completion. No early truncation.
D page aligned, DB80-BF, A/X/Y16; A/flags clobbered, X/Y preserved.
Scratch product144..155 (extent depends on bound), temporary136..139, distinct from inputs and cache.
Each coefficient group follows the core Mode7 first-write latch protocol.
"""

def product(x,y,out,words,bytes_,top=False,accbytes=12):
 lines=[];p=144;t=136
 def e(*s):lines.extend(s)
 for k in range(accbytes//2):e(' stz.b %d'%(p+2*k))
 for i in range(words):
  end='wqp_a%d_done'%i
  e(' lda.b %d'%(x+2*i),' beq '+end,' xba',' sta.w core_m7_latch',' sta.w MPYA',' sta.w MPYA')
  for j in range(bytes_):
   skip='wqp_b%d_%d_done'%(i,j);pos=2*i+j
   e(' sep #$20',' lda.b %d'%(y+j),' beq '+skip,' sta.w MPYB',' rep #$20',' lda.w MPYL',' sta.b %d'%t,' sep #$20',' lda.w MPYH',' sta.b %d'%(t+2),' stz.b %d'%(t+3),' lda.b %d'%(y+j),' bpl wqp_b%d_%d_unsigned'%(i,j),' rep #$20',' lda.b %d'%(x+2*i),' clc',' adc.b %d'%(t+1),' sta.b %d'%(t+1),'wqp_b%d_%d_unsigned:'%(i,j),' rep #$20',' lda.b %d'%(x+2*i),' bpl wqp_a%d_%d_unsigned'%(i,j),' sep #$20',' lda.b %d'%(y+j),' clc',' adc.b %d'%(t+2),' sta.b %d'%(t+2),'wqp_a%d_%d_unsigned:'%(i,j),' rep #$20')
   for k in range(pos,accbytes,2):
    rem=accbytes-k
    if rem==1:e(' sep #$20')
    e(' lda.b %d'%(p+k),' clc'if k==pos else'')
    if k==pos:e(' adc.b %d'%t)
    elif k==pos+2:e(' adc.b %d'%(t+2))
    else:e(' adc.b #0'if rem==1 else' adc #0')
    e(' sta.b %d'%(p+k))
   e(skip+':',' rep #$20')
  e(end+':')
 if top:
  e(' lda.b %d'%(x+6),' beq wqp_top_done',' clc')
  for j in range((accbytes-6)//2):e(' lda.b %d'%(p+6+2*j),' adc.b %d'%(y+2*j),' sta.b %d'%(p+6+2*j))
  e('wqp_top_done:')
 # Keep carry from guard bit47 while loading the extracted high limbs.
 e(' lda.b %d'%(p+4),' asl a')
 for j in range(3):
  if 6+2*j<accbytes:e(' lda.b %d'%(p+6+2*j),' adc #0',' sta.b %d'%(out+2*j))
  else:e(' stz.b %d'%(out+2*j))
 e(' stz.b %d'%(out+6))
 return '\n'.join(s for s in lines if s)+'\n'

def square(x,out):
 """Exact square of a nonnegative37-bit value using nine PPU products.

Three16-bit limbs (top<=31). Symmetry computes only six limb-pairs:
2PPU each for00/01/11;1PPU each for02/12/22. Cross terms double
complete32-bit products to33bits before full96-bit accumulation.
 """
 lines=[];p=144
 def e(*s):lines.extend(s)
 def raw(coef,b,tmp,smallcoef,smallb,label):
  e(' sep #$20',' lda.b %d'%b,' sta.w MPYB',' rep #$20',' lda.w MPYL',' sta.b %d'%tmp,' sep #$20',' lda.w MPYH',' sta.b %d'%(tmp+2),' stz.b %d'%(tmp+3))
  if not smallb:e(' lda.b %d'%b,' bpl '+label+'_b',' rep #$20',' lda.b %d'%coef,' clc',' adc.b %d'%(tmp+1),' sta.b %d'%(tmp+1),label+'_b:')
  e(' rep #$20')
  if not smallcoef:e(' lda.b %d'%coef,' bpl '+label+'_a',' sep #$20',' lda.b %d'%b,' clc',' adc.b %d'%(tmp+2),' sta.b %d'%(tmp+2),label+'_a:',' rep #$20')
 for k in range(6):e(' stz.b %d'%(p+2*k))
 for i in range(3):
  for j in range(i,3):
   coef=x+2*i;b=x+2*j;label='wqs_%d_%d'%(i,j);offset=2*(i+j)
   e(' lda.b %d'%coef,' beq '+label+'_done',' xba',' sta.w core_m7_latch',' sta.w MPYA',' sta.w MPYA')
   raw(coef,b,136,i==2,j==2,label+'_low')
   if j<2:
    raw(coef,b+1,140,i==2,False,label+'_high')
    e(' rep #$20',' lda.b 137',' clc',' adc.b 140',' sta.b 137',' sep #$20',' lda.b 139',' adc.b 142',' sta.b 139',' rep #$20')
   if i<j:e(' stz.b 140',' asl.b 136',' rol.b 138',' rol.b 140')
   for k in range(offset,12,2):
    e(' lda.b %d'%(p+k),' clc'if k==offset else'')
    if k==offset:e(' adc.b 136')
    elif k==offset+2:e(' adc.b 138')
    elif k==offset+4 and i<j:e(' adc.b 140')
    else:e(' adc #0')
    e(' sta.b %d'%(p+k))
   e(label+'_done:')
 e(' lda.b 148',' asl a')
 for j in range(3):e(' lda.b %d'%(p+6+2*j),' adc #0',' sta.b %d'%(out+2*j))
 e(' stz.b %d'%(out+6))
 return '\n'.join(s for s in lines if s)+'\n'
