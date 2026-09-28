"""雅楽風の楽器と効果音（NumPy で合成、外部素材なし）。平等院鳳凰堂の作品（aiimpl/byodoin, MIT）の音から写したもの。"""


import numpy as np
from scipy.signal import butter, sosfilt

SR = 48000
rng = np.random.default_rng(3)


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def bp(x, lo, hi, order=2):
    sos = butter(order, [lo, hi], btype='band', fs=SR, output='sos')
    return sosfilt(sos, x)


def lp(x, fc, order=2):
    return sosfilt(butter(order, fc, btype='low', fs=SR, output='sos'), x)


def hp(x, fc, order=2):
    return sosfilt(butter(order, fc, btype='high', fs=SR, output='sos'), x)


def env_adsr(n, a, d, s, r, sustain=0.8):
    e = np.ones(n) * sustain
    A, D, R = int(a * SR), int(d * SR), int(r * SR)
    A = min(A, n)
    e[:A] = np.linspace(0, 1, A)
    D2 = min(D, n - A)
    e[A:A + D2] = np.linspace(1, sustain, D2)
    if R > 0 and R < n:
        e[-R:] *= np.linspace(1, 0, R)
    return e


# 笙：合竹（和音）を息の強弱でふくらませる。自由リードの倍音
def sho_chord(notes, dur, att=1.2, rel=1.2):
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for k, m in enumerate(notes):
        f = midi(m) * (1 + rng.uniform(-0.0015, 0.0015))
        ph = rng.uniform(0, 6.28)
        for h in range(1, 10):
            amp = (1 / h ** 1.15) * (1.25 if h % 2 == 1 else 0.8)
            if f * h > 9000:
                break
            out += amp * np.sin(2 * np.pi * f * h * t + ph * h) * (1 + 0.03 * np.sin(2 * np.pi * (0.3 + 0.1 * k) * t))
    breath = 0.65 + 0.35 * np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 0.7
    out *= env_adsr(n, att, 0.1, 1.0, rel, 1.0) * breath
    out += 0.02 * bp(rng.standard_normal(n), 800, 4000) * env_adsr(n, att, 0.1, 1.0, rel, 1.0)
    return out / len(notes)


# 篳篥：鼻にかかった太い音。音の入りを下からずり上げる（塩梅）
def hichiriki(seq, t0):
    """seq=[(midi, dur), ...]"""
    total = sum(d for _, d in seq)
    n = int(total * SR)
    f = np.zeros(n)
    amp = np.zeros(n)
    i = 0
    prev = seq[0][0] - 2
    for m, d in seq:
        k = int(d * SR)
        tt = np.arange(k) / SR
        # 塩梅：前の音（か少し下）から目的の音へゆっくり
        start = midi(prev if prev != m else m - 1)
        target = midi(m)
        glide = np.clip(tt / 0.28, 0, 1) ** 0.6
        fk = start + (target - start) * glide
        fk *= 1 + 0.004 * np.sin(2 * np.pi * 5.2 * tt) * np.clip((tt - 0.4) / 0.4, 0, 1)
        f[i:i + k] = fk
        a = np.clip(tt / 0.08, 0, 1) * (0.85 + 0.15 * np.sin(np.pi * tt / d)) * np.clip((d - tt) / 0.06, 0, 1)
        amp[i:i + k] = a
        i += k
        prev = m
    ph = 2 * np.pi * np.cumsum(f) / SR
    sig = np.zeros(n)
    for h in range(1, 26):
        fh = f * h
        # フォルマント：1.1kHz と 2.6kHz あたりを強く
        g = (1 / h) * (1 + 2.2 * np.exp(-((fh - 1100) / 380) ** 2) + 1.3 * np.exp(-((fh - 2600) / 600) ** 2))
        g = np.where(fh < 11000, g, 0)
        sig += g * np.sin(h * ph)
    sig *= amp
    sig += 0.03 * bp(rng.standard_normal(n), 1500, 5000) * amp
    return sig


