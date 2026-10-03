"""Feature regression suite; run in Blender with --background --factory-startup."""
import importlib.util
import json
import pathlib
import sys
import traceback
import bpy
from mathutils import Vector

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / '.validation'
OUT.mkdir(exist_ok=True)
spec = importlib.util.spec_from_file_location('avatar_toolkit', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
addon = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = addon
spec.loader.exec_module(addon)
addon.register()
results = []
covered = set()

def activate(obj):
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    obj.hide_viewport = False
    obj.hide_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

def op(name, **kwargs):
    namespace, identifier = name.split('.')
    result = getattr(getattr(bpy.ops, namespace), identifier)(**kwargs)
    assert result == {'FINISHED'}, (name, result)
    covered.add(name)
    return result

def fixture():
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.object.armature_add()
    arm = bpy.context.object
    arm.name = 'Avatar'
    bpy.ops.object.mode_set(mode='EDIT')
    bones = arm.data.edit_bones
    bones.remove(bones[0])
    definitions = [('Hips', None, (0,0,0)), ('Spine','Hips',(0,0,1)), ('Chest','Spine',(0,0,2)), ('Neck','Chest',(0,0,3)), ('Head','Neck',(0,0,4)), ('Eye_L','Head',(-.2,0,4.5)), ('Eye_R','Head',(.2,0,4.5)), ('Unused','Hips',(1,0,0))]
    for name, parent, head in definitions:
        bone = bones.new(name)
        bone.head = head
        bone.tail = Vector(head) + Vector((0,0,.5))
        if parent:
            bone.parent = bones[parent]
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.mesh.primitive_cube_add()
    mesh = bpy.context.object
    mesh.name = 'Body'
    mesh.parent = arm
    mod = mesh.modifiers.new('Armature', 'ARMATURE')
    mod.object = arm
    mesh.vertex_groups.new(name='Hips').add(list(range(8)), 1, 'REPLACE')
    mesh.vertex_groups.new(name='Eye_L').add([0,1], 1, 'REPLACE')
    mesh.vertex_groups.new(name='Eye_R').add([4,5], 1, 'REPLACE')
    mesh.shape_key_add(name='Basis')
    for index, name in enumerate(('A','O','CH','WinkL','WinkR','LowerL','LowerR')):
        key = mesh.shape_key_add(name=name)
        key.data[index % 8].co.z += .05 * (index+1)
    mesh.shape_key_add(name='Empty')
    props = bpy.context.scene.avatar_toolkit
    props.active_armature = 'ARM_' + str(arm.as_pointer())
    props.validation_mode = 'NONE'
    props.viseme_mesh = 'MESH_' + str(mesh.as_pointer())
    props.mouth_a, props.mouth_o, props.mouth_ch = 'A', 'O', 'CH'
    props.head, props.eye_left, props.eye_right = 'Head', 'Eye_L', 'Eye_R'
    props.mesh_name_eye = mesh.name
    props.wink_left, props.wink_right = 'WinkL', 'WinkR'
    props.lowerlid_left, props.lowerlid_right = 'LowerL', 'LowerR'
    props.disable_eye_movement = props.disable_eye_blinking = False
    activate(arm)
    return arm, mesh, props

def case(name):
    def decorate(fn):
        try:
            arm, mesh, props = fixture()
            fn(arm, mesh, props)
            results.append({'test': name, 'status': 'PASS'})
            print('FEATURE_PASS', name, flush=True)
        except Exception:
            detail = traceback.format_exc()
            results.append({'test': name, 'status': 'FAIL', 'detail': detail})
            print('FEATURE_FAIL', name, detail, flush=True)
        return fn
    return decorate

@case('Viseme generation, preview and second avatar isolation')
def visemes(arm, mesh, props):
    op('avatar_toolkit.create_visemes')
    assert len([k for k in mesh.data.shape_keys.key_blocks if k.name.startswith('vrc.v_')]) == 15
    assert abs(mesh.data.shape_keys.key_blocks['vrc.v_aa'].data[0].co.z - mesh.data.shape_keys.key_blocks['Basis'].data[0].co.z - .05*.9998) < 1e-5
    op('avatar_toolkit.preview_visemes')
    assert mesh.data.shape_keys.key_blocks['A'].value > .9
    op('avatar_toolkit.preview_visemes')
    assert mesh.data.shape_keys.key_blocks['A'].value == 0
    arm, mesh, props = fixture()
    op('avatar_toolkit.create_visemes')
    assert 'vrc.v_aa' in mesh.data.shape_keys.key_blocks

@case('AV3 eye bone creation and rotation')
def av3(arm, mesh, props):
    op('avatar_toolkit.create_eye_tracking_av3')
    assert arm.data.bones['Eye_L'].parent.name == 'Head'
    assert arm.data.bones['Eye_L'].length > 0
    op('avatar_toolkit.rotate_eye_bones')

@case('SDK2 eye setup creates blink and lowerlid shapes')
def sdk2(arm, mesh, props):
    op('avatar_toolkit.create_eye_tracking_sdk2')
    for name in ('LeftEye','RightEye'):
        assert name in arm.data.bones and name in mesh.vertex_groups
    for name in ('vrc.blink_left','vrc.blink_right','vrc.lowerlid_left','vrc.lowerlid_right'):
        assert name in mesh.data.shape_keys.key_blocks, name

@case('Eye testing, rotation, blinking, adjustment and reset')
def eye_tests(arm, mesh, props):
    arm.data.bones['Eye_L'].name = 'LeftEye'
    arm.data.bones['Eye_R'].name = 'RightEye'
    mesh.vertex_groups['Eye_L'].name = 'LeftEye'
    mesh.vertex_groups['Eye_R'].name = 'RightEye'
    props.eye_left, props.eye_right = 'LeftEye','RightEye'
    for source, target in [('WinkL','vrc.blink_left'),('WinkR','vrc.blink_right'),('LowerL','vrc.lowerlid_left'),('LowerR','vrc.lowerlid_right')]:
        mesh.data.shape_keys.key_blocks[source].name = target
    op('avatar_toolkit.start_eye_testing')
    props.eye_rotation_x = 10
    from avatar_toolkit.functions.eye_tracking import set_rotation
    set_rotation(props, bpy.context)
    assert abs(arm.pose.bones['LeftEye'].rotation_euler.x) > .1
    op('avatar_toolkit.reset_eye_rotation')
    op('avatar_toolkit.test_blinking')
    assert mesh.data.shape_keys.key_blocks['vrc.blink_left'].value == 1
    op('avatar_toolkit.test_lowerlid')
    assert mesh.data.shape_keys.key_blocks['vrc.lowerlid_left'].value == 1
    op('avatar_toolkit.reset_blink_test')
    assert all(k.value == 0 for k in mesh.data.shape_keys.key_blocks)
    op('avatar_toolkit.adjust_eyes')
    op('avatar_toolkit.stop_eye_testing')
    props.iris_height = 1
    op('avatar_toolkit.adjust_iris_height')
    op('avatar_toolkit.reset_eye_tracking')

@case('Mesh attachment assigns weights and bone')
def attach(arm, mesh, props):
    bpy.ops.mesh.primitive_cube_add()
    accessory = bpy.context.object
    accessory.name = 'Hat'
    props.attach_mesh, props.attach_bone = accessory.name, 'Head'
    activate(arm)
    op('avatar_toolkit.attach_mesh')
    assert accessory.parent == arm
    assert arm.data.bones['Hat'].parent.name == 'Head'
    assert accessory.vertex_groups['Hat'].weight(0) == 1
    assert any(m.type == 'ARMATURE' and m.object == arm for m in accessory.modifiers)

@case('Modifier application preserves all shape keys')
def modifier(arm, mesh, props):
    activate(mesh)
    mod = mesh.modifiers.new('Subdivide', 'SUBSURF')
    mod.levels = 1
    expected = [k.name for k in mesh.data.shape_keys.key_blocks]
    op('avatar_toolkit.apply_shapekey_force', modifier=mod.name)
    assert len(mesh.data.vertices) > 8
    assert [k.name for k in mesh.data.shape_keys.key_blocks] == expected
    assert all(len(k.data) == len(mesh.data.vertices) for k in mesh.data.shape_keys.key_blocks)

@case('Transforms and empty shape-key cleanup')
def cleanup(arm, mesh, props):
    arm.scale = (2,2,2)
    op('avatar_toolkit.apply_transforms')
    assert tuple(arm.scale) == (1,1,1)
    op('avatar_toolkit.clean_shapekeys')
    assert 'Empty' not in mesh.data.shape_keys.key_blocks
    assert 'A' in mesh.data.shape_keys.key_blocks

@case('Unused weights, groups and bone constraint cleanup')
def bone_cleanup(arm, mesh, props):
    arm.pose.bones['Head'].constraints.new('COPY_LOCATION')
    op('avatar_toolkit.clean_constraints')
    assert not arm.pose.bones['Head'].constraints
    mesh.vertex_groups.new(name='UnusedGroup')
    op('avatar_toolkit.clean_vertex_groups')
    assert 'UnusedGroup' not in mesh.vertex_groups
    props.list_only_mode = False
    op('avatar_toolkit.clean_weights')
    assert 'Unused' not in arm.data.bones

@case('Bone connection')
def connect(arm, mesh, props):
    op('avatar_toolkit.connect_bones')
    assert (arm.data.bones['Spine'].tail_local - arm.data.bones['Chest'].head_local).length < 1e-5

def selected_bones(arm, names, active):
    activate(arm)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.armature.select_all(action='DESELECT')
    for name in names:
        bone = arm.data.edit_bones[name]
        bone.select = bone.select_head = bone.select_tail = True
    arm.data.edit_bones.active = arm.data.edit_bones[active]

@case('Merge bones to active transfers vertex weights')
def merge_active(arm, mesh, props):
    selected_bones(arm, ['Hips','Eye_L'], 'Hips')
    op('avatar_toolkit.merge_to_active')
    bpy.ops.object.mode_set(mode='OBJECT')
    assert 'Eye_L' not in arm.data.bones
    assert 'Eye_L' not in mesh.vertex_groups

@case('Merge bones to parent transfers vertex weights')
def merge_parent(arm, mesh, props):
    selected_bones(arm, ['Eye_L'], 'Eye_L')
    op('avatar_toolkit.merge_to_parent')
    bpy.ops.object.mode_set(mode='OBJECT')
    assert 'Eye_L' not in arm.data.bones
    assert mesh.vertex_groups['Head'].weight(0) > 0

@case('Remove selected bones')
def remove_bones(arm, mesh, props):
    selected_bones(arm, ['Unused'], 'Unused')
    op('avatar_toolkit.remove_selected_bones')
    bpy.ops.object.mode_set(mode='OBJECT')
    assert 'Unused' not in arm.data.bones

@case('Join selected avatar meshes preserves shapes')
def join_selected(arm, mesh, props):
    second = mesh.copy()
    second.data = mesh.data.copy()
    bpy.context.collection.objects.link(second)
    activate(mesh)
    second.select_set(True)
    op('avatar_toolkit.join_selected_meshes')
    assert len(mesh.data.vertices) == 16
    assert len(mesh.data.shape_keys.key_blocks['A'].data) == 16

@case('Join all avatar meshes')
def join_all(arm, mesh, props):
    second = mesh.copy()
    second.data = mesh.data.copy()
    bpy.context.collection.objects.link(second)
    op('avatar_toolkit.join_all_meshes')
    assert len([o for o in bpy.context.scene.objects if o.type == 'MESH' and o.parent == arm]) == 1

@case('Material consolidation')
def consolidate(arm, mesh, props):
    first = bpy.data.materials.new('Shared')
    second = first.copy()
    second.name = 'Shared.001'
    mesh.data.materials.append(first)
    mesh.data.materials.append(second)
    mesh.data.polygons[0].material_index = 1
    op('avatar_toolkit.combine_materials')
    assert len(mesh.data.materials) == 1

@case('Separate materials')
def separate_materials(arm, mesh, props):
    mesh.data.materials.append(bpy.data.materials.new('One'))
    mesh.data.materials.append(bpy.data.materials.new('Two'))
    mesh.data.polygons[0].material_index = 1
    activate(mesh)
    op('avatar_toolkit.separate_materials')
    assert len([o for o in bpy.context.scene.objects if o.type == 'MESH']) == 2

@case('Separate loose mesh parts')
def separate_loose(arm, mesh, props):
    activate(mesh)
    second = mesh.copy()
    second.data = mesh.data.copy()
    bpy.context.collection.objects.link(second)
    second.select_set(True)
    bpy.ops.object.join()
    op('avatar_toolkit.separate_loose')
    assert len([o for o in bpy.context.scene.objects if o.type == 'MESH']) == 2

@case('Armature merging retains accessory bones and parenting')
def armature_merge(arm, mesh, props):
    bpy.ops.object.armature_add()
    other = bpy.context.object
    other.name = 'AccessoryRig'
    other.data.bones[0].name = 'Accessory'
    props.merge_armature_into, props.merge_armature = arm.name, other.name
    props.join_meshes = False
    op('avatar_toolkit.merge_armatures')
    assert len([o for o in bpy.context.scene.objects if o.type == 'ARMATURE']) == 1
    assert 'Accessory' in arm.data.bones
    assert mesh.parent == arm

@case('Rigify metarig conversion')
def rigify(arm, mesh, props):
    arm.name = 'metarig'
    arm.data.bones['Spine'].name = 'spine'
    op('avatar_toolkit.convert_rigify_to_unity')
    assert arm.name == 'Armature'
    assert 'Spine' in arm.data.bones

@case('VRM conversion and collider removal')
def vrm(arm, mesh, props):
    arm.data.bones['Hips'].name = 'J_Bip_C_Hips'
    collider = bpy.data.objects.new('VRM_Collider', None)
    bpy.context.collection.objects.link(collider)
    collider.parent = arm
    op('avatar_toolkit.remove_all_colliders')
    assert 'VRM_Collider' not in bpy.data.objects
    op('avatar_toolkit.convert_vrm_to_unity')
    assert 'Hips' in arm.data.bones

@case('Resonite bone conversion')
def resonite(arm, mesh, props):
    op('avatar_toolkit.convert_resonite')
    assert 'Hips' in arm.data.bones

@case('Pose to shape key and rest pose')
def pose(arm, mesh, props):
    op('avatar_toolkit.start_pose_mode')
    arm.pose.bones['Hips'].location.z = .2
    old_count = len(mesh.data.shape_keys.key_blocks)
    op('avatar_toolkit.apply_pose_as_shapekey')
    assert len(mesh.data.shape_keys.key_blocks) > old_count
    activate(arm)
    op('avatar_toolkit.start_pose_mode')
    arm.pose.bones['Hips'].location.z = .2
    op('avatar_toolkit.apply_pose_as_rest')
    assert abs(arm.pose.bones['Hips'].location.z) < 1e-5

@case('Texture atlas pixels, UVs and files')
def atlas(arm, mesh, props):
    activate(mesh)
    mat = bpy.data.materials.new('AtlasSource')
    mat.include_in_atlas = True
    image = bpy.data.images.new('ColorImage', width=32, height=32, alpha=True)
    image.pixels[:] = [1,0,0,1] * (32*32)
    node = mat.node_tree.nodes.new('ShaderNodeTexImage')
    node.image = image
    mesh.data.materials.append(mat)
    mat.texture_atlas_albedo = image.name
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'atlas_fixture.blend'))
    props.texture_atlas_Has_Mat_List_Shown = True
    op('avatar_toolkit.atlas_materials')
    material = mesh.data.materials[0]
    assert material.name.startswith('Atlas_Final')
    images = [n.image for n in material.node_tree.nodes if n.type == 'TEX_IMAGE']
    assert len(images) == 6
    assert any(i.pixels[0] > .9 and i.pixels[1] < .1 for i in images)
    assert len(list(OUT.glob('Atlas_*.png'))) == 6

