"""Focused Blender regression fixtures for accessory and full-rig merges."""
import pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
source=(ROOT/'tests/blender_full_suite.py').read_text(encoding='utf-8')
exec(compile(source.split("@case(",1)[0],str(ROOT/'tests/blender_full_suite.py'),'exec'))
from avatar_toolkit.functions.custom_tools import armature_merging as merging
from mathutils import Matrix
from types import SimpleNamespace
from unittest.mock import patch


def accessory(arm,props,roots=1):
    activate(arm)
    bpy.ops.object.armature_add()
    rig=bpy.context.object; rig.name='Armature.003'
    bpy.ops.object.mode_set(mode='EDIT')
    bones=rig.data.edit_bones; bones.remove(bones[0])
    for i in range(roots):
        root=bones.new(f'Skirt {i}.L 001'); root.head=(i*.1,0,0); root.tail=(i*.1,0,.5)
        child=bones.new(f'Skirt {i}.L 002'); child.head=root.tail; child.tail=root.tail+Vector((0,0,.5)); child.parent=root; child.use_connect=True
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.mesh.primitive_cube_add()
    mesh=bpy.context.object; mesh.name='Skirt'; mesh.parent=rig
    modifier=mesh.modifiers.new('Skirt Rig','ARMATURE'); modifier.object=rig
    mesh.vertex_groups.new(name='Skirt 0.L 001').add(list(range(8)),1,'REPLACE')
    mesh.shape_key_add(name='Basis'); shape=mesh.shape_key_add(name='Skirt Shape',from_mix=False); shape.data[0].co.x+=.25
    shape.value=.3
    props.merge_destination=arm; props.merge_source=rig
    props.merge_attach_roots=True; props.merge_attach_bone='Hips'
    props.join_meshes=props.remove_zero_weights=props.cleanup_shape_keys=False
    bpy.context.view_layer.update()
    return rig,mesh


@case('UI search IDs resolve Armature and Armature.003 among four rigs')
def search_ids(arm,body,props):
    arm.name='Armature'; rig,mesh=accessory(arm,props,6)
    for i in range(2): bpy.ops.object.armature_add()
    op('avatar_toolkit.search_merge_armature_into',search_merge_armature_into_enum=f'ARM_{arm.as_pointer()}')
    op('avatar_toolkit.search_merge_armature',search_merge_armature_enum=f'ARM_{rig.as_pointer()}')
    assert props.merge_destination==arm and props.merge_source==rig
    assert props.merge_attach_bone=='Hips'
    base_pointer=arm.as_pointer()
    op('avatar_toolkit.merge_armatures')
    assert arm.as_pointer()==base_pointer
    assert len([o for o in bpy.context.scene.objects if o.type=='ARMATURE'])==3
    for i in range(6):
        root=arm.data.bones[f'Skirt {i}.L 001']; assert root.parent.name=='Hips'
        assert arm.data.bones[f'Skirt {i}.L 002'].parent==root
    assert mesh.parent==arm and mesh.modifiers[0].object==arm
    assert mesh.vertex_groups['Skirt 0.L 001'].weight(0)==1
    assert mesh.data.shape_keys.key_blocks['Skirt Shape'].value==.3 or abs(mesh.data.shape_keys.key_blocks['Skirt Shape'].value-.3)<1e-6
    assert 'Empty' in body.data.shape_keys.key_blocks


@case('Accessory roots can remain unparented or attach to another bone')
def root_options(arm,body,props):
    rig,mesh=accessory(arm,props)
    props.merge_attach_roots=False
    op('avatar_toolkit.merge_armatures')
    assert arm.data.bones['Skirt 0.L 001'].parent is None
    rig,mesh=accessory(arm,props); props.merge_attach_roots=True; props.merge_attach_bone='Chest'
    rows=[SimpleNamespace(source_name=b.name,action='KEEP',target_name='') for b in rig.data.bones]
    merging.perform_merge(bpy.context,merging.build_merge_plan(bpy.context,rows))
    added=next(b for b in arm.data.bones if b.name.startswith('Skirt 0.L 001__'))
    assert added.parent.name=='Chest'


