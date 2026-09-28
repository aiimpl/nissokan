import bpy
scn = bpy.context.scene
scn.frame_set(scn.frame_end)
for o in bpy.data.objects:
    if o.type != 'MESH' or o.hide_render:
        continue
    mods = [(m.type, m.name) for m in o.modifiers]
    mats = [m.name for m in o.data.materials if m]
    print(f'{o.name}\tv={len(o.data.vertices)}\tf={len(o.data.polygons)}\tmods={mods}\tmats={mats[:12]}{"..." if len(mats)>12 else ""}\tcoll={o.users_collection[0].name}')
