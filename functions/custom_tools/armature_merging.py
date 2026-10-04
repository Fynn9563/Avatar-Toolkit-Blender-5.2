"""Preview and stage armature merges before changing the original rigs."""
import json
import re
import bpy
from bpy.props import CollectionProperty, EnumProperty, StringProperty
from ...core.common import identify_bones, remove_unused_shapekeys
from ...core.logging_setup import logger


def resolve_armature(value, context):
    if isinstance(value, bpy.types.Object):
        return value if value.type == 'ARMATURE' and value.name in context.scene.objects else None
    if not value or value == 'NONE':
        return None
    for obj in context.scene.objects:
        if obj.type == 'ARMATURE' and (obj.name == value or value == f'ARM_{obj.as_pointer()}'):
            return obj
    return None


def selected_armatures(context):
    props = context.scene.avatar_toolkit
    return (resolve_armature(props.merge_destination, context) or resolve_armature(props.merge_armature_into, context),
            resolve_armature(props.merge_source, context) or resolve_armature(props.merge_armature, context))


def suggested_hips(armature):
    if not armature:
        return ''
    # Do not guess when several aliases compete for the same role.
    from ...core.dictionaries import reverse_bone_lookup, simplify_bonename
    matches = [b.name for b in armature.data.bones
               if b.name == 'Hips' or reverse_bone_lookup.get(simplify_bonename(b.name)) == 'hips']
    return matches[0] if len(matches) == 1 else ''


def bound_meshes(armature, context):
    meshes = []
    for obj in context.scene.objects:
        if obj.type != 'MESH':
            continue
        modifier_bound = any(m.type == 'ARMATURE' and m.object == armature for m in obj.modifiers)
        parent = obj.parent
        while parent and parent != armature and parent.type != 'ARMATURE':
            parent = parent.parent
        if modifier_bound or parent == armature:
            meshes.append(obj)
    return meshes


def _matrix_close(a, b, tolerance=1e-4):
    return max(abs(a[r][c] - b[r][c]) for r in range(4) for c in range(4)) <= tolerance


def compatible_bones(destination, source, source_name, target_name):
    first, second = destination.data.bones[target_name], source.data.bones[source_name]
    relative = destination.matrix_world.inverted() @ source.matrix_world
    if (relative @ second.head_local - first.head_local).length > 1e-4:
        return False
    if (relative @ second.tail_local - first.tail_local).length > 1e-4:
        return False
    if not _matrix_close(relative @ second.matrix_local, first.matrix_local):
        return False
    # Matching a posed/controlled source bone would discard its independent behavior.
    if source.pose.bones[source_name].constraints:
        return False
    if _custom_values(source.pose.bones[source_name]) != _custom_values(destination.pose.bones[target_name]):
        return False
    return _matrix_close(relative @ source.pose.bones[source_name].matrix,
                         destination.pose.bones[target_name].matrix)


class AvatarToolkitMergeBoneMapping(bpy.types.PropertyGroup):
    source_name: StringProperty(name='Source Bone')
    target_name: StringProperty(name='Destination Bone')
    action: EnumProperty(name='Action', items=[('KEEP', 'Keep Separate', 'Keep this bone and its weights'),
                                             ('MATCH', 'Use Destination', 'Use a compatible destination bone')], default='KEEP')
    reason: StringProperty()
    result_name: StringProperty(name='Result Bone')


class AvatarToolkit_UL_MergeBoneMapping(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=item.source_name, icon='BONE_DATA')
        row.prop(item, 'action', text='')
        destination, _ = selected_armatures(context)
        if item.action == 'MATCH' and destination:
            row.prop_search(item, 'target_name', destination.data, 'bones', text='')
        else:
            row.label(text=item.result_name or item.reason)


