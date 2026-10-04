"""Additional edit-mode and UI-context fixtures, loaded by extended suite."""
@case('Armature standardization and manual validation')
def standardize(arm, mesh, props):
    from unittest.mock import patch
    arm.data.bones['Hips'].name='pelvis'
    from avatar_toolkit.functions.tools import standardize_armature
    with patch.object(standardize_armature, 'validate_armature', return_value=(True,[],False)):
        op('avatar_toolkit.standardize_armature')
    assert 'Hips' in arm.data.bones
    op('avatar_toolkit.validate_armature_manual')
    op('avatar_toolkit.highlight_problem_bones')
    op('avatar_toolkit.clear_bone_highlighting')

@case('Digitigrade conversion creates calf and marks original chain')
def digitigrade(arm, mesh, props):
    activate(arm); bpy.ops.object.mode_set(mode='EDIT')
    bones=arm.data.edit_bones
    names=[]
    for side,x in [('L',-1),('R',1)]:
        parent=bones['Hips']
        for i in range(4):
            bone=bones.new(f'Leg{i}.{side}'); bone.head=(x, i*.1, -i); bone.tail=(x,(i+1)*.1,-i-1); bone.parent=parent; parent=bone
        names.append(f'Leg0.{side}')
    bpy.ops.armature.select_all(action='DESELECT')
    for name in names: bones[name].select=True
    old=len(bones)
    op('avatar_toolkit.create_digitigrade')
    assert len(bones)==old+2
    assert len([b for b in bones if '<noik>' in b.name])==4

@case('Shortest seam path selects connected edges')
def seam(arm, mesh, props):
    import bmesh
    activate(mesh); bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='DESELECT')
    bm=bmesh.from_edit_mesh(mesh.data); bm.verts.ensure_lookup_table(); bm.edges.ensure_lookup_table()
    edge=bm.edges[0]; edge.seam=True
    for v in edge.verts: v.select=True
    bmesh.update_edit_mesh(mesh.data)
    op('avatar_toolkit.find_shortest_seam_path')
    assert edge.select

@case('UV edge alignment in Image Editor context')
def uv_alignment(arm, mesh, props):
    from avatar_toolkit.functions.tools.uv_tools import set_uv_vertex_selection
    activate(mesh)
    second=mesh.copy(); second.data=mesh.data.copy(); bpy.context.collection.objects.link(second); second.select_set(True)
    for obj in [mesh, second]:
        for v in obj.data.vertices: v.select=True
        for i in range(len(obj.data.loops)): set_uv_vertex_selection(obj.data,i,i in (0,1))
    for uv in second.data.uv_layers.active.uv: uv.vector.x+=.3
    area=bpy.context.screen.areas[0]; previous=area.type; area.type='IMAGE_EDITOR'; area.ui_type='UV'
    region=next(r for r in area.regions if r.type=='WINDOW')
    try:
        with bpy.context.temp_override(area=area,region=region):
            bpy.context.scene.tool_settings.use_uv_select_sync=False
            bpy.ops.object.mode_set(mode='EDIT')
            op('avatar_toolkit.align_uv_edges_to_target')
            bpy.ops.object.mode_set(mode='OBJECT')
        expected=[tuple(mesh.data.uv_layers.active.uv[i].vector) for i in (0,1)]
        actual=[tuple(second.data.uv_layers.active.uv[i].vector) for i in (0,1)]
        assert all(any((Vector(a)-Vector(b)).length<1e-5 for b in expected) for a in actual), (actual,expected)
    finally: area.type=previous

@case('Material-list selection and expansion controls')
def material_controls(arm, mesh, props):
    mesh.data.materials.append(bpy.data.materials.new('Selectable'))
    for name in ('expand_section_materials','select_all_materials','select_none_materials','expand_all_materials','collapse_all_materials'):
        op('avatar_toolkit.'+name)

