import traceback
from types import FrameType
import bpy
import bpy_extras
from .animation import assign_action, ensure_channelbag
from numpy import double
from typing import Set, Dict
import re
import traceback

from .common import get_active_armature, ProgressTracker, identify_bones
from bpy.types import Context, Operator
from ..core.translations import t
from ..core.dictionaries import bone_names, resonite_translations, simplify_bonename
from ..core.logging_setup import logger
from ..core.armature_validation import validate_armature


from .resonite_loader import resonite_animx, resonite_types
import os

class AvatarToolKit_OT_ExportResonite(Operator):
    bl_idname = 'avatar_toolkit.export_resonite'
    bl_label = t("Importer.export_resonite.label")
    bl_description = t("Importer.export_resonite.desc")
    bl_options = {'REGISTER', 'UNDO'}
    filepath: bpy.props.StringProperty()

    @classmethod
    def poll(cls, context: Context):
        if get_active_armature(context) is None:
            return False
        return True

    def execute(self, context: Context):
        bpy.ops.export_scene.gltf('INVOKE_AREA',
            export_image_format = 'WEBP',
            export_image_quality = 75,
            export_materials = 'EXPORT',
            export_animations = True,
            export_animation_mode = 'ACTIONS',
            export_nla_strips_merged_animation_name = 'Animation')
        return {'FINISHED'}

class AvatarToolkit_OT_ConvertResonite(Operator):
    """Convert armature bone names to Resonite format with progress tracking and validation"""
    bl_idname = "avatar_toolkit.convert_resonite"
    bl_label = t("Tools.convert_resonite")
    bl_description = t("Tools.convert_resonite_desc")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: Context) -> bool:
        armature = get_active_armature(context)
        if not armature:
            return False
        is_valid, _, _ = validate_armature(armature)
        return is_valid

    def execute(self, context: Context) -> Set[str]:
        armature = get_active_armature(context)
        if not armature:
            logger.warning("No armature selected for Resonite conversion")
            self.report({'WARNING'}, t("Armature.validation.no_armature"))
            return {'CANCELLED'}

        translate_bone_fails: int = 0
        untranslated_bones: Set[str] = set()
        simplified_names: Dict[str, str] = {}

        try:
            context.view_layer.objects.active = armature
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.object.mode_set(mode='OBJECT')
            arm_data: bpy.types.Armature = armature.data
            # Cache simplified bone names
            for bone in arm_data.bones:
                bone.name = re.compile(re.escape("<noik>"), re.IGNORECASE).sub("", bone.name)

            total_bones = len(arm_data.bones)
            with ProgressTracker(context, total_bones, t("Tools.convert_resonite.operation")) as progress:
                for key_simple,bone_name in identify_bones(arm_data).items():
                    bone = arm_data.bones[bone_name]

                    if key_simple in resonite_translations:
                        new_name = resonite_translations[key_simple]
                        logger.debug(f"Translating bone: {bone.name} -> {new_name}")
                        bone.name = new_name
                    else:
                        untranslated_bones.add(bone.name)
                        bone.name = bone.name + "<noik>"
                        translate_bone_fails += 1
                        logger.debug(f"Failed to translate bone: {bone.name}")

                    progress.step(t("Tools.convert_resonite.processing", name=bone.name))

        except Exception:
            logger.error(f"Error during Resonite conversion: {traceback.format_exc()}")
            self.report({'ERROR'}, traceback.format_exc())
            return {'CANCELLED'}

        finally:
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except Exception:
                logger.warning(f"Error returning to object mode: {traceback.format_exc()}")

        if translate_bone_fails > 0:
            logger.info(f"Conversion completed with {translate_bone_fails} untranslated bones")
            logger.debug(f"Untranslated bones: {untranslated_bones}")
            self.report({'INFO'}, t("Tools.bones_translated_with_fails", translate_bone_fails=translate_bone_fails))
        else:
            logger.info("All bones translated successfully")
            self.report({'INFO'}, t("Tools.bones_translated_success"))

        return {'FINISHED'}


def makeorexistingfcurve(action: bpy.types.Action, data_path: str, action_group: str, index=0, target=None) -> bpy.types.FCurve:
    """Get or create a curve in the animation target's action slot."""
    channelbag = ensure_channelbag(action, target or bpy.context.object)
    
    # Use ensure() to get existing or create new F-Curve
    fcurve = channelbag.fcurves.find(data_path, index=index)
    if fcurve is None:
        fcurve = channelbag.fcurves.new(data_path, index=index, group_name=action_group)
    
    return fcurve

