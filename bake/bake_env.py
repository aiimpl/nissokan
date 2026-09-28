"""池のまわり（地形・洲浜と庭石・木）に、鳳凰堂と同じ夕日を焼き付けて書き出す。

    blender -b <byodoin.blend> -P bake_env.py -- 出力ディレクトリ [サンプル数] [焼くもの terrain,stones,trees]

木は種類ごとの原型を一度だけ焼き（葉は逆光で透ける光も含める）、並べ方は1本ずつの変換と
「樹冠に夕日が当たるか」で書く（three.js ではインスタンスで並べ、当たらない木は暗くする）。
"""
import json
import os
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

a = sys.argv[sys.argv.index('--') + 1:]
OUT = a[0]
SAMPLES = int(a[1]) if len(a) > 1 else 128
WHAT = a[2].split(',') if len(a) > 2 else ['terrain', 'stones', 'trees']
os.makedirs(OUT, exist_ok=True)
C.setup(SAMPLES)
path = os.path.join(OUT, 'env.json')
manifest = json.load(open(path)) if os.path.exists(path) else {'parts': {}, 'trees': {}}
if 'materials' in manifest:
    C.MATS.update({v: int(k) for k, v in manifest['materials'].items()})   # 材質の番号を前回とそろえる

# ---- 地形 ------------------------------------------------------------------
if 'terrain' in WHAT:
    ob = bpy.data.objects['地形_近景']
    C.prepare(ob)
    blobs, idx = C.export(ob, C.bake_all(ob))
    manifest['parts']['terrain'] = C.write(OUT, 'env_terrain', blobs, idx)
    print(f'[env] 地形: 頂点 {len(ob.data.vertices)}', flush=True)

# ---- 洲浜と庭石：1つにまとめて焼く -----------------------------------------------
if 'stones' in WHAT:
    # 庭石は堂の背後（西）のものだけ。東の池の中の石は、映りとくっついて水の上に浮いた塊に見えるので外す
    stones = [bpy.data.objects['洲浜']] + [o for o in bpy.data.objects if o.name.startswith('庭石_') and o.location.x < 12]
    bpy.ops.object.select_all(action='DESELECT')
    for o in stones:
        o.data = o.data.copy()
        o.select_set(True)
    bpy.context.view_layer.objects.active = stones[0]
    bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    C.prepare(ob, split_angle=0.6)
    blobs, idx = C.export(ob, C.bake_all(ob))
    manifest['parts']['stones'] = C.write(OUT, 'env_stones', blobs, idx)
    print(f'[env] 洲浜と庭石: 頂点 {len(ob.data.vertices)}', flush=True)

# ---- 木：並べ方を先に読む（原型を動かす前に） -----------------------------------
dg = bpy.context.evaluated_depsgraph_get()
SPAWNERS = ('木_近景', '松_中島')
insts = {}
for inst in dg.object_instances:
    if not inst.is_instance or inst.parent is None or inst.parent.original.name not in SPAWNERS:
        continue
    t = inst.object.original.name
    insts.setdefault(t, []).append(Matrix(inst.matrix_world))
print('[env] 木の本数', {k: len(v) for k, v in insts.items()}, flush=True)


# 種類ごとの樹冠の半径（原型の水平の広がり）
RADIUS = {}
for _c in ('木_近景_種類', '松_中島_種類'):
    for _o in bpy.data.collections[_c].objects:
        _xs = [v[0] for v in _o.bound_box]
        _ys = [v[1] for v in _o.bound_box]
        RADIUS[_o.name] = 0.5 * max(max(_xs) - min(_xs), max(_ys) - min(_ys))


def same(Ma, Mb):
    return all(abs(Ma[i][j] - Mb[i][j]) < 1e-3 for i in range(3) for j in range(4))


def tree_sun(M, top):
    """樹冠（原型の高さの 7 割）から夕日の方へ光線を飛ばす。自分の木の葉や枝は通り抜けて、ほかの物に当たれば 0"""
    dg_ = bpy.context.evaluated_depsgraph_get()
    out = []
    for key in C.KEYS:
        d = C.sun_dir(key)
        base = M @ Vector((0, 0, 0))
        o = M @ Vector((0, 0, top * 0.7))
        lit = 1.0
        for _ in range(64):
            hit, loc, _n, _i, _ob, hm = C.scn.ray_cast(dg_, o, d, distance=3000)
            if not hit:
                break
            # 自分の木の葉や枝、描画では外している物（西の山・霞の箱など）は通り抜ける。
            # 並べた木に当たると、光線は1本ずつではなく並べる元のオブジェクトを返すので、幹からの水平距離で自分の樹冠かを見分ける
            # 当たった物が木なら、光線は並べた1本ではなく種類の原型を返す。自分の幹から樹冠の半径以内なら自分の木
            name = _ob.original.name
            coll = _ob.original.users_collection[0].name if _ob.original.users_collection else ''
            own = name in RADIUS and (loc.xy - base.xy).length < RADIUS[name]
            far = coll == '木_遠景_種類'           # 遠景の木は描画でも外している
            if same(hm, M) or own or far or _ob.original.hide_render or name in C.HIDE:
                o = loc + d * 0.01
                continue
            lit = 0.0
            break
        out.append(lit)
    return out


# three.js の座標へ：p' = K p（x, z, -y）
K = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, 0), (0, 0, 0, 1)))
Ki = K.inverted()

tree_data = {}
for t, Ms in (insts.items() if 'trees' in WHAT else []):
    proto = bpy.data.objects[t]
    top = max(v[2] for v in proto.bound_box)
    rows = []
    for M in Ms:
        vis = tree_sun(M, top)
        T = K @ M @ Ki
        rows.append([round(x, 5) for col in T.col for x in col] + vis)
    tree_data[t] = rows

# ---- 木の原型を焼く：池から離れた北の空き地に写して、葉の透ける光も含める -----------------
FAR = Vector((0, 2600, 0))
LEAF_PASS = {'DIRECT', 'INDIRECT', 'DIFFUSE', 'TRANSMISSION', 'EMIT'}
for t, rows in tree_data.items():
    proto = bpy.data.objects[t]
    cp = proto.copy()
    cp.data = proto.data.copy()
    C.scn.collection.objects.link(cp)
    cp.hide_render = False
    cp.matrix_world = Matrix.Translation(FAR)
    C.prepare(cp)
    data = C.bake_all(cp, lit_kind='COMBINED', lit_pass=LEAF_PASS)
    blobs, idx = C.export(cp, data, world=False)
    head = C.write(OUT, 'tree_' + t, blobs, idx)
    head['instances'] = rows
    manifest['trees'][t] = head
    print(f'[env] 木 {t}: 頂点 {len(cp.data.vertices)}、{len(rows)} 本、夕日が当たる {sum(r[-1] for r in rows):.0f} 本', flush=True)

C.save_manifest(OUT, 'env.json', manifest)
print('[env] 書き出し完了', flush=True)
