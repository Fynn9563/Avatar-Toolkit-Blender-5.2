import bpy
import tomllib
from pathlib import Path
from bpy.app.handlers import persistent


modules = None
ordered_classes = None

def show_version_error_popup(minimum, maximum):
    def draw(self, context):
        self.layout.label(text="Sorry, this version of Avatar Toolkit does not work on this version of Blender.")
        self.layout.label(text=f"Requires Blender {minimum} or newer, below {maximum}.")
        self.layout.operator("wm.url_open", text="Open GitHub Repository").url = "https://github.com/Fynn9563/Avatar-Toolkit-Blender-5.2"
   
    bpy.context.window_manager.popup_menu(draw, title="Avatar Toolkit Version Error", icon='ERROR')

def register():
    import bpy
    version = bpy.app.version
    with (Path(__file__).parent / 'blender_manifest.toml').open('rb') as manifest_file:
        manifest = tomllib.load(manifest_file)
    minimum, maximum = manifest['blender_version_min'], manifest['blender_version_max']
    if not tuple(map(int, minimum.split('.'))) <= version < tuple(map(int, maximum.split('.'))):
        show_version_error_popup(minimum, maximum)
        return
        
    print("Starting registration")
    
    # Import modules using relative imports
    from . import core
    from .core import auto_load
    from .core.logging_setup import configure_logging
    from .core.addon_preferences import get_preference
    
    # Initialize logging
    configure_logging(False)
    
    auto_load.init()
    try:
        auto_load.register()
    except Exception:
        auto_load.unregister()
        raise
    
    # Verify property registration
    if not hasattr(bpy.types.Scene, "avatar_toolkit"):
        from .core.properties import register as register_properties
        register_properties()

    if hasattr(bpy.types.Scene, "avatar_toolkit"):
        log_level = get_preference("log_level", "WARNING")
        configure_logging(get_preference("enable_logging", False), log_level)
    
    #this needs to be done last, or at least after whatever things this uses is imported - @989onan
    from .functions.tools.apply_shapekey_to_basis import add_to_menu
    bpy.types.MESH_MT_shape_key_context_menu.append(add_to_menu)

    print("Registration complete")

def unregister():
    from .functions.tools.apply_shapekey_to_basis import add_to_menu
    bpy.types.MESH_MT_shape_key_context_menu.remove(add_to_menu)
    from .core import auto_load
    auto_load.unregister()