# 龍笛：息まじりの高い笛。装飾の小さな上下
def ryuteki(seq, t0):
    total = sum(d for _, d in seq)
    n = int(total * SR)
    f = np.zeros(n)
    amp = np.zeros(n)
    i = 0
    for m, d in seq:
        k = int(d * SR)
        tt = np.arange(k) / SR
        fk = midi(m) * (1 + 0.006 * np.sin(2 * np.pi * 5.8 * tt) * np.clip((tt - 0.25) / 0.3, 0, 1))
        # 打ち指の小さな跳ね
        fk *= np.where(tt < 0.06, 2 ** (2 / 12), 1.0)
        f[i:i + k] = fk
        amp[i:i + k] = np.clip(tt / 0.05, 0, 1) * np.clip((d - tt) / 0.08, 0, 1) * (0.8 + 0.2 * np.sin(np.pi * tt / d))
        i += k
    ph = 2 * np.pi * np.cumsum(f) / SR
    sig = np.sin(ph) + 0.22 * np.sin(2 * ph) + 0.06 * np.sin(3 * ph)
    noise = rng.standard_normal(n)
    breath = np.zeros(n)
    # 息の音：その音程のまわりだけ
    breath = bp(noise, 1800, 7000) * 0.18
    return (sig + breath) * amp


# 楽太鼓と鉦鼓
def taiko(strength=1.0, low=58):
    n = int(1.8 * SR)
    t = np.arange(n) / SR
    f = low * (1 + 0.6 * np.exp(-t * 18))
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-t * 2.6) + 0.35 * np.sin(1.6 * ph) * np.exp(-t * 5)
    hit = lp(rng.standard_normal(n), 900) * np.exp(-t * 40) * 0.8
    return (body + hit) * strength


def shoko():
    n = int(1.2 * SR)
    t = np.arange(n) / SR
    sig = np.zeros(n)
    for fr, a, dcy in ((1320, 1.0, 5), (2210, 0.7, 7), (3480, 0.5, 9), (4850, 0.3, 12)):
        sig += a * np.sin(2 * np.pi * fr * t) * np.exp(-t * dcy)
    sig += 0.4 * hp(rng.standard_normal(n), 3000) * np.exp(-t * 60)
    return sig * 0.5


# りん
def rin(f=620, dur=5.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    sig = np.zeros(n)
    for ratio, a, dcy in ((1.0, 1.0, 0.7), (2.76, 0.55, 1.4), (5.40, 0.3, 2.4), (8.93, 0.15, 3.5)):
        fr = f * ratio
        sig += a * np.sin(2 * np.pi * fr * t) * np.exp(-t * dcy) * (1 + 0.15 * np.sin(2 * np.pi * 3.1 * ratio * t))
    sig += 0.3 * hp(rng.standard_normal(n), 4000) * np.exp(-t * 80)
    return sig


# 梵鐘
def bonsho(f=98, dur=8.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    sig = np.zeros(n)
    for ratio, a, dcy, beat in ((0.5, 0.6, 0.25, 0.9), (1.0, 1.0, 0.35, 1.7), (1.62, 0.6, 0.5, 2.3), (2.23, 0.5, 0.7, 1.1),
                                (2.95, 0.35, 0.9, 2.9), (4.1, 0.2, 1.4, 3.4), (5.4, 0.12, 2.0, 1.3)):
        fr = f * ratio
        sig += a * (np.sin(2 * np.pi * fr * t) + 0.5 * np.sin(2 * np.pi * (fr + beat) * t)) * np.exp(-t * dcy)
    sig += 0.8 * lp(rng.standard_normal(n), 400) * np.exp(-t * 25)
    return sig / 2


# 秋の虫（鈴虫の「リーン」、コオロギのコロコロ）
def suzumushi(dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    car = np.sin(2 * np.pi * 4300 * t)
    gate = (np.sin(2 * np.pi * 42 * t) > 0).astype(float)
    ph = (t % 1.4) / 1.4
    burst = np.where(ph < 0.45, np.sin(np.pi * ph / 0.45), 0)
    return car * gate * burst


def korogi(dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    car = np.sin(2 * np.pi * 3600 * t)
    gate = (np.sin(2 * np.pi * 28 * t) > 0.2).astype(float)
    ph = (t % 0.9) / 0.9
    burst = np.where(ph < 0.3, 1.0, 0)
    return car * gate * burst
