"""Exact wheel/rider integer square roots from a bucket and one threshold."""
from math import isqrt
from head_clearance import write_if_changed


def generate(gen):
    lines = ['.module riding_sqrt_tables']

    def emit(label, values):
        if label:
            lines.append(label + '::')
        for i in range(0, len(values), 32):
            lines.append(' .db ' + ','.join(map(str, values[i:i+32])))

    def buckets(width, groups, first):
        for page in range(0, groups, 256):
            roots, thresholds = [], []
            for i in range(page, page+256):
                minimum = i*width
                maximum = minimum+width-1
                root = isqrt(maximum)
                if minimum >= first:
                    assert root-isqrt(minimum) <= 1
                roots.append(root & 255)
                thresholds.append(max(0, root*root-minimum))
            emit(None, roots)
            emit(None, thresholds)

    lines += ['.area _CODE_15', '_riding_sqrt_large::']
    buckets(256, 4096, 16384)
    # A multiple of 256 in the result always starts at a bucket boundary.
    emit('_riding_sqrt_upper', [isqrt(v << 16) >> 8 for v in range(16)])
    lines += ['.area _CODE_35', '_riding_sqrt_small::']
    buckets(16, 1024, 256)
    emit('_riding_sqrt_byte', [isqrt(v) for v in range(256)])
    path = gen/'physics_sqrt_rows.s'
    write_if_changed(path, '\n'.join(lines)+'\n')
    return path
