"""Editable humanoid mapping with explicit, reversible standardization."""
import json
import uuid
from collections import Counter
import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, PointerProperty, StringProperty
from ...core.common import get_active_armature
from ...core.dictionaries import standard_bones, reverse_bone_lookup, simplify_bonename
from ...core.logging_setup import logger

NAMES = {key: name for key, name in standard_bones.items() if not key.startswith('breast_')}
NAMES['jaw'] = 'Jaw'
REQUIRED = {'hips', 'spine', 'head'} | {f'{side}_{part}' for side in ('left', 'right')
                                      for part in ('arm', 'elbow', 'wrist', 'leg', 'knee', 'ankle')}
BONE_ID = '_avatar_toolkit_humanoid_id'
LABELS = {'hips': 'Hips', 'spine': 'Spine', 'chest': 'Chest', 'upper_chest': 'Upper Chest',
          'neck': 'Neck', 'head': 'Head', 'jaw': 'Jaw', 'left_eye': 'Left Eye', 'right_eye': 'Right Eye'}
for side in ('left', 'right'):
    for part, label in (('shoulder', 'Shoulder'), ('arm', 'Upper Arm'), ('elbow', 'Lower Arm'),
                        ('wrist', 'Hand'), ('leg', 'Upper Leg'), ('knee', 'Lower Leg'), ('ankle', 'Foot'), ('toe', 'Toes')):
        LABELS[f'{side}_{part}'] = f'{side.title()} {label}'
for finger in ('thumb', 'index', 'middle', 'ring', 'pinkie'):
    for index, part in enumerate(('Proximal', 'Intermediate', 'Distal'), 1):
        for suffix in ('l', 'r'): LABELS[f'{finger}_{index}_{suffix}'] = f'{finger.title()} {part}'
PARENTS = {'spine': 'hips', 'chest': 'spine', 'upper_chest': 'chest', 'neck': 'upper_chest',
           'head': 'neck', 'jaw': 'head', 'left_eye': 'head', 'right_eye': 'head'}
for side in ('left', 'right'):
    PARENTS.update({f'{side}_shoulder': 'upper_chest', f'{side}_arm': f'{side}_shoulder',
                    f'{side}_elbow': f'{side}_arm', f'{side}_wrist': f'{side}_elbow',
                    f'{side}_leg': 'hips', f'{side}_knee': f'{side}_leg',
                    f'{side}_ankle': f'{side}_knee', f'{side}_toe': f'{side}_ankle'})
    for finger in ('thumb', 'index', 'middle', 'ring', 'pinkie'):
        for index in range(1, 4):
            PARENTS[f'{finger}_{index}_{side[0]}'] = f'{finger}_{index-1}_{side[0]}' if index > 1 else f'{side}_wrist'


def _get_bone_name(item):
    identity = item.get('bone_id', '')
    if identity:
        for bone in item.id_data.bones:
            if bone.get(BONE_ID) == identity: return bone.name
    return item.get('source_name', '')


def _set_bone_name(item, name):
    item['source_name'] = name
    bone = item.id_data.bones.get(name)
    if bone:
        identity = bone.get(BONE_ID)
        if not identity or sum(other.get(BONE_ID) == identity for other in item.id_data.bones) > 1:
            bone[BONE_ID] = uuid.uuid4().hex
        item['bone_id'] = bone[BONE_ID]
    else: item['bone_id'] = ''


class AvatarToolkitHumanoidSlot(bpy.types.PropertyGroup):
    role: StringProperty()
    bone_name: StringProperty(name='Bone', get=_get_bone_name, set=_set_bone_name)
    hint: StringProperty()


class AvatarToolkitHumanoidMapping(bpy.types.PropertyGroup):
    slots: CollectionProperty(type=AvatarToolkitHumanoidSlot)
    initialized: BoolProperty(default=False)
    baseline: StringProperty()
    section: EnumProperty(name='Section', items=[('BODY', 'Body', ''), ('HEAD', 'Head', ''),
                                               ('LEFT', 'Left Hand', ''), ('RIGHT', 'Right Hand', '')])
    reparent: BoolProperty(name='Reparent Mapped Bones', default=False,
                          description='Rebuild assigned humanoid chains; this changes rig parenting')
    normalize_lengths: BoolProperty(name='Normalize Bone Lengths', default=False,
                                   description='Clamp extreme lengths of assigned bones; this changes the rest pose')
    show_changes: BoolProperty(name='Show Rename Preview', default=False)


