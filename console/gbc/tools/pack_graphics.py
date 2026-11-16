"""Losslessly repack generated scenery into independently cached ZX0 blocks."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile

import numpy as np

from assets import array
from levels import Packer
from zx0 import decompress

PATTERN_BLOCK_BYTES = 1024


def compress(data, compiler, cache):
    digest = hashlib.sha256(data).hexdigest()
    target = cache / (digest + '.zx0')
    if target.exists():
        result = target.read_bytes()
        if decompress(result, len(data)) == data:
            return result
        raise ValueError('Cached ZX0 block differs from its source')
    with tempfile.TemporaryDirectory(dir=cache) as directory:
        directory = Path(directory)
        source, packed = (directory / name for name in ('source', 'packed'))
        source.write_bytes(data)
        subprocess.run([str(compiler), '--alg=zx0', str(source), str(packed)], check=True, capture_output=True)
        result = packed.read_bytes()
        if decompress(result, len(data)) != data:
            raise ValueError('ZX0 round trip changed the source graphics')
        packed.replace(target)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gen', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    args = parser.parse_args()
    gen = args.gen
    manifest_path = gen / 'level_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('rom_mib', 4) != 4:
        raise ValueError('ZX0 graphics belong to the 4 MiB profile; use a separate generated directory')
    compiler = (args.sdk / 'bin/gbcompress').resolve()
    codec_key = hashlib.sha256(Path(__file__).read_bytes() + Path(__file__).with_name('zx0.py').read_bytes()
                               + compiler.read_bytes()).hexdigest()
    header_path = gen / 'level_catalogue.h'
    if (manifest.get('compression_key') == codec_key
        and manifest.get('map_codec') == 'zx0-raw3-plane32x16'
        and manifest.get('pattern_codec') == 'zx0-1024'
        and re.search(r'^#define WORLD_GRAPHICS_ZX0 1$', header_path.read_text(), re.M)
        and all((gen / ('level_bank_%d.c' % bank)).is_file()
                for bank in range(manifest['first_bank'], manifest['last_bank'] + 1))):
        print('ZX0 scenery unchanged: banks %d..%d' % (manifest['first_bank'], manifest['last_bank']))
        return
    cache = gen.parent / 'zx0-cache' / hashlib.sha256(compiler.read_bytes()).hexdigest()[:16]
    cache.mkdir(parents=True, exist_ok=True)
    blocks = {}
    for record in manifest['levels']:
        with np.load(gen / 'levels' / ('%02d' % (record['index'] + 1)) / 'tiles.npz') as source:
            patterns = source['patterns'].tobytes()
            pattern_blocks = [patterns[i:i + PATTERN_BLOCK_BYTES]
                              for i in range(0, len(patterns), PATTERN_BLOCK_BYTES)]
            ids, attrs = source['ids'], source['attrs']
            chunks = []
            for y in range(0, ids.shape[0], 16):
                for x in range(0, ids.shape[1], 32):
                    cells = ids[y:y + 16, x:x + 32].ravel()
                    chunks.append(bytes((cells & 255).astype(np.uint8))
                                  + bytes((cells >> 8).astype(np.uint8))
                                  + attrs[y:y + 16, x:x + 32].tobytes())
        blocks[record['index']] = pattern_blocks, chunks
    unique = set(blob for pair in blocks.values() for group in pair for blob in group)
    print('Compressing %d unique scenery blocks with ZX0' % len(unique), flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        compressed = dict(zip(unique, pool.map(lambda data: compress(data, compiler, cache), unique)))
    packer = Packer(manifest['first_bank'])
    pointers = {}
    def allocate(blob):
        if blob not in pointers:
            pointers[blob] = packer.allocate(compressed[blob])
        return pointers[blob]
    directory = []
    pattern_bytes = map_bytes = 0
    for record in manifest['levels']:
        pattern_blocks, chunks = blocks[record['index']]
        pattern_pointers = [allocate(blob) for blob in pattern_blocks]
        record['patterns'] = packer.allocate(b''.join(struct.pack('<HH', *p) for p in pattern_pointers), 2)
        record['pattern_blocks'] = pattern_pointers
        record['chunks'] = [allocate(blob) for blob in chunks]
        record['chunk_directory'] = packer.allocate(b''.join(struct.pack('<HH', *p) for p in record['chunks']), 2)
        with np.load(gen / 'levels' / ('%02d' % (record['index'] + 1)) / 'tiles.npz') as source:
            pal = source['palettes'].reshape(-1, 3).astype(np.uint16) >> 3
            colors = pal[:, 0] | (pal[:, 1] << 5) | (pal[:, 2] << 10)
        record['palette'] = packer.allocate(struct.pack('<28H', *colors), 2)
        record['objects_pointer'] = packer.allocate(b''.join(struct.pack('<HHBiiB', *obj) for obj in record['objects']), 2)
        w, h = record['size_px']
        ox, oy = record['origin_m']
        directory.append('{%d,%d,%dL,%dL,%d,{%d,%d},{%d,%d},{%d,%d},{%d,%d},%d,%d,%d}' %
                         (w, h, ox * 65536, oy * 65536, record['pattern_count'],
                          *record['patterns'], *record['chunk_directory'], *record['palette'],
                          *record['objects_pointer'], w // 256, h // 128, len(record['objects'])))
        pattern_bytes += sum(len(compressed[blob]) for blob in pattern_blocks)
        map_bytes += sum(len(compressed[blob]) for blob in chunks)
    if packer.bank >= 252:
        raise ValueError('Compressed graphics end at bank %d, overlapping coefficient banks 252..255' % packer.bank)
    catalogue = (gen / 'level_catalogue.c').read_text()
    catalogue = re.sub(r'(const world_level_t world_levels\[\]=\{).*?\n\};',
                       lambda match: match[1] + '\n' + ',\n'.join(directory) + '\n};', catalogue, count=1, flags=re.S)
    header = (gen / 'level_catalogue.h').read_text()
    header = re.sub(r'^[ \t]*#[ \t]*define[ \t]+WORLD_GRAPHICS_ZX0\b[^\n]*\n?', '', header, flags=re.M)
    header = header.replace('#define GBC_LEVEL_CATALOGUE_H',
                            '#define GBC_LEVEL_CATALOGUE_H\n#define WORLD_GRAPHICS_ZX0 1')
    manifest.update(rom_mib=4, compression_key=codec_key, map_codec='zx0-raw3-plane32x16',
                    pattern_codec='zx0-1024', pattern_block_bytes=PATTERN_BLOCK_BYTES,
                    last_bank=packer.bank, payload_bytes=sum(map(len, packer.banks)),
                    physical_bank_bytes=len(packer.banks) * 16384,
                    compressed_pattern_bytes=pattern_bytes, compressed_map_bytes=map_bytes)
    # Publish only after all blocks pass round-trip and size checks.
    with tempfile.TemporaryDirectory(dir=gen) as temporary:
        temporary = Path(temporary)
        for i, data in enumerate(packer.banks):
            bank = packer.first + i
            (temporary / ('level_bank_%d.c' % bank)).write_text(
                '#include <stdint.h>\n#pragma bank %d\n' % bank + array('level_bank_%d' % bank, data))
        (temporary / 'level_catalogue.c').write_text(catalogue)
        (temporary / 'level_catalogue.h').write_text(header)
        for path in temporary.iterdir():
            path.replace(gen / path.name)
        for path in gen.glob('level_bank_*.c'):
            if int(path.stem.rsplit('_', 1)[1]) > packer.bank:
                path.unlink()
        (temporary / 'level_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        (temporary / 'level_manifest.json').replace(manifest_path)
    print('ZX0 scenery: %d bytes, banks %d..%d; 4 MiB image fits' %
          (manifest['payload_bytes'], packer.first, packer.bank), flush=True)


if __name__ == '__main__':
    main()
