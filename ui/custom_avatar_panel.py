import bpy
from typing import Set, List, Tuple, Any
from bpy.types import Panel, Context, UILayout, Operator, Event, WindowManager
from .main_panel import AvatarToolKit_PT_AvatarToolkitPanel, CATEGORY_NAME
from .panel_layout import get_panel_order, should_open_by_default
from ..functions.custom_tools.mesh_attachment import AvatarToolkit_OT_AttachMesh
from ..functions.custom_tools.armature_merging import AvatarToolkit_OT_MergeArmature, resolve_armature
from ..core.translations import t
from ..core.common import (
    get_active_armature,
    get_all_meshes,
    get_armature_list
)
from ..core.armature_validation import validate_armature

class AvatarToolkit_OT_SearchMergeArmatureInto(Operator):
    """Search operator for selecting target armature to merge into"""
    bl_idname: str = "avatar_toolkit.search_merge_armature_into"
    bl_label: str = ""
    bl_description: str = t('MergeArmature.into_search_desc')
    bl_property: str = "search_merge_armature_into_enum"

    search_merge_armature_into_enum: bpy.props.EnumProperty(
        name=t('MergeArmature.into'),
        description=t('MergeArmature.into_desc'),
        items=get_armature_list
    )

    def execute(self, context: Context) -> Set[str]:
        obj = resolve_armature(self.search_merge_armature_into_enum, context)
        if not obj: return {'CANCELLED'}
        context.scene.avatar_toolkit.merge_destination = obj
        return {'FINISHED'}

    def invoke(self, context: Context, event: Event) -> Set[str]:
        context.window_manager.invoke_search_popup(self)
        return {'FINISHED'}

class AvatarToolkit_OT_SearchMergeArmature(Operator):
    """Search operator for selecting source armature to merge from"""
    bl_idname: str = "avatar_toolkit.search_merge_armature"
    bl_label: str = ""
    bl_description: str = t('MergeArmature.from_search_desc')
    bl_property: str = "search_merge_armature_enum"

    search_merge_armature_enum: bpy.props.EnumProperty(
        name=t('MergeArmature.from'),
        description=t('MergeArmature.from_desc'),
        items=get_armature_list
    )

    def execute(self, context: Context) -> Set[str]:
        obj = resolve_armature(self.search_merge_armature_enum, context)
        if not obj: return {'CANCELLED'}
        context.scene.avatar_toolkit.merge_source = obj
        return {'FINISHED'}

    def invoke(self, context: Context, event: Event) -> Set[str]:
        context.window_manager.invoke_search_popup(self)
        return {'FINISHED'}

class AvatarToolkit_OT_SearchAttachMesh(Operator):
    """Search operator for selecting mesh to attach to armature"""
    bl_idname: str = "avatar_toolkit.search_attach_mesh"
    bl_label: str = ""
    bl_description: str = t('AttachMesh.search_desc')
    bl_property: str = "search_attach_mesh_enum"

    search_attach_mesh_enum: bpy.props.EnumProperty(
        name=t('AttachMesh.select'),
        description=t('AttachMesh.select_desc'),
        items=lambda self, context: [
            (obj.name, obj.name, "") 
            for obj in bpy.data.objects 
            if obj.type == 'MESH' 
            and not any(mod.type == 'ARMATURE' for mod in obj.modifiers)
        ]
    )

    def execute(self, context: Context) -> Set[str]:
        context.scene.avatar_toolkit.attach_mesh = self.search_attach_mesh_enum
        return {'FINISHED'}

    def invoke(self, context: Context, event: Event) -> Set[str]:
        context.window_manager.invoke_search_popup(self)
        return {'FINISHED'}

class AvatarToolkit_OT_SearchAttachBone(Operator):
    """Search operator for selecting bone to attach mesh to"""
    bl_idname: str = "avatar_toolkit.search_attach_bone"
    bl_label: str = ""
    bl_description: str = t('AttachBone.search_desc')
    bl_property: str = "search_attach_bone_enum"

    search_attach_bone_enum: bpy.props.EnumProperty(
        name=t('AttachBone.select'),
        description=t('AttachBone.select_desc'),
        items=lambda self, context: [
            (bone.name, bone.name, "")
            for bone in get_active_armature(context).data.bones
        ] if get_active_armature(context) else []
    )

    def execute(self, context: Context) -> Set[str]:
        context.scene.avatar_toolkit.attach_bone = self.search_attach_bone_enum
        return {'FINISHED'}

    def invoke(self, context: Context, event: Event) -> Set[str]:
        context.window_manager.invoke_search_popup(self)
        return {'FINISHED'}

