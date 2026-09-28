// Cycles で焼いた夕日の光を読んで描く：鳳凰堂（テクスチャ）、地形・庭石（頂点）、木（頂点・インスタンス）
// 焼いた拡散光に、見る向きで変わる照り（夕日・空の映り込み）と空気の霞だけをここで足す
import * as THREE from 'three';
import { skyGLSL } from './sky.js';

// 材質ごとの照り：f0 は正面から見たときの反射率、rough は粗さ、metal は金属か、glow は自ら光る明るさ
const SURF = {
  '金具': { f0: [0.95, 0.70, 0.32], rough: 0.28, metal: 1 },
  '本瓦': { f0: [0.04, 0.04, 0.04], rough: 0.42, metal: 0 },
  '丹塗り': { f0: [0.04, 0.04, 0.04], rough: 0.65, metal: 0 },
  '黒': { f0: [0.04, 0.04, 0.04], rough: 0.5, metal: 0 },
  '石': { f0: [0.03, 0.03, 0.03], rough: 0.85, metal: 0 },
  '庭石': { f0: [0.03, 0.03, 0.03], rough: 0.7, metal: 0 },
  '灯り': { f0: [0.03, 0.03, 0.03], rough: 0.9, metal: 0, glow: [0.9, 0.5, 0.2] },
};
const DEF = { f0: [0.03, 0.03, 0.03], rough: 0.85, metal: 0 };

const L0 = 0.0005, LMAX = 64.0;              // bake/common.py の encode_lit と同じ
const LOGR = Math.log2(1 + LMAX / L0);

const vert = /* glsl */`
  #ifdef TEX
  varying vec2 vUv;            // uv は three.js が宣言する
  #else
  attribute vec3 lit_hi;
  attribute vec3 lit_lo;
  attribute vec4 shade;
  varying vec3 vLitHi, vLitLo;
  varying vec4 vShade;
  #endif
  #ifdef TREE
  attribute vec2 vis;            // 1本ごとの夕日の当たり（7°、3.5°）
  varying vec2 vVis;
  #endif
  attribute float mat;
  uniform sampler2D uSurf;
  varying vec3 vN, vW;
  varying float vLocalY;
  varying vec4 vS0, vS1;
  void main() {
    vec3 pos = position;
    #ifdef TEX
    vUv = uv;
    #else
    vLitHi = lit_hi; vLitLo = lit_lo;
    vShade = shade;
    #endif
    vS0 = texture2D(uSurf, vec2((mat + 0.5) / 32.0, 0.25));
    vS1 = texture2D(uSurf, vec2((mat + 0.5) / 32.0, 0.75));
    #ifdef TREE
    vVis = vis;
    mat4 M = modelMatrix * instanceMatrix;
    #else
    mat4 M = modelMatrix;
    #endif
    vN = normalize(mat3(M) * normal);
    vec4 w = M * vec4(pos, 1.0);
    #ifdef TREE
    vLocalY = (instanceMatrix * vec4(pos, 1.0)).y;
    #else
    vLocalY = pos.y;
    #endif
    vW = w.xyz;
    gl_Position = projectionMatrix * viewMatrix * w;
  }
`;

const frag = /* glsl */`
  ${skyGLSL}
  uniform vec3 uSunIrr;        // 夕日の照度（焼き付けと同じ単位）
  uniform float uReflect;      // 1=映り込みを描いているとき（水面より下は捨てる）
  #ifdef TEX
  uniform sampler2D uLitHi, uLitLo, uShade;
  varying vec2 vUv;
  #else
  varying vec3 vLitHi, vLitLo;
  varying vec4 vShade;
  #endif
  #ifdef TREE
  varying vec2 vVis;
  #endif
  varying vec3 vN, vW;
  varying float vLocalY;
  varying vec4 vS0, vS1;       // f0.rgb, rough / glow.rgb, metal
  const float PI = 3.14159265;
  vec3 decodeLit(vec3 e) { return ${L0} * (exp2(e * ${LOGR.toFixed(6)}) - 1.0); }
  void main() {
    if (uReflect > 0.5 && vLocalY < -0.02) discard;
    #ifdef TEX
    vec3 diff = mix(decodeLit(texture2D(uLitHi, vUv).rgb), decodeLit(texture2D(uLitLo, vUv).rgb), uMix);
    vec3 sh = texture2D(uShade, vUv).rgb;
    #else
    vec3 diff = mix(vLitHi, vLitLo, uMix);
    vec3 sh = vShade.xyz;
    #endif
    float sunVis = mix(sh.x, sh.y, uMix);
    float ao = sh.z;
    #ifdef TREE
    float tv = mix(vVis.x, vVis.y, uMix);
    diff *= mix(0.45, 1.0, tv);            // 夕日の当たらない木は直射の分だけ暗い
    sunVis *= tv;
    #endif
    vec3 N = normalize(vN);
    vec3 V = normalize(cameraPosition - vW);
    if (dot(N, V) < 0.0) N = -N;
    vec3 f0 = vS0.rgb; float rough = max(vS0.a, 0.05); float metal = vS1.a;
    // 夕日の照り（GGX）
    vec3 L = uSun, H = normalize(L + V);
    float NoL = max(dot(N, L), 0.0), NoV = max(dot(N, V), 1e-3), NoH = max(dot(N, H), 0.0), VoH = max(dot(V, H), 0.0);
    float a2 = pow(rough, 4.0);
    float D = a2 / (PI * pow(NoH * NoH * (a2 - 1.0) + 1.0, 2.0));
    float k = pow(rough + 1.0, 2.0) / 8.0;
    float G = NoL / (NoL * (1.0 - k) + k) * NoV / (NoV * (1.0 - k) + k);
    vec3 F = f0 + (1.0 - f0) * pow(1.0 - VoH, 5.0);
    vec3 spec = D * G * F / (4.0 * NoV + 1e-4) * uSunIrr * sunVis;
    // 空の映り込み：粗いほどぼけて弱く、隅ほど暗い
    vec3 R = reflect(-V, N);
    vec3 Fv = f0 + (max(vec3(1.0 - rough), f0) - f0) * pow(1.0 - NoV, 5.0);
    Fv *= mix(pow(1.0 - rough, 2.0), 1.0, metal);      // 粗い石や木は空をほとんど映さない（金属はそのまま）
    vec3 env = skyCol(normalize(mix(R, N, rough * rough)), false) * Fv * ao;
    vec3 c = diff * (1.0 - metal) + spec + env + vS1.rgb;
    // 空気の霞：見ている向きの地平の空の色へ
    float d = length(cameraPosition - vW);
    float hz = 1.0 - exp(-d / 2600.0);
    c = mix(c, skyBase(normalize(vec3(-V.x, 0.03, -V.z))), hz);
    gl_FragColor = vec4(c, 1.0);
  }
`;

