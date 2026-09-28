// 阿字池の水面：静かな池。風の吹き寄せの帯が渡るところだけさざ波が立ち、映り込みが崩れてきらめく
import * as THREE from 'three';
import { skyGLSL } from './sky.js';

const common = /* glsl */`
uniform float uT;
float hash12(vec2 p){ vec3 p3 = fract(vec3(p.xyx) * .1031); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.x + p3.y) * p3.z); }
vec3 hash32(vec2 p){ vec3 p3 = fract(vec3(p.xyx) * vec3(.1031, .1030, .0973)); p3 += dot(p3, p3.yxz + 33.33); return fract((p3.xxy + p3.yzz) * p3.zyx); }
float vnoise(vec2 p){
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3. - 2. * f);
  return mix(mix(hash12(i), hash12(i + vec2(1, 0)), u.x), mix(hash12(i + vec2(0, 1)), hash12(i + vec2(1, 1)), u.x), u.y);
}
float fbm(vec2 p){ float s = 0., a = 0.5; for (int i = 0; i < 5; i++){ s += a * vnoise(p); p = p * 2.03 + 11.7; a *= 0.5; } return s; }
`;

const vert = /* glsl */`
varying vec3 vW;
varying vec4 vClip;
void main(){
  vec4 w = modelMatrix * vec4(position, 1.);
  vW = w.xyz;
  vClip = projectionMatrix * viewMatrix * w;
  gl_Position = vClip;
}
`;

