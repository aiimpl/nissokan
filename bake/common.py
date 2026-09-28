"""焼き付けの共通部分：焼くときの世界（夕日・夕空）、立体の下ごしらえ、Cycles での頂点への焼き付け、書き出し。

座標は byodoin の geometry.py（x=東 y=北 z=上、原点=中堂）。書き出すときに three.js の y=上（北=-z）へ直す。
"""
import json
import math
import os

import bmesh
import bpy
import numpy as np
from mathutils import Vector

SUN_AZ = math.radians(270.0)            # 真西（秋分のころの日の入り）
KEYS = {                                # 夕日の高さ・色・強さ（照度）
    'hi': (7.0, (1.0, 0.62, 0.34), 4.0),
    'lo': (3.5, (1.0, 0.47, 0.20), 3.0),
}
SKY_STRENGTH = 0.5
HIDE = ('地形_遠景', '木_遠景', '霞', '工房ドーム', '台', '工房の光', '工房の補助光')

scn = bpy.context.scene
sky = None
sun = None


def setup(samples):
    """最終コマの状態で、西は平地・霞や工房や巻物や墨線を外した世界にして、Cycles を用意する"""
    global sky, sun
    scn.frame_set(scn.frame_end)
    # 見え隠れにキーが打ってあるので、先にアニメーションを消す（消さないと描くときに戻る）
    for ob in bpy.data.objects:
        ob.animation_data_clear()
        if ob.type == 'LIGHT':
            ob.data.animation_data_clear()
        if ob.name in HIDE or ob.users_collection[0].name in ('墨線', '巻物'):
            ob.hide_render = True
    wt = scn.world.node_tree
    wt.animation_data_clear()
    sky = next(n for n in wt.nodes if n.type == 'TEX_SKY')
    sky.sun_disc = False                # 直射は光源の夕日だけに（二重にしない）
    sky.sun_rotation = SUN_AZ           # 空の太陽は方位そのまま
    wt.nodes['Background'].inputs['Strength'].default_value = SKY_STRENGTH
    sun = bpy.data.objects['夕日']
    scn.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'METAL'
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True
    scn.cycles.device = 'GPU'
    scn.cycles.samples = samples
    scn.cycles.use_denoising = False
    scn.render.use_compositing = False
    scn.render.bake.target = 'VERTEX_COLORS'
    scn.render.bake.margin = 0


def set_sun(key):
    el, col, energy = KEYS[key]
    e = math.radians(el)
    d = Vector((math.sin(SUN_AZ) * math.cos(e), math.cos(SUN_AZ) * math.cos(e), math.sin(e)))
    sun.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    sun.data.color = col
    sun.data.energy = energy
    sky.sun_elevation = e


def sun_dir(key):
    e = math.radians(KEYS[key][0])
    return Vector((math.sin(SUN_AZ) * math.cos(e), math.cos(SUN_AZ) * math.cos(e), math.sin(e)))


# ---- 立体の下ごしらえ ------------------------------------------------------
def islands_of(bm):
    seen, out = set(), []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, island = [f], []
        seen.add(f.index)
        while stack:
            g = stack.pop()
            island.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index)
                        stack.append(h)
        out.append(island)
    return out


def prepare(ob, max_edge=None, split_angle=None, remove=None):
    """モディファイアを確定し、（必要なら）不要な塊を外し、長い辺を割り、材質の境目と角で頂点を分ける"""
    bpy.context.view_layer.objects.active = ob
    ob.data = ob.data.copy()            # ほかと共有しているメッシュを切り離す
    for m in list(ob.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)
    me = ob.data
    mat_names = [m.name for m in me.materials]
    bm = bmesh.new()
    bm.from_mesh(me)
    info = {}
    if remove:
        kill, info = remove(islands_of(bm), mat_names)
        bmesh.ops.delete(bm, geom=[g for fs in kill for g in fs], context='FACES')
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    if max_edge:
        # 辺ごとに必要な数だけ、1回で割る（割っては三角形にし直すのを繰り返すと、細い三角形が連鎖して増える）
        groups = {}
        for e in bm.edges:
            n = math.ceil(e.calc_length() / max_edge) - 1
            if n > 0:
                groups.setdefault(min(n, 24), []).append(e)
        for n, es in sorted(groups.items()):
            es = [e for e in es if e.is_valid]
            bmesh.ops.subdivide_edges(bm, edges=es, cuts=n, use_grid_fill=False)
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
    if split_angle is not None:
        # 頂点ごとの光がにじまないよう、材質の境目と角は頂点を分ける
        for e in bm.edges:
            lf = e.link_faces
            if len(lf) == 2 and (lf[0].material_index != lf[1].material_index or lf[0].normal.angle(lf[1].normal, 0) > split_angle):
                e.smooth = False
        bmesh.ops.split_edges(bm, edges=[e for e in bm.edges if not e.smooth])
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    return info