@case('Translation operator applies dictionary results in a UI context')
def translate_ui(arm, mesh, props):
    from avatar_toolkit.core.translation_manager import get_avatar_translation_manager, TranslationMode
    manager=get_avatar_translation_manager(); previous=manager.translation_mode; manager.translation_mode=TranslationMode.DICTIONARY_ONLY
    arm.data.bones['Eye_L'].name='\u5de6\u76ee'
    area=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D'); region=next(r for r in area.regions if r.type=='WINDOW')
    try:
        with bpy.context.temp_override(area=area,region=region):
            op('avatar_toolkit.translate_names',translation_type='bones')
        assert '\u5de6\u76ee' not in arm.data.bones
    finally: manager.translation_mode=previous

@case('Panel drawing validates RNA properties and operator identifiers')
def panels(arm, mesh, props):
    from types import SimpleNamespace, MethodType
    import inspect
    from unittest.mock import patch
    from avatar_toolkit.core import auto_load, updater
    class Layout:
        def __getattr__(self,name):
            return lambda *args,**kwargs: Layout()
        def prop(self,data,name,**kwargs):
            assert hasattr(data,name),(type(data),name)
            return Layout()
        def prop_search(self,data,name,search,search_name,**kwargs):
            assert hasattr(data,name),(type(data),name)
            assert hasattr(search,search_name),(type(search),search_name)
            return Layout()
        def operator(self,name,**kwargs):
            space,identifier=name.split('.')
            getattr(getattr(bpy.ops,space),identifier).get_rna_type()
            return SimpleNamespace()
    area=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D'); region=next(r for r in area.regions if r.type=='WINDOW')
    failures=[]; count=0
    with patch.object(updater,'check_for_update_background'), bpy.context.temp_override(area=area,region=region):
        for cls in auto_load.registered_classes:
            if issubclass(cls,bpy.types.Panel) and not '.mmd.' in cls.__module__ and hasattr(cls,'draw'):
                try:
                    holder=SimpleNamespace(layout=Layout())
                    for name, method in inspect.getmembers(cls, inspect.isfunction):
                        setattr(holder,name,MethodType(method,holder))
                    cls.draw(holder,bpy.context); count+=1
                except Exception: failures.append((cls.__name__,traceback.format_exc()))
    assert not failures, failures
    assert count>=10, count

@case('All registered operator polls tolerate empty, mesh, edit and pose contexts')
def operator_polls(arm, mesh, props):
    from avatar_toolkit.core import auto_load
    classes=[c for c in auto_load.registered_classes if issubclass(c,bpy.types.Operator)]
    failures=[]
    activate(arm); bpy.ops.object.select_all(action='DESELECT'); bpy.context.view_layer.objects.active=None
    for target,mode in [(None,None),(mesh,'OBJECT'),(mesh,'EDIT'),(arm,'OBJECT'),(arm,'POSE'),(arm,'EDIT')]:
        if target:
            activate(target)
            if mode!='OBJECT': bpy.ops.object.mode_set(mode=mode)
        for cls in classes:
            if 'poll' in cls.__dict__:
                try: cls.poll(bpy.context)
                except Exception: failures.append((cls.bl_idname,mode,traceback.format_exc()))
    assert not failures, failures