function surfTexture(materials) {
  const data = new Float32Array(32 * 2 * 4);
  for (const [id, name] of Object.entries(materials)) {
    const s = SURF[name] || DEF;
    const i = Number(id);
    data.set([...s.f0, s.rough], i * 4);
    data.set([...(s.glow || [0, 0, 0]), s.metal], (32 + i) * 4);
  }
  const t = new THREE.DataTexture(data, 32, 2, THREE.RGBAFormat, THREE.FloatType);
  t.needsUpdate = true;
  return t;
}

const ARR = { float16: Uint16Array, float32: Float32Array, uint8: Uint8Array };

async function loadGeometry(url, head) {
  const buf = await (await fetch(url)).arrayBuffer();
  const g = new THREE.BufferGeometry();
  for (const at of head.attributes) {
    const A = ARR[at.type];
    const arr = new A(buf, at.offset, at.bytes / A.BYTES_PER_ELEMENT);
    let attr;
    if (at.type === 'float16') attr = new THREE.Float16BufferAttribute(arr, at.size);
    else if (at.name === 'mat') attr = new THREE.BufferAttribute(new Float32Array(arr), 1);
    else attr = new THREE.BufferAttribute(arr, at.size, at.type === 'uint8');                // 8bit は 0〜1 に
    g.setAttribute(at.name, attr);
  }
  g.setIndex(new THREE.BufferAttribute(new Uint32Array(buf, head.index.offset, head.index.count), 1));
  g.computeBoundingSphere();
  return g;
}

const texLoader = new THREE.TextureLoader();
function loadTex(url, renderer) {
  return new Promise((ok, ng) => texLoader.load(url, (t) => {
    t.colorSpace = THREE.NoColorSpace;          // 焼いた値そのもの（色空間の変換なし）
    t.anisotropy = renderer.capabilities.getMaxAnisotropy();
    t.minFilter = THREE.LinearMipmapLinearFilter;
    ok(t);
  }, undefined, ng));
}

function material(shared, surf, defines, extra = {}) {
  return new THREE.ShaderMaterial({
    vertexShader: vert, fragmentShader: frag, defines,
    uniforms: { ...shared, uSurf: { value: surf }, ...extra },
    side: THREE.DoubleSide,
  });
}

export async function loadHall(base, shared, renderer) {
  const man = await (await fetch(base + 'hall.json')).json();
  const surf = surfTexture(man.materials);
  const group = new THREE.Group();
  for (const [p, h] of Object.entries(man.parts)) {
    const [g, lh, ll, sh] = await Promise.all([
      loadGeometry(`${base}hall_${p}.bin`, h),
      loadTex(base + h.files.lit_hi, renderer), loadTex(base + h.files.lit_lo, renderer), loadTex(base + h.files.shade, renderer),
    ]);
    const mesh = new THREE.Mesh(g, material(shared, surf, { TEX: 1 }, { uLitHi: { value: lh }, uLitLo: { value: ll }, uShade: { value: sh } }));
    mesh.frustumCulled = false;
    group.add(mesh);
  }
  return group;
}

export async function loadEnv(base, shared) {
  const man = await (await fetch(base + 'env.json')).json();
  const surf = surfTexture(man.materials);
  const group = new THREE.Group();
  for (const [p, h] of Object.entries(man.parts)) {
    const g = await loadGeometry(`${base}env_${p}.bin`, h);
    const mesh = new THREE.Mesh(g, material(shared, surf, {}));
    mesh.frustumCulled = false;
    group.add(mesh);
  }
  let n = 0;
  for (const [t, h] of Object.entries(man.trees)) {
    const g = await loadGeometry(`${base}tree_${t}.bin`, h);
    const rows = h.instances;
    const vis = new Float32Array(rows.length * 2);
    rows.forEach((r, i) => { vis[i * 2] = r[16]; vis[i * 2 + 1] = r[17]; });
    g.setAttribute('vis', new THREE.InstancedBufferAttribute(vis, 2));
    const mesh = new THREE.InstancedMesh(g, material(shared, surf, { TREE: 1 }), rows.length);
    const M = new THREE.Matrix4();
    rows.forEach((r, i) => { M.fromArray(r.slice(0, 16)); mesh.setMatrixAt(i, M); });
    mesh.instanceMatrix.needsUpdate = true;
    mesh.computeBoundingSphere();
    mesh.frustumCulled = false;
    group.add(mesh);
    n += rows.length;
  }
  return { group, trees: n };
}
