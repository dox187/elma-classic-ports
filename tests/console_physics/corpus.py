"""Version 1 of the common corpus. Each mask is held for 1/30 simulated second."""

def controls(segments):
    return [mask for mask, ticks in segments for _ in range(ticks)]


def cases():
    # Replay both routes on every course. All riders start in the default direction.
    gas = controls([(1, 360)])
    mixed = controls([(1, 60), (2, 30), (0, 24), (5, 12), (1, 54),
                      (9, 12), (1, 48), (2, 36), (4, 12), (0, 72)])
    result = []
    for level in range(54):
        for name, inputs in [('throttle', gas), ('mixed', mixed)]:
            result.append(dict(id=f'{level+1:02}-{name}', level=level, inputs=inputs))
    # Reach the long descent before applying either rotation.
    result.append(dict(id='freefall-rotation', level=43,
                       inputs=controls([(0, 264), (4, 6), (0, 36), (8, 6), (0, 168)])))
    # Found by driving the PC reference from spawn to the flower. The final
    # coast leaves time for a port that reaches the flower later than the PC.
    result.append(dict(id='flat-track-finish', level=1,
                       inputs=controls([(1, 72), (9, 48), (1, 96), (0, 48), (1, 12),
                                        (9, 48), (5, 144), (1, 48), (0, 48), (1, 96), (0, 84)])))
    return result
