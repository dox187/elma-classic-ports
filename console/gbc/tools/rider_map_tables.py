"""Keep DMA ranges and terrain tails fixed while fitting direct rider products in scenery."""
from collections import defaultdict
import re
import struct

CODEC = 'raw-uniform-high32x16'
BANK_BYTES = 16384
TABLE_BYTES = 12288
BANK_COUNT = 8


def product_tables(constants):
    """Planar little-endian signed16 products, in the exact order read by SM83."""
    scales = {name: tuple(map(int, values.split(','))) for name, values in
              re.findall(r'q24_C_RIDER_([SF])\[2\]=\{(\d+,\d+)\}', constants)}
    if set(scales) != {'S', 'F'}:
        raise ValueError('Direct rider tables require two scheduled Q24 spring and damper scales')
    tables = []
    for slot in range(BANK_COUNT):
        table = bytearray()
        limits = []
        for name, half, base, count in (('S', 1024, 0, 2048), ('F', 8192, 4096 * (slot % 4), 4096)):
            results = []
            for value in range(base, base + count):
                signed = value if value < half else value - 2 * half
                results.append((signed * scales[name][slot // 4] + (1 << 23)) >> 24)
            limits.append((min(results), max(results)))
            for page in range(0, count, 256):
                group = results[page:page + 256]
                for shift in (0, 8):
                    table.extend((value >> shift) & 255 for value in group)
        spring, damper = limits
        if (min(spring[0], damper[0], spring[0] - damper[1]) < -32768 or
                max(spring[1], damper[1], spring[1] - damper[0]) >= 32768):
            return None
        tables.append(table)
    return tables


def validate(gen, manifest, constants):
    """Check physical table ownership, its linked input bytes and all encoded map extents."""
    first = manifest.get('rider_product_first_bank')
    if (type(first) is not int or not 0 < first <= 248 or first % BANK_COUNT or
            not manifest['first_bank'] <= first <= first + BANK_COUNT - 1 <= manifest['last_bank']):
        raise ValueError('Direct rider tables need eight aligned low graphics banks')
    tables = product_tables(constants)
    if tables is None:
        raise ValueError('Direct rider difference exceeds signed16')
    for slot, expected in enumerate(tables):
        bank = first + slot
        path = gen / f'level_bank_{bank}.c'
        initializer = path.read_text().split('{', 1)[1].split('}', 1)[0]
        prefix = initializer.split(',', TABLE_BYTES)[:TABLE_BYTES]
        if bytes(map(int, prefix)) != expected:
            raise ValueError(f'Bad direct rider product data in graphics bank {bank}')
    for record in manifest['levels']:
        for encoded, address in record['chunks']:
            bank = encoded & 511
            compact = bool(encoded & 0x8000)
            length = 1024 if compact else 1536
            if (not 0 <= encoded <= 65535 or (not compact and bank != encoded) or
                    not manifest['first_bank'] <= bank <= manifest['last_bank'] or
                    not 0x4000 <= address <= 0x8000 - length or
                    (first <= bank < first + BANK_COUNT and address < 0x4000 + TABLE_BYTES)):
                raise ValueError(f'Invalid direct rider scenery pointer on level {record["index"] + 1}')


def repack(packer, records, constants):
    """Only the original 1536-byte map extents and their far pointers may move."""
    chunks = sorted({tuple(pointer) for record in records for pointer in record['chunks']})
    extents = defaultdict(list)
    payloads = {}
    for bank, address in chunks:
        start = address - 0x4000
        data = bytes(packer.banks[bank - packer.first][start:start + 1536])
        if len(data) != 1536:
            raise ValueError('Map chunk extends outside its original graphics bank')
        high = data[512:1024]
        tag = 0
        if high == bytes([high[0]]) * 512 and high[0] < 64:
            tag = 0x8000 | high[0] << 9
            data = data[:512] + data[1024:]
        payloads[bank, address] = data, tag
        regions = extents[bank]
        if regions and regions[-1][1] == start:
            regions[-1][1] += 1536
        else:
            regions.append([start, start + 1536])

    # Four low-bank ranges select the upper two damper input bits, and
    # the next four use the second scheduled phase. Each range repeats
    # the spring result so both products need only one MBC5 switch.
    usable = {bank for bank, regions in extents.items()
              if bank < 256 and regions[0][0] == 0 and regions[0][1] >= TABLE_BYTES}
    first = next((bank for bank in sorted(usable) if bank % BANK_COUNT == 0
                  and all(bank + i in usable for i in range(BANK_COUNT))), None)
    if first is None:
        return None
    for bank in range(first, first + BANK_COUNT):
        extents[bank][0][0] = TABLE_BYTES
    holes = [[end - start, bank, start] for bank, regions in extents.items()
             for start, end in regions if start < end]
    placements = {}
    for pointer in sorted(payloads, key=lambda key: (-len(payloads[key][0]), key)):
        data, tag = payloads[pointer]
        size = len(data)
        fits = [entry for entry in holes if entry[0] >= size]
        if not fits:
            return None
        slot = min(fits, key=lambda entry: (entry[0] % size, *entry))
        _, bank, start = slot
        placements[pointer] = bank | tag, start + 0x4000
        slot[0] -= size
        slot[2] += size

    tables = product_tables(constants)
    if tables is None:
        return None
    for pointer, (encoded_bank, address) in placements.items():
        data, _ = payloads[pointer]
        bank = packer.banks[(encoded_bank & 511) - packer.first]
        start = address - 0x4000
        bank[start:start + len(data)] = data
    for record in records:
        record['chunks'] = [placements[tuple(pointer)] for pointer in record['chunks']]
        bank, address = record['chunk_directory']
        result = packer.banks[bank - packer.first]
        for index, pointer in enumerate(record['chunks']):
            struct.pack_into('<HH', result, address - 0x4000 + index * 4, *pointer)
    for slot, table in enumerate(tables):
        assert len(table) == TABLE_BYTES
        packer.banks[first + slot - packer.first][:TABLE_BYTES] = table
    return first
