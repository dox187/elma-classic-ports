"""The sounds of the game for the S-DSP: the wavs of elma.res cut, mixed
and scaled as the original mixer prepares them (SDL_HHIGH.CPP, the mixer of
the Windows version, and H_WAV.CPP), converted to BRR, and laid out in the
memory of the SPC700 with the sample directory and the parameters of the
driver (spc/driver.asm).

  gen_snd.py ELMA_RES DRIVER.bin OUTDIR

writes OUTDIR/snd.asm (the driver, the image of the sound memory and the
table of the engine's pitch) and OUTDIR/snd.inc. Also usable as a module:
pc_waves() gives the samples as the original mixer holds them.
"""

import math
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from elmadata import Resource  # noqa: E402

# The original mixer (SDL_HHIGH.CPP): the length of its cross-fades and the
# parts of harl.wav and harl2.wav that make the engine.
MIX = 100
I1, I2, I3, I4, I5 = 7526, 34648, 38766, 14490, 18906
RATE = 11025                    # every wav plays at this rate in the game

# The S-DSP plays 32000 samples a second; pitch 4096 is that rate.
DSP_RATE = 32000
PITCH1 = RATE * 4096 / DSP_RATE  # 1411.2: the original rate
# The driver's clock: timer 2 (64 kHz) divided by 50, 1280 ticks a second,
# 25 samples of the DSP each; 64 ticks are a buffer of the original mixer
# (550 samples at 11025 Hz, 49.9 ms).
TICK_SAMPLES = 25

# The memory of the SPC700 (the same as in spc/driver.asm):
DRIVER_ADDR = 0x0200
IMAGE_ADDR = 0x0600             # the directory (10 entries), then the rest
PARAMS_ADDR = 0x0628
PITCH_TAB_ADDR = 0x0640         # low bytes, then the high bytes at +256
BRR_ADDR = 0x0840
ARAM_END = 0x10000              # no echo buffer (its writes are off)
PEAK_MAX = 32000                # the loudest sample value kept
CHUNK = 255                     # bytes of the loader's chunks
PIECE_CHUNKS = 128              # chunks in a bank of the ROM (32640 bytes)

# Sample numbers of the directory (spc/driver.asm):
SRCN_START, SRCN_IDLE, SRCN_GAS, SRCN_FRIC = 0, 1, 2, 3
# The effects by the ids of the game (WAV_UTODES... in HANGHIGH.H): their
# wav, the amplitude the game normalizes them to and the rate they are kept
# at (the bright siker.wav and fordul.wav at twice the rate: at 11025 Hz the
# interpolation of the DSP dulls them, and the treble boost against that
# would bring out its images above 5.5 kHz).
EFFECTS = [
    ("utodes.wav", 0.25, RATE),     # 1 WAV_UTODES: a hit
    ("torik.wav", 0.34, RATE),      # 2 WAV_TORES: death
    ("siker.wav", 0.8, 2 * RATE),   # 3 WAV_SIKER: the flower
    ("eves.wav", 0.5, RATE),        # 4 WAV_EVES: an apple
    ("fordul.wav", 0.3, 2 * RATE),  # 5 WAV_FORDULAS: turn
    ("ugras.wav", 0.34, RATE),      # 6, 7 WAV_UGRAS1/2: volt
]
SRCN_EFFECT0 = 4


def _short(v):
    """A double stored into a short in C: truncation toward zero."""
    return np.trunc(v).astype(np.int64).clip(-32768, 32767).astype(np.int64)


def read_wav(res, name):
    """The 16-bit samples of a wav of elma.res (the game reads them so,
    whatever rate the header says)."""
    d = res.read(name)
    size = struct.unpack_from("<i", d, 40)[0]
    return np.frombuffer(d[44:44 + size], dtype="<i2").astype(np.int64)


