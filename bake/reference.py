"""答え合わせ用：焼き付けと同じ光・同じ世界で、Cycles が直接描いた1枚。

    blender -b <byodoin.blend> -P reference.py -- 出力.png 夕日のキー(hi/lo) カメラx y z 注視点x y z レンズmm [サンプル数]
"""
import math
import sys

import bpy
from mathutils import Vector

a = sys.argv[sys.argv.index('--') + 1:]
OUT, KEY = a[0], a[1]
cx, cy, cz, tx, ty, tz, lens = map(float, a[2:9])
SAMPLES = int(a[9]) if len(a) > 9 else 128
SUN_AZ = math.radians(270.0)
KEYS = {
    'hi': (7.0, (1.0, 0.62, 0.34), 4.0),
    'lo': (3.5, (1.0, 0.47, 0.20), 3.0),
}
SKY_STRENGTH = 0.5

scn = bpy.context.scene
scn.frame_set(scn.frame_end)

# ---- 焼くときの世界：西は平地、霞・工房・巻物・墨線は外す -------------------
HIDE = ('地形_遠景', '木_遠景', '霞', '工房ドーム', '台', '工房の光', '工房の補助光')
for ob in bpy.data.objects:
    ob.animation_data_clear()
    if ob.name in HIDE or ob.users_collection[0].name in ('墨線', '巻物'):
        ob.hide_render = True
for ob in bpy.data.objects:
    if ob.type == 'LIGHT':
        ob.data.animation_data_clear()
wt = scn.world.node_tree
wt.animation_data_clear()
for n in wt.nodes:
    if n.type == 'TEX_SKY':
        sky = n
sky.sun_disc = False                    # 直射は光源の夕日だけに（二重にしない）
sky.sun_rotation = SUN_AZ
wt.nodes['Background'].inputs['Strength'].default_value = SKY_STRENGTH
sun = bpy.data.objects['夕日']


def set_sun(key):
    el, col, energy = KEYS[key]
    e = math.radians(el)
    d = Vector((math.sin(SUN_AZ) * math.cos(e), math.cos(SUN_AZ) * math.cos(e), math.sin(e)))
    sun.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    sun.data.color = col
    sun.data.energy = energy
    sky.sun_elevation = e


# ---- Cycles ---------------------------------------------------------------
scn.render.engine = 'CYCLES'
prefs = bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type = 'METAL'
prefs.get_devices()
for d in prefs.devices:
    d.use = True
scn.cycles.device = 'GPU'
scn.cycles.samples = SAMPLES
scn.cycles.use_denoising = False
scn.render.bake.target = 'VERTEX_COLORS'
scn.render.bake.margin = 0


set_sun(KEY)
cam = scn.camera
tgt = bpy.data.objects['注視点']
cam.location = (cx, cy, cz)
tgt.location = (tx, ty, tz)
cam.data.lens = lens
cam.data.clip_end = 5000
scn.view_settings.view_transform = 'Standard'
scn.cycles.use_denoising = True
scn.render.resolution_percentage = 50
scn.render.filepath = OUT
bpy.ops.render.render(write_still=True)
