"""Exercise the signed cartridge's radial product rows and its merged-vector ABI."""
import argparse
from math import isqrt
from pathlib import Path
import struct
from check_corner_results import WheelQueries


def check(rom, reference):
    cart, previous = WheelQueries(rom), WheelQueries(reference)
    try:
        m, sym = cart.m, cart.sym
        # Poison all scratch and persistent SRAM before the cold level setup.
        poison = bytes((i * 47 + 13) & 255 for i in range(8192))
        for bank in range(4):
            m[0x4000] = bank
            m[0xa000:0xc000] = poison
        m[0x4000] = 0
        cart.invoke('_cpu_fast')
        cart.invoke('_physics_collision_select', a=31)
        expected = bytearray(poison)
        def rom_bytes(symbol, size):
            address = sym[symbol]
            start = (address >> 16)*16384 + (address & 16383)
            return cart.image[start:start+size]
        for source,end,destination in (('ss_pair_image','ss_pair_end',0xab00),
                                       ('haircut_gate_image','haircut_gate_end',0xaca0),
                                       ('pair_bound_image','pair_bound_image_end',0xa570)):
            if source in sym:
                size = sym[end]-sym[source]
                expected[destination-0xa000:destination-0xa000+size] = rom_bytes(source,size)
        if '_wheel_course_size' in sym:
            metadata = rom_bytes('_wheel_terrain_maps',4*32)[-4:]
            width,height,address = struct.unpack('<BBH',metadata)
            assert cart.read('_wheel_course_size',2) == bytes((width,height))
            offset = 9*16384 + (address & 16383)
            rows = cart.image[offset:offset+3*height]
            for i in range(3):
                start = 0xd00+256*i
                expected[start:start+height] = rows[i::3]
        assert bytes(m[0xa000:0xa800]) == expected[:0x800]
        assert bytes(m[0xaa52:0xc000]) == expected[0xa52:]
        directory = bytes(m[0xa800:0xaa52])
        src = sym['_riding_normal_rsqrt']
        factors = struct.unpack_from('<297H', cart.image, (src>>16)*16384 + (src&16383))
        used = set()
        axes = 0
        for i, factor in enumerate(factors):
            entry = int.from_bytes(directory[2*i:2*i+2],'little')
            address, bank = entry & ~3, entry & 3
            assert bank and 0xa000 <= address < 0xc000
            m[0x4000] = bank
            radius = isqrt(16384 + 512*(i+1)-1)
            last = (radius+15)//16
            size = 32+2*last
            assert address>>8 == (address+size-1)>>8
            data = bytes(m[address:address+size])
            for j in range(address,address+size):
                assert (bank,j) not in used
                used.add((bank,j))
            for x in range(-radius,radius+1):
                high,low=divmod(x,16)
                frac,=struct.unpack_from('<H',data,2*(15-low))
                whole,=struct.unpack_from('<H',data,30+2*abs(high))
                assert frac + (-whole if high<0 else whole) == x*factor >> 4
                axes += 1
        m[0x4000] = 0
        linked = 0
        for i in range(297):
            lower = 16384+512*i
            y = isqrt(lower)*2//3
            x = isqrt(lower-y*y)
            if x*x+y*y < lower:
                x += 1
            # Near the outer ring, step one axis until a reachable center
            # lies in this reciprocal bin. Consecutive radii can span >512.
            while x*x+y*y >= lower+512:
                y -= 1
                x = isqrt(lower-y*y-1)+1
            for dx,dy in ((x,y),(-x,y),(y,-x),(-y,-x)):
                squared = dx*dx+dy*dy
                got=cart.call('_riding_normal_physical',dx,dy,0xa201,squared)[1]
                want=previous.call('_riding_normal_fast',dx,dy,0xa201,squared)[1]
                assert got==want,(i,dx,dy,got,want)
                linked += 1
        # Test a real VBlank on every selected SRAM bank while the table is visible.
        seen=set()
        mapped = sym['normal_sram_mapped']
        for x,y in ((-127,18),(-283,215),(400,-36)):
            d2=x*x+y*y
            i=(d2-16384)//512
            bank = directory[2*i]&3
            fired=[]
            def inject(_):
                if not fired:
                    fired.append(True)
                    m[0xff0f]=1
            def handler(_):
                sp=cart.reg.SP
                if int.from_bytes(bytes(m[sp:sp+2]),'little') & 65535 == mapped & 65535:
                    seen.add(bank)
            cart.p.hook_register(mapped>>16,mapped&65535,inject,None)
            cart.p.hook_register(0,0x40,handler,None)
            m[0xffff],m[0xff0f]=1,0
            _,got,_=cart.call('_riding_normal_physical',x,y,0xa201,d2,irq=True)
            m[0xffff],m[0xff0f]=0,0
            cart.p.hook_deregister(mapped>>16,mapped&65535)
            cart.p.hook_deregister(0,0x40)
            _,want,_=previous.call('_riding_normal_fast',x,y,0xa201,d2)
            assert fired and got==want and bytes(m[0xa800:0xaa52])==directory
        assert seen=={1,2,3},seen
        cases=(-32768,-4096,-513,-512,-410,-256,-128,-1,0,1,127,255,410,511,512,4095,32767)
        for x in cases:
            for y in cases:
                squared=(x*x+y*y+2**31)%2**32-2**31
                cart.invoke('_riding_merge_normal',de=x&65535,bc=y&65535)
                want=previous.call('_riding_normal_fast',x,y,0xa201,squared)[1]
                assert cart.read('_Ct',6)==want,(x,y,squared,cart.read('_Ct',6),want)
        print(f'{axes} exact SRAM axis products, {linked} linked vectors, {len(seen)} interrupted banks, {len(cases)**2} merged vectors.')
    finally:
        cart.p.stop(save=False)
        previous.p.stop(save=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom',type=Path,required=True)
    parser.add_argument('--reference',type=Path,required=True)
    args=parser.parse_args()
    check(args.rom,args.reference)
