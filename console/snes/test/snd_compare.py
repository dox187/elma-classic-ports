"""Compares the sound of the SNES (a WAV captured from an emulator) with the
mix of the original (test/snd_pcmix.py at the same rate): aligns them,
prints the loudness and the balance of the bands over time, and draws their
spectrograms.

  snd_compare.py SNES.wav PC.wav [--png OUT.png] [--step 0.5]
"""

import argparse
import struct

import numpy as np

BANDS = [(0, 500), (500, 1500), (1500, 3000), (3000, 5500), (5500, 16000)]


def read_wav(path):
    d = open(path, "rb").read()
    ch = struct.unpack_from("<H", d, 22)[0]
    rate = struct.unpack_from("<I", d, 24)[0]
    pos = 12
    while d[pos:pos + 4] != b"data":
        pos += 8 + struct.unpack_from("<I", d, pos + 4)[0]
    n = struct.unpack_from("<I", d, pos + 4)[0]
    s = np.frombuffer(d[pos + 8:pos + 8 + n], dtype="<i2").reshape(-1, ch)
    return s[:, 0].astype(float), rate


def envelope(x, hop):
    n = len(x) // hop
    return np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(axis=1) + 1.0)


def align(a, b, rate):
    """The offset of b in a (samples), from the envelopes, then refined."""
    hop = rate // 200
    ea, eb = np.log(envelope(a, hop)), np.log(envelope(b, hop))
    ea -= ea.mean()
    eb -= eb.mean()
    n = len(ea) + len(eb)
    c = np.fft.irfft(np.fft.rfft(ea, n) * np.conj(np.fft.rfft(eb, n)), n)
    lag = int(np.argmax(c))
    if lag > len(ea):
        lag -= n
    off = lag * hop
    # Refined on the waveform around the coarse offset:
    best, bo = None, off
    seg = slice(rate, rate * 4)
    for d in range(-hop, hop + 1):
        o = off + d
        if o < 0:
            continue
        x = a[o + seg.start:o + seg.stop]
        y = b[seg]
        if len(x) < len(y):
            continue
        v = np.dot(x, y) / (np.linalg.norm(x) * np.linalg.norm(y) + 1e-9)
        if best is None or v > best:
            best, bo = v, o
    return bo


def bands(x, rate):
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1.0 / rate)
    return [spec[(f >= lo) & (f < hi)].sum() + 1e-3 for lo, hi in BANDS]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("snes")
    ap.add_argument("pc")
    ap.add_argument("--png")
    ap.add_argument("--step", type=float, default=0.5)
    a = ap.parse_args()
    s, rate = read_wav(a.snes)
    p, rate2 = read_wav(a.pc)
    if rate != rate2:
        raise SystemExit("the rates differ: %d %d" % (rate, rate2))
    off = align(s, p, rate)
    print("the PC mix starts at %.4f s of the SNES capture" % (off / rate))
    s = s[off:off + len(p)]
    p = p[:len(s)]
    step = int(a.step * rate)
    print("   time  SNES dB  PC dB   diff | band balance SNES-PC (dB): " +
          " ".join("%d-%d" % b for b in BANDS))
    diffs = []
    for i in range(0, len(p) - step + 1, step):
        x, y = s[i:i + step], p[i:i + step]
        lx = 20 * np.log10(np.sqrt((x ** 2).mean()) + 1)
        ly = 20 * np.log10(np.sqrt((y ** 2).mean()) + 1)
        bx, by = bands(x, rate), bands(y, rate)
        tx, ty = sum(bx), sum(by)
        bal = ["%+5.1f" % (10 * np.log10((u / tx) / (v / ty))) for u, v in zip(bx, by)]
        if ly > 40:
            diffs.append(lx - ly)
        print("%7.2f %8.1f %6.1f %6.1f | %s" % (i / rate, lx, ly, lx - ly, " ".join(bal)))
    if diffs:
        print("loudness SNES-PC over the sounding parts: mean %+.2f dB, "
              "mean |diff| %.2f dB" % (np.mean(diffs), np.mean(np.abs(diffs))))
    if a.png:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(2, 1, figsize=(16, 8), sharex=True)
        for k, (x, name) in enumerate(((s, "SNES"), (p, "PC"))):
            ax[k].specgram(x, NFFT=1024, Fs=rate, noverlap=768, cmap="magma",
                           vmin=-20, vmax=80)
            ax[k].set_ylim(0, 8000)
            ax[k].set_ylabel(name + " Hz")
        ax[1].set_xlabel("s")
        fig.tight_layout()
        fig.savefig(a.png, dpi=80)


if __name__ == "__main__":
    main()
