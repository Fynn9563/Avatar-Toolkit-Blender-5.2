"""Focused fixtures for the humanoid mapping editor and Apply transaction."""
import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
text = (ROOT/'tests/blender_full_suite.py').read_text(encoding='utf-8')
exec(compile(text.split('@case(', 1)[0], str(ROOT/'tests/blender_full_suite.py'), 'exec'))
from avatar_toolkit.functions.tools import standardize_armature as standard
from avatar_toolkit.functions.custom_tools.armature_merging import _mesh_positions, _verify_positions, _matrix_close
from unittest.mock import patch
from types import SimpleNamespace


def slot(arm, role):
    return next(item for item in standard.initialize_mapping(arm).slots if item.role == role)


def extra(arm, name, parent=None, length=.5):
    activate(arm); bpy.ops.object.mode_set(mode='EDIT')
    bone = arm.data.edit_bones.new(name); bone.head=(1,0,0); bone.tail=(1,0,length)
    if parent: bone.parent=arm.data.edit_bones[parent]
    bpy.ops.object.mode_set(mode='OBJECT')
    return arm.data.bones[name]


@case('Auto-mapping creates persistent roles without changing rig names or transforms')
def initial(arm, mesh, props):
    arm.data.bones['Hips'].name='pelvis'
    matrix=arm.data.bones['pelvis'].matrix_local.copy()
    op('avatar_toolkit.humanoid_auto_map')
    assert slot(arm,'hips').bone_name=='pelvis'
    assert 'Hips' not in arm.data.bones and _matrix_close(matrix,arm.data.bones['pelvis'].matrix_local)
    mapping=arm.data.avatar_toolkit_humanoid
    assert not mapping.reparent and not mapping.normalize_lengths
    assert len(mapping.slots)==len(standard.NAMES)


@case('Unknown bone names can be manually assigned and survive external renaming')
def manual(arm, mesh, props):
    arm.data.bones['Hips'].name='CustomRoot'
    item=slot(arm,'hips'); assert not item.bone_name
    item.bone_name='CustomRoot'; arm.data.bones['CustomRoot'].name='Root Renamed'
    assert item.bone_name=='Root Renamed'
    op('avatar_toolkit.standardize_armature')
    assert 'Hips' in arm.data.bones and item.bone_name=='Hips'
    assert mesh.vertex_groups['Hips'].weight(0)==1


@case('Default Apply preserves rest pose, parenting, extra bones and posed meshes')
def preservation(arm, mesh, props):
    arm.data.bones['Hips'].name='pelvis'; extra(arm,'SkirtExtra',parent='pelvis',length=100)
    arm.pose.bones['pelvis'].rotation_mode='XYZ'; arm.pose.bones['pelvis'].rotation_euler.z=.2
    before={bone.name:(bone.matrix_local.copy(),bone.length,bone.parent.name if bone.parent else None) for bone in arm.data.bones}
    expected=_mesh_positions(bpy.context,mesh)
    op('avatar_toolkit.standardize_armature')
    for old,(matrix,length,parent) in before.items():
        bone=arm.data.bones['Hips' if old=='pelvis' else old]
        assert _matrix_close(matrix,bone.matrix_local) and abs(length-bone.length)<1e-6
        assert (bone.parent.name if bone.parent else None)==('Hips' if parent=='pelvis' else parent)
    _verify_positions(bpy.context,mesh,expected)
    assert 'Empty' in mesh.data.shape_keys.key_blocks


@case('Ambiguous aliases stay unassigned and Auto Map keeps manual choices')
def ambiguous(arm, mesh, props):
    arm.data.bones['Hips'].name='pelvis'; extra(arm,'hip')
    mapping=standard.initialize_mapping(arm); item=slot(arm,'hips')
    assert not item.bone_name and item.hint.startswith('Ambiguous')
    item.bone_name='hip'; op('avatar_toolkit.humanoid_auto_map')
    assert item.bone_name=='hip'


@case('Duplicate and missing assignments are rejected before modifying the rig')
def invalid(arm, mesh, props):
    slot(arm,'head').bone_name='Hips'
    try: standard.build_standardize_plan(arm)
    except ValueError as exc: assert 'multiple roles' in str(exc)
    else: raise AssertionError('Duplicate accepted')
    slot(arm,'head').bone_name='MissingBone'
    try: standard.build_standardize_plan(arm)
    except ValueError as exc: assert 'missing' in str(exc)
    else: raise AssertionError('Missing bone accepted')
    assert 'Hips' in arm.data.bones