def editable(armature):
    if armature.data.is_editmode: raise ValueError('Switch to Object or Pose Mode to edit humanoid assignments.')
    if armature.library or armature.override_library or armature.data.library or armature.data.override_library:
        raise ValueError('Choose a local, editable armature.')
    if armature.data.users > 1: raise ValueError('Make this armature data single-user before editing its mapping.')


def save_baseline(mapping):
    mapping.baseline = json.dumps({item.role: {'name': item.bone_name, 'id': item.get('bone_id', '')} for item in mapping.slots})


def initialize_mapping(armature):
    editable(armature)
    mapping = armature.data.avatar_toolkit_humanoid
    known = {item.role for item in mapping.slots}
    for role in NAMES:
        if role not in known: mapping.slots.add().role = role
    if not mapping.initialized:
        mapping.initialized = True; auto_map(armature); save_baseline(mapping)
    return mapping


def auto_map(armature):
    mapping = armature.data.avatar_toolkit_humanoid
    occupied = {item.bone_name for item in mapping.slots if item.bone_name}
    candidates = {role: [] for role in NAMES}
    for bone in armature.data.bones:
        role = next((role for role, name in NAMES.items() if name == bone.name), None)
        if not role:
            role = reverse_bone_lookup.get(simplify_bonename(bone.name))
            if not role: role = reverse_bone_lookup.get(simplify_bonename(bone.name.rsplit(':', 1)[-1]))
        if role in candidates: candidates[role].append(bone.name)
    for item in mapping.slots:
        if item.bone_name: continue
        available = [name for name in candidates[item.role] if name not in occupied]
        if len(available) == 1:
            item.bone_name = available[0]; occupied.add(available[0]); item.hint = 'Auto-mapped; review assignment'
        elif available: item.hint = 'Ambiguous: ' + ', '.join(available)
        else: item.hint = ''


def assigned_roles(armature):
    return {item.role: item.bone_name for item in armature.data.avatar_toolkit_humanoid.slots if item.role in NAMES and item.bone_name}


def expected_parent(role, assigned):
    role = PARENTS.get(role)
    while role and role not in assigned: role = PARENTS.get(role)
    return assigned.get(role)


def mapping_status(armature):
    assigned = assigned_roles(armature); counts = Counter(assigned.values())
    identities = Counter(bone.get(BONE_ID) for bone in armature.data.bones if bone.get(BONE_ID))
    slots = {item.role: item for item in armature.data.avatar_toolkit_humanoid.slots}
    errors, warnings = [], []
    for role, name in assigned.items():
        if name not in armature.data.bones: errors.append(f'{LABELS[role]}: bone {name!r} is missing')
        elif slots[role].get('bone_id') and identities[slots[role]['bone_id']] != 1:
            errors.append(f'{LABELS[role]}: assigned bone was deleted or duplicated; assign it again')
        elif counts[name] > 1: errors.append(f'{name}: assigned to multiple roles')
        else:
            parent_name = expected_parent(role, assigned)
            if parent_name:
                parent = armature.data.bones[name].parent
                while parent and parent.name != parent_name: parent = parent.parent
                if not parent: warnings.append(f'{LABELS[role]} is outside the expected humanoid chain')
    return assigned, errors, warnings, REQUIRED - assigned.keys()


