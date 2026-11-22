"""Check the native per-wheel prepared-pair cache on a linked game ROM."""
import argparse
from io import BytesIO
from pathlib import Path
import re
import struct

from pyboy import PyBoy


def check(rom):
    symbols = {name: int(value, 16) for name, value in
               re.findall(r'DEF (\S+) 0x([\da-fA-F]+)', rom.with_suffix('.noi').read_text())}
    bank = symbols['_riding_cert_hit'] >> 16
    # Run individual routines from a WRAM caller after the boot ROM finishes.
    image = bytearray(rom.read_bytes())
    image[0x100:0x102] = bytes([0x18, 0xfe])
    emu = PyBoy(BytesIO(image), window='null', cgb=True, sound_emulated=False)
    emu.set_emulation_speed(0)
    emu.tick(200, False)
    mem = emu.memory
    mem[0xffff] = mem[0xff0f] = 0
    mem[0x3000], mem[0x2000], mem[symbols['__current_bank']] = 0, bank, bank
    code, stack, result = 0xdff0, 0xdfa0, 0xdfdf
    wheels = [symbols['_Bike'] + offset for offset in (24, 48)]
    ct = symbols['_Ct']
    center = struct.pack('<II', 0x12345678, 0xfedcba98)
    pairs = [struct.pack('<10h', 0, 16384, 406, -528, 96,
                        16384, 0, 407, 88, 93),
             struct.pack('<10h', 14804, 7020, 406, 317, -222,
                        -14531, 7568, 406, -111, 83)]
    poison = bytes([0xa5]) * 20

    def call(name, de=0, a=0):
        addr = symbols[name]
        assert addr >> 16 in (bank, 0)
        # DI; LD DE,arg; LD A,n; CALL addr; LD (result),A; JR $.
        program = [0xf3, 0x11, de & 255, de >> 8, 0x3e, a,
                   0xcd, addr & 255, addr >> 8 & 255,
                   0xea, result & 255, result >> 8, 0x18, 0xfe]
        mem[code:code + len(program)] = program
        emu.register_file.SP, emu.register_file.PC = stack, code
        emu.tick(1, False)
        assert emu.register_file.PC == code + 12 and emu.register_file.SP == stack, name
        assert mem[symbols['__current_bank']] == bank, name
        return mem[result]

    def fill(wheel, records):
        # A normal entry first establishes the square key. The fine filter
        # then sees two accepted contacts with sufficient radial clearance.
        mem[wheel:wheel + 8] = center
        assert call('_riding_cert_hit', wheel) == 255
        mem[ct:ct + 20] = records
        assert call('_riding_prepare_contacts', wheel, 2) == 2
        assert bytes(mem[wheel:wheel + 8]) == center

    def expect_hit(wheel, records):
        mem[ct:ct + 20] = poison
        assert call('_riding_cert_hit', wheel) == 254
        assert bytes(mem[ct:ct + 20]) == records

    def fill_both():
        call('_physics_collision_reset')
        for wheel, records in zip(wheels, pairs):
            fill(wheel, records)

    def check_motion():
        # Enter the normal banked wheel path on an exact hit, then compare it
        # with the resolver entered directly with the same freshly prepared Ct.
        # The four bytes before its k/dvx/dvy/tq block are the bank-call frame.
        args_at = stack + 4
        fields = (('_Bike', 119), ('_move_residual', 32),
                  ('_riding_audio_contact', 2), ('_riding_audio_impact', 2),
                  ('_riding_landing_contact', 2), ('_riding_landing_nx', 4),
                  ('_riding_landing_ny', 4))
        states = ((0, 0, 0, -300, -700, 0),
                  (0, 0, 0, 15000, 200, -100),
                  (5000, -65000, 1234, -160, 885, 6000),
                  (-70000, 10000, -731, 10000, -20000, -6000),
                  (-900000, -900000, 10000000, 0, 0, 0),
                  (0, 0, 0, 300, 700, 0))
        outcomes = set()
        impacts = set()
        for slot, wheel in enumerate(wheels):
            for vx, vy, omega, dvx, dvy, tq in states:
                for phase in (0, 1):
                    for prior in (0, 1):
                        observed = []
                        for cached in (False, True):
                            call('_physics_collision_reset')
                            for field, size in fields:
                                start = symbols[field]
                                mem[start:start+size] = bytes(size)
                            fill(wheel, pairs[slot])
                            mem[wheel+8:wheel+24] = struct.pack('<iiIi', vx, vy, 0xa54329, omega)
                            mem[symbols['_riding_subphase']] = phase
                            mem[symbols['_riding_audio_contact']+slot] = prior
                            mem[symbols['_riding_audio_impact']+slot] = 1
                            mem[args_at:args_at+14] = struct.pack('<Hiii', wheel, dvx, dvy, tq)
                            if cached:
                                mem[ct:ct+20] = poison
                                call('_riding_wheel')
                            else:
                                call('_riding_wheel_contact', args_at, 2)
                            observed.append([bytes(mem[symbols[f]:symbols[f]+n]) for f,n in fields])
                            outcomes.add(mem[symbols['_riding_landing_contact']+slot])
                            impacts.add(mem[symbols['_riding_audio_impact']+slot])
                        assert observed[0] == observed[1], (slot, vx, vy, dvx, dvy, phase, prior)
        assert outcomes == {0, 1, 2} and impacts == {0, 1}, (outcomes, impacts)

    try:
        for slot, wheel in enumerate(wheels):
            for bit in range(64):
                fill_both()
                # The shared contact scratch and the wheel's motion may change
                # between calls. The saved pair belongs solely to this center.
                mem[wheel + 8:wheel + 24] = bytes([bit]) * 16
                expect_hit(wheel, pairs[slot])
                mem[wheel + bit // 8] ^= 1 << (bit % 8)
                mem[ct:ct + 20] = poison
                assert call('_riding_cert_hit', wheel) == 255, (slot, bit)
                assert bytes(mem[ct:ct + 20]) == poison
                expect_hit(wheels[1-slot], pairs[1-slot])

        for reset, arg in (('_physics_collision_reset', 0), ('_physics_collision_select', 1)):
            fill_both()
            call(reset, a=arg)
            for wheel in wheels:
                assert call('_riding_cert_hit', wheel) == 255, reset

        for wheel in wheels:
            for n, l0, l1, count in ((2, 400, 407, 2), (2, 407, 400, 2),
                                     (2, 411, 407, 1), (2, 407, 411, 1),
                                     (2, 411, 411, 0), (1, 407, 407, 1)):
                call('_physics_collision_reset')
                mem[wheel:wheel + 8] = center
                assert call('_riding_cert_hit', wheel) == 255
                records = bytearray(pairs[0])
                struct.pack_into('<h', records, 4, l0)
                struct.pack_into('<h', records, 14, l1)
                mem[ct:ct+20] = records
                assert call('_riding_prepare_contacts', wheel, n) == count
                # Probe the original key even if the filter applied a push.
                mem[wheel:wheel + 8] = center
                assert call('_riding_cert_hit', wheel) == 255, (n, l0, l1)
        check_motion()
    finally:
        emu.stop(save=False)

    print('Both ordered pairs restored byte-for-byte. All 128 one-bit center changes, '
          '12 push/filter cases, reset, level selection and 48 motion/audio comparisons passed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    check(parser.parse_args().rom)
