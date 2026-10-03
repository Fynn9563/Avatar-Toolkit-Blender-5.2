"""Action slot helpers for Blender 5.x."""
from bpy_extras import anim_utils


def ensure_channelbag(action, target):
    """Use the target's assigned slot, or create a slot for its ID type."""
    if target is None:
        raise ValueError("An animation target is required")
    animation_data = target.animation_data_create()
    slot = animation_data.action_slot if animation_data.action == action else None
    if slot is None:
        slot = next((s for s in action.slots if s.target_id_type == target.id_type
                     and s.name_display == target.name), None)
    if slot is None:
        slot = action.slots.new(id_type=target.id_type, name=target.name)
    return anim_utils.action_ensure_channelbag_for_slot(action, slot)


def assign_action(target, action):
    channelbag = ensure_channelbag(action, target)
    animation_data = target.animation_data_create()
    animation_data.action = action
    animation_data.action_slot = next(s for s in action.slots if s.handle == channelbag.slot_handle)
