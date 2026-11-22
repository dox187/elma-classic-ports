"""Select immediate brake Q24 indices when every relevant table entry agrees."""
import re

from head_clearance import write_if_changed


def generate(gen, assembly, destination=None):
    dispatch = (gen / 'physics_q24_dispatch.c').read_text()
    indices = {name: (int(first), int(second)) for name, first, second in re.findall(
        r'q24_index_C_BRAKE_(A|W|GW)\[2\]=\{(\d+),(\d+)\}', dispatch)}
    definitions = []
    for symbol, names in (('brake_angle_index', ('A',)), ('brake_damping_index', ('W', 'GW'))):
        values = {index for name in names for index in indices[name]}
        if len(values) == 1:
            definitions.append(f'{symbol} = {values.pop()}\n')
    output = destination or gen / 'physics_brake_game.s'
    write_if_changed(output, ''.join(definitions) + assembly.read_text())
    return output
