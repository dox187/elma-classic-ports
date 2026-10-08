"""The mixer of the original game (desktop/F_SDL/SDL_HHIGH.CPP, from
F_WIN/W_HHIGH.CPP) in Python, to compare the SNES sounds with: the engine,
the friction and the effects mixed into buffers of 550 samples at 11025 Hz,
with the arithmetic of the C code.

  snd_pcmix.py ELMA_RES OUT.wav [--rate R]

mixes the sequence of test/snes_snd.c (as the game would play it) into
OUT.wav, at 11025 Hz or resampled to R (an ideal resampler, as SDL's).
"""

import argparse
import math
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))
import gen_snd  # noqa: E402
from elmadata import Resource  # noqa: E402

MIX = gen_snd.MIX
RATE = gen_snd.RATE
BUFFER = 550            # SDL_SOUND.CPP: blocks of 1100 bytes
A_INDIT, A_ALACSONY, A_ATMENETBE, A_ATMENET, A_MAGAS = range(5)


def s16(v):
    """A value stored into a short (C on two's complement)."""
    return ((int(v) + 32768) & 0xFFFF) - 32768


def s16d(v):
    """A double stored into a short: truncation, then the wrap."""
    return s16(math.trunc(v))


class Wav2:
    """wav2: linear interpolation over a loop, the position 16.16."""

    def __init__(self, t):
        self.t = [int(v) for v in t]
        n = len(self.t)
        self.m = [s16(self.t[(i + 1) % n] - self.t[i]) for i in range(n)]
        self.size = n * 65536
        self.pos = 0

    def reset(self, phase=-1):
        self.pos = 0 if phase < 0 else phase * 65536

    def next(self, dt):
        self.pos = (self.pos + dt) & 0xFFFFFFFF
        if self.pos >= self.size:
            self.pos -= self.size
        hi, lo = self.pos >> 16, self.pos & 0xFFFF
        return s16(self.t[hi] + ((self.m[hi] * lo) >> 16))