# ---- 焼き付け --------------------------------------------------------------
PASSES = {
    'DIFFUSE': {'DIRECT', 'INDIRECT', 'COLOR'},
}


def bake(ob, name, kind, key=None, pass_filter=None):
    me = ob.data
    at = me.color_attributes.get(name) or me.color_attributes.new(name, 'FLOAT_COLOR', 'POINT')
    me.color_attributes.active_color = at
    if key:
        set_sun(key)
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    pf = pass_filter or PASSES.get(kind)
    if pf:
        bpy.ops.object.bake(type=kind, pass_filter=pf, target='VERTEX_COLORS')
    else:
        bpy.ops.object.bake(type=kind, target='VERTEX_COLORS')
    buf = np.empty(len(me.vertices) * 4, np.float32)
    at.data.foreach_get('color', buf)
    return buf.reshape(-1, 4)[:, :3]


def bake_all(ob, lit_kind='DIFFUSE', lit_pass=None):
    """夕日の2通りの高さの拡散光と当たり、隅の暗さを焼く"""
    data = {}
    for key in KEYS:
        data['lit_' + key] = bake(ob, 'lit_' + key, lit_kind, key, lit_pass)
        data['sun_' + key] = bake(ob, 'sun_' + key, 'SHADOW', key)
    data['ao'] = bake(ob, 'ao', 'AO')
    return data


# ---- 書き出し：頂点（位置・法線・焼いた値・材質）と三角形 -----------------------
MATS = {}           # 材質名 → 番号（three.js で照りの強さ・金属かを引く）


def export(ob, data, world=True, origin=None):
    """world=True ならワールド座標で、False ならオブジェクトの原点まわりで（木の原型など）書く"""
    me = ob.data
    me.calc_loop_triangles()
    nv = len(me.vertices)
    pos = np.empty(nv * 3, np.float32)
    me.vertices.foreach_get('co', pos)
    pos = pos.reshape(-1, 3)
    nrm = np.empty(nv * 3, np.float32)
    me.vertices.foreach_get('normal', nrm)
    nrm = nrm.reshape(-1, 3)
    if world:
        M = np.array(ob.matrix_world, np.float32)
        pos = pos @ M[:3, :3].T + M[:3, 3]
        Nm = np.linalg.inv(M[:3, :3]).T
        nrm = nrm @ Nm.T
        nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
    tri = np.empty(len(me.loop_triangles) * 3, np.uint32)
    me.loop_triangles.foreach_get('vertices', tri)
    tmat = np.empty(len(me.loop_triangles), np.int32)
    me.loop_triangles.foreach_get('material_index', tmat)
    gid = np.array([MATS.setdefault(m.name, len(MATS)) for m in me.materials] or [0], np.uint8)
    vmat = np.zeros(nv, np.uint8)
    t3 = tri.reshape(-1, 3)
    for k in range(3):
        vmat[t3[:, k]] = gid[tmat]
    P = np.stack([pos[:, 0], pos[:, 2], -pos[:, 1]], 1)
    Nn = np.stack([nrm[:, 0], nrm[:, 2], -nrm[:, 1]], 1)
    f16 = lambda x: np.ascontiguousarray(x, np.float16)
    u8 = lambda x: np.ascontiguousarray(np.clip(np.round(x * 255), 0, 255), np.uint8)
    blobs = [
        ('position', np.ascontiguousarray(P, np.float32), 3),   # 望遠の寄りで継ぎ目が出ないよう float32
        ('normal', f16(Nn), 3),
        ('lit_hi', f16(np.minimum(data['lit_hi'], 60000)), 3),
        ('lit_lo', f16(np.minimum(data['lit_lo'], 60000)), 3),
        ('shade', u8(np.stack([data['sun_hi'][:, 0], data['sun_lo'][:, 0], data['ao'][:, 0], np.zeros(nv)], 1)), 4),
        ('mat', vmat, 1),
    ]
    return blobs, tri.astype(np.uint32)


