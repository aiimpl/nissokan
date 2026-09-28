"""日想観の音（21秒）。コンテ（conte/CONTE.md）の時刻に合わせて、池・虫・雅楽・りん・楽太鼓・梵鐘を置く。

    python sound/compose.py 出力.wav
"""
import sys

import numpy as np
from scipy.io import wavfile

from instruments import SR, rng, bp, lp, sho_chord, hichiriki, taiko, rin, bonsho, suzumushi, korogi

DUR = 21.0
N = int(SR * DUR)
T_TOUCH = 17.5          # 日輪が大棟に触れる（web/shots.js の S4：夕日 4.3°→3.19°、14〜19秒）


def place(buf, sig, t0, gain=1.0, pan=0.0):
    i0 = int(t0 * SR)
    sig = sig[:N - i0]
    buf[i0:i0 + len(sig), 0] += sig * gain * np.cos((pan + 1) * np.pi / 4)
    buf[i0:i0 + len(sig), 1] += sig * gain * np.sin((pan + 1) * np.pi / 4)


mix = np.zeros((N, 2))
t = np.arange(N) / SR

# 池：ごく小さな水の音。吹き寄せ（1〜6秒）のあいだだけ、さざ波と風が少しふくらむ
gust = np.exp(-((t - 3.5) / 1.8) ** 2)
for ch in (0, 1):
    lap = bp(rng.standard_normal(N), 250, 1800) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.23 * t + ch)) ** 2
    ripple = bp(rng.standard_normal(N), 1500, 6000) * gust
    wind = lp(rng.standard_normal(N), 500) * gust
    mix[:, ch] += lap * 0.010 + ripple * 0.006 + wind * 0.012

# 秋の虫：左右に分けて、ずっと遠く
fade = lambda n: np.clip(np.arange(n) / SR / 2.0, 0, 1)
s1 = suzumushi(DUR)
place(mix, lp(s1 * fade(len(s1)), 7000), 0.0, 0.010, -0.6)
k1 = korogi(DUR - 0.8)
place(mix, k1 * fade(len(k1)), 0.8, 0.007, 0.55)

# 笙：3秒目から薄く入り、日が下りるにつれて高い合竹へ
place(mix, sho_chord([69, 71, 76, 81, 83], 9.0, att=3.0, rel=2.0), 3.0, 0.20)
place(mix, sho_chord([71, 76, 78, 83, 88], 8.5, att=2.5, rel=3.0), 11.5, 0.22)
# 篳篥：5秒目に一音、長く（塩梅で下から入る）
place(mix, hichiriki([(71, 4.6), (69, 1.4)], 5.0), 5.0, 0.045, 0.1)
# りん：中堂へ寄るところ
place(mix, rin(760, 6.0), 11.0, 0.12)
# 楽太鼓：日輪が大棟に触れる瞬間
place(mix, taiko(1.0, 56), T_TOUCH, 0.30)
# 梵鐘：残照。余韻のまま終わる
place(mix, bonsho(98, 8.0), 19.0, 0.34)

# 軽い残響（多重ディレイ）
rev = np.zeros_like(mix)
for d, a in ((0.031, 0.35), (0.047, 0.3), (0.071, 0.25), (0.113, 0.2), (0.173, 0.15), (0.257, 0.1), (0.371, 0.07), (0.53, 0.05)):
    k = int(d * SR)
    rev[k:, 0] += mix[:-k, 1] * a
    rev[k:, 1] += mix[:-k, 0] * a
mix = mix + lp(rev, 5000) * 0.55
fi = int(0.3 * SR)
mix[:fi] *= np.linspace(0, 1, fi)[:, None]
fo = int(0.8 * SR)
mix[-fo:] *= np.linspace(1, 0, fo)[:, None] ** 1.5
peak = np.abs(mix).max()
mix = mix / peak * 0.89
out = sys.argv[1] if len(sys.argv) > 1 else 'nissokan.wav'
wavfile.write(out, SR, (mix * 32767).astype(np.int16))
print('wrote', out, f'{DUR}s', f'peak(before norm)={peak:.2f}')
