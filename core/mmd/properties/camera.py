"""Properties animated by MMD camera actions and read by camera drivers."""
import math
import bpy


class MMDCamera(bpy.types.PropertyGroup):
    angle: bpy.props.FloatProperty(
        name="Field of View", subtype='ANGLE', default=math.radians(30),
        min=math.radians(0.1), max=math.radians(179),
    )
    is_perspective: bpy.props.BoolProperty(name="Perspective", default=True)

    @staticmethod
    def register():
        bpy.types.Object.mmd_camera = bpy.props.PointerProperty(type=MMDCamera)

    @staticmethod
    def unregister():
        del bpy.types.Object.mmd_camera