@case('Unassigned target-name and vertex-group conflicts are rejected')
def collisions(arm, mesh, props):
    extra(arm,'CustomHips'); slot(arm,'hips').bone_name='CustomHips'
    try: standard.build_standardize_plan(arm)
    except ValueError as exc: assert 'unassigned bone' in str(exc)
    else: raise AssertionError('Name conflict accepted')
    arm.data.bones['Hips'].name='ExtraRoot'; mesh.vertex_groups.new(name='Hips')
    mesh.vertex_groups.new(name='CustomHips').add([0],.5,'REPLACE')
    try: standard.build_standardize_plan(arm)
    except ValueError as exc: assert 'vertex group' in str(exc)
    else: raise AssertionError('Weight conflict accepted')


@case('Swapping mapped bone names preserves distinct weights and mappings')
def permutations(arm, mesh, props):
    slot(arm,'hips').bone_name='Head'; slot(arm,'head').bone_name='Hips'
    mesh.vertex_groups.new(name='Head').add([2],.6,'REPLACE')
    op('avatar_toolkit.standardize_armature')
    assert mesh.vertex_groups['Head'].weight(0)==1
    assert abs(mesh.vertex_groups['Hips'].weight(2)-.6)<1e-6
    assert slot(arm,'hips').bone_name=='Hips' and slot(arm,'head').bone_name=='Head'


@case('External constraints, bone parenting, shape masks and drivers follow renames')
def references(arm, mesh, props):
    arm.data.bones['Hips'].name='pelvis'
    marker=bpy.data.objects.new('Marker',None); bpy.context.collection.objects.link(marker)
    marker.parent=arm; marker.parent_type='BONE'; marker.parent_bone='pelvis'
    constraint=marker.constraints.new('COPY_LOCATION'); constraint.target=arm; constraint.subtarget='pelvis'
    shape=mesh.data.shape_keys.key_blocks['A']; shape.vertex_group='pelvis'
    curve=shape.driver_add('value'); var=curve.driver.variables.new(); var.type='TRANSFORMS'
    var.targets[0].id=arm; var.targets[0].bone_target='pelvis'; curve.driver.expression='0.2'
    op('avatar_toolkit.standardize_armature')
    assert marker.parent_bone=='Hips' and constraint.subtarget=='Hips' and shape.vertex_group=='Hips'
    assert curve.driver.variables[0].targets[0].bone_target=='Hips'


@case('Modifier-only mesh weight groups survive mapped name permutations')
def modifier_groups(arm, mesh, props):
    mesh.parent=None
    mesh.vertex_groups.new(name='Head').add([2],.6,'REPLACE')
    slot(arm,'hips').bone_name='Head'; slot(arm,'head').bone_name='Hips'
    op('avatar_toolkit.standardize_armature')
    assert mesh.vertex_groups['Head'].weight(0)==1
    assert abs(mesh.vertex_groups['Hips'].weight(2)-.6)<1e-6
    assert not any(group.name.startswith('__AvatarStandardize_') for group in mesh.vertex_groups)


@case('Renaming animated bones isolates actions shared with another rig')
def animation(arm, mesh, props):
    arm.data.bones['Hips'].name='pelvis'; arm.pose.bones['pelvis'].keyframe_insert(data_path='location',frame=1)
    original=arm.animation_data.action
    other=arm.copy(); other.data=arm.data.copy(); bpy.context.collection.objects.link(other)
    assert other.animation_data.action==original
    from avatar_toolkit.core.animation import ensure_channelbag
    op('avatar_toolkit.standardize_armature')
    assert arm.animation_data.action!=original and other.animation_data.action==original
    assert any('"Hips"' in curve.data_path for curve in ensure_channelbag(arm.animation_data.action,arm).fcurves)
    assert any('"pelvis"' in curve.data_path for curve in ensure_channelbag(original,other).fcurves)