def write(out_dir, name, blobs, idx):
    head = {'attributes': [], 'count': int(len(blobs[0][1]))}
    off = 0
    with open(os.path.join(out_dir, name + '.bin'), 'wb') as f:
        for (k, arr, n) in blobs:
            b = arr.tobytes()
            head['attributes'].append({'name': k, 'type': str(arr.dtype), 'size': n, 'offset': off, 'bytes': len(b)})
            f.write(b)
            off += len(b)
            pad = (-off) % 4
            f.write(b'\0' * pad)
            off += pad
        b = idx.tobytes()
        head['index'] = {'type': 'uint32', 'offset': off, 'count': int(len(idx))}
        f.write(b)
    return head


def save_manifest(out_dir, name, manifest):
    manifest['materials'] = {v: k for k, v in MATS.items()}
    manifest['sun'] = {'azimuth': math.degrees(SUN_AZ), 'keys': {k: v[0] for k, v in KEYS.items()}}
    with open(os.path.join(out_dir, name), 'w') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)


# ---- テクスチャへの焼き付け（部材が接し合う建物用） ------------------------------
# 頂点に焼くと、別の部材に接する頂点（柱の上下の端など）がうまく焼けず 0 になる。建物は面の内側で光を測る
TEXEL = 0.025                           # 目標の1テクセルの大きさ（m）
PACK = 0.55                             # 展開した面が画像を埋める割合の見込み
L0, LMAX = 0.0005, 64.0                 # 明るさを対数で 8bit に詰める範囲


def lightmap_size(ob):
    area = sum(p.area for p in ob.data.polygons)
    need = area / (TEXEL * TEXEL) / PACK
    s = 1024
    while s * s < need and s < 4096:
        s *= 2
    return s, area


def unwrap(ob):
    """全部の面を同じ密度で展開して詰める（似た向きでつながった面はひとまとまり）"""
    me = ob.data
    uv = me.uv_layers.new(name='lm')
    me.uv_layers.active = uv
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.0, area_weight=0.0, scale_to_bounds=False)
    size, _ = lightmap_size(ob)
    bpy.ops.uv.pack_islands(rotate=True, margin_method='FRACTION', margin=3.0 / size)
    bpy.ops.object.mode_set(mode='OBJECT')
    return size


TEX_SAMPLES = {'DIFFUSE': 128, 'SHADOW': 16, 'AO': 32}   # 拡散光は多め、光源1つの影と隅の暗さは少なくてもきれいに出る


def bake_tex(ob, img, kind, key=None, pass_filter=None):
    scn.cycles.samples = TEX_SAMPLES.get(kind, scn.cycles.samples)
    for m in ob.data.materials:
        nt = m.node_tree
        n = nt.nodes.get('焼き先') or nt.nodes.new('ShaderNodeTexImage')
        n.name = '焼き先'
        n.image = img
        nt.nodes.active = n
    if key:
        set_sun(key)
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    scn.render.bake.target = 'IMAGE_TEXTURES'
    scn.render.bake.margin = 6
    pf = pass_filter or PASSES.get(kind)
    if pf:
        bpy.ops.object.bake(type=kind, pass_filter=pf, target='IMAGE_TEXTURES')
    else:
        bpy.ops.object.bake(type=kind, target='IMAGE_TEXTURES')
    s = img.size[0]
    px = np.empty(s * s * 4, np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(s, s, 4)[:, :, :3].copy()


def save_png(path, rgb):
    """0〜1 の RGB を 8bit の PNG に（色空間の変換なし）"""
    s = rgb.shape[0]
    img = bpy.data.images.new('書き出し', s, s, alpha=False, float_buffer=False)
    img.colorspace_settings.name = 'Non-Color'
    rgba = np.concatenate([np.clip(rgb, 0, 1), np.ones((s, s, 1), np.float32)], 2)
    img.pixels.foreach_set(rgba.ravel())
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)


