"""鳳凰堂の立体に、東岸から見た夕日の逆光を Cycles で焼き付け（テクスチャ）、three.js 用に書き出す。

    blender -b <byodoin.blend> -P bake_hall.py -- 出力ディレクトリ [段 p1,p2,...] [サンプル数]

段ごとに書くもの
  hall_<段>.bin          頂点（位置・法線・uv・材質）と三角形
  hall_<段>_lit_hi.png   拡散光（直接＋間接＋色）、夕日の高さ 7°。明るさは対数で 8bit（common.encode_lit）
  hall_<段>_lit_lo.png   同じく 3.5°
  hall_<段>_shade.png    R=夕日の当たり 7°、G=3.5°、B=隅の暗さ
実物にない翼廊と中堂の軒の釣灯籠と、東岸から真横に見えて浮いた板に見える北の反橋は外す。
"""
import json
import math
import os
import sys
import time

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

a = sys.argv[sys.argv.index('--') + 1:]
OUT = a[0]
PARTS = a[1].split(',') if len(a) > 1 else ['p1', 'p2', 'p3', 'p4', 'p5']
SAMPLES = int(a[2]) if len(a) > 2 else 256
os.makedirs(OUT, exist_ok=True)
C.setup(SAMPLES)


BRIDGE = (0.5, 5.5, 27.0, 40.5)         # 北の反橋の範囲（x0, x1, y0, y1）。東岸からは真横に見え、黒い板が浮いて見えるので外す


def eave_lanterns(islands, mat_names):
    """軒の釣灯籠（灯りを含む高い所の小さな塊と、そのすぐ上に載る金具の笠）と、北の反橋"""
    def box(fs):
        vs = {v for g in fs for v in g.verts}
        xs, ys, zs = [v.co.x for v in vs], [v.co.y for v in vs], [v.co.z for v in vs]
        return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)
    glow, kill = [], []
    for fs in islands:
        mats = {mat_names[g.material_index] for g in fs}
        x0, x1, y0, y1, z0, z1 = box(fs)
        if '灯り' in mats and z0 > 2.5 and x1 - x0 < 0.5 and y1 - y0 < 0.5:
            glow.append(((x0 + x1) / 2, (y0 + y1) / 2, z1))
            kill.append(fs)
    for fs in islands:
        if {mat_names[g.material_index] for g in fs} != {'金具'}:
            continue
        x0, x1, y0, y1, z0, z1 = box(fs)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if x1 - x0 < 0.5 and any(abs(cx - gx) < 0.05 and abs(cy - gy) < 0.05 and abs(z0 - gz) < 0.1 for gx, gy, gz in glow):
            kill.append(fs)
    bridge = 0
    for fs in islands:
        x0, x1, y0, y1, z0, z1 = box(fs)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if BRIDGE[0] < cx < BRIDGE[1] and BRIDGE[2] < cy < BRIDGE[3]:
            kill.append(fs)
            bridge += 1
    return kill, {'lanterns': len(glow), 'bridge_parts': bridge, 'faces': sum(len(fs) for fs in kill)}


path = os.path.join(OUT, 'hall.json')
manifest = json.load(open(path)) if os.path.exists(path) else {'parts': {}}
if 'materials' in manifest:
    C.MATS.update({v: int(k) for k, v in manifest['materials'].items()})   # 材質の番号を前回とそろえる
# 鳳凰は山場の望遠（1画素 約1.5cm）で主役になるので、高欄・鳳凰の段だけ細かく焼く
TEXEL = {'p5': 0.008}
for p in PARTS:
    t0 = time.time()
    C.TEXEL = TEXEL.get(p, 0.025)
    ob = bpy.data.objects['鳳凰堂_' + p]
    info = C.prepare(ob, remove=eave_lanterns)
    ob.data.set_sharp_from_angle(angle=math.radians(30))   # 30° より鋭い角は法線を分ける
    size = C.unwrap(ob)
    files, _ = C.bake_tex_all(ob, OUT, 'hall_' + p, size)
    blobs, idx = C.export_tex(ob)
    head = C.write(OUT, 'hall_' + p, blobs, idx)
    head.update(files=files, size=size, removed=info)
    manifest['parts'][p] = head
    C.save_manifest(OUT, 'hall.json', manifest)      # 段ごとに保存（途中で止まっても続きから）
    print(f'[bake] {p}: 頂点 {head["count"]}、三角形 {len(idx) // 3}、テクスチャ {size}²、'
          f'外した釣灯籠 {info.get("lanterns", 0)} 個・反橋の部材 {info.get("bridge_parts", 0)} 個、{time.time() - t0:.0f} 秒', flush=True)