@case('Optional reparenting uses assigned roles and optional-ancestor fallback')
def parenting(arm, mesh, props):
    activate(arm); bpy.ops.object.mode_set(mode='EDIT'); arm.data.edit_bones['Head'].parent=None; bpy.ops.object.mode_set(mode='OBJECT')
    extra(arm,'AccessoryRoot')
    mapping=standard.initialize_mapping(arm); mapping.reparent=True
    op('avatar_toolkit.standardize_armature')
    assert arm.data.bones['Head'].parent.name=='Neck'
    assert arm.data.bones['Neck'].parent.name=='Chest'
    assert arm.data.bones['AccessoryRoot'].parent is None


@case('Optional length normalization changes extreme mapped bones only')
def lengths(arm, mesh, props):
    extra(arm,'AccessoryRoot',length=100)
    activate(arm); bpy.ops.object.mode_set(mode='EDIT'); arm.data.edit_bones['Head'].length=100; bpy.ops.object.mode_set(mode='OBJECT')
    standard.initialize_mapping(arm).normalize_lengths=True
    op('avatar_toolkit.standardize_armature')
    assert abs(arm.data.bones['Head'].length-7.5)<1e-5
    assert abs(arm.data.bones['AccessoryRoot'].length-100)<1e-5


@case('A failed Apply restores names, parenting, lengths, weights and animation')
def rollback(arm, mesh, props):
    arm.data.bones['Hips'].name='pelvis'; arm.pose.bones['pelvis'].keyframe_insert(data_path='location',frame=1)
    activate(arm); bpy.ops.object.mode_set(mode='EDIT'); arm.data.edit_bones['Head'].parent=None; arm.data.edit_bones['Head'].length=100; bpy.ops.object.mode_set(mode='OBJECT')
    mapping=standard.initialize_mapping(arm); mapping.reparent=True; mapping.normalize_lengths=True
    action=arm.animation_data.action; plan=standard.build_standardize_plan(arm)
    with patch.object(standard,'save_baseline',side_effect=RuntimeError('Injected failure')):
        try: standard.apply_standardization(bpy.context,arm,plan)
        except RuntimeError: pass
        else: raise AssertionError('Failure not raised')
    assert 'pelvis' in arm.data.bones and 'Hips' not in arm.data.bones
    assert arm.data.bones['Head'].parent is None and abs(arm.data.bones['Head'].length-100)<1e-5
    assert mesh.vertex_groups['pelvis'].weight(0)==1 and arm.animation_data.action==action


@case('Assignment from selection, bone selection, Clear and Revert work')
def controls(arm, mesh, props):
    standard.initialize_mapping(arm)
    op('avatar_toolkit.humanoid_clear_mapping'); assert not standard.assigned_roles(arm)
    activate(arm); bpy.ops.object.mode_set(mode='POSE')
    bone=arm.data.bones['Hips']; arm.pose.bones['Hips'].select=True; arm.data.bones.active=bone
    op('avatar_toolkit.humanoid_assign_selected',role='hips'); assert slot(arm,'hips').bone_name=='Hips'
    op('avatar_toolkit.humanoid_reset_mapping'); assert slot(arm,'head').bone_name=='Head'
    op('avatar_toolkit.humanoid_select_bone',role='head'); assert arm.data.bones.active.name=='Head'
    op('avatar_toolkit.standardize_armature'); assert bpy.context.mode=='POSE'


@case('All mapping sections draw searchable roles and optional repair toggles')
def ui(arm, mesh, props):
    standard.initialize_mapping(arm)
    class Layout:
        def __init__(self): self.roles=[]; self.props=[]
        def row(self,**kwargs): return self
        def label(self,**kwargs): pass
        def prop(self,data,name,**kwargs): self.props.append(name)
        def prop_search(self,item,name,*args,**kwargs): self.roles.append(item.role)
        def operator(self,*args,**kwargs): return SimpleNamespace()
    for section,count in [('BODY',20),('HEAD',5),('LEFT',15),('RIGHT',15)]:
        arm.data.avatar_toolkit_humanoid.section=section; layout=Layout(); standard.draw_mapping(layout,bpy.context)
        assert len(layout.roles)==count,(section,layout.roles)
        assert 'reparent' in layout.props and 'normalize_lengths' in layout.props


