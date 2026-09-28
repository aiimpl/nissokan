"""焼き付けと同じ夕空（Blender の多重散乱の空）を、全天の表として three.js 用に書き出す。

    blender -b <byodoin.blend> -P sky.py -- 出力ディレクトリ

出力 sky_hi.bin / sky_lo.bin：float16 の RGB、横 SW × 縦 SH。横は方位（左端=北、時計回り）、
縦は仰角（上端=+90°、下端=-10°）。太陽の円盤は含めない（three.js 側で描く）。
"""
import math
import os
import sys

import bpy
import numpy as np

OUT = sys.argv[sys.argv.index('--') + 1]
os.makedirs(OUT, exist_ok=True)
SW, SH = 2048, 576                    # 仰角 -10〜90° を 576 行（約0.17°刻み）
SUN_AZ = math.radians(270.0)
KEYS = {'hi': 7.0, 'lo': 3.5}
SKY_STRENGTH = 0.5

scn = bpy.context.scene
scn.frame_set(scn.frame_end)
wt = scn.world.node_tree
wt.animation_data_clear()
sky = next(n for n in wt.nodes if n.type == 'TEX_SKY')
sky.sun_disc = False
sky.sun_rotation = SUN_AZ
wt.nodes['Background'].inputs['Strength'].default_value = SKY_STRENGTH
# 見え隠れにキーが打ってあるので、先にアニメーションを消してから隠す（消さないと描くときに戻る）
for ob in bpy.data.objects:
    ob.animation_data_clear()
    ob.hide_render = ob.type != 'CAMERA'

scn.render.engine = 'CYCLES'
scn.cycles.samples = 16
scn.cycles.use_denoising = False
scn.render.use_compositing = False
scn.render.film_transparent = False
scn.view_settings.view_transform = 'Standard'
scn.render.image_settings.file_format = 'OPEN_EXR'
scn.render.image_settings.color_depth = '32'
scn.render.resolution_x, scn.render.resolution_y = 4096, 2048
scn.render.resolution_percentage = 100

# 全天のカメラ：まっすぐ上を向けずに水平に置き、正距円筒で撮る
cam = scn.camera
cam.animation_data_clear()
cam.constraints.clear()
cam.location = (0, 0, 30)          # 建物より高い所（隠しても念のため）
cam.rotation_euler = (math.pi / 2, 0, 0)       # 水平・北（+Y）向き
cam.data.animation_data_clear()
cam.data.type = 'PANO'
cam.data.panorama_type = 'EQUIRECTANGULAR'

for key, el in KEYS.items():
    sky.sun_elevation = math.radians(el)
    path = os.path.join(OUT, f'_sky_{key}.exr')
    scn.render.filepath = path
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(path)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)[::-1, :, :3]        # 上端=天頂に
    # 画像の列 → 方位：中央が正面（北）。列 u の方位 = (u/w - 0.5) * 360°（右へ行くほど東回り）
    az = (np.arange(SW) + 0.5) / SW * 360.0             # 出力の列の方位（北から時計回り）
    col = ((az / 360.0 + 0.5) % 1.0) * w
    # 行 → 仰角：上端 +90°、下端 -90°
    elv = 90.0 - (np.arange(SH) + 0.5) / SH * 100.0     # 出力の行の仰角
    row = (90.0 - elv) / 180.0 * h
    ci = np.clip(col.astype(int), 0, w - 1)
    ri = np.clip(row.astype(int), 0, h - 1)
    out = px[ri][:, ci]
    np.ascontiguousarray(out, np.float16).tofile(os.path.join(OUT, f'sky_{key}.bin'))
    # 向きの確かめ：太陽の方位のあたりが一番明るいはず
    lum = out[:, :, 0] + out[:, :, 1] + out[:, :, 2]
    r, c = np.unravel_index(np.argmax(lum[: SH * 9 // 10]), lum.shape)
    print(f'[sky] {key}: 最も明るい所 方位 {az[c]:.1f}° 仰角 {elv[r]:.1f}°', flush=True)
    os.remove(path)