def build_standardize_plan(armature):
    editable(armature); mapping = initialize_mapping(armature)
    assigned, errors, warnings, missing = mapping_status(armature)
    if errors: raise ValueError(errors[0])
    if not assigned: raise ValueError('Assign at least one bone before applying.')
    names = {old: NAMES[role] for role, old in assigned.items() if old != NAMES[role]}
    for old, new in names.items():
        if new in armature.data.bones and new not in names:
            raise ValueError(f'{old} cannot become {new}: an unassigned bone already uses that name.')
    from ..custom_tools.armature_merging import bound_meshes
    meshes = bound_meshes(armature, bpy.context)
    for mesh in meshes:
        if mesh.library or mesh.override_library or mesh.data.library or mesh.data.override_library:
            raise ValueError(f'{mesh.name} is linked and cannot be updated safely.')
        if any(mod.type == 'ARMATURE' and mod.object and mod.object != armature for mod in mesh.modifiers):
            raise ValueError(f'{mesh.name} uses multiple rigs; separate its bindings before renaming bones.')
        for old, new in names.items():
            if new in mesh.vertex_groups and new not in names:
                raise ValueError(f'{mesh.name}: vertex group {new} conflicts with the assigned bone.')
    parenting = {name: expected_parent(role, assigned) for role, name in assigned.items()
                 if expected_parent(role, assigned) and (not armature.data.bones[name].parent or
                    armature.data.bones[name].parent.name != expected_parent(role, assigned))} if mapping.reparent else {}
    if parenting:
        tree = {bone.name: parenting.get(bone.name, bone.parent.name if bone.parent else None) for bone in armature.data.bones}
        for name in tree:
            path = set(); current = name
            while current:
                if current in path: raise ValueError(f'Reparenting would create a cycle at {current}. Review assignments and helper parents.')
                path.add(current); current = tree.get(current)
    lengths = {}
    if mapping.normalize_lengths:
        valid = sorted(armature.data.bones[name].length for name in assigned.values() if armature.data.bones[name].length > 1e-5)
        if valid:
            median = valid[len(valid)//2]
            for role, name in assigned.items():
                length = armature.data.bones[name].length
                minimum = 0 if role.startswith(('thumb_', 'index_', 'middle_', 'ring_', 'pinkie_')) else median * .05
                corrected = min(median * 15, max(minimum, length))
                if abs(corrected-length) > 1e-6: lengths[name] = corrected
    return {'names': names, 'assigned': assigned, 'parents': parenting, 'lengths': lengths,
            'meshes': meshes, 'warnings': warnings, 'missing': missing}


def _reference_snapshot(armature, names):
    from ..custom_tools.armature_merging import _replace_path
    result = []
    def record(holder, field, updated):
        original = getattr(holder, field)
        if original != updated: result.append((holder, field, original, updated))
    for obj in bpy.data.objects:
        if obj.parent == armature and obj.parent_type == 'BONE': record(obj, 'parent_bone', names.get(obj.parent_bone, obj.parent_bone))
        constraints = list(obj.constraints)
        if obj.type == 'ARMATURE': constraints += [c for bone in obj.pose.bones for c in bone.constraints]
        for constraint in constraints:
            for target, field in (('target', 'subtarget'), ('pole_target', 'pole_subtarget')):
                if getattr(constraint, target, None) == armature and hasattr(constraint, field):
                    record(constraint, field, names.get(getattr(constraint, field), getattr(constraint, field)))
            if constraint.type == 'ARMATURE':
                for target in constraint.targets:
                    if target.target == armature: record(target, 'subtarget', names.get(target.subtarget, target.subtarget))
    ids = []
    for prop in bpy.data.bl_rna.properties:
        if prop.type == 'COLLECTION': ids.extend(item for item in getattr(bpy.data, prop.identifier) if isinstance(item, bpy.types.ID) and hasattr(item, 'animation_data'))
    ids.extend(item.node_tree for item in ids.copy() if getattr(item, 'node_tree', None))
    for data in ids:
        if not data.animation_data: continue
        for curve in data.animation_data.drivers:
            if data in (armature, armature.data): record(curve, 'data_path', _replace_path(curve.data_path, names))
            for variable in curve.driver.variables:
                for target in variable.targets:
                    if target.id in (armature, armature.data):
                        record(target, 'bone_target', names.get(target.bone_target, target.bone_target))
                        record(target, 'data_path', _replace_path(target.data_path, names))
    return result


def _actions(armature):
    bindings = []
    for data in (armature, armature.data):
        animation = data.animation_data
        if not animation: continue
        if animation.action: bindings.append(animation)
        def strips(items):
            for strip in items:
                if strip.type == 'META': strips(strip.strips)
                elif strip.action: bindings.append(strip)
        for track in animation.nla_tracks: strips(track.strips)
    return bindings


def apply_standardization(context, armature, plan):
    from ..custom_tools.armature_merging import _activate, _replace_path
    mode, active, selection = context.mode, context.view_layer.objects.active, list(context.selected_objects)
    bones = dict(armature.data.bones.items())
    original_names = [(bone, name) for name, bone in bones.items()]
    rest = {name: (bone.head_local.copy(), bone.tail_local.copy(), bone.matrix_local.copy(), bone.parent.name if bone.parent else '', bone.use_connect) for name, bone in bones.items()}
    groups = [(group, group.name) for mesh in plan['meshes'] for group in mesh.vertex_groups]
    masks = [(key, key.vertex_group) for mesh in plan['meshes'] if mesh.data.shape_keys for key in mesh.data.shape_keys.key_blocks]
    refs = _reference_snapshot(armature, plan['names'])
    action_backups, paths, copies = [], [], []
    changed_rest = False
    prefix = '__AvatarStandardize_'
    while any(name.startswith(prefix) for name in bones) or any(name.startswith(prefix) for _, name in groups): prefix += '_'
    def rename(items, mapping):
        pending = [(bone, mapping[name]) for bone, name in items if name in mapping]
        for index, (bone, _) in enumerate(pending): bone.name = f'{prefix}{index}'
        for bone, name in pending: bone.name = name
    try:
        _activate(context, [armature], armature)
        action_map = {}
        if plan['names']:
            for binding in _actions(armature):
                action = binding.action; handle = binding.action_slot.handle if binding.action_slot else None
                action_backups.append((binding, action, handle))
                if action not in action_map: action_map[action] = action.copy(); copies.append(action_map[action])
                binding.action = action_map[action]
                if handle is not None: binding.action_slot = next(slot for slot in binding.action.slots if slot.handle == handle)
            for action in copies:
                for layer in action.layers:
                    for strip in layer.strips:
                        for bag in getattr(strip, 'channelbags', []):
                            for curve in bag.fcurves: paths.append((curve, curve.data_path, _replace_path(curve.data_path, plan['names'])))
        rename(original_names, plan['names'])
        # Modifier-only meshes may not receive Blender's automatic group renames.
        pending_groups = [(group, plan['names'][old]) for group, old in groups if old in plan['names']]
        for index, (group, _) in enumerate(pending_groups): group.name = f'{prefix}Group{index}'
        for group, new in pending_groups: group.name = new
        for key, old in masks: key.vertex_group = plan['names'].get(old, old)
        for holder, field, _, new in refs: setattr(holder, field, new)
        for curve, _, new in paths: curve.data_path = new
        if plan['parents'] or plan['lengths']:
            changed_rest = True; bpy.ops.object.mode_set(mode='EDIT'); edit = armature.data.edit_bones
            for old in plan['parents']:
                bone = edit[plan['names'].get(old, old)]; bone.use_connect = False; bone.parent = None
            for old, parent in plan['parents'].items(): edit[plan['names'].get(old, old)].parent = edit[plan['names'].get(parent, parent)]
            for old, length in plan['lengths'].items(): edit[plan['names'].get(old, old)].length = length
            bpy.ops.object.mode_set(mode='OBJECT')
        context.view_layer.update(); save_baseline(armature.data.avatar_toolkit_humanoid)
    except Exception:
        if context.object.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
        current = [(armature.data.bones[plan['names'].get(old, old)], old) for _, old in original_names] if changed_rest else [(bone, old) for bone, old in original_names]
        rename([(bone, bone.name) for bone, _ in current], {bone.name: old for bone, old in current})
        if changed_rest:
            bpy.ops.object.mode_set(mode='EDIT')
            for name, (head, tail, matrix, parent, connected) in rest.items():
                bone = armature.data.edit_bones[name]; bone.use_connect = False; bone.parent = None
                bone.matrix = matrix; bone.head = head; bone.tail = tail
            for name, (_, _, _, parent, connected) in rest.items():
                bone = armature.data.edit_bones[name]; bone.parent = armature.data.edit_bones.get(parent); bone.use_connect = connected
            bpy.ops.object.mode_set(mode='OBJECT')
        for index, (group, _) in enumerate(groups): group.name = f'{prefix}Group{index}'
        for group, old in groups: group.name = old
        for key, old in masks: key.vertex_group = old
        for holder, field, old, _ in refs: setattr(holder, field, old)
        for binding, action, handle in action_backups:
            binding.action = action
            if handle is not None: binding.action_slot = next(slot for slot in action.slots if slot.handle == handle)
        for action in copies:
            if action.users == 0: bpy.data.actions.remove(action)
        raise
    finally:
        _activate(context, selection, active or armature)
        if mode in {'POSE', 'EDIT_ARMATURE'} and context.object and context.object.type == 'ARMATURE': bpy.ops.object.mode_set(mode='POSE' if mode == 'POSE' else 'EDIT')


def draw_mapping(layout, context):
    armature = get_active_armature(context)
    if not armature: return
    mapping = armature.data.avatar_toolkit_humanoid
    if not mapping.initialized:
        layout.operator('avatar_toolkit.humanoid_auto_map', text='Set Up Bone Mapping', icon='ARMATURE_DATA'); return
    assigned, errors, warnings, missing = mapping_status(armature)
    layout.label(text=f'{len(REQUIRED)-len(missing)} / {len(REQUIRED)} required roles assigned', icon='ERROR' if errors else 'INFO')
    row = layout.row(align=True)
    row.operator('avatar_toolkit.humanoid_auto_map', text='Auto Map'); row.operator('avatar_toolkit.humanoid_reset_mapping', text='Revert'); row.operator('avatar_toolkit.humanoid_clear_mapping', text='Clear')
    layout.prop(mapping, 'section', expand=True)
    counts = Counter(assigned.values())
    for item in mapping.slots:
        role = item.role
        finger = role.startswith(('thumb_', 'index_', 'middle_', 'ring_', 'pinkie_'))
        head = role in {'head', 'neck', 'left_eye', 'right_eye', 'jaw'}
        visible = ((mapping.section == 'BODY' and not finger and not head) or (mapping.section == 'HEAD' and head) or
                   (mapping.section in {'LEFT', 'RIGHT'} and finger and role.endswith('_' + mapping.section[0].lower())))
        if not visible: continue
        row = layout.row(align=True); row.alert = bool(item.bone_name and (item.bone_name not in armature.data.bones or counts[item.bone_name] > 1)) or (role in REQUIRED and not item.bone_name)
        row.label(text=LABELS[role] + (' *' if role in REQUIRED else '')); row.prop_search(item, 'bone_name', armature.data, 'bones', text='')
        op = row.operator('avatar_toolkit.humanoid_assign_selected', text='', icon='EYEDROPPER'); op.role = role
        if item.bone_name:
            op = row.operator('avatar_toolkit.humanoid_select_bone', text='', icon='VIEWZOOM'); op.role = role
        if item.hint.startswith('Ambiguous') and not item.bone_name: layout.label(text=item.hint, icon='QUESTION')
    layout.label(text='* Required humanoid role. Empty optional roles are allowed.')
    layout.prop(mapping, 'reparent'); layout.prop(mapping, 'normalize_lengths')
    if mapping.reparent or mapping.normalize_lengths: layout.label(text='These options change parenting or the rest pose.', icon='ERROR')
    for message in errors[:3]: layout.label(text=message, icon='ERROR')
    if warnings: layout.label(text=f'{len(warnings)} hierarchy warnings; review bone assignments.', icon='INFO')


class HumanoidOperator:
    @classmethod
    def poll(cls, context):
        armature = get_active_armature(context)
        return bool(armature and context.mode in {'OBJECT', 'POSE'} and not armature.data.is_editmode
                    and not armature.library and not armature.data.library)


class AvatarToolkit_OT_HumanoidAutoMap(HumanoidOperator, bpy.types.Operator):
    bl_idname = 'avatar_toolkit.humanoid_auto_map'
    bl_label = 'Auto Map Humanoid Bones'
    bl_description = 'Suggest unambiguous matches for empty roles; keep existing assignments'
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        try:
            armature = get_active_armature(context); initialize_mapping(armature); auto_map(armature); return {'FINISHED'}
        except ValueError as exc: self.report({'ERROR'}, str(exc)); return {'CANCELLED'}


class AvatarToolkit_OT_HumanoidClear(HumanoidOperator, bpy.types.Operator):
    bl_idname = 'avatar_toolkit.humanoid_clear_mapping'
    bl_label = 'Clear Humanoid Assignments'
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        for item in initialize_mapping(get_active_armature(context)).slots: item.bone_name = ''; item.hint = ''
        return {'FINISHED'}


class AvatarToolkit_OT_HumanoidReset(HumanoidOperator, bpy.types.Operator):
    bl_idname = 'avatar_toolkit.humanoid_reset_mapping'
    bl_label = 'Revert Humanoid Assignments'
    bl_description = 'Restore assignments from the last Apply, or initial auto-mapping'
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        mapping = initialize_mapping(get_active_armature(context)); baseline = json.loads(mapping.baseline or '{}')
        for item in mapping.slots:
            item['source_name'] = baseline.get(item.role, {}).get('name', '')
            item['bone_id'] = baseline.get(item.role, {}).get('id', ''); item.hint = ''
        return {'FINISHED'}


class AvatarToolkit_OT_HumanoidAssignSelected(HumanoidOperator, bpy.types.Operator):
    bl_idname = 'avatar_toolkit.humanoid_assign_selected'
    bl_label = 'Assign Selected Bone'
    bl_options = {'REGISTER', 'UNDO'}
    role: StringProperty()
    def execute(self, context):
        armature = get_active_armature(context); bone = armature.data.bones.active
        if context.object != armature or context.mode != 'POSE' or not bone or not armature.pose.bones[bone.name].select:
            self.report({'WARNING'}, 'Select a bone on this armature in Pose Mode first.'); return {'CANCELLED'}
        item = next((item for item in initialize_mapping(armature).slots if item.role == self.role), None)
        if not item: return {'CANCELLED'}
        item.bone_name = bone.name; item.hint = 'Manually assigned'; return {'FINISHED'}


class AvatarToolkit_OT_HumanoidSelectBone(HumanoidOperator, bpy.types.Operator):
    bl_idname = 'avatar_toolkit.humanoid_select_bone'
    bl_label = 'Select Assigned Bone'
    role: StringProperty()
    def execute(self, context):
        from ..custom_tools.armature_merging import _activate
        armature = get_active_armature(context); name = assigned_roles(armature).get(self.role)
        if name not in armature.data.bones: return {'CANCELLED'}
        _activate(context, [armature], armature); bpy.ops.object.mode_set(mode='POSE')
        for bone in armature.pose.bones: bone.select = False
        armature.pose.bones[name].select = True; armature.data.bones.active = armature.data.bones[name]; return {'FINISHED'}


class AvatarToolkit_OT_StandardizeArmature(HumanoidOperator, bpy.types.Operator):
    bl_idname = 'avatar_toolkit.standardize_armature'
    bl_label = 'Configure Humanoid Bones'
    bl_description = 'Assign humanoid bone roles and review changes before applying standard names'
    bl_options = {'REGISTER', 'UNDO'}
    def invoke(self, context, event):
        try:
            armature = get_active_armature(context); initialize_mapping(armature); self._armature_id = armature.as_pointer()
            return context.window_manager.invoke_props_dialog(self, width=700, confirm_text='Apply Standardization')
        except ValueError as exc: self.report({'ERROR'}, str(exc)); return {'CANCELLED'}
    def draw(self, context):
        draw_mapping(self.layout, context); armature = get_active_armature(context)
        if not armature: return
        try:
            plan = build_standardize_plan(armature)
            self.layout.label(text=f"{len(plan['names'])} renames; {len(plan['parents'])} parent relationships; {len(plan['lengths'])} length changes")
            self.layout.prop(armature.data.avatar_toolkit_humanoid, 'show_changes')
            if armature.data.avatar_toolkit_humanoid.show_changes:
                for old, new in plan['names'].items(): self.layout.label(text=f'{old} → {new}')
        except ValueError as exc: self.layout.label(text=str(exc), icon='ERROR')
    def execute(self, context):
        try:
            armature = get_active_armature(context)
            if hasattr(self, '_armature_id') and armature.as_pointer() != self._armature_id: raise ValueError('The selected rig changed. Open its bone mapping again.')
            plan = build_standardize_plan(armature); apply_standardization(context, armature, plan)
            self.report({'INFO'}, f"Renamed {len(plan['names'])} assigned bones; {len(plan['missing'])} required roles remain unassigned.")
            return {'FINISHED'}
        except Exception as exc:
            logger.exception('Humanoid standardization failed'); self.report({'ERROR'}, str(exc)); return {'CANCELLED'}


def register():
    bpy.types.Armature.avatar_toolkit_humanoid = PointerProperty(type=AvatarToolkitHumanoidMapping)


def unregister():
    if hasattr(bpy.types.Armature, 'avatar_toolkit_humanoid'): del bpy.types.Armature.avatar_toolkit_humanoid