class Mixer:
    def __init__(self, res):
        w = gen_snd.pc_waves(res)
        self.pw1, self.pw2, self.pw3 = (list(map(int, w[k])) for k in ("pw1", "pw2", "pw3"))
        self.pw42 = Wav2(w["pw4"])
        self.surl = list(map(int, w["surl"]))
        self.bank = {k: list(map(int, w["effect%d" % k])) for k in range(1, 7)}
        self.bank[7] = self.bank[6]
        self.mute = False
        self.jarmotor = False
        self.allapot = A_INDIT
        self.gaz = 0
        self.most = self.kell = 1.0
        self.i_indit = self.i_alacsony = self.i_atmenet = 0
        self.surl_most = self.surl_kell = 0.0
        self.surltart = 0
        self.waves = []            # [samples, position, volume]

    # The interface of the game (HANGHIGH.H):
    def startmotor(self):
        self.jarmotor = True
        self.allapot = A_INDIT
        self.i_indit = 0
        self.most = self.kell = 1.0

    def stopmotor(self):
        self.jarmotor = False
        self.allapot = A_INDIT
        self.i_indit = 0
        self.most = self.kell = 1.0

    def setmotor(self, frekvencia, gaz):
        self.gaz = gaz
        if frekvencia > 2.0:
            frekvencia = 2.0
        if frekvencia < 1.0:
            frekvencia = 0.0
        self.kell = frekvencia

    def setsurlodas(self, ero):
        self.surl_kell = min(1.0, max(0.0, ero))

    def startwave(self, wid, hangero):
        if self.mute or len(self.waves) >= 5:
            return
        self.waves.append([self.bank[wid], 0, int(hangero * 65536.0)])

    # The mixer:
    def _motor(self, sb, n):
        if not self.jarmotor:
            return
        pw1, pw2, pw3 = self.pw1, self.pw2, self.pw3
        counter = 0
        while True:
            if self.allapot == A_INDIT:
                if self.i_indit + n > len(pw1):
                    k = len(pw1) - self.i_indit
                    for i in range(k):
                        sb[counter + i] = s16(sb[counter + i] + pw1[self.i_indit + i])
                    counter += k
                    self.allapot = A_ALACSONY
                    self.i_alacsony = MIX
                else:
                    k = n - counter
                    for i in range(k):
                        sb[counter + i] = s16(sb[counter + i] + pw1[self.i_indit + i])
                    self.i_indit += k
                    return
            elif self.allapot == A_ALACSONY:
                if self.gaz:
                    self.allapot = A_ATMENETBE
                    self.i_atmenet = 0
                else:
                    k = n - counter
                    if k > len(pw2) - self.i_alacsony:
                        k = len(pw2) - self.i_alacsony
                        for i in range(k):
                            sb[counter + i] = s16(sb[counter + i] + pw2[self.i_alacsony + i])
                        counter += k
                        self.i_alacsony = 0
                    else:
                        for i in range(k):
                            sb[counter + i] = s16(sb[counter + i] + pw2[self.i_alacsony + i])
                        self.i_alacsony += k
                        return
            elif self.allapot == A_ATMENETBE:
                k = n - counter
                last = self.i_atmenet + k
                if last > MIX:
                    last = MIX
                    self.allapot = A_ATMENET
                nov = 0
                for i in range(self.i_atmenet, last):
                    if self.i_alacsony >= len(pw2):
                        self.i_alacsony = 0
                    a = i * (1.0 / MIX)
                    sb[counter + nov] = s16d(sb[counter + nov] + a * pw3[i]
                                             + (1 - a) * pw2[self.i_alacsony])
                    self.i_alacsony += 1
                    nov += 1
                counter += nov
                self.i_atmenet += nov
                if counter + nov == n:
                    return
            elif self.allapot == A_ATMENET:
                k = n - counter
                if k > len(pw3) - self.i_atmenet:
                    k = len(pw3) - self.i_atmenet
                    for i in range(k):
                        sb[counter + i] = s16(sb[counter + i] + pw3[self.i_atmenet + i])
                    counter += k
                    self.allapot = A_MAGAS
                    self.pw42.reset(MIX)
                    self.most = 1.0
                else:
                    for i in range(k):
                        sb[counter + i] = s16(sb[counter + i] + pw3[self.i_atmenet + i])
                    self.i_atmenet += k
                    return
            else:   # A_MAGAS
                k = n - counter
                if not self.gaz and k > MIX:
                    self.allapot = A_ALACSONY
                    self.i_alacsony = MIX
                    dt = int(65536.0 * self.most)
                    for i in range(MIX):
                        g = self.pw42.next(dt)
                        alap = i / MIX
                        sb[counter + i] = s16d(sb[counter + i] + alap * pw2[i]
                                               + (1.0 - alap) * g)
                    counter += MIX
                else:
                    dt = int(65536.0 * self.most)
                    dtkell = int(65536.0 * self.kell)
                    ddt = math.trunc((dtkell - dt) / k) if k > 30 else 0
                    for i in range(k):
                        sb[counter + i] = s16(sb[counter + i] + self.pw42.next(dt))
                        dt += ddt
                    self.most = dt / 65536.0
                    return

    def _surl(self, sb, n):
        if self.surl_kell < 0.1 and self.surl_most < 0.1:
            self.surl_most = 0.0
            return
        most = int(65536.0 * self.surl_most)
        kell = int(65536.0 * self.surl_kell)
        d = math.trunc((kell - most) / n)
        size = len(self.surl)
        for i in range(n):
            v = self.surl[self.surltart] * most
            self.surltart += 1
            if self.surltart >= size:
                self.surltart = 0
            sb[i] = s16(sb[i] + (v >> 16))
            most += d
        self.surl_most = most / 65536.0

    def callback(self, n=BUFFER):
        sb = [0] * n
        if self.mute:
            self.waves = []
            return sb
        self._motor(sb, n)
        self._surl(sb, n)
        left = []
        for w in self.waves:
            t, pos, vol = w
            k = min(n, len(t) - pos)
            for i in range(k):
                sb[i] = s16(sb[i] + s16((t[pos + i] * vol) >> 16))
            w[1] = pos + k
            if w[1] < len(t):
                left.append(w)
        self.waves = left
        return sb