def build_merge_plan(context, mappings=None):
    destination, source = selected_armatures(context)
    if not destination or not source or destination == source:
        raise ValueError('Choose two different armatures in this scene.')
    for obj in (destination, source):
        if obj.library or obj.override_library or obj.data.library or obj.data.override_library:
            raise ValueError(f'{obj.name} must be a local, editable armature.')
        if abs(obj.matrix_world.determinant()) < 1e-10:
            raise ValueError(f'{obj.name} has a zero scale; correct its transform first.')
    if destination.name not in context.view_layer.objects:
        raise ValueError('The destination must be available in the active view layer.')
    if source.data.pose_position != destination.data.pose_position:
        raise ValueError('Both rigs must use the same Pose Position / Rest Position setting.')
    if source.constraints:
        raise ValueError('The source has object constraints. Bake or remove them before merging.')
    for data in (source, source.data):
        animation = data.animation_data
        if animation and (animation.action or animation.nla_tracks or animation.drivers):
            raise ValueError('The source has animation or drivers. Keep that rig separate until its animation is baked or transferred.')
    for original, target in ((source, destination), (source.data, destination.data)):
        for key, value in _custom_values(original).items():
            if key in target and _custom_values(target)[key] != value:
                raise ValueError(f'Custom property {key!r} differs between the rigs. Rename or reconcile it before merging.')
    for obj in bpy.data.objects:
        if obj.name not in context.scene.objects and (obj.parent == source or any(getattr(mod, 'object', None) == source for mod in obj.modifiers)):
            raise ValueError(f'{obj.name} uses the source in another scene. Move its dependent objects into this scene before merging.')
    destination_meshes, source_meshes = bound_meshes(destination, context), bound_meshes(source, context)
    props = context.scene.avatar_toolkit
    editable_meshes = source_meshes + (destination_meshes if props.join_meshes or props.cleanup_shape_keys or props.remove_zero_weights else [])
    for obj in editable_meshes:
        if obj.library or obj.override_library or obj.data.library or obj.data.override_library:
            raise ValueError(f'{obj.name} must be a local, editable mesh.')
    for obj in source_meshes:
        targets = {m.object for m in obj.modifiers if m.type == 'ARMATURE' and m.object}
        if any(target != source for target in targets):
            raise ValueError(f'{obj.name} uses several rigs. Resolve its armature modifiers before merging.')
    aliases = identify_bones(destination.data)
    source_aliases = {name: role for role, name in identify_bones(source.data).items()}
    choices = {item.source_name: (item.action, item.target_name) for item in mappings} if mappings is not None else {}
    entries = []
    used_targets = set()
    for bone in source.data.bones:
        candidate = bone.name if bone.name in destination.data.bones else aliases.get(source_aliases.get(bone.name))
        valid = bool(candidate and compatible_bones(destination, source, bone.name, candidate))
        action, target = choices.get(bone.name, ('MATCH' if valid else 'KEEP', candidate or ''))
        if action == 'MATCH':
            if target not in destination.data.bones or not compatible_bones(destination, source, bone.name, target):
                raise ValueError(f'{bone.name}: the selected destination bone has a different rest pose or independent pose/constraints. Keep it separate.')
            if target in used_targets:
                raise ValueError(f'Several source bones map to {target}. Keep the ambiguous bones separate.')
            used_targets.add(target)
        reason = 'Compatible match' if action == 'MATCH' else ('Name conflict: rename' if bone.name in destination.data.bones else 'Add bone')
        # Suffix similarities are suggestions only, never automatic destructive matches.
        if not candidate and re.sub(r'\.\d{3}$', '', bone.name) in destination.data.bones:
            reason = 'Suffix similarity: kept separate'
        entries.append({'source': bone.name, 'action': action, 'target': target, 'reason': reason})
    reserved = set(destination.data.bones.keys())
    reserved.update(group.name for mesh in destination_meshes for group in mesh.vertex_groups)
    names = {}
    for entry in entries:
        if entry['action'] == 'MATCH':
            names[entry['source']] = entry['target']
            continue
        desired = entry['source']
        if desired in reserved:
            desired = f"{desired}__{source.name}"
        desired = desired.encode('utf-8')[:55].decode('utf-8', errors='ignore')
        suffix, unique = 1, desired
        while unique in reserved:
            unique = f'{desired}.{suffix:03d}'; suffix += 1
        reserved.add(unique); names[entry['source']] = unique
    roots = [b.name for b in source.data.bones if b.parent is None and any(e['source'] == b.name and e['action'] == 'KEEP' for e in entries)]
    props = context.scene.avatar_toolkit
    attachment = props.merge_attach_bone if props.merge_attach_roots else ''
    if roots and props.merge_attach_roots and attachment not in destination.data.bones:
        raise ValueError('Choose a destination attachment bone, or turn off Attach Source Roots.')
    children = [o for o in context.scene.objects if o.parent == source]
    for child in children:
        if child.library or child.override_library:
            raise ValueError(f'{child.name} is linked and cannot be reparented safely.')
    if props.join_meshes:
        if any(o.parent_type == 'BONE' for o in destination_meshes + source_meshes):
            raise ValueError('Bone-parented meshes must remain separate. Turn off Join Meshes.')
        if len(destination_meshes + source_meshes) != len(set(destination_meshes + source_meshes)):
            raise ValueError('A mesh belongs to both rigs. Turn off Join Meshes and resolve its binding.')
    return {'destination': destination, 'source': source, 'entries': entries, 'names': names,
            'roots': roots, 'attachment': attachment, 'source_meshes': source_meshes,
            'destination_meshes': destination_meshes, 'children': children}


