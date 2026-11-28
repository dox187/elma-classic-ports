"""Align native solver poses to the common clock without moving event times."""
import math
from fractions import Fraction


def sample_30hz(native, ticks):
    """native yields (model seconds, pose), starting at spawn and ending at or past the horizon or at a terminal event."""
    native = iter(native)
    right_time, right = next(native)
    if right_time != 0:
        raise ValueError('Missing spawn pose')
    left_time, left = right_time, right
    samples = []
    for tick in range(1, ticks + 1):
        target = Fraction(tick, 30)
        while right_time < target and right['event'] is None:
            left_time, left = right_time, right
            right_time, right = next(native)
            if right_time <= left_time:
                raise ValueError('Native clock did not advance')
        if right_time <= target:
            samples.append(right)
            continue
        weight = float((target - left_time) / (right_time - left_time))
        rotation = math.remainder(right['angle'] - left['angle'], math.tau)
        samples.append(dict(x=left['x'] + weight * (right['x'] - left['x']),
                            y=left['y'] + weight * (right['y'] - left['y']),
                            angle=left['angle'] + weight * rotation, event=left['event']))
    return samples
