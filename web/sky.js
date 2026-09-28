// 夕空：Blender の多重散乱の空（焼き付けと同じ）を表で読み、日輪だけここで描く
import * as THREE from 'three';

const SKY_W = 2048, SKY_H = 576;              // 横=方位（左端=北・時計回り）、縦=仰角 +90°〜-10°

// 空の表と日輪（水面・建物からも呼ぶ）
export const skyGLSL = /* glsl */`
uniform sampler2D uSkyHi, uSkyLo;
uniform float uMix;          // 0=夕日 7°、1=3.5°
uniform vec3 uSun;           // 夕日への向き（three.js の座標）
uniform vec3 uSunDisc;       // 日輪の明るさ（色つき、まわりの空の約7倍）
// three.js の向き → 方位（北から時計回り）・仰角。x=東、z=南
vec2 dirAzEl(vec3 d) {
  // 真西・真東の向きは南北の成分が -0 になり、GPU によっては atan が反対向きを返す。ごく小さく足して避ける
  float az = atan(d.x, -d.z + 1e-7);
  if (az < 0.) az += 6.2831853;
  return vec2(az, asin(clamp(d.y, -1., 1.)));
}
vec3 skyBase(vec3 d) {
  vec2 ae = dirAzEl(d);
  float el = max(degrees(ae.y), -9.9);
  vec2 uv = vec2(ae.x / 6.2831853, (el + 10.) / 100.);
  return mix(texture2D(uSkyHi, uv).rgb, texture2D(uSkyLo, uv).rgb, uMix);
}
// 日輪：視直径 0.53°。低いほど大気の屈折で縦につぶれ、周辺ほど暗く赤い
float sunDisc(vec3 d, out float limb) {
  vec2 a = dirAzEl(d), s = dirAzEl(uSun);
  float dAz = a.x - s.x;
  dAz = mod(dAz + 3.14159265, 6.2831853) - 3.14159265;
  float dEl = a.y - s.y;
  float el = degrees(s.y);
  float squash = mix(0.86, 0.93, clamp((el - 3.5) / 3.5, 0., 1.));   // 高さ 3.5° で縦 0.86 倍
  vec2 q = vec2(dAz * cos(s.y), dEl / squash) / radians(0.265);
  float r = length(q);
  limb = sqrt(max(1. - r * r, 0.));
  return 1. - smoothstep(0.985, 1.015, r);
}
vec3 skyCol(vec3 d, bool withDisc) {
  vec3 c = skyBase(d);
  // 日輪のまわりの暈：空の表は 0.2° 刻みで、望遠で切り取る数度の中では平たくなるので、細かい所だけ足す
  float ang = degrees(acos(clamp(dot(normalize(d), uSun), -1., 1.)));
  c += uSunDisc * (0.08 * exp(-ang / 0.4) + 0.03 * exp(-ang / 1.5));
  if (withDisc) {
    float limb;
    float m = sunDisc(normalize(d), limb);
    // 周辺減光：中心は明るい橙、縁は赤く暗い
    vec3 dc = uSunDisc * mix(vec3(0.55, 0.28, 0.14), vec3(1.0, 0.8, 0.62), pow(limb, 0.45));
    c = mix(c, dc, m);
  }
  return c;
}
`;

const vert = /* glsl */`
varying vec3 vDir;
void main() {
  // 色は球の元の向きで引き、置き場所だけ（映り込みでは上下反転された）世界の向きに。
  // 空は無限遠なので、反転した世界で下を向いた画素には、反転前の上向きの空が映る
  vDir = position;
  vec3 w = (modelMatrix * vec4(position, 0.)).xyz;
  vec4 p = projectionMatrix * mat4(mat3(viewMatrix)) * vec4(w, 1.);
  gl_Position = p.xyww;
}
`;
const frag = /* glsl */`
${skyGLSL}
varying vec3 vDir;
void main() { gl_FragColor = vec4(skyCol(normalize(vDir), true), 1.); }
`;

function halfToRGBA(buf) {
  const src = new Uint16Array(buf);
  const n = src.length / 3;
  const out = new Uint16Array(n * 4);
  for (let i = 0; i < n; i++) {
    out[i * 4] = src[i * 3]; out[i * 4 + 1] = src[i * 3 + 1]; out[i * 4 + 2] = src[i * 3 + 2];
    out[i * 4 + 3] = 0x3c00;   // 1.0
  }
  return out;
}

async function skyTex(url) {
  const buf = await (await fetch(url)).arrayBuffer();
  // 表は上端=天頂。テクスチャは v=0 が下なので、行を上下入れ替えずに flipY 相当で v を仰角の昇順にする
  const rgba = halfToRGBA(buf);
  const flipped = new Uint16Array(rgba.length);
  const row = SKY_W * 4;
  for (let y = 0; y < SKY_H; y++) flipped.set(rgba.subarray(y * row, (y + 1) * row), (SKY_H - 1 - y) * row);
  const t = new THREE.DataTexture(flipped, SKY_W, SKY_H, THREE.RGBAFormat, THREE.HalfFloatType);
  t.wrapS = THREE.RepeatWrapping;
  t.wrapT = THREE.ClampToEdgeWrapping;
  t.magFilter = t.minFilter = THREE.LinearFilter;
  t.needsUpdate = true;
  return t;
}

export async function loadSky(base, shared) {
  shared.uSkyHi = { value: await skyTex(base + 'sky_hi.bin') };
  shared.uSkyLo = { value: await skyTex(base + 'sky_lo.bin') };
  const mesh = new THREE.Mesh(new THREE.SphereGeometry(10, 96, 48),
    new THREE.ShaderMaterial({ vertexShader: vert, fragmentShader: frag, uniforms: shared, depthWrite: false, side: THREE.DoubleSide }));
  mesh.frustumCulled = false;
  mesh.renderOrder = -1;
  return mesh;
}
