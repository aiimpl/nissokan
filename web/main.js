// 日想観：阿字池に沈む夕日と鳳凰堂。時刻 t（秒）を渡すと、その瞬間の1コマを描く
import * as THREE from 'three';
import { loadSky } from './sky.js';
import { loadHall, loadEnv } from './baked.js';
import { makePond } from './pond.js';
import { SHOTS, LENGTH, shotAt } from './shots.js';

const q = new URLSearchParams(location.search);
const OFFLINE = q.has('render');
const W = OFFLINE ? 1920 : Math.min(innerWidth * devicePixelRatio, 1920);
const H = Math.round(W * 9 / 16);
const SS = OFFLINE ? 2 : 1;            // 縦横2倍で描いて縮める
const SUB = OFFLINE ? 3 : 1;           // 1コマを何回に分けて描いて平均するか（シャッター 1/60 秒）
const SHUTTER = 1 / 60;
const BAKE = q.get('bake') || '../build/bake/';      // make bake で焼いたデータ

const renderer = new THREE.WebGLRenderer({ antialias: false, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(1);
renderer.autoClear = false;
renderer.setSize(W, H, false);
renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
document.body.appendChild(renderer.domElement);

const camera = new THREE.PerspectiveCamera(40, W / H, 0.1, 6000);

// 空・建物・池で共有する値
const shared = {
  uT: { value: 0 },
  uMix: { value: 0 },
  uSun: { value: new THREE.Vector3() },
  uSunIrr: { value: new THREE.Vector3() },
  uSunDisc: { value: new THREE.Vector3() },
  uReflect: { value: 0 },
};

const rtOpt = { type: THREE.HalfFloatType, depthBuffer: true };
const rtScene = new THREE.WebGLRenderTarget(W * SS, H * SS, { ...rtOpt, samples: OFFLINE ? 4 : 0 });
const rtRefl = new THREE.WebGLRenderTarget(W * SS, H * SS, { ...rtOpt, samples: OFFLINE ? 4 : 0 });
const rtAcc = new THREE.WebGLRenderTarget(W * SS, H * SS, { type: THREE.FloatType, depthBuffer: false });

const world = new THREE.Group();          // 水面より上のもの（映り込みでは上下反転する）
const scene = new THREE.Scene();
scene.add(world);
world.add(await loadSky(BAKE, shared));
world.add(await loadHall(BAKE, shared, renderer));
if (!q.has('noenv')) world.add((await loadEnv(BAKE, shared)).group);
const pond = makePond(shared, rtRefl);
scene.add(pond.mesh);

// 仕上げ：縮小・露出・にじみ・日輪の縦筋・フィルムの肩・粒
const quadVert = 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0., 1.); }';
const accMat = new THREE.ShaderMaterial({
  vertexShader: quadVert,
  fragmentShader: 'uniform sampler2D uTex; uniform float uW; varying vec2 vUv; void main(){ gl_FragColor = vec4(texture2D(uTex, vUv).rgb * uW, 1.); }',
  uniforms: { uTex: { value: rtScene.texture }, uW: { value: 1 / SUB } },
  blending: THREE.AdditiveBlending, depthTest: false, depthWrite: false,
});
const postMat = new THREE.ShaderMaterial({
  vertexShader: quadVert,
  fragmentShader: /* glsl */`
    uniform sampler2D uTex;
    uniform vec2 uTexel;
    uniform float uExposure;
    uniform vec2 uSunUv;        // 画面上の日輪の位置
    uniform float uT;
    varying vec2 vUv;
    float h12(vec2 p){ vec3 p3 = fract(vec3(p.xyx) * .1031); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.x + p3.y) * p3.z); }
    vec3 film(vec3 x){ return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0., 1.); }
    void main(){
      vec3 c = vec3(0.);
      c += texture2D(uTex, vUv + uTexel * vec2(-0.5, -0.5)).rgb;
      c += texture2D(uTex, vUv + uTexel * vec2( 0.5, -0.5)).rgb;
      c += texture2D(uTex, vUv + uTexel * vec2(-0.5,  0.5)).rgb;
      c += texture2D(uTex, vUv + uTexel * vec2( 0.5,  0.5)).rgb;
      c *= 0.25 * uExposure;
      // 明るすぎる所だけ周りへにじませる：狭いにじみと、日輪のまわりの広いにじみ
      vec3 bl = vec3(0.), bw = vec3(0.);
      float ws = 0., ww = 0.;
      for (int y = -4; y <= 4; y++) for (int x = -4; x <= 4; x++){
        vec2 o = vec2(x, y);
        vec3 v = min(texture2D(uTex, vUv + uTexel * o * 1.8).rgb * uExposure, vec3(60.));
        float w = exp(-dot(o, o) / 5.);
        bl += max(v - 1.5, 0.) * w; ws += w;
        vec3 v2 = min(texture2D(uTex, vUv + uTexel * o * 14.).rgb * uExposure, vec3(60.));
        bw += max(v2 - 2.0, 0.) * w; ww += w;
      }
      c += bl / ws * 0.35 + bw / ww * 0.10;
      // 周辺をわずかに暗く（レンズの減光）
      vec2 vq = vUv - 0.5;
      c *= 1. - 0.32 * dot(vq, vq);
      c = film(c);
      c = pow(c, vec3(1. / 2.2));
      c += (h12(gl_FragCoord.xy + fract(uT) * 91.) - 0.5) / 255. * 2.;
      gl_FragColor = vec4(c, 1.);
    }
  `,
  uniforms: { uTex: { value: rtAcc.texture }, uTexel: { value: new THREE.Vector2(1 / (W * SS), 1 / (H * SS)) },
    uExposure: { value: 1 }, uSunUv: { value: new THREE.Vector2(-1, -1) }, uT: shared.uT },
  depthTest: false, depthWrite: false,
});
const quadScene = new THREE.Scene();
const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), accMat);
quad.frustumCulled = false;
quadScene.add(quad);
const ortho = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

