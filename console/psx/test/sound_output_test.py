#!/usr/bin/env python3
"""Verify real SPU output, sound-option mute and menu/replay silence.

Uses PCSX-Redux's SDL disk backend: no audible output or host mixer changes.
The captured native stereo F32 output is checked independently of the game's
PCM buffers and stream counters. Requires a build of elma.exe and game assets.
"""
import argparse
import array
import json
import math
import os
import re
import resource
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PSX = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(PSX))
sys.path.insert(0, HERE)
import pcsx  # noqa: E402
from core_boot_test import make_pcdrv_dir  # noqa: E402
from mc_test import make_card  # noqa: E402
from res_layout import resource_layout  # noqa: E402

RATE = 44100
FRAME_BYTES = 8  # SDL output is two native F32 samples per frame.


def check_capture(path, output):
    samples = array.array("f")
    with open(path, "rb") as f:
        samples.frombytes(f.read())
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples or any(not math.isfinite(x) or abs(x) > 1.01 for x in samples):
        raise ValueError("invalid stereo F32 capture")
    marks = [(int(m), int(s), int(b)) for m, s, b in re.findall(
        r"AUDIO_MARK mute=(\d+) sound=(\d+) bytes=(\d+)", output)]
    if [(m, s) for m, s, _ in marks] != [(0, 1), (0, 0), (0, 1), (1, 1), (0, 1)]:
        raise ValueError("missing ride, sound option, menu or replay transition")
    for i, (mute, sound, start) in enumerate(marks):
        end = marks[i + 1][2] if i + 1 < len(marks) else len(samples) * 4
        # Ignore device buffering around an edge, never the steady interval.
        first = start // FRAME_BYTES + int(0.15 * RATE)
        last = end // FRAME_BYTES - int(0.10 * RATE)
        segment = samples[2 * first:2 * last]
        if len(segment) < int(0.15 * RATE) * 2:
            raise ValueError("capture interval too short")
        rms = math.sqrt(sum(x * x for x in segment) / len(segment))
        peak = max(abs(x) for x in segment)
        duty = sum(abs(x) > 1e-5 for x in segment) / len(segment)
        silent = mute or not sound
        print("sound output: %s %.3fs RMS %.5f peak %.5f nonzero %.1f%%" % (
            "muted" if silent else "riding", len(segment) / (2 * RATE), rms, peak, duty * 100))
        if silent and peak > 1e-5:
            raise ValueError("audible data remains while muted")
        if not silent and (rms < 0.003 or peak < 0.02 or duty < 0.75):
            raise ValueError("riding output is too quiet or intermittent")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--build", default=os.path.join(PSX, "build"))
    p.add_argument("--res", default=os.path.join(REPO, "elma.res"))
    p.add_argument("--lgr", default=os.path.join(REPO, "build/Lgr/Default_old.lgr"))
    p.add_argument("--timeout", type=float, default=600)
    p.add_argument("--spu-irq", action="store_true", help="also enable Redux's SpuIrq compatibility option")
    p.add_argument("--card-save", action="store_true", help="save the memory card between the two rides")
    args = p.parse_args()
    work = os.path.abspath(os.path.join(args.build, "sound-output-test" +
                                      ("-irq" if args.spu_irq else "") + ("-card" if args.card_save else "")))
    os.makedirs(work, exist_ok=True)
    raw = os.path.join(work, "sdlaudio.raw")
    if os.path.exists(raw):
        os.remove(raw)
    config = os.path.join(work, "home/.config/pcsx-redux")
    os.makedirs(config, exist_ok=True)
    with open(os.path.join(config, "pcsx.json"), "w") as f:
        json.dump({"emulator": {"SpuIrq": args.spu_irq}, "spu": {"Backend": "disk"}}, f)
    card = os.path.join(work, "card.mcd")
    with open(card, "wb") as f:
        f.write(make_card("fresh"))
    make_pcdrv_dir(os.path.join(work, "pcdrv"), args.res, args.lgr)
    # Disk output only. The other backends cannot connect to the host audio
    # services even if an emulator ignores the requested disk backend.
    os.environ.update(SDL_AUDIO_DRIVER="disk", SDL_AUDIODRIVER="disk",
                      PULSE_SERVER="unix:/nonexistent/pulse", PIPEWIRE_REMOTE="/nonexistent/pipewire",
                      ALSA_CONFIG_PATH="/dev/null")
    resource.setrlimit(resource.RLIMIT_FSIZE, (128 * 1024 * 1024, 128 * 1024 * 1024))
    result = pcsx.run(exe=os.path.join(args.build, "elma.exe"),
                      map_file=os.path.join(args.build, "elma.map"), ram8=False, sound=True,
                      pcdrv=os.path.join(work, "pcdrv"), workdir=work, timeout=args.timeout,
                      lua=os.path.join(HERE, "sound_output_test.lua"),
                      extra_flags=["-memcard1", card],
                      args={"memory_lua": os.path.join(HERE, "mem_test.lua"),
                            "capture_path": raw, "level": 0, "play": 120, "after": "again",
                            "card_save": int(args.card_save),
                            "path": ",".join(resource_layout(args.res)["internal_steps"])})
    for line in result.output.splitlines():
        if line.startswith(("Audio:", "sound output:", "AUDIO_MARK", "AUDIO_CARD", "PASS", "FAIL", "LUA")):
            print(line)
    if result.returncode or "FAIL:" in result.output or not re.search(r"^PASS:", result.output, re.M):
        print("FAIL: gameplay or capture failed (emulator exit %d)" % result.returncode)
        return 1
    try:
        if "Audio: driver disk," not in result.output:
            raise ValueError("SDL disk backend was not used")
        if args.card_save and "AUDIO_CARD resumed after save" not in result.output:
            raise ValueError("memory-card save and audio restart were not exercised")
        check_capture(raw, result.output)
    except (OSError, ValueError) as e:
        print("FAIL:", e)
        return 1
    print("PASS: digital output, option mute, menu silence and replay resume")
    return 0


if __name__ == "__main__":
    sys.exit(main())
