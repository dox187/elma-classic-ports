"""Pack exact rounded contact lengths for reachable integer wheel offsets."""
from collections import Counter
from math import isqrt

from head_clearance import write_if_changed


def generate(gen, reader, roots_path):
    roots = tuple(map(int, roots_path.read_text().split('\n', 1)[1].strip().rstrip(',').split(',')))
    lower, upper = 65536, 168448
    slots = [Counter() for _ in range((upper-lower)//32)]
    # Signed Q14 normals round downward before the final once-rounded dot.
    # Equal squared distances can therefore have different lengths.
    radius = isqrt(upper-1)
    for x in range(-radius, radius+1):
        for y in range(-radius, radius+1):
            squared = x*x + y*y
            if lower <= squared < upper:
                r = roots[(squared-16384) >> 9]
                length = (x*(x*r >> 4) + y*(y*r >> 4) + 8192) >> 14
                slots[(squared-lower) >> 5][length] += 1

    rows, patterns = [], {}
    for i in range(0, len(slots), 16):
        bins = slots[i:i+16]
        # Each code selects one of three consecutive results. Code zero
        # delegates empty and ambiguous slots to the original dot product.
        counts = Counter()
        for group in bins:
            if len(group) == 1:
                counts.update(group)
        base = max(counts, key=lambda n: (sum(counts[n+j] for j in range(3)), -n))
        codes = []
        for group in bins:
            length = next(iter(group)) if len(group) == 1 else None
            codes.append(length-base+1 if length is not None and base <= length <= base+2 else 0)
        pattern = bytes(sum(codes[j+k] << (2*k) for k in range(4)) for j in range(0, 16, 4))
        assert 250 < base < 504
        rows.extend((base-250, patterns.setdefault(pattern, len(patterns))))

    out = ['.module normal_lengths', '.area _CODE_5', reader.read_text()]
    for name, data in (('normal_length_rows', rows), ('normal_length_patterns', b''.join(patterns))):
        out.append(name+'::')
        for i in range(0, len(data), 16):
            out.append(' .db '+','.join(map(str, data[i:i+16])))
    path = gen/'normal_lengths.s'
    write_if_changed(path, '\n'.join(out)+'\n')
    return path