def encode_lit(L):
    """明るさ（線形）→ 0〜1：log2(1 + L/L0) / log2(1 + LMAX/L0)。three.js で逆に戻す"""
    return np.log2(1 + np.clip(L, 0, LMAX) / L0) / math.log2(1 + LMAX / L0)


def bake_tex_all(ob, out_dir, name, size, samples_lit=None):
    """拡散光（夕日 2 通り）・夕日の当たり（2 通り）・隅の暗さを焼き、PNG 3 枚に書く"""
    img = bpy.data.images.new('焼き_' + name, size, size, float_buffer=True, alpha=False)
    img.colorspace_settings.name = 'Non-Color'
    maps = {}
    for key in KEYS:
        maps['lit_' + key] = bake_tex(ob, img, 'DIFFUSE', key)
        maps['sun_' + key] = bake_tex(ob, img, 'SHADOW', key)[:, :, 0]
    maps['ao'] = bake_tex(ob, img, 'AO')[:, :, 0]
    bpy.data.images.remove(img)
    # 画像の上下：Blender の uv と同じく下が 0。three.js の TextureLoader は既定の flipY=true でそのまま合う
    files = {}
    for key in KEYS:
        f = f'{name}_lit_{key}.png'
        save_png(os.path.join(out_dir, f), encode_lit(maps['lit_' + key]))
        files['lit_' + key] = f
    f = f'{name}_shade.png'
    save_png(os.path.join(out_dir, f), np.stack([maps['sun_hi'], maps['sun_lo'], maps['ao']], 2))
    files['shade'] = f
    return files, maps


def export_tex(ob):
    """面の展開の継ぎ目と角ごとに頂点を分けて、位置・法線・uv・材質と三角形を書き出す（ワールド座標）"""
    me = ob.data
    me.calc_loop_triangles()
    nl = len(me.loops)
    lv = np.empty(nl, np.int32)
    me.loops.foreach_get('vertex_index', lv)
    uv = np.empty(nl * 2, np.float32)
    me.uv_layers['lm'].data.foreach_get('uv', uv)
    uv = uv.reshape(-1, 2)
    cn = np.empty(nl * 3, np.float32)
    me.corner_normals.foreach_get('vector', cn)
    cn = cn.reshape(-1, 3)
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3)
    # 角ごとの材質
    pm = np.empty(len(me.polygons), np.int32)
    me.polygons.foreach_get('material_index', pm)
    ls = np.empty(len(me.polygons), np.int32)
    me.polygons.foreach_get('loop_start', ls)
    lt = np.empty(len(me.polygons), np.int32)
    me.polygons.foreach_get('loop_total', lt)
    lmat = np.repeat(pm, lt)
    gid = np.array([MATS.setdefault(m.name, len(MATS)) for m in me.materials] or [0], np.uint8)
    # (頂点, uv, 法線) が同じ角はまとめる
    key = np.concatenate([lv[:, None].astype(np.float64), np.round(uv * 65536), np.round(cn * 1000), lmat[:, None]], 1)
    uniq, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.ravel()
    M = np.array(ob.matrix_world, np.float32)
    pos = co[lv[first]] @ M[:3, :3].T + M[:3, 3]
    nrm = cn[first] @ np.linalg.inv(M[:3, :3])
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
    tl = np.empty(len(me.loop_triangles) * 3, np.int32)
    me.loop_triangles.foreach_get('loops', tl)
    idx = inv[tl].astype(np.uint32)
    P = np.stack([pos[:, 0], pos[:, 2], -pos[:, 1]], 1)
    Nn = np.stack([nrm[:, 0], nrm[:, 2], -nrm[:, 1]], 1)
    blobs = [
        ('position', np.ascontiguousarray(P, np.float32), 3),
        ('normal', np.ascontiguousarray(Nn, np.float16), 3),
        ('uv', np.ascontiguousarray(uv[first], np.float32), 2),
        ('mat', np.ascontiguousarray(gid[lmat[first]], np.uint8), 1),
    ]
    return blobs, idx