def wav(res, name, maxamp, start=-1, end=-1, part=None):
    """wav::wav of H_WAV.CPP: a part of a file normalized so that its peak
    is 32000*maxamp. part=(a, b) cuts another range but scales it as the
    range start..end is scaled."""
    s = read_wav(res, name)
    if end <= 0:
        start, end = 0, len(s)
    peak = max(1, int(np.abs(s[start:end]).max()))
    a, b = part if part else (start, end)
    return _short(s[a:b] * (32000.0 * maxamp / peak))


def loopol(t, n):
    """wav::loopol: the start becomes a cross-fade from the last n
    samples, which are then cut."""
    t = t.copy()
    size = len(t)
    i = np.arange(n)
    arany = i / n
    t[:n] = _short(arany * t[:n] + (1 - arany) * t[size - n:])
    return t[:size - n]


def vegereilleszt(t, p, n):
    """wav::vegereilleszt: the last n samples fade from the start of t into
    the start of p (as the game does it)."""
    t = t.copy()
    size = len(t)
    i = np.arange(n)
    arany = i / n
    t[size - n:] = _short((1 - arany) * t[:n] + arany * p[:n])
    return t


def hangero(t, szorzo):
    return _short(t * szorzo)


def pc_waves(res):
    """The samples of the original mixer (starthanghigh of SDL_HHIGH.CPP):
    dict of name -> int array, the parts of the engine and the effects."""
    w = {}
    for k, (name, amp, _) in enumerate(EFFECTS):
        w["effect%d" % (k + 1)] = wav(res, name, amp)
    w["surl"] = loopol(wav(res, "dorzsol.wav", 0.44), MIX)
    b = 0.26
    w["pw1"] = wav(res, "harl.wav", b, 0, I1 + MIX)
    pw2 = loopol(wav(res, "harl.wav", b, I1, I2), MIX)
    pw3 = wav(res, "harl.wav", b, I2 - MIX, I3)
    pw4 = loopol(wav(res, "harl2.wav", b, I4, I5), MIX)
    w["pw3"] = vegereilleszt(pw3, pw4, MIX)
    w["pw4"] = pw4
    w["pw2"] = hangero(pw2, 0.4)
    return w


def _loop_cut(length):
    """The length of the cross-fade of a loop near MIX that leaves a loop
    of whole BRR blocks."""
    for d in range(16):
        for n in (MIX - d, MIX + d):
            if n > 0 and (length - n) % 16 == 0:
                return n
    raise AssertionError