@case('Atlas packs different image sizes and remaps linked meshes once')
def multi_atlas(arm, mesh, props):
    from avatar_toolkit.functions.atlas_materials import get_material_images_from_scene
    activate(mesh)
    for index,size in enumerate((32,64)):
        material=bpy.data.materials.new(f'Packed{index}'); material.include_in_atlas=True
        image=bpy.data.images.new(f'PackedImage{index}',width=size,height=size,alpha=True)
        image.pixels[:]=([1,0,0,1] if index==0 else [0,1,0,1])*(size*size)
        node=material.node_tree.nodes.new("ShaderNodeTexImage"); node.image=image
        material.texture_atlas_albedo=image.name; mesh.data.materials.append(material)
    mesh.data.polygons[0].material_index=1
    instance=mesh.copy(); bpy.context.collection.objects.link(instance)
    assert instance.data==mesh.data
    assert len(get_material_images_from_scene(bpy.context))==2
    original=[tuple(uv.vector) for uv in mesh.data.uv_layers.active.uv]
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'multi_atlas.blend'))
    props.texture_atlas_Has_Mat_List_Shown=True
    op('avatar_toolkit.atlas_materials')
    material=mesh.data.materials[0]; image=next(n.image for n in material.node_tree.nodes if n.type=='TEX_IMAGE' and n.image.name.startswith('Atlas_albedo'))
    assert tuple(image.size)==(96,64), tuple(image.size)
    colors=list(image.pixels[:])
    assert sum(colors[i]>.9 and colors[i+1]<.1 for i in range(0,len(colors),4))==32*32
    assert sum(colors[i+1]>.9 and colors[i]<.1 for i in range(0,len(colors),4))==64*64
    # Red (32px) placed to the right of green (64px), not remapped again for the instance.
    loop=mesh.data.polygons[1].loop_indices[0]
    expected=(original[loop][0]*32/96+64/96,original[loop][1]*32/64)
    assert (Vector(mesh.data.uv_layers.active.uv[loop].vector)-Vector(expected)).length<1e-5

@case('AnimX quaternion coordinate conversion and cubic tangent handles')
def animx_rotation_curves(arm, mesh, props):
    import struct
    from io import BytesIO
    from avatar_toolkit.core.resonite_loader import common
    from avatar_toolkit.core.animation import ensure_channelbag
    header=BytesIO(); common.WriteCSharp_str(header,'AnimX'); header.write(bytes([1,2])); header.write(struct.pack('<f',1)); common.WriteCSharp_str(header,'QuaternionCurve'); header.write(bytes([0]))
    payload=BytesIO(); payload.write(bytes([0,25])); common.WriteCSharp_str(payload,'Hips'); common.WriteCSharp_str(payload,'Rotation'); payload.write(bytes([1])); payload.write(struct.pack('<fffff',1,0,0,2**-.5,2**-.5))
    payload.write(bytes([2,23])); common.WriteCSharp_str(payload,'Hips'); common.WriteCSharp_str(payload,'Position'); payload.write(bytes([2,2,3])); payload.write(struct.pack('<ffffffff',0,0,0,0,1,2,3,1))
    payload.write(struct.pack('<ffffffffffff',3,6,9,3,6,9,3,6,9,3,6,9))
    path=OUT/'quaternion-tangents.animx'; path.write_bytes(header.getvalue()+payload.getvalue()); activate(arm)
    op('avatar_toolkit.animx_importer',filepath=str(path))
    bag=ensure_channelbag(arm.animation_data.action,arm)
    path=arm.pose.bones['Hips'].path_from_id('rotation_quaternion')
    assert abs(bag.fcurves.find(path,index=0).evaluate(0)-2**-.5)<1e-5
    assert abs(bag.fcurves.find(path,index=2).evaluate(0)+2**-.5)<1e-5
    path=arm.pose.bones['Hips'].path_from_id('location'); curve=bag.fcurves.find(path,index=0)
    assert curve.keyframe_points[0].interpolation=='BEZIER'
    assert abs(curve.keyframe_points[0].handle_right.y-1)<1e-5

@case('Eye testing helper resets pose selections with Blender 5 API')
def eye_helper(arm,mesh,props):
    from avatar_toolkit.functions import eye_tracking as eye
    arm.data.bones['Eye_L'].name='LeftEye'; arm.data.bones['Eye_R'].name='RightEye'
    op('avatar_toolkit.start_eye_testing')
    props.eye_rotation_x=5
    eye.stop_testing(bpy.context)
    assert props.eye_rotation_x==0
    assert eye.eye_left is None