const frag = /* glsl */`
${common}
${skyGLSL}
uniform sampler2D uRefl;          // 上下反転した世界を同じカメラで描いたもの
uniform vec2 uReflTexel;
uniform vec4 uGust;               // 吹き寄せ：xy=帯の中心の進み（m）、z=強さ、w=帯の幅
uniform vec2 uWind;               // 風の向き（水平、単位ベクトル）
uniform vec3 uSunIrr;
varying vec3 vW;
varying vec4 vClip;

// 吹き寄せの強さ（0=鏡のような凪、1=さざ波がはっきり）
float gustAt(vec2 p){
  vec2 q = p - uGust.xy;
  float along = dot(q, uWind), across = dot(q, vec2(-uWind.y, uWind.x));
  float band = exp(-pow(along / uGust.w, 2.));
  float spot = smoothstep(0.35, 0.75, fbm(p * 0.035 + vec2(3.1, 7.7)) + 0.25 * sin(across * 0.05));
  float calm = 0.06 + 0.05 * fbm(p * 0.02 + uT * 0.01);           // 凪でも少しは動く
  return clamp(calm + uGust.z * band * spot, 0., 1.);
}

// さざ波（法線だけ）：風の向きに寄った 40 本。短い波ほど風に敏感
vec3 rippleSlope(vec2 p, float fw, float g){
  vec2 s = vec2(0.);
  float unres = 0.;
  for (int i = 0; i < 40; i++){
    float fi = float(i);
    float lam = 1.6 * pow(0.88, fi) * (0.8 + 0.4 * hash12(vec2(fi, 9.1)));       // 1.6m → 約1cm
    float ang = (hash12(vec2(fi, 3.1)) - 0.5) * 1.6;
    vec2 d = mat2(cos(ang), -sin(ang), sin(ang), cos(ang)) * uWind;
    float k = 6.2831853 / lam;
    float om = sqrt(9.81 * k + 0.074 / 1000. * k * k * k);
    float stp = 0.06 * (0.5 + hash12(vec2(fi, 7.7))) * mix(0.25, 1., smoothstep(0.6, 0.05, lam));
    float amp = stp / k * mix(0.08, 1., g);
    float filt = smoothstep(fw * 3., fw * 8., lam);
    float ph = k * dot(d, p) - om * uT + hash12(vec2(fi, 1.3)) * 6.2831;
    s += d * amp * k * cos(ph) * filt;
    unres += pow(amp * k, 2.) * 0.5 * (1. - filt);
  }
  return vec3(s, unres);
}

// きらめき：区画ごとに乱れた傾きを振って、夕日を映す向きの区画だけ光らせる（reality-js と同じ考え方）
float glints(vec2 p, vec2 need, float fw, float sigma, float rate){
  float acc = 0.;
  for (int l = 0; l < 2; l++){
    float cs = max(l == 0 ? 0.025 : 0.06, fw * 1.2);
    vec2 q = p / cs + float(l) * 17.3;
    vec2 id = floor(q), f = fract(q);
    vec3 h0 = hash32(id);
    float tt = uT * rate + h0.z * 7.;
    vec3 hr = hash32(id + floor(tt) * 1.618);
    float r = sqrt(-2. * log(max(hr.x, 1e-4)));
    vec2 sl = r * vec2(cos(6.2831 * hr.y), sin(6.2831 * hr.y)) * sigma;
    float hit = exp(-dot(sl - need, sl - need) / (0.06 * 0.06));
    vec2 c = h0.xy * 0.6 + 0.2;
    float r2 = max(0.012, pow(0.5 * fw / cs, 2.));
    acc += hit * exp(-dot(f - c, f - c) / r2) * 0.012 / r2 * sin(3.14159 * fract(tt)) * 2.2;
  }
  return acc;
}

void main(){
  vec2 p = vec2(vW.x, -vW.z);                  // 池の平面座標（x=東、y=北）
  vec3 V = normalize(cameraPosition - vW);
  float dist = length(cameraPosition - vW);
  float fw = max(length(fwidth(p)), 1e-4);
  float g = gustAt(p);
  vec3 rp = rippleSlope(p, fw, g);
  vec2 grad = rp.xy;
  vec3 N = normalize(vec3(-grad.x, 1., grad.y));
  float NV = max(dot(N, V), 1e-3);
  float F = 0.02 + 0.98 * pow(1. - NV, 5.);

  // 映り込み：画面の位置で上下反転の世界を読み、さざ波の傾きでずらす。
  // 実際の水面の映り込みは縦に伸びて揺らぐので、ずれは縦を主に、横は小さく（遠いほど小さい）
  vec2 suv = vClip.xy / vClip.w * 0.5 + 0.5;
  vec2 off = vec2(grad.x * 0.35, grad.y) * 1900. / max(dist, 4.);
  vec3 refl = texture2D(uRefl, suv + off * uReflTexel).rgb;
  vec3 R = reflect(-V, N);
  R.y = abs(R.y);

  // 水の中：浅い池の濁った緑褐色。日の当たる向こう側ほど少し明るい
  vec3 body = vec3(0.010, 0.013, 0.009) * (1. + 0.6 * pow(max(dot(-V, uSun), 0.), 3.));
  vec3 col = body * (1. - F) + refl * F;

  // 夕日が建物や木に隠れる所ではきらめかない：映り込みの画で、日輪の映る向き（画面の縦方向）に空が見えているか
  float skyVis = 0.;
  for (int k = -2; k <= 2; k++) {
    vec2 o = vec2(0., float(k) * 6.) * uReflTexel;
    vec3 rr = texture2D(uRefl, suv + o).rgb;
    skyVis += smoothstep(0.35, 0.8, dot(rr, vec3(0.3, 0.5, 0.2)) / max(dot(skyBase(vec3(R.x, max(R.y, 0.01), R.z)), vec3(0.3, 0.5, 0.2)), 1e-3));
  }
  skyVis /= 5.;
  // きらめき：夕日を映す向きの傾き
  vec3 L = uSun;
  vec3 Hh = normalize(L + V);
  vec2 need = vec2(-Hh.x / Hh.y, Hh.z / Hh.y) - grad;
  float sig = sqrt(0.0004 + rp.z) + 0.02 * g;
  float gl = glints(p + vec2(0., uT * 0.1), need, fw, sig, 1.6);
  float Fs = 0.02 + 0.98 * pow(1. - max(dot(V, Hh), 0.), 5.);     // 日輪を映す向きの反射率（低い角度ほど強い）
  col += uSunDisc * Fs * gl * 0.35 * smoothstep(0.02, 0.2, g) * skyVis;
  // 画素より細かいきらめきの平均：傾きの分布から、夕日を映す向きの割合（遠くで光の道になる）
  float pdf = exp(-dot(need, need) / (2. * sig * sig)) / (6.2831 * sig * sig);
  // 真横に近い角度では、細かい波どうしが隠し合うので光は伸びきらない（遮蔽）
  float mask = NV / (NV + 0.06);
  col += uSunIrr * Fs * pdf / (4. * NV * pow(Hh.y, 4.)) * mask * smoothstep(10., 120., dist) * skyVis;
  gl_FragColor = vec4(col, 1.);
}
`;

export function makePond(shared, reflTarget) {
  const uniforms = {
    ...shared,
    uRefl: { value: reflTarget.texture },
    uReflTexel: { value: new THREE.Vector2(1 / reflTarget.width, 1 / reflTarget.height) },
    uGust: { value: new THREE.Vector4(0, 0, 0, 30) },
    uWind: { value: new THREE.Vector2(0.94, 0.34).normalize() },   // 西南西から東へ（池を手前へ渡る）
  };
  const geo = new THREE.PlaneGeometry(420, 200, 1, 1);
  geo.rotateX(-Math.PI / 2);
  geo.translate(8, 0, 0);
  const mat = new THREE.ShaderMaterial({ vertexShader: vert, fragmentShader: frag, uniforms, extensions: { derivatives: true } });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.renderOrder = 1;
  return { mesh, uniforms };
}
