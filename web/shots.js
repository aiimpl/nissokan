// コンテの時間割り（conte/CONTE.md）。座標は byodoin の geometry.py（x=東 y=北 z=上、原点=中堂、単位 m）
// 各ショットは始めと終わりの値を持ち、あいだは加減速のついた補間。ズームなし・往復なし
export const LENGTH = 21;

// gust：吹き寄せの帯 [中心x, 中心y, 強さ, 帯の幅]。中心は時間で西から東（手前）へ進む
export const SHOTS = [
  { // S1+S2 水鏡 → 対岸：水面すれすれから目の高さへ、ゆっくり上がりながら見上げる
    name: '水鏡・対岸', t0: 0, t1: 11,
    cam: [[80, 0, 0.45], [88, 0, 1.6]], at: [[0, 0, -2], [0, 0, 5.2]], lens: [50, 50],
    sunEl: [7.2, 6.0], exposure: [0.03, 0.03],
    // 吹き寄せ：風の速さ（5m/s）で池を渡り、水鏡を崩して 7 秒でおさまる（S2 は凪）
    gust: (u) => { const t = u * 11; return [40 + 5 * t, 0, t < 7 ? 0.5 * Math.sin(Math.PI * t / 7) : 0, 16]; },
  },
  { // S3 中堂：扉の上の丸い窓へ、前進だけでゆっくり寄る
    name: '中堂', t0: 11, t1: 14,
    cam: [[46, 0, 2.2], [40, 0, 2.3]], at: [[0, 0, 5.4], [0, 0, 5.4]], lens: [50, 50],
    sunEl: [5.4, 5.0], exposure: [0.07, 0.07],
    gust: () => [0, 0, 0, 20],
  },
  { // S4 日輪と鳳凰：東岸から望遠で固定。日が二羽の間に下りて大棟に乗る
    // 大棟の上端は仰角 3.51°（画から実測）。日輪の半径 0.23° なので、17.5 秒で触れ、19 秒で半分沈む
    name: '日輪と鳳凰', t0: 14, t1: 19,
    cam: [[160, 0, 3], [160, 0, 3]], at: [[0, 0, 12.4], [0, 0, 12.4]], lens: [200, 200],
    sunEl: [4.3, 3.5], exposure: [0.014, 0.014],
    gust: () => [0, 0, 0, 20],
  },
  { // S5 残照：水面すれすれの引き。日は屋根に隠れ、空だけが燃える
    name: '残照', t0: 19, t1: 21,
    cam: [[130, 0, 1.5], [133, 0, 1.5]], at: [[0, 0, 6], [0, 0, 6]], lens: [28, 28],
    sunEl: [3.5, 3.4], exposure: [0.035, 0.035],
    gust: () => [0, 0, 0.3, 40],
  },
];

const ease = (u) => u * u * (3 - 2 * u);
const lerp = (a, b, u) => a + (b - a) * u;
const lerp3 = (a, b, u) => a.map((v, i) => lerp(v, b[i], u));

export function shotAt(t) {
  const s = SHOTS.find((x) => t < x.t1) || SHOTS[SHOTS.length - 1];
  const u = Math.min(Math.max((t - s.t0) / (s.t1 - s.t0), 0), 1);
  const e = ease(u);
  return {
    name: s.name,
    cam: lerp3(s.cam[0], s.cam[1], e),
    at: lerp3(s.at[0], s.at[1], e),
    lens: lerp(s.lens[0], s.lens[1], e),
    sunEl: lerp(s.sunEl[0], s.sunEl[1], u),       // 日は一定の速さで沈む
    exposure: lerp(s.exposure[0], s.exposure[1], e),
    gust: s.gust(u),
  };
}
