"""Pack exact rounded contact lengths for reachable integer wheel offsets."""
from collections import Counter
from math import isqrt

from head_clearance import write_if_changed


def pack_lengths(slots, width, lower, roots):
    rows, patterns = [], {}
    for i in range(0, len(slots), width):
        bins = slots[i:i+width]
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
        pattern = bytes(sum(codes[j+k] << (2*k) for k in range(4)) for j in range(0, width, 4))
        assert 160 < base <= 415
        reciprocal = roots[(lower-16384)//512 + i//width]
        # The original endpoint round-trip guard has at most one accepted
        # length among these three successive physical lengths.
        certified = []
        for code in (1, 2, 3):
            length = base+code-1
            error = min(940, (131071-16*length)//(length+2))
            if length <= 410 and abs(reciprocal*length-262144) <= error:
                certified.append(code)
        assert len(certified) <= 1
        rows.append((base-160, patterns.setdefault(pattern, len(patterns)), next(iter(certified), 0)))

    # A row's pattern offset occupies six bits and its round-trip code two.
    # When other coefficients need more patterns, the excess rows use the
    # original dot product through an all-zero pattern.
    dictionary = list(patterns)
    if len(dictionary) > 64:
        dictionary = dictionary[:63] + [bytes(width//4)]
    directory = bytes(byte for base, index, tag in rows
                      for byte in (base, 4*min(index, 63)+tag))

    return directory, b''.join(dictionary)


def generate(gen, reader, roots_path):
    roots = tuple(map(int, roots_path.read_text().split('\n', 1)[1].strip().rstrip(',').split(',')))
    inner, lower, upper = 32768, 65536, 168448
    deep_slots = [Counter() for _ in range((lower-inner)//64)]
    slots = [Counter() for _ in range((upper-lower)//32)]
    # Signed Q14 normals round downward before the final once-rounded dot.
    # Equal squared distances can therefore have different lengths.
    radius = isqrt(upper-1)
    for x in range(-radius, radius+1):
        for y in range(-radius, radius+1):
            squared = x*x + y*y
            if inner <= squared < upper:
                r = roots[(squared-16384) >> 9]
                length = (x*(x*r >> 4) + y*(y*r >> 4) + 8192) >> 14
                if squared < lower:
                    deep_slots[(squared-inner) >> 6][length] += 1
                else:
                    slots[(squared-lower) >> 5][length] += 1

    directory, patterns = pack_lengths(slots, 16, lower, roots)
    inner_rows, inner_patterns = pack_lengths(deep_slots, 8, inner, roots)

    def assemble(name, prefix, tables):
        out = ['.module '+name, prefix, reader.read_text()]
        for label, data in tables:
            out.append(label+'::')
            for i in range(0, len(data), 16):
                out.append(' .db '+','.join(map(str, data[i:i+16])))
        path = gen/(name+'.s')
        write_if_changed(path, '\n'.join(out)+'\n')
        return path

    outer = assemble('normal_lengths', '', (('normal_length_rows', directory),
                                            ('normal_length_patterns', patterns)))
    inner = assemble('normal_inner_lengths', 'NORMAL_INNER_LENGTHS = 1',
                     (('normal_inner_rows', inner_rows), ('normal_inner_patterns', inner_patterns)))
    return outer, inner
