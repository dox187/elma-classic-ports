"""Stress the protected Mode 7 coefficient latch with injected scroll writes.

Find compiled first-coefficient stores from their preceding shadow store, then
inject BG1 scroll writes immediately after each executed first store. Restoring
the shared latch through M7X must preserve the complete state/event trace.
The optional negative control omits restoration and must change the trace.
"""
import argparse
import json
from pathlib import Path

import mesen
import perf_check
from finish_test import read_script


def sites(rom, shadow):
    data = Path(rom).read_bytes()
    found = set()
    for address in (shadow & 65535, (shadow + 1) & 65535):
        pattern = bytes((0x8d, address & 255, address >> 8, 0x8d, 0x1b, 0x21))
        start = 0
        while (start := data.find(pattern, start)) >= 0:
            after = start + len(pattern)
            found.add(((0x80 + after // 32768) << 16) | 0x8000 | (after % 32768))
            start += 1
    if not found:
        raise ValueError('No shadow-protected first coefficient writes found')
    return sorted(found)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--rom', required=True)
    ap.add_argument('--level', type=int, default=0)
    ap.add_argument('--script')
    ap.add_argument('--out', required=True)
    ap.add_argument('--negative-control', action='store_true')
    args = ap.parse_args()
    out = Path(args.out).resolve()
    script = args.script or read_script(perf_check.ROOT / 'test/warmup_finish.txt')[1]
    symbols = mesen.read_symbols(args.rom)
    addresses = sites(args.rom, symbols['core_m7_latch'])
    reference = perf_check.run(args.rom, args.level, script, out / 'reference', 0, 300)
    original = perf_check.make_lua

    def run_variant(name, restore):
        def instrument(s, max_steps):
            lua, names = original(s, max_steps)
            lua += '\nlocal latch_hits={}\n'
            for addr in addresses:
                lua += '''cb(%d,function()
 latch_hits[%d]=(latch_hits[%d] or 0)+1
 emu.write(0x80210d,0x5a,pmem) emu.write(0x80210d,0xc3,pmem)
 emu.write(0x80210e,0x39,pmem) emu.write(0x80210e,0xa6,pmem)
 %s
end)\n''' % (addr, addr, addr,
                'emu.write(0x80211f,emu.read(%d,pmem),pmem)' % (s['core_m7_latch'] + 1) if restore else '')
            lua += '''cb(%d,function() if state_count==max_steps then
 for addr,n in pairs(latch_hits) do print("LATCH_HIT "..addr.." "..n) end
 end end)\n''' % s['phys_step_ret']
            return lua, names
        perf_check.make_lua = instrument
        try:
            candidate = perf_check.run(args.rom, args.level, script, out / name, 0, 300)
        finally:
            perf_check.make_lua = original
        hits = {}
        for line in (out / name / 'raw.txt').read_text().splitlines():
            fields = line.split()
            if fields and fields[0] == 'LATCH_HIT':
                hits[int(fields[1])] = int(fields[2])
        return {'comparison': perf_check.compare(candidate, reference),
                'visited_sites': len(hits), 'injections': sum(hits.values()),
                'site_hits': hits}

    restored = run_variant('restored', True)
    negative = run_variant('unrestored', False) if args.negative_control else None
    ok = bool(restored['comparison']['ok'] and restored['injections'] and
              (negative is None or not negative['comparison']['states_bit_exact']))
    report = {'ok': ok, 'rom_sha256': reference[0]['rom_sha256'],
              'level': args.level, 'compiled_first_write_sites': len(addresses),
              'restored': restored, 'negative_control': negative}
    (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Mode 7 latch: %s; %d/%d sites, %d injected scroll sequences' %
          ('PASS' if ok else 'FAIL', restored['visited_sites'], len(addresses), restored['injections']))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