def _activate(context, objects, active):
    if context.object and context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.hide_set(False); obj.hide_select = False; obj.hide_viewport = False; obj.select_set(True)
    context.view_layer.objects.active = active


def _copy_object(obj, collection):
    duplicate = obj.copy(); duplicate.data = obj.data.copy()
    duplicate.name = f'__AvatarMerge_{obj.name}'
    collection.objects.link(duplicate)
    duplicate.hide_viewport = duplicate.hide_select = False
    duplicate.hide_set(False)
    return duplicate


def _rna_values(item):
    values = {}
    for prop in item.bl_rna.properties:
        if prop.is_readonly or prop.identifier in {'rna_type', 'type'} or prop.type == 'COLLECTION':
            continue
        value = getattr(item, prop.identifier)
        values[prop.identifier] = tuple(value) if getattr(prop, 'is_array', False) else value
    return values


def _constraint_snapshot(constraint):
    result = {'type': constraint.type, 'values': _rna_values(constraint)}
    if constraint.type == 'ARMATURE':
        result['targets'] = [_rna_values(target) for target in constraint.targets]
    return result


_POSE_PROPS = ('rotation_mode', 'location', 'rotation_euler', 'rotation_quaternion', 'rotation_axis_angle',
               'scale', 'lock_location', 'lock_rotation', 'lock_rotation_w', 'lock_rotations_4d', 'lock_scale',
               'custom_shape', 'custom_shape_scale_xyz', 'custom_shape_translation', 'custom_shape_rotation',
               'use_custom_shape_bone_size', 'custom_shape_wire_width', 'ik_stretch', 'ik_rotation_weight',
               'ik_linear_weight', 'use_ik_rotation_control', 'use_ik_linear_control')


def _pose_snapshot(obj):
    result = {}
    for bone in obj.pose.bones:
        props = {}
        names = set(_POSE_PROPS)
        names.update(prop.identifier for prop in bone.bl_rna.properties
                     if not prop.is_readonly and prop.identifier.startswith(('bbone_', 'ik_', 'use_ik_', 'lock_ik_')))
        for name in names:
            if hasattr(bone, name):
                rotations = {'rotation_euler', 'rotation_quaternion', 'rotation_axis_angle'}
                active_rotation = 'rotation_quaternion' if bone.rotation_mode == 'QUATERNION' else 'rotation_axis_angle' if bone.rotation_mode == 'AXIS_ANGLE' else 'rotation_euler'
                if name in rotations and name != active_rotation: continue
                value = getattr(bone, name)
                props[name] = tuple(value) if hasattr(value, '__len__') and not isinstance(value, (str, bpy.types.ID)) else value
        result[bone.name] = {'values': props, 'custom': dict(bone.items()),
                             'shape_transform': bone.custom_shape_transform.name if bone.custom_shape_transform else '',
                             'constraints': [_constraint_snapshot(c) for c in bone.constraints]}
    return result


def _custom_values(data):
    def plain(value):
        if hasattr(value, 'to_dict'): return {key: plain(item) for key, item in value.to_dict().items()}
        if hasattr(value, 'to_list'): return value.to_list()
        return value
    # Mapping storage belongs to its rig; bone identities do not affect compatibility.
    metadata = {'avatar_toolkit_humanoid', '_avatar_toolkit_humanoid_id'}
    return {key: plain(value) for key, value in data.items() if key not in metadata}


def _copy_custom(source, destination, added=None):
    if added is None: added = []
    for key, value in _custom_values(source).items():
        if key not in destination:
            destination[key] = value
            added.append(key)
            if not isinstance(value, (dict, bpy.types.ID)):
                metadata = source.id_properties_ui(key).as_dict()
                if metadata: destination.id_properties_ui(key).update(**metadata)
    return added