def snes_samples(res, emphasize=True):
    """The samples for the S-DSP, each a whole number of 16-sample blocks:
    list of (srcn, name, data, loop_start or None, entry points of other
    sample numbers {srcn: offset}, rate) and the parameters of the
    driver. emphasize: against the interpolation of the DSP."""
    b = 0.26
    out = []
    h = emphasis(RATE) if emphasize else np.array([1.0])

    def looped(intro, loop):
        # The intro runs into the loop, the loop into itself:
        return np.concatenate([filtered(intro, h, None, loop),
                               filtered(loop, h, loop, loop)])

    # The start of the engine and its idle loop in one: Pw1 runs into the
    # idle loop where the game continues it (Pw2 from MIX). The loop is
    # Pw2 turned so that it starts there; the cross-fade of the loop is a
    # few samples longer or shorter than MIX for whole blocks.
    n2 = _loop_cut(I2 - I1)
    pw2 = loopol(wav(res, "harl.wav", b, I1, I2), n2)
    pw2 = hangero(pw2, 0.4)
    loop2 = np.concatenate([pw2[n2:], pw2[:n2]])
    intro = wav(res, "harl.wav", b, 0, I1 + MIX, part=(0, I1 + n2))
    trim = len(intro) % 16      # leading silence of harl.wav
    intro = intro[trim:]
    # Where the game enters the idle loop after the gas (Pw2 from 0): the
    # block nearest to it.
    idle_at = len(intro) + int(round((len(loop2) - n2) / 16.0)) * 16 % len(loop2)
    out.append((SRCN_START, "start", looped(intro, loop2), len(intro),
                {SRCN_IDLE: idle_at}, RATE))
    # The gas: Pw3, then the loop of Pw4 from MIX on, where the game starts
    # it. Pw3 starts a few samples earlier for whole blocks.
    n4 = _loop_cut(I5 - I4)
    pw4 = loopol(wav(res, "harl2.wav", b, I4, I5), n4)
    loop4 = np.concatenate([pw4[MIX:], pw4[:MIX]])
    early = (-(I3 - (I2 - MIX))) % 16
    pw3 = wav(res, "harl.wav", b, I2 - MIX, I3, part=(I2 - MIX - early, I3))
    pw3 = vegereilleszt(pw3, pw4, MIX)
    out.append((SRCN_GAS, "gas", looped(pw3, loop4), len(pw3), {}, RATE))
    # The friction loop:
    s = wav(res, "dorzsol.wav", 0.44)
    s = loopol(s, _loop_cut(len(s)))
    out.append((SRCN_FRIC, "fric", filtered(s, h, s, s), 0, {}, RATE))
    # The effects, with a block of silence at the end (the DSP mutes a
    # sample as soon as it reaches its last block).
    for k, (name, amp, rate) in enumerate(EFFECTS):
        s = wav(res, name, amp).astype(float)
        if rate != RATE:
            s = resample(s, rate / RATE)
        s = np.concatenate([s, np.zeros((-len(s)) % 16 + 16)])
        if emphasize:
            s = filtered(s, emphasis(rate))
        out.append((SRCN_EFFECT0 + k, name[:-4], s, None, {}, rate))
    # Whole numbers, in the range of the BRR (a sample louder than that is
    # turned down):
    samples = []
    for srcn, name, data, loop, entries, rate in out:
        data = np.asarray(data, float)
        peak = np.abs(data).max()
        scale = min(1.0, PEAK_MAX / peak) if peak else 1.0
        data = np.round(data * scale).astype(np.int64)
        samples.append((srcn, name, data, loop, entries, rate, scale))
    pitch1 = int(round(PITCH1))
    params = {
        # Ticks from the key-on of the start to the end of Pw1 (counted from
        # the tick of the key-on itself), and of the gas to the end of Pw3
        # (counted from the next), the 5 samples of the key-on included:
        "intro_ticks": int(math.ceil((len(intro) * 4096 / pitch1 + 5)
                                     / TICK_SAMPLES)) + 1,
        "pw3_ticks": int(math.ceil((len(pw3) * 4096 / pitch1 + 5)
                                   / TICK_SAMPLES)),
        "pitch1": pitch1,
        "effect_pitch": [int(round(rate * 4096 / DSP_RATE))
                         for _, _, rate in EFFECTS],
    }
    return samples, params


# The interpolation of the S-DSP -----------------------------------------------

