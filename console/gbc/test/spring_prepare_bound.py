"""Worst-case SM83 cycles over both outcomes of every reachable conditional.

The spring prefixes contain no loops. Reject indirect control flow, unknown
opcodes or cycles so future changes cannot silently increase an optional
block's deadline. The one resolved indirect jump is the linked GBDK bank call.
"""
from functools import cache
from pathlib import Path
import sys

# Unprefixed instruction timings, in machine cycles. Conditional instructions
# are handled separately. Table order is the SM83 opcode order.
LOW = [
 1,3,2,2,1,1,2,1,5,2,2,2,1,1,2,1,
 0,3,2,2,1,1,2,1,3,2,2,2,1,1,2,1,
 0,3,2,2,1,1,2,1,0,2,2,2,1,1,2,1,
 0,3,2,2,3,3,3,1,0,2,2,2,1,1,2,1,
]
HIGH = [
 0,3,0,0,0,4,2,0,0,0,0,0,0,0,2,0,
 0,3,0,0,0,4,2,0,0,0,0,0,0,0,2,0,
 3,3,2,0,0,4,2,0,4,0,4,0,0,0,2,0,
 3,3,2,1,0,4,2,0,3,2,4,1,0,0,2,0,
]
TWO = {0x06,0x0e,0x16,0x1e,0x26,0x2e,0x36,0x3e,0xc6,0xce,0xd6,0xde,
       0xe0,0xe6,0xe8,0xee,0xf0,0xf6,0xf8,0xfe}
THREE = {0x01,0x08,0x11,0x21,0x31,0xea,0xfa}


def guard_sites(rom, symbols):
    """Return the linked LD A,lines at every optional guard, in execution order."""
    entry = symbols['_physics_prepare_spring']
    guard = symbols['_riding_spring_budget']
    assert entry >> 16 == guard >> 16 and entry < guard
    offset = (entry >> 16) * 0x4000 + (entry & 0x3fff)
    code = Path(rom).read_bytes()[offset:offset + guard - entry]
    call = bytes((0xcd, guard & 255, (guard >> 8) & 255))
    sites = []
    for i in range(2, len(code) - 3):
        if code[i:i+3] == call:
            assert code[i-2] == 0x3e and code[i+3] == 0xd0  # ret nc
            sites.append((entry + i - 2, code[i-1]))
    assert len(sites) in (4, 6, 7, 8), sites
    return sites


def bounds(rom, symbols, starts, stops=()):
    sys.setrecursionlimit(max(10000,sys.getrecursionlimit()))
    rom=Path(rom).read_bytes()
    bankcall=symbols['___sdcc_bcall_ehl']
    # LDH A,(bank); PUSH AF; LD A,E; LDH (bank),A; LD (ROMB0),A; RST $20;
    # POP HL; LD L,A; LD A,H; LDH (bank),A; LD (ROMB0),A; LD A,L; RET.
    bankhr=symbols['__current_bank'] & 255
    assert rom[bankcall:bankcall+19]==bytes([0xf0,bankhr,0xf5,0x7b,0xe0,bankhr,
        0xea,0,0x20,0xe7,0xe1,0x6f,0x7c,0xe0,bankhr,0xea,0,0x20,0x7d])
    assert rom[bankcall+19]==0xc9 and rom[0x20]==0xe9
    trampoline=4*sum([3,4,1,3,4,4,1,3,1,1,3,4,1,4])
    image = symbols.get('ss_force_image')
    if image is not None:
        run_start = symbols['ss_wram_code']
        run_end = run_start + symbols['ss_force_image_end'] - image
        assert 0xc000 <= run_start < run_end <= 0xe000
        assert image >> 16 == (symbols['ss_force_image_end'] - 1) >> 16
        load_offset = (image >> 16) * 0x4000 + (image & 0x3fff)
    seen=set()
    @cache
    def cost(bank,pc):
        if (bank << 16 | pc) in stops:
            return 0
        if (bank,pc) in seen:
            raise ValueError(f'Cycle at {bank}:{pc:04x}')
        seen.add((bank,pc))
        if image is not None and run_start <= pc < run_end:
            # Follow absolute branches at their execution addresses. Read the
            # instructions from the banked image that the CRT copies to WRAM.
            index = load_offset + pc - run_start
        else:
            assert 0 <= pc < 0x8000
            index=(bank*0x4000+(pc&0x3fff)) if pc>=0x4000 else pc
        op=rom[index]
        if op in (0xf3, 0xfb):
            raise ValueError(f'Changed interrupt enable in optional work at {bank}:{pc:04x}')
        following=lambda length:cost(bank,pc+length)
        ptr=int.from_bytes(rom[index+1:index+3],'little')
        def call():
            if ptr!=bankcall:
                return cost(bank,ptr)
            target=rom[index-2]+256*rom[index-1]
            assert rom[index-5]==0x1e and rom[index-3]==0x21
            return trampoline+cost(rom[index-4],target)
        if op==0xc9: result=16
        elif op in (0xc0,0xc8,0xd0,0xd8): result=max(20,8+following(1))
        elif op==0xcd: result=24+call()+following(3)
        elif op in (0xc4,0xcc,0xd4,0xdc): result=max(12,24+call())+following(3)
        elif op==0xc3: result=16+cost(bank,ptr)
        elif op in (0xc2,0xca,0xd2,0xda): result=max(12+following(3),16+cost(bank,ptr))
        elif op in (0x18,0x20,0x28,0x30,0x38):
            target=pc+2+int.from_bytes(rom[index+1:index+2],'little',signed=True)
            result=12+cost(bank,target)
            if op!=0x18: result=max(result,8+following(2))
        elif op==0xcb:
            ext=rom[index+1]
            cycles=2 if ext&7!=6 else 3 if ext>>6==1 else 4
            result=4*cycles+following(2)
        else:
            if op<0x40: cycles=LOW[op]
            elif op<0x80:
                cycles=0 if op==0x76 else 2 if op&7==6 or (op>>3)&7==6 else 1
            elif op<0xc0: cycles=2 if op&7==6 else 1
            else: cycles=HIGH[op-0xc0]
            if not cycles: raise ValueError(f'Unsupported {op:02x} at {bank}:{pc:04x}')
            size=2 if op in TWO else 3 if op in THREE else 1
            result=4*cycles+following(size)
        seen.remove((bank,pc))
        return result
    return {n:cost(s>>16,s&0xffff) for n,s in starts.items()}