class AvatarToolKit_PT_CustomPanel(Panel):
    """Panel containing tools for custom avatar creation and merging"""
    bl_label: str = t('CustomPanel.label')
    bl_idname: str = "VIEW3D_PT_avatar_toolkit_custom"
    bl_space_type: str = 'VIEW_3D'
    bl_region_type: str = 'UI'
    bl_category: str = CATEGORY_NAME
    bl_parent_id: str = AvatarToolKit_PT_AvatarToolkitPanel.bl_idname
    bl_order: int = get_panel_order('custom_avatar')
    bl_options: Set[str] = set() if not should_open_by_default('CUSTOM_AVATAR') else {'DEFAULT_CLOSED'}

    def draw(self, context: Context) -> None:
        """Draw the custom avatar panel UI"""
        layout: UILayout = self.layout
        toolkit = context.scene.avatar_toolkit

        # Mode Selection Box
        mode_box: UILayout = layout.box()
        col: UILayout = mode_box.column(align=True)
        col.label(text=t('CustomPanel.merge_mode'), icon='TOOL_SETTINGS')
        col.separator(factor=0.5)

        row: UILayout = col.row(align=True)
        row.scale_y = 1.5
        row.prop(toolkit, "merge_mode", expand=True)
        
        if toolkit.merge_mode == 'ARMATURE':
            self.draw_armature_tools(layout, context)
        else:
            self.draw_mesh_tools(layout, context)

    def draw_armature_tools(self, layout: UILayout, context: Context) -> None:
        """Draw the armature merging tools section"""
        toolkit = context.scene.avatar_toolkit
        
        box = layout.box()
        col = box.column(align=True)
        col.prop(toolkit, 'merge_destination')
        col.prop(toolkit, 'merge_source')
        col.separator()
        col.prop(toolkit, 'merge_attach_roots')
        if toolkit.merge_attach_roots and toolkit.merge_destination:
            col.prop_search(toolkit, 'merge_attach_bone', toolkit.merge_destination.data, 'bones')
            if not toolkit.merge_attach_bone:
                col.label(text='Choose an attachment bone, or leave roots unparented.', icon='INFO')
        box = layout.box()
        col = box.column(align=True)
        col.label(text='Optional Cleanup', icon='SETTINGS')
        col.prop(toolkit, 'join_meshes')
        col.prop(toolkit, 'remove_zero_weights')
        col.prop(toolkit, 'cleanup_shape_keys')
        row = layout.row()
        row.scale_y = 1.5
        row.operator(AvatarToolkit_OT_MergeArmature.bl_idname, text='Preview Merge', icon='ARMATURE_DATA')

    def draw_mesh_tools(self, layout: UILayout, context: Context) -> None:
        """Draw the mesh attachment tools section"""
        toolkit = context.scene.avatar_toolkit
        
        # Mesh Tools Box
        tools_box: UILayout = layout.box()
        col: UILayout = tools_box.column(align=True)
        col.label(text=t('AttachMesh.label'), icon='MESH_DATA')
        col.separator(factor=0.5)

        if not get_active_armature(context) or not get_all_meshes(context):
            col.label(text=t('AttachMesh.warn_no_armature'), icon='INFO')
            return

        # Selection Box with consistent styling
        selection_box: UILayout = layout.box()
        col: UILayout = selection_box.column(align=True)
        col.label(text=t('CustomPanel.mesh_selection'), icon='OBJECT_DATA')
        col.separator(factor=0.5)

        # Selection rows with icons and better alignment
        row: UILayout = col.row(align=True)
        row.label(text=t('CustomPanel.select_armature'), icon='ARMATURE_DATA')
        row.operator(AvatarToolkit_OT_SearchMergeArmatureInto.bl_idname,
                    text=toolkit.merge_armature_into)

        row: UILayout = col.row(align=True)
        row.label(text=t('CustomPanel.select_mesh'), icon='MESH_DATA')
        row.operator(AvatarToolkit_OT_SearchAttachMesh.bl_idname,
                    text=toolkit.attach_mesh)

        row: UILayout = col.row(align=True)
        row.label(text=t('CustomPanel.select_bone'), icon='BONE_DATA')
        row.operator(AvatarToolkit_OT_SearchAttachBone.bl_idname,
                    text=toolkit.attach_bone)

        # Attach button with emphasis
        attach_box: UILayout = layout.box()
        col: UILayout = attach_box.column(align=True)
        row: UILayout = col.row(align=True)
        row.scale_y = 1.5
        row.operator(AvatarToolkit_OT_AttachMesh.bl_idname, icon='ARMATURE_DATA')