@case('UV selection reads and writes active UV layer')
def uv_selection(arm, mesh, props):
    from avatar_toolkit.functions.tools.uv_tools import get_uv_vertex_selection, set_uv_vertex_selection
    assert len(get_uv_vertex_selection(mesh.data)) == len(mesh.data.loops)
    set_uv_vertex_selection(mesh.data, 0, True)
    assert get_uv_vertex_selection(mesh.data)[0]

@case('Offline dictionary translation and Unicode')
def translation(arm, mesh, props):
    from avatar_toolkit.core.translation_manager import AvatarToolkitTranslationManager, TranslationMode
    from avatar_toolkit.core.translation_service import safe_decode_text
    manager = AvatarToolkitTranslationManager()
    manager.translation_mode = TranslationMode.DICTIONARY_ONLY
    assert safe_decode_text('左目') == '左目'
    result = manager.translate_single('左目', category='bone')
    assert result.translated_name != '左目'

# Inventory all registered operators. A registration/poll check is recorded separately
# from execution coverage and does not imply the feature was exercised.
from avatar_toolkit.core import auto_load
inventory = []
for cls in auto_load.registered_classes:
    if issubclass(cls, bpy.types.Operator):
        inventory.append({'operator': cls.bl_idname, 'module': cls.__module__,
                          'executed': cls.bl_idname in covered})
report = {'blender': bpy.app.version_string, 'results': results, 'operators': sorted(inventory, key=lambda x: x['operator'])}
(OUT / 'full-test-results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
addon.unregister()
failed = [r for r in results if r['status'] == 'FAIL']
print('FULL_SUITE_RESULT', len(results)-len(failed), 'passed;', len(failed), 'failed', flush=True)
if failed:
    raise RuntimeError('Feature suite failures: ' + ', '.join(r['test'] for r in failed))
