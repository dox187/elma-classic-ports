"""Lower unsupported816-TCC stack offsets to equivalent65816 instructions.

Only16-bit LDA/STA are accepted. Stack addresses use bank7E's bank00 mirror;
X, A and status semantics are preserved. NMI does not access the scratch word.
This correctness fallback is intentionally not a rendering performance change.
"""
import re


def lower(text):
    definitions={k:int(v)for k,v in re.findall(r'^\.define\s+(\S+)\s+(\d+)\s*$',text,re.M)}
    output=[];count=0;accu16=True;index16=True
    for line in text.splitlines():
        mode=re.fullmatch(r'(rep|sep) #\$([0-9a-fA-F]+)',line)
        if mode:
            mask=int(mode[2],16)
            if mask&32:accu16=mode[1]=='rep'
            if mask&16:index16=mode[1]=='rep'
        match=re.fullmatch(r'(\w+) (.*),s',line)
        if not match:output.append(line);continue
        expression=match[2]
        for key,value in definitions.items():expression=expression.replace(key,str(value))
        if not re.fullmatch(r'[\d +()\-]+',expression):raise ValueError('Unknown stack expression '+line)
        offset=eval(expression,{'__builtins__':{}})
        if 0<=offset<=255:output.append(line);continue
        if not -8190<offset<8190:raise ValueError('Stack offset outside low WRAM '+line)
        if not accu16 or not index16:raise ValueError('Stack lowering requires proven16-bit A/X modes at '+line)
        if match[1]=='lda':
            output+=['; lowered '+line,'phx','tsx','lda.l $7e0000+'+str(offset+2)+',x',
                     'sta.l wide_stack_load_scratch','plx','lda.l wide_stack_load_scratch']
        elif match[1]=='sta':
            output+=['; lowered '+line,'php','phx','tsx','sta.l $7e0000+'+str(offset+3)+',x','plx','plp']
        else:raise ValueError('Unsupported large stack operation '+line)
        count+=1
    return '\n'.join(output)+'\n',count