# The Gaussian interpolation of the S-DSP (its 512 coefficients, as the
# emulators have them from the hardware): it dulls a sample of 11025 Hz
# (-4 dB at 2.8 kHz, -10 dB at 4.4 kHz). The samples get the opposite
# before they are converted, so that they sound as the game plays them.
GAUSS = [
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2,
    2, 2, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 5, 5, 5, 5,
    6, 6, 6, 6, 7, 7, 7, 8, 8, 8, 9, 9, 9, 10, 10, 10,
    11, 11, 11, 12, 12, 13, 13, 14, 14, 15, 15, 15, 16, 16, 17, 17,
    18, 19, 19, 20, 20, 21, 21, 22, 23, 23, 24, 24, 25, 26, 27, 27,
    28, 29, 29, 30, 31, 32, 32, 33, 34, 35, 36, 36, 37, 38, 39, 40,
    41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56,
    58, 59, 60, 61, 62, 64, 65, 66, 67, 69, 70, 71, 73, 74, 76, 77,
    78, 80, 81, 83, 84, 86, 87, 89, 90, 92, 94, 95, 97, 99, 100, 102,
    104, 106, 107, 109, 111, 113, 115, 117, 118, 120, 122, 124, 126, 128, 130, 132,
    134, 137, 139, 141, 143, 145, 147, 150, 152, 154, 156, 159, 161, 163, 166, 168,
    171, 173, 175, 178, 180, 183, 186, 188, 191, 193, 196, 199, 201, 204, 207, 210,
    212, 215, 218, 221, 224, 227, 230, 233, 236, 239, 242, 245, 248, 251, 254, 257,
    260, 263, 267, 270, 273, 276, 280, 283, 286, 290, 293, 297, 300, 304, 307, 311,
    314, 318, 321, 325, 328, 332, 336, 339, 343, 347, 351, 354, 358, 362, 366, 370,
    374, 378, 381, 385, 389, 393, 397, 401, 405, 410, 414, 418, 422, 426, 430, 434,
    439, 443, 447, 451, 456, 460, 464, 469, 473, 477, 482, 486, 491, 495, 499, 504,
    508, 513, 517, 522, 527, 531, 536, 540, 545, 550, 554, 559, 563, 568, 573, 577,
    582, 587, 592, 596, 601, 606, 611, 615, 620, 625, 630, 635, 640, 644, 649, 654,
    659, 664, 669, 674, 678, 683, 688, 693, 698, 703, 708, 713, 718, 723, 728, 732,
    737, 742, 747, 752, 757, 762, 767, 772, 777, 782, 787, 792, 797, 802, 806, 811,
    816, 821, 826, 831, 836, 841, 846, 851, 855, 860, 865, 870, 875, 880, 884, 889,
    894, 899, 904, 908, 913, 918, 923, 927, 932, 937, 941, 946, 951, 955, 960, 965,
    969, 974, 978, 983, 988, 992, 997, 1001, 1005, 1010, 1014, 1019, 1023, 1027, 1032, 1036,
    1040, 1045, 1049, 1053, 1057, 1061, 1066, 1070, 1074, 1078, 1082, 1086, 1090, 1094, 1098, 1102,
    1106, 1109, 1113, 1117, 1121, 1125, 1128, 1132, 1136, 1139, 1143, 1146, 1150, 1153, 1157, 1160,
    1164, 1167, 1170, 1174, 1177, 1180, 1183, 1186, 1190, 1193, 1196, 1199, 1202, 1205, 1207, 1210,
    1213, 1216, 1219, 1221, 1224, 1227, 1229, 1232, 1234, 1237, 1239, 1241, 1244, 1246, 1248, 1251,
    1253, 1255, 1257, 1259, 1261, 1263, 1265, 1267, 1269, 1270, 1272, 1274, 1275, 1277, 1279, 1280,
    1282, 1283, 1284, 1286, 1287, 1288, 1290, 1291, 1292, 1293, 1294, 1295, 1296, 1297, 1297, 1298,
    1299, 1300, 1300, 1301, 1302, 1302, 1303, 1303, 1303, 1304, 1304, 1304, 1304, 1304, 1305, 1305,
]


def gauss_response(f, pitch):
    """The gain of the interpolation at f (cycles per sample of the source)
    for a sample played at pitch (4096: one sample per output sample)."""
    g = GAUSS
    offs = range(0, 256, 4) if pitch % 4096 else (0,)
    acc = 0
    for off in offs:
        w = np.array([g[255 - off], g[511 - off], g[256 + off], g[off]]) / 2048.0
        pos = np.array([-1, 0, 1, 2]) - off / 256.0
        acc = acc + np.sum(w[None, :] * np.exp(-2j * np.pi * f[:, None] * pos[None, :]),
                           axis=1)
    return np.abs(acc / len(offs))


def emphasis(rate, taps=11, maxboost_db=10.0):
    """A symmetric FIR for samples of rate: the inverse of the
    interpolation up to 5 kHz (the band of the original's 11025 Hz)."""
    f = np.linspace(0, 0.5, 1024)
    t = np.minimum(1 / gauss_response(f, rate * 4096 / DSP_RATE),
                   10 ** (maxboost_db / 20))
    hz = f * rate
    w = np.where(hz <= 5000, 1.0, np.where(hz <= RATE / 2, 0.3, 0.01))
    m = (taps - 1) // 2
    a = np.concatenate([np.ones((len(f), 1)), 2 * np.cos(
        2 * np.pi * f[:, None] * np.arange(1, m + 1)[None, :])], axis=1)
    c = np.linalg.lstsq(a * w[:, None], t * w, rcond=None)[0]
    return np.concatenate([c[:0:-1], c])