@case('Different rig transforms and nested mesh parenting preserve placement')
def transformed(arm,body,props):
    rig,mesh=accessory(arm,props)
    base_parent=bpy.data.objects.new('Avatar Parent',None); bpy.context.collection.objects.link(base_parent)
    source_parent=bpy.data.objects.new('Clothes Parent',None); bpy.context.collection.objects.link(source_parent)
    base_parent.location=(2,1,.5); base_parent.rotation_euler.z=.25
    source_parent.location=(-1,.5,2); source_parent.scale=(2,2,2)
    arm.parent=base_parent; arm.location=(.5,0,0); arm.rotation_euler.y=.2
    rig.parent=source_parent; rig.rotation_euler.z=.3
    intermediate=bpy.data.objects.new('Nested Skirt Parent',None); bpy.context.collection.objects.link(intermediate)
    intermediate.parent=rig; mesh.parent=intermediate; mesh.location=(.2,.3,.4)
    bpy.context.view_layer.update()
    expected=merging._mesh_positions(bpy.context,mesh)
    op('avatar_toolkit.merge_armatures')
    assert arm.parent==base_parent and source_parent.name in bpy.data.objects
    assert intermediate.parent==arm and mesh.parent==intermediate
    merging._verify_positions(bpy.context,mesh,expected)


@case('Modifier-bound mesh with no source parent is rebound')
def modifier_binding(arm,body,props):
    rig,mesh=accessory(arm,props); mesh.parent=None
    before=mesh.matrix_world.copy(); bpy.context.view_layer.update()
    op('avatar_toolkit.merge_armatures')
    assert mesh.parent is None and mesh.modifiers[0].object==arm
    assert merging._matrix_close(mesh.matrix_world,before)


@case('Renaming rig objects does not break pointer selection')
def rename_selection(arm,body,props):
    rig,mesh=accessory(arm,props)
    arm.name='Renamed Avatar'; rig.name='Renamed Clothes'
    op('avatar_toolkit.merge_armatures')
    assert mesh.modifiers[0].object==arm


@case('Compatible full-rig bones match with weights and children retained')
def matching(arm,body,props):
    rig,mesh=accessory(arm,props)
    activate(rig); bpy.ops.object.mode_set(mode='EDIT')
    root=rig.data.edit_bones['Skirt 0.L 001']; root.name='pelvis'; root.head=(0,0,0); root.tail=(0,0,.5)
    bpy.ops.object.mode_set(mode='OBJECT')
    plan=merging.build_merge_plan(bpy.context)
    assert plan['names']['pelvis']=='Hips' and plan['entries'][0]['action']=='MATCH'
    op('avatar_toolkit.merge_armatures')
    assert 'pelvis' not in arm.data.bones
    assert arm.data.bones['Skirt 0.L 002'].parent.name=='Hips'
    assert mesh.vertex_groups['Hips'].weight(0)==1


@case('Same-name bones at different rest positions stay separate')
def collision(arm,body,props):
    rig,mesh=accessory(arm,props)
    rig.data.bones['Skirt 0.L 001'].name='Hips'
    activate(rig); bpy.ops.object.mode_set(mode='EDIT'); rig.data.edit_bones['Hips'].head.x=.4; rig.data.edit_bones['Hips'].tail.x=.4; bpy.ops.object.mode_set(mode='OBJECT')
    plan=merging.build_merge_plan(bpy.context); renamed=plan['names']['Hips']
    assert renamed!='Hips'
    op('avatar_toolkit.merge_armatures')
    assert arm.data.bones[renamed].parent.name=='Hips'
    assert mesh.vertex_groups[renamed].weight(0)==1


@case('Explicit incompatible matches fail before changing either rig')
def invalid_match(arm,body,props):
    rig,mesh=accessory(arm,props)
    original_data=arm.data
    rows=[SimpleNamespace(source_name='Skirt 0.L 001',action='MATCH',target_name='Head')]
    try: merging.build_merge_plan(bpy.context,rows)
    except ValueError: pass
    else: raise AssertionError('Incompatible match accepted')
    assert arm.data==original_data and mesh.parent==rig and rig.name in bpy.data.objects


@case('Missing Hips requires explicit attachment choice')
def no_hips(arm,body,props):
    rig,mesh=accessory(arm,props)
    arm.data.bones['Hips'].name='RootWithoutAlias'; props.merge_attach_bone=''
    assert merging.suggested_hips(arm)==''
    try: merging.build_merge_plan(bpy.context)
    except ValueError: pass
    else: raise AssertionError('Missing attachment accepted')
    props.merge_attach_roots=False
    op('avatar_toolkit.merge_armatures')