# The sequence of test/snes_snd.c --------------------------------------------

FPS = 60.0988           # NTSC
T_GAS1, T_IDLE2, T_GAS2, T_FRIC, T_FRICTOP, T_FRICEND = 90, 270, 390, 510, 600, 690
T_EFFECTS, T_BURST, T_STOP, T_AGAIN, T_STOP2 = 700, 1100, 1160, 1220, 1300
EFFECTS = [(4, 253), (1, 64), (1, 250), (5, 253), (6, 253), (7, 253), (3, 255),
           (2, 255)]


def frekvencia(omega88):
    """The game's 2 - exp(-0.025*|omega|) (LEJATSZO.CPP), omega in 8.8."""
    x = min(30.0, abs(omega88) / 256.0 * 0.025)
    return 2.0 - math.exp(-x)


def sequence_frame(f):
    """What test/snes_snd.c does at frame f: (calls, effects); calls is
    None for snd_stop, else (gas, omega 8.8, friction 8.8)."""
    gas, omega, fric = 0, 0, 0
    if f < T_GAS1:
        pass
    elif f < T_IDLE2:
        gas, omega = 1, (f - T_GAS1) * 284
    elif f < T_GAS2:
        pass
    elif f < T_FRIC:
        gas, omega = 1, 50 * 256
    elif f < T_FRICEND:
        fric = (f - T_FRIC) * 4 if f < T_FRICTOP else (T_FRICEND - f) * 4
    if T_STOP <= f < T_AGAIN or f >= T_STOP2:
        return (None if f in (T_STOP, T_STOP2) else "idle"), []
    eff = []
    if T_EFFECTS <= f < T_EFFECTS + 8 * 50 and (f - T_EFFECTS) % 50 == 0:
        eff.append(EFFECTS[(f - T_EFFECTS) // 50])
    if f == T_BURST:
        eff += [(1, 200)] * 7
    return (gas, omega, fric), eff


def mix_sequence(res, frames=T_STOP2 + 20):
    """The sequence as the game plays it: the state of each frame is seen
    by the next buffer of the mixer, the effects start with it."""
    m = Mixer(res)
    out = []
    running = False
    pending = []
    state = None
    f = 0
    nbuf = int(math.ceil(frames / FPS * RATE / BUFFER))
    for b in range(nbuf):
        t = b * BUFFER / RATE
        while f / FPS <= t and f < frames:
            call, eff = sequence_frame(f)
            if call is None:
                m.stopmotor()
                m.mute = True
                running = False
                pending = []
            elif call != "idle":
                if not running:
                    m.mute = False
                    m.startmotor()
                    running = True
                state = call
                pending += eff
            f += 1
        if running and state:
            gas, omega, fric = state
            m.setsurlodas(fric / 256.0)
            m.setmotor(frekvencia(omega), gas)
            for wid, vol in pending:
                m.startwave(wid, vol / 256.0)
        pending = []
        out += m.callback()
    return np.array(out, dtype=np.int16)


def write_wav(path, data, rate):
    data = np.asarray(data, dtype="<i2")
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 36 + 2 * len(data)) + b"WAVEfmt ")
        f.write(struct.pack("<IHHIIHH", 16, 1, 1, rate, 2 * rate, 2, 16))
        f.write(b"data" + struct.pack("<I", 2 * len(data)))
        f.write(data.tobytes())


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("res")
    ap.add_argument("out")
    ap.add_argument("--rate", type=int, default=RATE)
    a = ap.parse_args()
    data = mix_sequence(Resource(a.res))
    if a.rate != RATE:
        data = np.clip(np.round(gen_snd.resample(data.astype(float), a.rate / RATE)),
                       -32768, 32767)
    write_wav(a.out, data, a.rate)


if __name__ == "__main__":
    main()