def filtered(x, h, before=None, after=None):
    """x filtered by the symmetric FIR h (no delay): before/after are the
    samples around x (zeros if None); a loop gets its own end and start."""
    m = len(h) // 2
    z = np.zeros(m)
    pre = z if before is None else np.asarray(before[-m:], float)
    post = z if after is None else np.asarray(after[:m], float)
    y = np.convolve(np.concatenate([pre, x, post]), h, mode="valid")
    return y


def resample(x, ratio):
    """Band-limited resampling by ratio (new rate / old rate)."""
    n = len(x)
    m = int(round(n * ratio))
    spec = np.fft.rfft(np.concatenate([x, x[::-1]]).astype(float))
    out = np.zeros(m + 1, dtype=complex)
    k = min(len(spec), len(out))
    out[:k] = spec[:k]
    return np.fft.irfft(out, 2 * m)[:m] * (m / n)


# BRR -----------------------------------------------------------------------

def _clamp16(v):
    return np.clip(v, -32768, 32767)


def _wrap16(v):
    return ((v + 32768) & 0xFFFF) - 32768


def brr_decode_sample(n, shift, filt, p1, p2):
    """One sample as the S-DSP decodes it (blargg's SPC_DSP): n the nibble,
    p1 and p2 the last two decoded samples. Works on numpy arrays."""
    s = (n << shift) >> 1
    if shift >= 13:
        s = np.where(n < 0, -2048, 0)
    q2 = p2 >> 1
    if filt == 1:
        s = s + (p1 >> 1) + ((-p1) >> 5)
    elif filt == 2:
        s = s + p1 - q2 + (q2 >> 4) + ((p1 * -3) >> 6)
    elif filt == 3:
        s = s + p1 - q2 + ((p1 * -13) >> 7) + ((q2 * 3) >> 4)
    return _wrap16(_clamp16(s) * 2)