def _set_values(item, values):
    for name, value in values.items():
        setattr(item, name, value)


def _restore_pose(obj, snapshot):
    for name, info in snapshot.items():
        bone = obj.pose.bones.get(name)
        if not bone:
            continue
        bone.rotation_mode = info['values']['rotation_mode']
        _set_values(bone, {key: value for key, value in info['values'].items() if key != 'rotation_mode'})
        for key in list(bone.keys()): del bone[key]
        for key, value in info['custom'].items(): bone[key] = value
        bone.custom_shape_transform = obj.pose.bones.get(info['shape_transform'])
        for constraint in list(bone.constraints): bone.constraints.remove(constraint)
        for info_constraint in info['constraints']:
            constraint = bone.constraints.new(info_constraint['type'])
            _set_values(constraint, info_constraint['values'])
            for values in info_constraint.get('targets', []): _set_values(constraint.targets.new(), values)


def _replace_path(path, names):
    def substitute(match):
        old = json.loads(match.group(1))
        return 'bones[' + json.dumps(names.get(old, old), ensure_ascii=False) + ']'
    return re.sub(r'bones\[("(?:\\.|[^"\\])*")\]', substitute, path)


def _mesh_positions(context, obj):
    import numpy as np
    context.view_layer.update()
    evaluated = obj.evaluated_get(context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        coordinates = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
        mesh.vertices.foreach_get('co', coordinates)
        matrix = np.array(evaluated.matrix_world)
        return coordinates.reshape((-1, 3)) @ matrix[:3, :3].T + matrix[:3, 3]
    finally:
        evaluated.to_mesh_clear()


def _verify_positions(context, obj, expected):
    import numpy as np
    actual = _mesh_positions(context, obj)
    if actual.shape != expected.shape or not np.allclose(actual, expected, rtol=0, atol=1e-4):
        raise ValueError(f'{obj.name}: this rig combination changes mesh deformation. The merge was cancelled without replacing the original rigs.')

def _reference_changes(context, plan, staged_destination):
    source, destination, names = plan['source'], plan['destination'], plan['names']
    changes = []
    def replace(holder, attr, value):
        if getattr(holder, attr) != value:
            changes.append((holder, attr, getattr(holder, attr), value))
    def target(holder, id_attr, bone_attr=None, path_attr=None):
        original = getattr(holder, id_attr, None)
        if original == source:
            replace(holder, id_attr, destination)
            if bone_attr and getattr(holder, bone_attr, ''):
                replace(holder, bone_attr, names.get(getattr(holder, bone_attr), getattr(holder, bone_attr)))
            if path_attr: replace(holder, path_attr, _replace_path(getattr(holder, path_attr), names))
        elif original == source.data:
            replace(holder, id_attr, staged_destination.data)
            if path_attr: replace(holder, path_attr, _replace_path(getattr(holder, path_attr), names))
        elif original == staged_destination:
            replace(holder, id_attr, destination)
    for obj in context.scene.objects:
        # Destination/source pose constraints are reconstructed from the staged rig.
        constraints = list(obj.constraints)
        if obj.type == 'ARMATURE' and obj not in (source, destination):
            constraints += [c for bone in obj.pose.bones for c in bone.constraints]
        for constraint in constraints:
            for id_attr, bone_attr in (('target', 'subtarget'), ('pole_target', 'pole_subtarget')):
                if hasattr(constraint, id_attr): target(constraint, id_attr, bone_attr if hasattr(constraint, bone_attr) else None)
            if constraint.type == 'ARMATURE':
                for entry in constraint.targets: target(entry, 'target', 'subtarget')
    # Include shape-key and mesh drivers, not just object drivers.
    ids = []
    for prop in bpy.data.bl_rna.properties:
        if prop.type == 'COLLECTION':
            ids.extend(item for item in getattr(bpy.data, prop.identifier) if isinstance(item, bpy.types.ID) and hasattr(item, 'animation_data'))
    ids.extend(item.node_tree for item in ids.copy() if getattr(item, 'node_tree', None))
    for data in ids:
        animation = data.animation_data
        if animation:
            for curve in animation.drivers:
                for variable in curve.driver.variables:
                    for entry in variable.targets: target(entry, 'id', 'bone_target', 'data_path')
    return changes


def _retarget_pose(obj, plan, staged_destination):
    for bone in obj.pose.bones:
        for constraint in bone.constraints:
            for id_attr, bone_attr in (('target', 'subtarget'), ('pole_target', 'pole_subtarget')):
                if not hasattr(constraint, id_attr): continue
                old = getattr(constraint, id_attr)
                if old in (plan['source'], staged_destination):
                    setattr(constraint, id_attr, plan['destination'])
                    if old == plan['source'] and hasattr(constraint, bone_attr):
                        current = getattr(constraint, bone_attr); setattr(constraint, bone_attr, plan['names'].get(current, current))
            if constraint.type == 'ARMATURE':
                for entry in constraint.targets:
                    if entry.target in (plan['source'], staged_destination):
                        if entry.target == plan['source']: entry.subtarget = plan['names'].get(entry.subtarget, entry.subtarget)
                        entry.target = plan['destination']


def _remap_groups(mesh, names):
    # Temporary names avoid Blender's automatic suffixes during permutations.
    pending = [(group, names[group.name]) for group in mesh.vertex_groups if group.name in names]
    prefix = '__AvatarMergeGroup_'
    while any(name.startswith(prefix) for name in mesh.vertex_groups.keys()): prefix += '_'
    for index, (group, _) in enumerate(pending): group.name = f'{prefix}{index}'
    for group, name in pending:
        existing = mesh.vertex_groups.get(name)
        if existing and existing != group:
            for vertex in mesh.data.vertices:
                weights = {item.group: item.weight for item in vertex.groups}
                if group.index in weights:
                    existing.add([vertex.index], min(1.0, weights[group.index] + weights.get(existing.index, 0)), 'REPLACE')
            mesh.vertex_groups.remove(group)
        else:
            group.name = name
    if mesh.data.shape_keys:
        for key in mesh.data.shape_keys.key_blocks:
            key.vertex_group = names.get(key.vertex_group, key.vertex_group)


def _group_schema(mesh):
    return [(group.name, group.lock_weight) for group in mesh.vertex_groups]


def _assign_mesh(mesh, data, schema):
    # Clearing groups also clears weights in its current mesh datablock: isolate it first.
    temporary = mesh.data.copy()
    mesh.data = temporary
    mesh.vertex_groups.clear()
    for name, locked in schema:
        mesh.vertex_groups.new(name=name).lock_weight = locked
    mesh.data = data
    bpy.data.meshes.remove(temporary)


def perform_merge(context, plan, previous_mode=None):
    destination, source = plan['destination'], plan['source']
    props = context.scene.avatar_toolkit
    original_mode = previous_mode or context.mode
    original_active = context.view_layer.objects.active
    original_selection = list(context.selected_objects)
    old_destination_data, old_pose = destination.data, _pose_snapshot(destination)
    world = {obj: obj.matrix_world.copy() for obj in plan['children'] + plan['source_meshes']}
    parents = {obj: (obj.parent, obj.parent_type, obj.parent_bone, obj.matrix_parent_inverse.copy()) for obj in world}
    mesh_backups = {}; applied_changes = []; added_properties = []; committed = False
    original_visible = (destination.hide_viewport, destination.hide_select, destination.hide_get())
    staging = bpy.data.collections.new('__AvatarMergeStaging')
    context.scene.collection.children.link(staging)
    stage_data = []; stage_mesh_data = []
    try:
        staged_destination = _copy_object(destination, staging); stage_data.append(staged_destination.data)
        staged_source = _copy_object(source, staging); stage_data.append(staged_source.data)
        # Linking the copies refreshes driver dependencies before capturing deformation.
        context.view_layer.update()
        expected = {obj: _mesh_positions(context, obj) for obj in dict.fromkeys(plan['destination_meshes'] + plan['source_meshes'])}
        _copy_custom(source.data, staged_destination.data)
        # Disable mirror editing only on temporary copies.
        staged_destination.data.use_mirror_x = staged_source.data.use_mirror_x = False
        staged_destination.pose.use_mirror_x = staged_source.pose.use_mirror_x = False
        muted = [(constraint, constraint.mute) for bone in staged_source.pose.bones for constraint in bone.constraints]
        for constraint, _ in muted: constraint.mute = True
        context.view_layer.update()
        relative = destination.matrix_world.inverted() @ source.matrix_world
        deformation = {}
        for entry in plan['entries']:
            if entry['action'] == 'KEEP':
                bone = source.data.bones[entry['source']]
                pose = staged_source.pose.bones[entry['source']].matrix.copy() if source.data.pose_position == 'POSE' else bone.matrix_local
                deformation[plan['names'][entry['source']]] = relative @ pose @ bone.matrix_local.inverted() @ relative.inverted()
        for constraint, mute in muted: constraint.mute = mute
        parent_names = {plan['names'][bone.name]: plan['names'][bone.parent.name] if bone.parent else plan['attachment']
                        for bone in source.data.bones if any(e['source'] == bone.name and e['action'] == 'KEEP' for e in plan['entries'])}
        _activate(context, [staged_source], staged_source)
        bpy.ops.object.mode_set(mode='EDIT')
        keep = [entry for entry in plan['entries'] if entry['action'] == 'KEEP']
        temporary_prefix = '__AvatarMergeBone_'
        while any(name.startswith(temporary_prefix) for name in staged_source.data.edit_bones.keys()): temporary_prefix += '_'
        for index, entry in enumerate(keep): staged_source.data.edit_bones[entry['source']].name = f'{temporary_prefix}{index}'
        for entry in plan['entries']:
            if entry['action'] == 'MATCH': staged_source.data.edit_bones.remove(staged_source.data.edit_bones[entry['source']])
        for index, entry in enumerate(keep): staged_source.data.edit_bones[f'{temporary_prefix}{index}'].name = plan['names'][entry['source']]
        bpy.ops.object.mode_set(mode='OBJECT')
        if keep:
            _activate(context, [staged_destination, staged_source], staged_destination)
            if bpy.ops.object.join() != {'FINISHED'}: raise RuntimeError('Blender could not join the staged rigs.')
        _activate(context, [staged_destination], staged_destination)
        bpy.ops.object.mode_set(mode='EDIT')
        for name, parent_name in parent_names.items():
            bone = staged_destination.data.edit_bones[name]
            original_name = next(original for original, mapped in plan['names'].items() if mapped == name)
            bone.align_roll((relative.to_3x3() @ source.data.bones[original_name].matrix_local.to_3x3().col[2]).normalized())
            parent = staged_destination.data.edit_bones.get(parent_name)
            if bone.parent != parent:
                bone.use_connect = False; bone.parent = parent
        bpy.ops.object.mode_set(mode='OBJECT')
        context.view_layer.update()
        desired_pose = {name: matrix @ staged_destination.data.bones[name].matrix_local for name, matrix in deformation.items()}
        import uuid
        for name in deformation:
            bone = staged_destination.data.bones[name]
            if bone.get('_avatar_toolkit_humanoid_id'): bone['_avatar_toolkit_humanoid_id'] = uuid.uuid4().hex
        def depth(name):
            bone = staged_destination.data.bones[name]; count = 0
            while bone.parent: count += 1; bone = bone.parent
            return count
        for name in sorted(desired_pose, key=depth):
            staged_destination.pose.bones[name].matrix = desired_pose[name]
            context.view_layer.update()
        context.view_layer.update()
        stage_meshes = {}
        originals = list(plan['source_meshes'])
        if props.join_meshes or props.cleanup_shape_keys or props.remove_zero_weights:
            originals = list(dict.fromkeys(plan['destination_meshes'] + originals))
        for mesh in originals:
            duplicate = _copy_object(mesh, staging); stage_mesh_data.append(duplicate.data)
            if mesh in plan['source_meshes']:
                _remap_groups(duplicate, plan['names'])
                if mesh.parent == source:
                    duplicate.parent = staged_destination
                    if duplicate.parent_type == 'BONE': duplicate.parent_bone = plan['names'].get(mesh.parent_bone, mesh.parent_bone)
                    context.view_layer.update()
                    duplicate.matrix_world = world[mesh]
            for mod in duplicate.modifiers:
                if mod.type == 'ARMATURE' and mod.object in (source, destination): mod.object = staged_destination
            if props.cleanup_shape_keys: remove_unused_shapekeys(duplicate)
            if props.remove_zero_weights:
                used = {g.group for vertex in duplicate.data.vertices for g in vertex.groups if g.weight > 0}
                for group in reversed(list(duplicate.vertex_groups)):
                    if group.index not in used: duplicate.vertex_groups.remove(group)
            _verify_positions(context, duplicate, expected[mesh])
            stage_meshes[mesh] = duplicate
        # Joining is staged as well. The first original mesh remains the output object.
        joined_originals = []
        if props.join_meshes and len(stage_meshes) > 1:
            joined_originals = list(stage_meshes)
            keeper = joined_originals[0]; staged_keeper = stage_meshes[keeper]
            _activate(context, list(stage_meshes.values()), staged_keeper)
            if bpy.ops.object.join() != {'FINISHED'}: raise RuntimeError('Blender could not join the staged meshes.')
            stage_meshes = {keeper: staged_keeper}
            expected[keeper] = _mesh_positions(context, staged_keeper)
        merged_pose = _pose_snapshot(staged_destination)
        reference_changes = _reference_changes(context, plan, staged_destination)
        # Commit only after all staging operations have completed.
        _activate(context, [destination], destination)
        destination.data = staged_destination.data
        _copy_custom(source, destination, added_properties)
        destination.data.use_mirror_x = old_destination_data.use_mirror_x
        _restore_pose(destination, merged_pose)
        _retarget_pose(destination, plan, staged_destination)
        for mesh, duplicate in stage_meshes.items():
            mesh_backups[mesh] = (mesh.data, _group_schema(mesh))
            _assign_mesh(mesh, duplicate.data, _group_schema(duplicate))
        for child in plan['children']:
            child.parent = destination
            if child.parent_type == 'BONE': child.parent_bone = plan['names'].get(child.parent_bone, child.parent_bone)
            context.view_layer.update()
            child.matrix_world = world[child]
        for mesh in plan['source_meshes']:
            for mod in mesh.modifiers:
                if mod.type == 'ARMATURE' and mod.object == source:
                    mod.object = destination; applied_changes.append((mod, 'object', source, destination))
        for holder, attr, old, new in reference_changes:
            setattr(holder, attr, new); applied_changes.append((holder, attr, old, new))
        context.view_layer.update()
        outputs = set(expected) - set(joined_originals[1:])
        for mesh in outputs: _verify_positions(context, mesh, expected[mesh])
        # Deletions are last: errors before this point restore the originals.
        if joined_originals:
            keeper = joined_originals[0]
            for mesh in joined_originals[1:]: mesh.user_remap(keeper)
            for mesh in joined_originals[1:]: bpy.data.objects.remove(mesh, do_unlink=True)
        bpy.data.objects.remove(source, do_unlink=True)
        committed = True
        props.merge_source = None; props.merge_armature = ''
        props.active_armature = f'ARM_{destination.as_pointer()}'
    except Exception:
        for holder, attr, old, _ in reversed(applied_changes): setattr(holder, attr, old)
        for key in added_properties: del destination[key]
        destination.data = old_destination_data
        _restore_pose(destination, old_pose)
        for mesh, (data, schema) in mesh_backups.items(): _assign_mesh(mesh, data, schema)
        for obj, (parent, kind, bone, inverse) in parents.items():
            obj.parent = parent; obj.parent_type = kind; obj.parent_bone = bone; obj.matrix_parent_inverse = inverse; obj.matrix_world = world[obj]
        raise
    finally:
        if context.object and context.object.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(staging.objects): bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(staging)
        for data in stage_data + stage_mesh_data:
            try:
                if data.users == 0:
                    (bpy.data.armatures if isinstance(data, bpy.types.Armature) else bpy.data.meshes).remove(data)
            except ReferenceError: pass
        surviving = [o for o in original_selection if o.name in context.scene.objects] if not committed else [destination]
        active = original_active if not committed and original_active and original_active.name in context.scene.objects else destination
        _activate(context, surviving, active)
        if not committed:
            destination.hide_viewport, destination.hide_select = original_visible[:2]
            destination.hide_set(original_visible[2])
        if original_mode in {'POSE', 'EDIT_ARMATURE'} and active.type == 'ARMATURE':
            bpy.ops.object.mode_set(mode='POSE' if original_mode == 'POSE' else 'EDIT')
    return plan


class AvatarToolkit_OT_MergeArmature(bpy.types.Operator):
    bl_idname = 'avatar_toolkit.merge_armatures'
    bl_label = 'Merge Armatures'
    bl_description = 'Preview bone mapping and attach accessory roots before merging'
    bl_options = {'REGISTER', 'UNDO'}
    mappings: CollectionProperty(type=AvatarToolkitMergeBoneMapping)
    mapping_index: bpy.props.IntProperty()

    def _restore_mode(self, context):
        mode = getattr(self, '_previous_mode', 'OBJECT')
        if context.object and context.object.type == 'ARMATURE' and context.mode == 'OBJECT' and mode in {'POSE', 'EDIT_ARMATURE'}:
            bpy.ops.object.mode_set(mode='POSE' if mode == 'POSE' else 'EDIT')

    def cancel(self, context):
        self._restore_mode(context)

    @classmethod
    def poll(cls, context):
        if not hasattr(context.scene, 'avatar_toolkit'): return False
        destination, source = selected_armatures(context)
        if not destination or not source or destination == source:
            cls.poll_message_set('Choose two different armatures in this scene.')
            return False
        return True

    def invoke(self, context, event):
        try:
            self._previous_mode = context.mode
            if context.object and context.object.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
            plan = build_merge_plan(context)
            self._preview_ids = (plan['destination'].as_pointer(), plan['source'].as_pointer())
            self.mappings.clear()
            for entry in plan['entries']:
                row = self.mappings.add(); row.source_name = entry['source']; row.action = entry['action']
                row.target_name = entry['target']; row.reason = entry['reason']
                row.result_name = plan['names'][entry['source']]
            return context.window_manager.invoke_props_dialog(self, width=720, confirm_text='Merge Armatures')
        except Exception as exc:
            self._restore_mode(context)
            self.report({'ERROR'}, str(exc)); return {'CANCELLED'}

    def draw(self, context):
        layout = self.layout; props = context.scene.avatar_toolkit
        destination, source = selected_armatures(context)
        layout.label(text=f'{source.name if source else "Source"} into {destination.name if destination else "Destination"}')
        layout.prop(props, 'merge_attach_roots')
        if props.merge_attach_roots and destination: layout.prop_search(props, 'merge_attach_bone', destination.data, 'bones')
        layout.template_list('AvatarToolkit_UL_MergeBoneMapping', '', self, 'mappings', self, 'mapping_index', rows=8)
        if self.mappings and self.mapping_index < len(self.mappings): layout.label(text=self.mappings[self.mapping_index].reason)
        layout.label(text='Matching requires compatible rest positions; other bones remain separate.', icon='INFO')
        try:
            plan = build_merge_plan(context, self.mappings)
            for row in self.mappings: row.result_name = plan['names'][row.source_name]
            layout.label(text=f"{sum(e['action']=='KEEP' for e in plan['entries'])} bones added; {sum(e['action']=='MATCH' for e in plan['entries'])} matched; {len(plan['source_meshes'])} source meshes")
            if plan['attachment']:
                for root in plan['roots']: layout.label(text=f"{root} attaches to {plan['attachment']}", icon='BONE_DATA')
            if props.join_meshes or props.cleanup_shape_keys or props.remove_zero_weights:
                layout.label(text='Optional cleanup enabled:', icon='INFO')
                if props.join_meshes: layout.label(text='Join bound meshes')
                if props.cleanup_shape_keys: layout.label(text='Remove unused shape keys')
                if props.remove_zero_weights: layout.label(text='Remove empty vertex groups')
        except ValueError as exc: layout.label(text=str(exc), icon='ERROR')

    def execute(self, context):
        try:
            previous_mode = getattr(self, '_previous_mode', context.mode)
            self._previous_mode = previous_mode
            if context.object and context.object.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
            plan = build_merge_plan(context, self.mappings if self.mappings else None)
            if hasattr(self, '_preview_ids') and self._preview_ids != (plan['destination'].as_pointer(), plan['source'].as_pointer()):
                raise ValueError('The selected rigs changed. Open a new merge preview.')
            if self.mappings and {m.source_name for m in self.mappings} != set(plan['source'].data.bones.keys()):
                raise ValueError('The source bones changed. Open a new merge preview.')
            perform_merge(context, plan, previous_mode)
            self.report({'INFO'}, f"Merged into {plan['destination'].name}; retained accessory bones and rebound meshes.")
            return {'FINISHED'}
        except Exception as exc:
            logger.exception('Armature merge failed')
            self._restore_mode(context)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