class AvatarToolKit_OT_AnimX_Importer(Operator,bpy_extras.io_utils.ImportHelper):
    bl_idname = 'avatar_toolkit.animx_importer'
    bl_label = t('Tools.animx_importer.label')
    bl_description = t('Tools.animx_importer.desc')
    bl_options = {'REGISTER', 'UNDO'}

    #fps = bpy.props.FloatProperty(default=25) #25 fps
    
    filter_glob: bpy.props.StringProperty(
        default="*.animx",
        options={'HIDDEN'}
    )
    files: bpy.props.CollectionProperty(type=bpy.types.OperatorFileListElement, options={'HIDDEN', 'SKIP_SAVE'})
    filepath: bpy.props.StringProperty()

    directory:bpy.props.StringProperty(subtype='DIR_PATH')

    @classmethod
    def poll(cls, context: Context) -> bool:
        return context.active_object != None
        
    def execute(self, context: Context) -> set:
        
        Froox_animations: list[resonite_animx.AnimX] = []

        #decoding using self contained library:
        files = [os.path.join(self.directory, file.name) for file in self.files] or [self.filepath]
        #files.append(self.filepath)
        for file in files:
            froox_animation: resonite_animx.AnimX = resonite_animx.AnimX()
            froox_animation.interval.x = 30 #should be default fps
            if not froox_animation.read(file=file):
                self.report({'ERROR'}, 'Invalid AnimX file')
                return {'CANCELLED'}
            Froox_animations.append(froox_animation)

        #TODO: Allow multiple targets and setting animations to each one somehow with an interface.
        target: bpy.types.Object = context.active_object
        if target.animation_data == None:
            target.animation_data_create()

        #Load data into Blender Animations.
        for froox_animation in Froox_animations:
            action: bpy.types.Action = bpy.data.actions.new(froox_animation.name.x)
            assign_action(target, action)
            action.use_fake_user = True
            for track in froox_animation.tracks:
                data_path: str
                actualproperty: str = track.property.x

                match(actualproperty):
                    case("Position"):
                        actualproperty = "location"
                    case("Rotation"):
                        actualproperty = "rotation_quaternion"
                    case("Scale"):
                        actualproperty = "scale"
                data_path = actualproperty

                if target.type == "ARMATURE":
                    bone = target.pose.bones.get(track.node.x)
                    if bone is None:
                        raise ValueError(f"AnimX bone not found: {track.node.x}")
                    data_path = bone.path_from_id(actualproperty)

                    for posebone in target.pose.bones:
                        posebone.rotation_mode = "QUATERNION"

                print("reading frames for "+data_path)
                value_type = track.FrameType.split('.')[-1]
                if value_type in ('float', 'double'):
                    components = [('x', 0, 1)]
                elif value_type in ('float3', 'double3'):
                    components = [('x', 0, 1), ('y', 2, 1), ('z', 1, 1)]
                elif value_type in ('floatQ', 'doubleQ') or (
                        value_type in ('float4', 'double4') and actualproperty == 'rotation_quaternion'):
                    # Swapping Y/Z is a reflection: quaternion vector part changes sign.
                    components = [('w', 0, 1), ('x', 1, -1), ('y', 3, -1), ('z', 2, -1)]
                elif value_type in ('float4', 'double4'):
                    components = [('x', 0, 1), ('y', 1, 1), ('z', 2, 1), ('w', 3, 1)]
                else:
                    continue
                for component, index, factor in components:
                    curve = makeorexistingfcurve(action, data_path, track.node.x, index, target)
                    self.readTrackData(track, curve, component, factor)
        return {'FINISHED'}

    def readTrackData(self, track, fcurve_reso, valuetype="", factor=1):
        fps = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
        component = valuetype.lstrip('.')
        frames = track.keyframes
        for i, frame in enumerate(frames):
            seconds = i * track.interval.x if isinstance(track, resonite_animx.RawTrack) else frame.time.x
            value = getattr(frame.value, component) * factor
            point = fcurve_reso.keyframe_points.insert(seconds * fps, value)
            if isinstance(track, resonite_animx.DiscreteTrack):
                point.interpolation = 'CONSTANT'
            elif isinstance(track, resonite_animx.CurveTrack):
                point.interpolation = 'CONSTANT' if frame.interpolation.x == 0 else 'LINEAR'
                if track.tangents and frame.RequiresTangents():
                    point.interpolation = 'BEZIER'
                    point.handle_left_type = point.handle_right_type = 'FREE'
                    before = seconds - frames[i-1].time.x if i else 1 / fps
                    after = frames[i+1].time.x - seconds if i+1 < len(frames) else 1 / fps
                    point.handle_left = (seconds*fps - before*fps/3, value - getattr(frame.left_tan, component)*factor*before/3)
                    point.handle_right = (seconds*fps + after*fps/3, value + getattr(frame.right_tan, component)*factor*after/3)
            else:
                point.interpolation = 'LINEAR'
        fcurve_reso.update()