def brr_encode(x, loop_start=None, filter0=()):
    """BRR of the samples x (a multiple of 16): each block with the filter
    and shift of the least error, decoded as the DSP does. filter0: blocks
    that must not depend on the samples before them (entry points, the
    loop). Returns the bytes and the decoded samples."""
    x = np.asarray(x, dtype=np.int64)
    nblocks = len(x) // 16
    must0 = set(filter0)
    if loop_start is not None:
        must0.add(loop_start // 16)
    must0.add(0)
    combos = [(f, sh) for f in range(4) for sh in range(13)]
    filt_all = np.array([c[0] for c in combos])
    shift_all = np.array([c[1] for c in combos])
    out = bytearray()
    dec = np.zeros(len(x), dtype=np.int64)
    p1 = p2 = 0
    for b in range(nblocks):
        target = x[b * 16:(b + 1) * 16]
        sel = filt_all == 0 if b in must0 else np.ones(len(combos), bool)
        fs, shs = filt_all[sel], shift_all[sel]
        k = len(fs)
        q1 = np.full(k, p1, dtype=np.int64)
        q2 = np.full(k, p2, dtype=np.int64)
        err = np.zeros(k)
        nib = np.zeros((k, 16), dtype=np.int64)
        outs = np.zeros((k, 16), dtype=np.int64)
        for i in range(16):
            # The prediction of each filter from the history:
            r2 = q2 >> 1
            pred = np.where(fs == 0, 0, np.where(
                fs == 1, (q1 >> 1) + ((-q1) >> 5), np.where(
                    fs == 2, q1 - r2 + (r2 >> 4) + ((q1 * -3) >> 6),
                    q1 - r2 + ((q1 * -13) >> 7) + ((r2 * 3) >> 4))))
            want = target[i] / 2.0 - pred
            n = np.clip(np.round(want * 2.0 / (1 << shs)), -8, 7).astype(np.int64)
            s = ((n << shs) >> 1) + pred
            d = _wrap16(_clamp16(s) * 2)
            e = (d - target[i]).astype(np.float64)
            err += e * e
            nib[:, i] = n
            outs[:, i] = d
            q2, q1 = q1, d
        j = int(np.argmin(err))
        f, sh = int(fs[j]), int(shs[j])
        last = b == nblocks - 1
        hdr = (sh << 4) | (f << 2) | (2 if last and loop_start is not None
                                       else 0) | (1 if last else 0)
        out.append(hdr)
        for i in range(0, 16, 2):
            out.append(((int(nib[j, i]) & 15) << 4) | (int(nib[j, i + 1]) & 15))
        dec[b * 16:(b + 1) * 16] = outs[j]
        p1, p2 = int(outs[j, 15]), int(outs[j, 14])
    return bytes(out), dec


def brr_decode(data, loop_offset=None, count=None):
    """Decodes BRR (a check of brr_encode)."""
    out = []
    p1 = p2 = 0
    pos = 0
    while pos + 9 <= len(data):
        hdr = data[pos]
        sh, f = hdr >> 4, (hdr >> 2) & 3
        for i in range(16):
            byte = data[pos + 1 + i // 2]
            n = (byte >> 4) if i % 2 == 0 else (byte & 15)
            n = n - 16 if n >= 8 else n
            d = int(brr_decode_sample(np.int64(n), sh, f, np.int64(p1),
                                      np.int64(p2)))
            out.append(d)
            p2, p1 = p1, d
        pos += 9
        if hdr & 1:
            break
    return np.array(out[:count] if count else out, dtype=np.int64)


# The image -----------------------------------------------------------------

def omega_table():
    """The table of the 65816: |omega| of the wheel (rad per time unit of
    the game, 8.8) >> 6 -> the engine's pitch index v, 0..255, the game's
    2 - exp(-0.025*|omega|) being 1 + v/255 (LEJATSZO.CPP)."""
    t = []
    for i in range(1024):
        x = 0.025 * (i / 4.0)
        t.append(int(round(255 * (1 - math.exp(-min(x, 30.0))))))
    return t


def pitch_table(pitch1):
    """The DSP pitch of the gas loop at each index of omega_table."""
    return [int(round(PITCH1 * (1 + v / 255.0))) for v in range(256)]


def build_image(res, emphasize=True):
    """The image of the sound memory from IMAGE_ADDR: the directory, the
    parameters, the pitch table and the BRR samples. Returns the image and
    a description."""
    samples, params = snes_samples(res, emphasize)
    brr = bytearray()
    dirs = {}
    info = []
    for srcn, name, data, loop, entries, rate, scale in samples:
        filter0 = [off // 16 for off in entries.values()]
        enc, dec = brr_encode(data, loop, filter0)
        addr = BRR_ADDR + len(brr)
        loop_addr = addr + (loop // 16) * 9 if loop is not None else addr
        dirs[srcn] = (addr, loop_addr)
        for e, off in entries.items():
            dirs[e] = (addr + (off // 16) * 9, loop_addr)
        err = dec - data
        snr = 10 * math.log10(max(1e-9, float(np.mean(data.astype(float) ** 2)))
                              / max(1e-9, float(np.mean(err.astype(float) ** 2))))
        info.append((srcn, name, len(data), len(enc), addr, loop, snr, rate,
                     scale))
        brr += enc
    end = BRR_ADDR + len(brr)
    if end > ARAM_END:
        raise SystemExit("the sounds do not fit in the sound memory: %04X" % end)
    img = bytearray(BRR_ADDR - IMAGE_ADDR)
    for srcn, (a, l) in dirs.items():
        struct.pack_into("<HH", img, srcn * 4, a, l)
    struct.pack_into("<HHH", img, PARAMS_ADDR - IMAGE_ADDR, params["intro_ticks"],
                     params["pw3_ticks"], params["pitch1"])
    for k, p in enumerate(params["effect_pitch"]):
        struct.pack_into("<H", img, PARAMS_ADDR - IMAGE_ADDR + 6 + 2 * k, p)
    for v, p in enumerate(pitch_table(params["pitch1"])):
        img[PITCH_TAB_ADDR - IMAGE_ADDR + v] = p & 0xFF
        img[PITCH_TAB_ADDR - IMAGE_ADDR + 256 + v] = p >> 8
    img += brr
    img += bytes((-len(img)) % CHUNK)
    if IMAGE_ADDR + len(img) > ARAM_END:
        raise SystemExit("the sounds do not fit in the sound memory")
    return bytes(img), {"samples": info, "params": params, "dirs": dirs,
                        "end": end}


def write_asm(path_asm, path_inc, driver, img):
    pieces = [img[i:i + CHUNK * PIECE_CHUNKS]
              for i in range(0, len(img), CHUNK * PIECE_CHUNKS)]
    with open(path_asm, "w") as f:
        f.write("; Generated by tools/gen_snd.py from elma.res: do not edit.\n")
        f.write('.include "hdr.asm"\n\n')
        f.write('.SECTION "snd_driver" SUPERFREE\nsnd_driver:\n')
        _db(f, driver)
        f.write(".ENDS\n\n")
        for k, p in enumerate(pieces):
            f.write('.SECTION "snd_image%d" SUPERFREE\nsnd_image%d:\n' % (k, k))
            _db(f, p)
            f.write(".ENDS\n\n")
        f.write('.SECTION "snd_tables" SUPERFREE\n')
        f.write("; The pieces of the image: address (24 bits), chunks (16 bits).\n")
        f.write("snd_pieces:\n")
        for k, p in enumerate(pieces):
            f.write("\t.dl snd_image%d\n\t.dw %d\n" % (k, len(p) // CHUNK))
        f.write("; |omega| >> 6 -> the pitch index of the engine.\n")
        f.write("snd_omega_tab:\n")
        _db(f, bytes(omega_table()))
        f.write(".ENDS\n")
    with open(path_inc, "w") as f:
        f.write("; Generated by tools/gen_snd.py: do not edit.\n")
        f.write(".DEFINE SND_DRIVER_SIZE %d\n" % len(driver))
        f.write(".DEFINE SND_DRIVER_ADDR $%04X\n" % DRIVER_ADDR)
        f.write(".DEFINE SND_IMAGE_CHUNKS %d\n" % (len(img) // CHUNK))
        f.write(".DEFINE SND_PIECES %d\n" % len(pieces))


def _db(f, data):
    for i in range(0, len(data), 16):
        f.write("\t.db " + ",".join("$%02X" % b for b in data[i:i + 16]) + "\n")


def main():
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    res = Resource(sys.argv[1])
    driver = open(sys.argv[2], "rb").read()
    if DRIVER_ADDR + len(driver) > IMAGE_ADDR:
        raise SystemExit("the driver is too long: %d bytes" % len(driver))
    out = sys.argv[3]
    img, desc = build_image(res)
    write_asm(os.path.join(out, "snd.asm"), os.path.join(out, "snd.inc"),
              driver, img)
    with open(os.path.join(out, "snd_image.bin"), "wb") as f:
        f.write(img)
    print("sound: driver %d bytes at $%04X, samples $%04X-$%04X, %d bytes "
          "of %d free" % (len(driver), DRIVER_ADDR, BRR_ADDR, desc["end"] - 1,
                          ARAM_END - desc["end"], ARAM_END - BRR_ADDR))
    for srcn, name, n, size, addr, loop, snr, rate, scale in desc["samples"]:
        print("  %d %-7s %5d Hz %6d samples %6d bytes at $%04X%s, SNR %.1f dB%s"
              % (srcn, name, rate, n, size, addr,
                 "" if loop is None else " loop %d" % loop, snr,
                 "" if scale == 1 else ", turned down %.2f dB"
                 % (20 * math.log10(scale))))
    print("  ticks: intro %(intro_ticks)d, gas start %(pw3_ticks)d" % desc["params"])


if __name__ == "__main__":
    main()