@case('Deleting an assigned bone cannot silently assign a replacement with the same name')
def deleted_assignment(arm, mesh, props):
    standard.initialize_mapping(arm)
    activate(arm); bpy.ops.object.mode_set(mode='EDIT')
    arm.data.edit_bones.remove(arm.data.edit_bones['Head']); replacement=arm.data.edit_bones.new('Head')
    replacement.head=(0,0,4); replacement.tail=(0,0,4.5)
    bpy.ops.object.mode_set(mode='OBJECT')
    try: standard.build_standardize_plan(arm)
    except ValueError as exc: assert 'deleted or duplicated' in str(exc)
    else: raise AssertionError('Replacement was silently assigned')
    slot(arm,'head').bone_name='Head'; assert not standard.mapping_status(arm)[1]


@case('Compatible rigs with separate saved mappings can still merge')
def mapped_full_merge(arm, mesh, props):
    source=arm.copy(); source.data=arm.data.copy(); bpy.context.collection.objects.link(source)
    source.name='Mapped Source'
    standard.initialize_mapping(arm); standard.initialize_mapping(source)
    assert arm.data.bones['Hips'].get(standard.BONE_ID)!=source.data.bones['Hips'].get(standard.BONE_ID)
    props.merge_destination=arm; props.merge_source=source; props.merge_attach_roots=True; props.merge_attach_bone='Hips'
    props.join_meshes=props.remove_zero_weights=props.cleanup_shape_keys=False
    op('avatar_toolkit.merge_armatures')
    assert len(arm.data.bones)==8 and slot(arm,'hips').bone_name=='Hips'
    assert not standard.mapping_status(arm)[1]


@case('Merging copied accessory bones preserves destination mapping identities')
def copied_accessory(arm, mesh, props):
    standard.initialize_mapping(arm)
    source=arm.copy(); source.data=arm.data.copy(); bpy.context.collection.objects.link(source); source.name='Accessory Source'
    activate(source); bpy.ops.object.mode_set(mode='EDIT')
    for bone in list(source.data.edit_bones):
        if bone.name!='Hips': source.data.edit_bones.remove(bone)
    root=source.data.edit_bones['Hips']; root.name='SkirtRoot'; root.head.x=.2; root.tail.x=.2
    bpy.ops.object.mode_set(mode='OBJECT')
    props.merge_destination=arm; props.merge_source=source; props.merge_attach_roots=True; props.merge_attach_bone='Hips'
    props.join_meshes=props.remove_zero_weights=props.cleanup_shape_keys=False
    op('avatar_toolkit.merge_armatures')
    assert arm.data.bones['Hips'].get(standard.BONE_ID)!=arm.data.bones['SkirtRoot'].get(standard.BONE_ID)
    assert slot(arm,'hips').bone_name=='Hips' and not standard.mapping_status(arm)[1]


@case('Optional reparenting rejects cycles before changing the rig')
def parent_cycle(arm, mesh, props):
    slot(arm,'hips').bone_name='Spine'; slot(arm,'spine').bone_name='Hips'
    arm.data.avatar_toolkit_humanoid.reparent=True
    try: standard.build_standardize_plan(arm)
    except ValueError as exc: assert 'cycle' in str(exc)
    else: raise AssertionError('Cyclic reparenting accepted')
    assert arm.data.bones['Spine'].parent.name=='Hips'


@case('Mapping data survives saving and reopening a blend file')
def persistence(arm, mesh, props):
    mapping=standard.initialize_mapping(arm); slot(arm,'hips').bone_name='Unused'; mapping.section='LEFT'
    path=OUT/'humanoid-mapping.blend'; bpy.ops.wm.save_as_mainfile(filepath=str(path))
    bpy.ops.wm.open_mainfile(filepath=str(path))
    arm=bpy.data.objects['Avatar']
    assert slot(arm,'hips').bone_name=='Unused' and arm.data.avatar_toolkit_humanoid.section=='LEFT'


(OUT/'humanoid-results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
addon.unregister()
assert not hasattr(bpy.types.Armature,'avatar_toolkit_humanoid')
failed=[result for result in results if result['status']=='FAIL']
print('HUMANOID_SUITE_RESULT',len(results)-len(failed),'passed;',len(failed),'failed',flush=True)
if failed: raise RuntimeError('Humanoid mapping regressions failed')