@case('Source animation is rejected without deletion or cleanup')
def source_animation(arm,body,props):
    rig,mesh=accessory(arm,props)
    rig.pose.bones[0].keyframe_insert(data_path='location',frame=1)
    source_data=rig.data; base_data=arm.data
    try: merging.build_merge_plan(bpy.context)
    except ValueError as exc: assert 'animation' in str(exc)
    else: raise AssertionError('Animated source accepted')
    assert rig.data==source_data and arm.data==base_data


@case('External constraints and shape-key driver bone targets are remapped')
def references(arm,body,props):
    rig,mesh=accessory(arm,props)
    rig.data.bones['Skirt 0.L 001'].name='Hips'
    activate(rig); bpy.ops.object.mode_set(mode='EDIT'); rig.data.edit_bones['Hips'].head.x=.4; rig.data.edit_bones['Hips'].tail.x=.4; bpy.ops.object.mode_set(mode='OBJECT')
    marker=bpy.data.objects.new('Bone Follower',None); bpy.context.collection.objects.link(marker)
    constraint=marker.constraints.new('COPY_LOCATION'); constraint.target=rig; constraint.subtarget='Hips'
    shape=mesh.data.shape_keys.key_blocks['Skirt Shape']; curve=shape.driver_add('value'); variable=curve.driver.variables.new(); variable.type='TRANSFORMS'
    variable.targets[0].id=rig; variable.targets[0].bone_target='Hips'; variable.targets[0].transform_type='ROT_X'; curve.driver.expression='0.3'
    plan=merging.build_merge_plan(bpy.context); expected_name=plan['names']['Hips']
    op('avatar_toolkit.merge_armatures')
    assert constraint.target==arm and constraint.subtarget==expected_name
    target=mesh.data.shape_keys.animation_data.drivers[0].driver.variables[0].targets[0]
    assert target.id==arm and target.bone_target==expected_name


@case('Failure during commit restores original meshes, rigs and references')
def rollback(arm,body,props):
    rig,mesh=accessory(arm,props)
    original_arm_data=arm.data; original_mesh_data=mesh.data
    original_weights=merging._group_schema(mesh); positions=merging._mesh_positions(bpy.context,mesh)
    constraint=arm.pose.bones['Head'].constraints.new('COPY_LOCATION'); constraint.target=body; constraint.influence=.2
    plan=merging.build_merge_plan(bpy.context)
    with patch.object(merging,'_reference_changes',return_value=[(mesh,'attribute_that_does_not_exist',None,None)]):
        try: merging.perform_merge(bpy.context,plan)
        except AttributeError: pass
        else: raise AssertionError('Injected failure was not raised')
    assert arm.data==original_arm_data and mesh.data==original_mesh_data
    assert rig.name in bpy.data.objects and mesh.parent==rig and mesh.modifiers[0].object==rig
    assert merging._group_schema(mesh)==original_weights
    assert len(arm.pose.bones['Head'].constraints)==1
    merging._verify_positions(bpy.context,mesh,positions)
    assert not any(c.name.startswith('__AvatarMergeStaging') for c in bpy.data.collections)


@case('Optional mesh joining and cleanup run on staged copies')
def optional_cleanup(arm,body,props):
    rig,mesh=accessory(arm,props)
    body.vertex_groups.new(name='Empty Mask'); props.join_meshes=True; props.remove_zero_weights=True; props.cleanup_shape_keys=True
    op('avatar_toolkit.merge_armatures')
    meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
    assert len(meshes)==1 and len(meshes[0].data.vertices)==16
    assert 'Empty Mask' not in meshes[0].vertex_groups
    assert 'Skirt Shape' in meshes[0].data.shape_keys.key_blocks
    assert 'Empty' not in meshes[0].data.shape_keys.key_blocks


@case('Destination pose constraints and custom properties are preserved')
def pose_properties(arm,body,props):
    rig,mesh=accessory(arm,props)
    arm.pose.bones['Head']['Control']={'nested':3}
    rig.pose.bones[0]['ClothControl']=.8
    activate(arm); bpy.ops.object.mode_set(mode='POSE')
    op('avatar_toolkit.merge_armatures')
    assert bpy.context.mode=='POSE'
    assert arm.pose.bones['Head']['Control']['nested']==3
    assert abs(arm.pose.bones['Skirt 0.L 001']['ClothControl']-.8)<1e-6


