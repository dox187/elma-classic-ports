"""Compare one prepared contact and the public rolling ABI on two linked cartridges."""
import argparse
from io import BytesIO
from pathlib import Path
import random
import re
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from rolling_tables import SLOPE_TANGENTS, VERTICAL_TANGENT

from pyboy import PyBoy


FIELDS = {
    '_Bike': 119, '_move_residual': 32, '_Ct': 20,
    '_riding_audio_impact': 2, '_riding_audio_contact': 2,
    '_riding_landing_contact': 2, '_riding_landing_nx': 4,
    '_riding_landing_ny': 4, '_q24_fraction': 4, '_q24_saturated': 1,
}


class Cartridge:
    def __init__(self, rom):
        self.symbols = {k: int(v, 16) for k, v in re.findall(
            r'DEF (\S+) 0x([0-9a-fA-F]+)', rom.with_suffix('.noi').read_text())}
        image = bytearray(rom.read_bytes())
        image[0x100:0x102] = bytes([0x18, 0xfe])
        # Enter the real banked wheel entry with one ordered, already prepared
        # contact. Geometry is an input here. The resolver, audio, rolling,
        # coefficient tables and circle motion run from each cartridge.
        for symbol in ('_riding_cert_hit', '_riding_prepare_contacts'):
            address = self.symbols[symbol]
            offset = (address >> 16) * 0x4000 + (address & 0x3fff)
            image[offset:offset+3] = bytes([0x3e, 1, 0xc9])
        self.emu = PyBoy(BytesIO(image), window='null', cgb=True, sound_emulated=False)
        self.emu.set_emulation_speed(0)
        self.emu.tick(200, False)
        mem = self.emu.memory
        mem[0xffff] = mem[0xff0f] = 0

    def run(self, fields, mode, phase, slot, impulses):
        mem, regs = self.emu.memory, self.emu.register_file
        for name, data in fields.items():
            addr = self.symbols[name]
            mem[addr:addr + len(data)] = data
        mem[self.symbols['_riding_subphase']] = phase
        wheel = self.symbols['_Bike'] + (1 + slot) * 24
        stack, code = 0xdf80, 0xdfd0
        addr = self.symbols['_riding_wheel' if mode == 'single' else '_riding_roll32']
        bank = addr >> 16
        mem[0x3000], mem[0x2000], mem[self.symbols['__current_bank']] = 0, bank, bank
        # A banked caller has four extra bytes before k. The public near
        # rolling ABI has its contact pointer between k and the impulses.
        args = (b'\x5a' * 4 + struct.pack('<H', wheel) if mode == 'single'
                else struct.pack('<HH', wheel, self.symbols['_Ct']))
        args += struct.pack('<iii', *impulses)
        guard = args + b'\x96\x69'
        mem[stack:stack + len(guard)] = guard
        mem[code:code+5] = [0xcd, addr & 255, addr >> 8 & 255, 0x18, 0xfe]
        regs.SP, regs.PC = stack, code
        for _ in range(10):
            self.emu.tick(1, False)
            if regs.PC == code+3:
                break
        assert (regs.PC, regs.SP) == (code+3, stack), (mode, regs.PC, regs.SP)
        assert bytes(mem[stack:stack+len(guard)]) == guard
        assert mem[self.symbols['__current_bank']] == bank
        # Read bank-9 code where it actually appears in the switchable window.
        original = self.symbols['_riding_cert_hit'] & 0xffff
        assert bytes(mem[original:original+3]) == b'\x3e\x01\xc9'
        return {name: bytes(mem[self.symbols[name]:self.symbols[name]+size])
                for name, size in FIELDS.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--rom', type=Path, required=True)
    args = parser.parse_args()
    base, target = Cartridge(args.reference), Cartridge(args.rom)
    rng = random.Random(31043)
    normals = [(0, 0), (0, 16384), (0, -16384), (16384, 0), (-16384, 0),
               (-32768, 32767), (32767, -32768), (11585, 11585), (1, -1)]
    values = [-2**31, -2**31+1, -65537, -65536, -46138, -46137, -46136,
              -32769, -232, -231, -230, -1, 0, 1, 231, 232, 32768,
              46136, 46137, 46138, 65535, 2**31-1]
    # With zero Y velocity, these shallow tangents yield exactly -vx.
    # Probe either side of the signed16 speed bounds and every high byte
    # near its projection rounding threshold in each table.
    shallow = []
    for magnitude in (9, 61):
        speeds = {-32769, -32768, 0, 32767, 32768}
        for high in range(-128, 128):
            remainder = (8192 - high * 256 * magnitude) % 16384
            low = min(255, remainder // magnitude)
            speeds.add(high * 256 + low)
            if low < 255:
                speeds.add(high * 256 + low + 1)
        shallow.extend((magnitude, speed) for speed in sorted(speeds))
    # Sweep the corrected high-word limits in all 21 atlas slopes, plus
    # low-byte aliases that must use the full signed16 coefficient path.
    # Dot saturation must occur before the speed delta and wheel projection.
    atlas_cases = []
    coefficients = (-86, 8, -15, -108, -104, -59, -27, -33, 104, -18, -32, -61,
                    -78, -5, -9, 50, 10, -56, -75, 24, -105, 0, 170, -248)
    for coefficient in coefficients:
        for high in (-17, -16, -1, 0, 1, 15, 16):
            for low in (-32768, -32767, -1, 0, 1, 32767):
                y = high*65536 + low
                for impulse_y in (y, -y, 0x3456789):
                    x = rng.choice((-2**31, -2**31+1, 2**31-1, -1, 0, 1))
                    impulse_x = rng.choice((-2**31, 2**31-1, -32768, 32767))
                    atlas_cases.append(((coefficient, 16384), x, y,
                                        (impulse_x, impulse_y, rng.choice((-2400, 0, 2400)))))
    # -vx plus the two separately rounded impulses lands on INT32_MIN.
    # The unit tangent's negated output must saturate to INT32_MAX.
    for _ in range(4):
        phase = ((1200 + len(shallow) + 16 + len(atlas_cases)) >> 1) & 1
        torque_scale = (2115702, 3208767)[phase]
        speed_scale = (112030763, 73867549)[phase]
        torque = (-9*torque_scale + (1 << 23)) >> 24
        delta = (torque*speed_scale + (1 << 23)) >> 24
        atlas_cases.append(((0, 16384), (1 << 31) + delta, 0, (9, 0, 0)))
    # The table reader switches independently between signed16, signed20,
    # signed24 and full-width inputs. Probe both sides of its exact width checks
    # in all four coordinates and force full-tag misses with aliased lows.
    limits = (-8388609, -8388608, -8388607, -524289, -524288, -524287, -32769, -32768, -1,
              0, 32767, 32768, 524286, 524287, 524288, 8388606, 8388607, 8388608)
    for tx, ty in (*SLOPE_TANGENTS, VERTICAL_TANGENT):
        normal = (ty, -tx)
        for i, value in enumerate(limits):
            words = [rng.randint(-32768, 32767) for _ in range(4)]
            words[i % 4] = value
            atlas_cases.append((normal, *words[:2], (*words[2:], rng.choice((-2400, 0, 2400)))))
        for _ in range(8):
            words = [rng.randint(-524288, 524287) for _ in range(4)]
            atlas_cases.append((normal, *words[:2], (*words[2:], rng.randint(-65536, 65535))))
        # Four extreme components exercise carry from each product digit,
        # mixed word widths and the final upper two quotient bits.
        for x in (-8388608, 8388607):
            for y in (-8388608, 8388607):
                atlas_cases.append((normal, x, y, (-1-x, -1-y, 2400)))
        alias = (ty ^ 256, -tx)
        atlas_cases.append((alias, -12345, 67890, (33333, -22222, 0)))
    for x in (-1048576, -32768, -1, 0, 1, 32767, 1048575):
        for y in (-2**31, 2**31-1):
            atlas_cases.append(((20, -16384), x, y, (x, y, 0)))
    observed = set()
    cases = 0
    try:
        for i in range(1200 + len(shallow) + 16 + len(atlas_cases)):
            fields = {key: rng.randbytes(size) for key, size in FIELDS.items()}
            slot, phase, prior = i & 1, i >> 1 & 1, i >> 2 & 1
            if i >= 1200 + len(shallow) + 16:
                normal, vx, vy, impulses = atlas_cases[i - 1200 - len(shallow) - 16]
            elif i >= 1200 + len(shallow):
                # A nonzero normal impulse and normal velocity disappear
                # from the rolling solution. Include a moving initial omega.
                normal, vx, vy = (0, 16384), 0, 0x76543210
                impulses = (0, -1234567, 0)
            elif i >= 1200:
                magnitude, speed = shallow[i - 1200]
                normal, vx, vy = (-magnitude, 16384), -speed, 0
                impulses = (0, 0, 0)
            elif i < len(values) * 8:
                # Both sides of the exact support and first-impact thresholds.
                normal, vx, vy = (16384, 0), values[i // 8], 0
                impulses = (1, 0, 0)
            else:
                normal = (rng.choice(normals) if i % 2 else
                          (rng.randint(-32768, 32767), rng.randint(-32768, 32767)))
                sample = lambda: (rng.choice(values) if rng.randrange(2) else
                                  rng.randint(-2**31, 2**31-1))
                vx, vy = sample(), sample()
                impulses = tuple(sample() for _ in range(3))
            k = bytearray(fields['_Bike'])
            struct.pack_into('<ii', k, 24*(1+slot)+8, vx, vy)
            fields['_Bike'] = k
            fields['_Ct'] = struct.pack('<hh', *normal) + fields['_Ct'][4:]
            prior_contact = bytearray(fields['_riding_audio_contact'])
            prior_contact[slot] = prior
            fields['_riding_audio_contact'] = prior_contact
            # Residuals reachable between calls are signed Q24 fractions.
            fields['_move_residual'] = struct.pack('<8i', *[
                rng.randint(-0x800000, 0x7fffff) for _ in range(8)])
            if i >= 1200 + len(shallow):
                # Byte 3 is normally the extension of byte 2. The native
                # zero-velocity translation still canonicalizes it.
                fields['_move_residual'] = rng.randbytes(32)
            for mode in ('single', 'roll'):
                params = fields, mode, phase, slot, impulses
                expected, actual = base.run(*params), target.run(*params)
                for name in FIELDS:
                    assert expected[name] == actual[name], (
                        i, mode, phase, slot, prior, vx, vy, normal, impulses,
                        name, expected[name].hex(), actual[name].hex())
                if mode == 'single':
                    observed.add((actual['_riding_audio_contact'][slot],
                                  actual['_riding_audio_impact'][slot]))
                cases += 1
        assert observed == {(0, 0), (1, 0), (1, 1)}, observed
    finally:
        base.emu.stop(save=False)
        target.emu.stop(save=False)
    print(f'{cases} native wheel comparisons passed, including motion residuals, '
          'Q24 fractions and saturation, contact/audio bytes, bank and stack.')


if __name__ == '__main__':
    main()
