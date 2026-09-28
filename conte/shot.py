"""コンテの下絵：平等院のシーンの完成状態（最終コマ）を、夕日の向きと高さを変えて撮る。

    blender -b <byodoin.blend> -P shot.py -- 出力.png 日の方位° 日の高さ° カメラx y z 注視点x y z レンズmm [解像度% 霞の濃さ 空の強さ]
方位は北から時計回り（270=真西）。座標は byodoin の geometry.py（x=東 y=北 z=上、原点=中堂）。
"""
import math
import sys

import bpy
from mathutils import Vector

a = sys.argv[sys.argv.index('--') + 1:]
out = a[0]
az, el = math.radians(float(a[1])), math.radians(float(a[2]))
cx, cy, cz, tx, ty, tz, lens = map(float, a[3:10])
pct = int(a[10]) if len(a) > 10 else 50
HAZE = float(a[11]) if len(a) > 11 else 0.0012
SKY = float(a[12]) if len(a) > 12 else 0.35

scn = bpy.context.scene
scn.frame_set(scn.frame_end)

# 夕日：光源と空の太陽を同じ向きに
sun = bpy.data.objects['夕日']
sun.animation_data_clear()
sun.data.animation_data_clear()
sun.data.energy = 3.0
sdir = Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
sun.rotation_euler = (-sdir).to_track_quat('-Z', 'Y').to_euler()
for n in scn.world.node_tree.nodes:
    if n.type == 'TEX_SKY':
        n.sun_elevation = el
        n.sun_rotation = az  # 空の太陽は方位そのまま（光源と向きをそろえる）

# 西は宇治の平地：遠景の山と森を外し、霞を薄く、空の回り込みを弱めて逆光に
for name in ('地形_遠景', '木_遠景'):
    bpy.data.objects[name].hide_render = True
    bpy.data.objects[name].animation_data_clear()
for n in bpy.data.materials['霞'].node_tree.nodes:
    if n.type == 'VALUE':
        n.outputs[0].animation_data_clear() if hasattr(n.outputs[0], 'animation_data_clear') else None
bpy.data.materials['霞'].node_tree.animation_data_clear()
for n in bpy.data.materials['霞'].node_tree.nodes:
    if n.type == 'VALUE':
        n.outputs[0].default_value = HAZE
scn.world.node_tree.animation_data_clear()
scn.world.node_tree.nodes['Background'].inputs['Strength'].default_value = SKY

cam = scn.camera
tgt = bpy.data.objects['注視点']
for idb in (cam, tgt, cam.data):
    idb.animation_data_clear()
cam.location = (cx, cy, cz)
tgt.location = (tx, ty, tz)
cam.data.lens = lens
cam.data.clip_end = 5000
# 太陽の円盤：視直径 0.53° の光る球を、太陽の方向の十分遠くに置く（空の円盤は霞で見えなくなるため）
R = 3000.0
disc_m = bpy.data.materials.new('日輪')
disc_m.use_nodes = True
nt = disc_m.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
em = nt.nodes.new('ShaderNodeEmission')
em.inputs['Color'].default_value = (1.0, 0.55, 0.22, 1)
em.inputs['Strength'].default_value = 60.0
o = nt.nodes.new('ShaderNodeOutputMaterial')
nt.links.new(em.outputs[0], o.inputs['Surface'])
bpy.ops.mesh.primitive_uv_sphere_add(radius=R * math.tan(math.radians(0.265)), segments=48, ring_count=24,
                                     location=Vector((cx, cy, cz)) + sdir * R)
disc = bpy.context.active_object
disc.data.materials.append(disc_m)
disc.visible_shadow = False

scn.render.resolution_percentage = pct
scn.render.filepath = out
bpy.ops.render.render(write_still=True)
