"""Run with Blender --background --factory-startup --python-exit-code 1 --python this_file."""
import importlib.util
import pathlib
import sys
from contextlib import nullcontext
import bpy
from bpy_extras import anim_utils

root = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('avatar_toolkit', root / '__init__.py', submodule_search_locations=[str(root)])
addon = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = addon
spec.loader.exec_module(addon)
addon.register()

from avatar_toolkit.core.animation import assign_action, ensure_channelbag
from avatar_toolkit.core.mmd.core.camera import MMDCamera
from avatar_toolkit.core.mmd.core.rigid_body import RigidBodyMaterial
from avatar_toolkit.core.mmd.core import vmd, pmx
from avatar_toolkit.core.mmd.core.vmd.importer import VMDImporter
from avatar_toolkit.core.resonite_utils import makeorexistingfcurve

def check_animation(target, expected_curves):
    data = target.animation_data
    assert data and data.action and data.action_slot, target.name
    assert data.action_slot.target_id_type == target.id_type
    bag = anim_utils.action_get_channelbag_for_slot(data.action, data.action_slot)
    assert len(bag.fcurves) == expected_curves, (target.name, len(bag.fcurves))
    return bag

with nullcontext(root / '.validation' / 'fixtures') as tmp:
    tmp = pathlib.Path(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.ops.object.armature_add()
    arm = bpy.context.object
    arm.name = 'TestArmature'
    arm.pose.bones[0].name = 'Bone'
    shared = bpy.data.actions.new('Shared')
    decoy = bpy.data.objects.new('Decoy', None)
    ensure_channelbag(shared, decoy).fcurves.new('location', index=0)
    bag = ensure_channelbag(shared, arm)
    curve = bag.fcurves.new('location', index=0)
    curve.keyframe_points.insert(1, 2)
    curve.keyframe_points.insert(10, 8)
    assign_action(arm, shared)
    assert check_animation(arm, 1).slot_handle == bag.slot_handle
    bpy.context.scene.frame_set(10)
    assert abs(arm.location.x - 8) < 1e-5
    curve2 = makeorexistingfcurve(shared, 'location', 'Test', 1, arm)
    assert curve2 == makeorexistingfcurve(shared, 'location', 'Test', 1, arm)
    print('PASS: action slots and AnimX curve creation')

    motion = vmd.File()
    motion.boneAnimation = vmd.BoneAnimation()
    for frame, value in ((0, 0), (10, 2)):
        key = vmd.BoneFrameKey()
        key.frame_number = frame
        key.location = (value, 0, 0)
        key.rotation = (0, 0, 0, 1)
        key.interp = [20] * 64
        motion.boneAnimation['Bone'].append(key)
    motion.propertyAnimation = vmd.PropertyAnimation()
    key = vmd.PropertyFrameKey()
    key.ik_states = [('Bone', True)]
    motion.propertyAnimation.append(key)
    motion.cameraAnimation = vmd.CameraAnimation()
    for frame in (0, 10):
        key = vmd.CameraKeyFrameKey()
        key.frame_number = frame
        key.distance = -5
        key.location = (frame / 10, 0, 0)
        key.rotation = (0, 0, 0)
        key.interp = [20] * 24
        key.angle = 30
        motion.cameraAnimation.append(key)
    motion_path = str(tmp / 'motion.vmd')
    motion.save(filepath=motion_path)
    VMDImporter(motion_path, frame_margin=0).assign(arm)
    check_animation(arm, 8)
    bpy.context.scene.frame_set(11)
    assert abs(arm.pose.bones['Bone'].location.x - 2) < 1e-5
    print('PASS: VMD bone and IK import with evaluated animation')
    assert bpy.ops.mmd_tools.import_vmd(filepath=motion_path, bone_mapper='BLENDER', margin=0) == {'FINISHED'}
    check_animation(arm, 8)
    VMDImporter(motion_path, frame_margin=0, use_NLA=True).assign(arm)
    strip = arm.animation_data.nla_tracks[-1].strips[0]
    assert strip.action_slot.target_id_type == 'OBJECT'
    print('PASS: VMD operator and NLA slot assignment')

    bpy.ops.object.camera_add()
    camera = bpy.context.object
    MMDCamera.convertToMMDCamera(camera)
    VMDImporter(motion_path, frame_margin=0).assign(camera)
    check_animation(camera.parent, 8)
    check_animation(camera, 1)
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 3
    baked = MMDCamera.newMMDCameraAnimation(camera)
    check_animation(baked.object(), 8)
    check_animation(baked.camera(), 1)
    print('PASS: VMD camera import and camera baking')
    motion.lightAnimation = vmd.LightAnimation()
    key = vmd.LightKeyFrameKey()
    key.color = (0.1, 0.2, 0.3)
    key.direction = (0, -1, 0)
    motion.lightAnimation.append(key)
    motion.save(filepath=motion_path)
    bpy.ops.object.light_add(type='SUN')
    light = bpy.context.object
    from avatar_toolkit.core.mmd.core.light import MMDLight
    MMDLight.convertToMMDLight(light)
    VMDImporter(motion_path, frame_margin=0).assign(light)
    check_animation(light.data, 3)
    check_animation(light, 3)
    print('PASS: VMD light animation targets')
    material = RigidBodyMaterial.getMaterial(0)
    assert material.surface_render_method == 'BLENDED'
    print('PASS: rigid body materials')

    model = pmx.Model()
    model.name = model.name_e = 'CompatibilityModel'
    bone = pmx.Bone()
    bone.name = bone.name_e = 'Bone'
    bone.location = (0, 0, 0)
    bone.displayConnection = (0, 1, 0)
    model.bones.append(bone)
    for co in ((0, 0, 0), (1, 0, 0), (0, 1, 0)):
        vertex = pmx.Vertex()
        vertex.co = co
        vertex.normal = (0, 0, 1)
        vertex.weight = pmx.BoneWeight()
        vertex.weight.bones = [0]
        model.vertices.append(vertex)
    model.faces = [(0, 1, 2), (0, 1, 2)]
    for name in ('First', 'Overlapping'):
        mat = pmx.Material()
        mat.name = mat.name_e = name
        mat.diffuse = (1, 1, 1, 0.5)
        mat.specular = mat.ambient = (0, 0, 0)
        mat.edge_color = (0, 0, 0, 1)
        mat.vertex_count = 3
        model.materials.append(mat)
    path = str(tmp / 'model.pmx')
    pmx.save(path, model)
    assert bpy.ops.mmd_tools.import_model(filepath=path, types={'MESH', 'ARMATURE', 'MORPHS', 'DISPLAY'}, clean_model=False, remove_doubles=False) == {'FINISHED'}
    imported = next(o for o in bpy.context.scene.objects if o.type == 'MESH' and len(o.data.polygons) == 2)
    assert len(imported.data.polygons) == 2
    assert imported.data.materials[1].surface_render_method == 'BLENDED'
    assert any(m.type == 'ARMATURE' for m in imported.modifiers)
    print('PASS: PMX model, armature, materials and overlapping faces')

    from avatar_toolkit.core.mmd import cycles_converter
    cycles_converter.convertToCyclesShader(imported)
    cycles_converter.convertToCyclesShader(imported, use_principled=True)
    print('PASS: MMD material shader conversion')

    bpy.ops.object.select_all(action='DESELECT')
    imported.select_set(True)
    bpy.context.view_layer.objects.active = imported
    assert bpy.ops.export_scene.fbx(filepath=str(tmp / 'avatar.fbx'), use_selection=True) == {'FINISHED'}
    assert bpy.ops.export_scene.gltf(filepath=str(tmp / 'avatar.glb'), use_selection=True, export_image_format='WEBP', export_image_quality=75, export_materials='EXPORT', export_animations=True, export_animation_mode='ACTIONS', export_nla_strips_merged_animation_name='Animation') == {'FINISHED'}
    print('PASS: FBX and Resonite glTF export settings')

    bpy.context.scene.avatar_toolkit.active_armature = 'ARM_' + str(arm.as_pointer())
    bpy.context.scene.avatar_toolkit.validation_mode = 'NONE'
    assert bpy.ops.avatar_toolkit.start_pose_mode() == {'FINISHED'}
    assert bpy.context.mode == 'POSE'
    assert bpy.ops.avatar_toolkit.stop_pose_mode() == {'FINISHED'}
    assert bpy.context.mode == 'OBJECT'
    print('PASS: start and stop pose mode')

    bpy.ops.object.select_all(action='DESELECT')
    imported.select_set(True)
    bpy.context.view_layer.objects.active = imported
    basis = imported.data.shape_keys.key_blocks[0] if imported.data.shape_keys else imported.shape_key_add(name='Basis')
    shape = imported.shape_key_add(name='Test')
    shape.data[0].co.z += 1
    shape.value = 0.5
    imported.active_shape_key_index = len(imported.data.shape_keys.key_blocks) - 1
    before = basis.data[0].co.z
    assert bpy.ops.avatar_toolkit.shape_key_to_basis() == {'FINISHED'}
    assert abs(basis.data[0].co.z - before - 0.5) < 1e-5
    print('PASS: apply shape key to basis preserves geometry')

    stl = tmp / 'triangle.STL'
    stl.write_text('solid triangle\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid triangle\n')
    assert getattr(bpy.ops.avatar_toolkit, 'import')(filepath=str(stl)) == {'FINISHED'}
    assert any(o.type == 'MESH' and len(o.data.polygons) == 1 for o in bpy.context.scene.objects)
    print('PASS: generic single-file STL import and uppercase extension')

from avatar_toolkit.core import properties, auto_load
for _ in range(2):
    addon.unregister()
    assert not hasattr(bpy.types.Scene, 'avatar_toolkit')
    assert not hasattr(bpy.types.Material, 'include_in_atlas')
    assert not bpy.app.timers.is_registered(properties.auto_populate_safe)
    assert properties.depsgraph_update_handler not in bpy.app.handlers.depsgraph_update_post
    assert not auto_load.registered_classes
    addon.register()
    assert hasattr(bpy.types.Material, 'include_in_atlas')
addon.unregister()
try:
    class A: pass
    class B: pass
    auto_load.toposort({A: {B}, B: {A}})
except RuntimeError:
    pass
else:
    raise AssertionError('Dependency cycles must fail')
print('PASS: repeat registration, property/handler/timer cleanup and cycle detection')
print('ALL COMPATIBILITY TESTS PASSED', bpy.app.version_string)