// byodoin の座標（x=東 y=北 z=上）→ three.js（y=上、北=-z）
const b2t = (v) => new THREE.Vector3(v[0], v[2], -v[1]);
const BAKE_EL = [7.0, 3.5];               // 焼いた夕日の高さ（hi, lo）
const SUN_IRR = [[4.0, 2.48, 1.36], [3.0, 1.41, 0.60]];   // 焼いたときの照度（色×強さ）

// 確かめ用：?cam=x,y,z&at=x,y,z&lens=mm&el=度&exp=露出 で上書き（座標は byodoin）
const num3 = (k) => q.get(k) && q.get(k).split(',').map(Number);
const OVR = { cam: num3('cam'), at: num3('at'), lens: q.get('lens') && Number(q.get('lens')), sunEl: q.get('el') && Number(q.get('el')), exposure: q.get('exp') && Number(q.get('exp')) };

function setState(t) {
  const s = shotAt(t);
  for (const [k, v] of Object.entries(OVR)) if (v) s[k] = v;
  camera.position.copy(b2t(s.cam));
  camera.up.set(0, 1, 0);
  camera.lookAt(b2t(s.at));
  camera.fov = 2 * Math.atan(12 / s.lens) * 180 / Math.PI;
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld();
  const el = THREE.MathUtils.degToRad(s.sunEl);
  shared.uSun.value.set(-Math.cos(el), Math.sin(el), 0);      // 真西
  const m = THREE.MathUtils.clamp((BAKE_EL[0] - s.sunEl) / (BAKE_EL[0] - BAKE_EL[1]), 0, 1);
  shared.uMix.value = m;
  const irr = SUN_IRR[0].map((v, i) => v + (SUN_IRR[1][i] - v) * m);
  shared.uSunIrr.value.set(...irr);
  // 日輪：高さ 7° の黄橙から 3.5° の赤橙へ。明るさはまわりの空（約55）の約7倍
  // 高さ 3〜7° の日輪は写真では濃い橙に写る（明るさはまわりの空の数倍）
  const disc = [[1.0, 0.34, 0.08], [1.0, 0.22, 0.045]];
  shared.uSunDisc.value.set(...disc[0].map((v, i) => (v + (disc[1][i] - v) * m) * 380));
  pond.uniforms.uGust.value.set(...s.gust);
  postMat.uniforms.uExposure.value = s.exposure;
  const sp = shared.uSun.value.clone().multiplyScalar(1000).add(camera.position).project(camera);
  postMat.uniforms.uSunUv.value.set(sp.x * 0.5 + 0.5, sp.y * 0.5 + 0.5);
}

function renderAt(t) {
  renderer.setRenderTarget(rtAcc);
  renderer.setClearColor(0x000000, 1);
  renderer.clear();
  // 分けて描く時刻は、そのコマのショットの中に収める（カットをまたぐと二重写しになる）
  const sh = SHOTS.find((x) => t < x.t1) || SHOTS[SHOTS.length - 1];
  for (let i = 0; i < SUB; i++) {
    const ts = Math.min(Math.max(t + (SUB > 1 ? (i / (SUB - 1) - 0.5) * SHUTTER : 0), sh.t0), sh.t1 - 1e-4);
    shared.uT.value = ts;
    setState(ts);
    // 映り込み：水面より上の世界を上下反転して同じカメラで描く
    world.scale.y = -1;
    shared.uReflect.value = 1;
    pond.mesh.visible = false;
    renderer.setRenderTarget(rtRefl);
    renderer.clear();
    renderer.render(scene, camera);
    world.scale.y = 1;
    shared.uReflect.value = 0;
    pond.mesh.visible = true;
    renderer.setRenderTarget(rtScene);
    renderer.clear();
    renderer.render(scene, camera);
    renderer.setRenderTarget(rtAcc);
    quad.material = accMat;
    renderer.render(quadScene, ortho);
  }
  shared.uT.value = t;
  setState(t);
  renderer.setRenderTarget(null);
  quad.material = postMat;
  renderer.render(quadScene, ortho);
}

window.renderAt = (t) => {
  renderAt(t);
  const px = new Uint8Array(4);
  const gl = renderer.getContext();
  gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);    // 描き終わるまで待つ
  return true;
};
window.SHOTS = SHOTS;
if (q.has('dbg')) window.dbg = { shared, setState, renderAt };
window.ready = true;

if (!OFFLINE) {
  const t0 = performance.now();
  const start = Number(q.get('t') || 0);
  const loop = () => {
    renderAt((start + (performance.now() - t0) / 1000) % LENGTH);
    requestAnimationFrame(loop);
  };
  if (q.has('still')) renderAt(start); else loop();
}
