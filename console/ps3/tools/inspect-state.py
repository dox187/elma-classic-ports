#!/usr/bin/env python3
"""Read-only legacy state inspection for import/editor acceptance testing."""
import argparse
import hashlib
import json
import pathlib
import struct


def decode(block):
    a, b, c = 23, 9782, 3391
    result = bytearray(block)
    short = lambda value: ((value + 32768) & 65535) - 32768
    for i in range(len(result)):
        result[i] ^= a & 255
        a = a - c * (abs(a) // c * (-1 if a < 0 else 1))
        b = short(b + a * c)
        a = short(31 * b + c)
    return bytes(result)


def inspect(path):
    data = path.read_bytes()
    if len(data) != 67910:
        raise ValueError(f"Expected 67910-byte legacy state, got {len(data)}")
    version = struct.unpack('<i', decode(data[:4]))[0]
    if version != 200:
        raise ValueError(f"Unsupported state version {version}")
    players = decode(data[61924:67724])
    count = struct.unpack('<i', decode(data[67724:67728]))[0]
    if not 0 <= count <= 50:
        raise ValueError(f"Invalid player count {count}")
    name = lambda block: block.split(b'\0', 1)[0].decode('latin1')
    selected = [name(decode(data[67728:67743])), name(decode(data[67743:67758]))]
    result = []
    for i in range(count):
        player = players[i * 116:(i + 1) * 116]
        completed, level = struct.unpack_from('<ii', player, 108)
        if not 0 <= completed <= 90:
            raise ValueError(f"Invalid completed level count for player {i}")
        skipped = sum(bool(value) for value in player[16:16 + completed])
        result.append(dict(name=name(player[:16]), completed=completed,
                           skipped=skipped, finished=completed - skipped,
                           editor_unlocked=completed - skipped >= 5,
                           current_level=level))
    magic = struct.unpack_from('<i', data, len(data) - 4)[0]
    if magic not in (123432112, 123432221):
        raise ValueError(f"Invalid state check number {magic}")
    return dict(path=str(path), sha256=hashlib.sha256(data).hexdigest(),
                version=version, selected_players=selected,
                editor_file=name(decode(data[67866:67886])),
                replay_file=name(decode(data[67886:67906])), players=result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('states', nargs='+', type=pathlib.Path)
    args = parser.parse_args()
    for path in args.states:
        try:
            print(json.dumps(inspect(path), indent=2))
        except (OSError, ValueError) as error:
            parser.exit(1, f"{path}: {error}\n")


if __name__ == '__main__':
    main()