@case('Posed accessory and posed destination retain evaluated deformation')
def posed_merge(arm,body,props):
    rig,mesh=accessory(arm,props)
    arm.pose.bones['Hips'].rotation_mode='XYZ'; arm.pose.bones['Hips'].rotation_euler.z=.2
    rig.pose.bones[0].rotation_mode='XYZ'; rig.pose.bones[0].rotation_euler.x=.3
    rig.pose.bones[0].scale=(1.1,.9,1.2)
    rig.scale=(-1.5,1.5,1.5); rig.rotation_euler.y=.2
    bpy.context.view_layer.update()
    expected=merging._mesh_positions(bpy.context,mesh); base_expected=merging._mesh_positions(bpy.context,body)
    op('avatar_toolkit.merge_armatures')
    merging._verify_positions(bpy.context,mesh,expected); merging._verify_positions(bpy.context,body,base_expected)


@case('Source custom properties and external property drivers are retained')
def custom_driver(arm,body,props):
    rig,mesh=accessory(arm,props)
    rig['ClothStrength']=.3; rig.id_properties_ui('ClothStrength').update(min=0,max=1,description='Cloth strength')
    rig.data['ClothSettings']={'quality':2}
    rig.update_tag(refresh={'OBJECT'})
    curve=mesh.data.shape_keys.key_blocks['Skirt Shape'].driver_add('value'); variable=curve.driver.variables.new()
    variable.type='SINGLE_PROP'; variable.targets[0].id=rig; variable.targets[0].data_path='["ClothStrength"]'; curve.driver.expression=f'{variable.name} + 0.0'
    bpy.context.scene.frame_set(bpy.context.scene.frame_current)
    op('avatar_toolkit.merge_armatures')
    assert abs(arm['ClothStrength']-.3)<1e-6 and arm.data['ClothSettings']['quality']==2
    assert arm.id_properties_ui('ClothStrength').as_dict()['description']=='Cloth strength'
    assert mesh.data.shape_keys.animation_data.drivers[0].driver.variables[0].targets[0].id==arm


@case('Bone-parented accessory objects preserve their world placement')
def bone_parent(arm,body,props):
    rig,mesh=accessory(arm,props)
    marker=bpy.data.objects.new('Accessory Marker',None); bpy.context.collection.objects.link(marker)
    marker.parent=rig; marker.parent_type='BONE'; marker.parent_bone=rig.data.bones[0].name; marker.location=(.2,.3,.4)
    bpy.context.view_layer.update(); expected=marker.matrix_world.copy()
    op('avatar_toolkit.merge_armatures')
    bpy.context.view_layer.update()
    assert marker.parent==arm and marker.parent_bone in arm.data.bones
    assert merging._matrix_close(marker.matrix_world,expected)


@case('Conflicting custom properties are rejected without mutation')
def custom_conflict(arm,body,props):
    rig,mesh=accessory(arm,props); rig['Strength']=.3; arm['Strength']=.8
    try: merging.build_merge_plan(bpy.context)
    except ValueError as exc: assert 'Custom property' in str(exc)
    else: raise AssertionError('Conflicting properties accepted')
    assert rig['Strength']!=arm['Strength'] and mesh.parent==rig


@case('Added bone constraints and IK settings survive merging')
def constraint_settings(arm,body,props):
    rig,mesh=accessory(arm,props)
    target=bpy.data.objects.new('Cloth Constraint Target',None); bpy.context.collection.objects.link(target)
    bone=rig.pose.bones[0]; bone.ik_min_x=-.3; bone.use_ik_limit_x=True; bone.bbone_curveinx=.2
    constraint=bone.constraints.new('COPY_ROTATION'); constraint.target=target; constraint.influence=.25
    bpy.context.view_layer.update(); expected=merging._mesh_positions(bpy.context,mesh)
    op('avatar_toolkit.merge_armatures')
    bone=arm.pose.bones['Skirt 0.L 001']
    assert bone.constraints[0].target==target and bone.constraints[0].influence==.25
    assert bone.use_ik_limit_x and abs(bone.ik_min_x+.3)<1e-6 and abs(bone.bbone_curveinx-.2)<1e-6
    merging._verify_positions(bpy.context,mesh,expected)


(OUT/'merge-results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
addon.unregister()
failures=[r for r in results if r['status']=='FAIL']
print('MERGE_SUITE_RESULT',len(results)-len(failures),'passed;',len(failures),'failed',flush=True)
if failures: raise RuntimeError('Merge regressions failed')
