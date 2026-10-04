"""Exercise the built archive with Blender's extension-style module namespace."""
import importlib.util
import pathlib
import sys
import types
import zipfile
import tomllib
import bpy
import platform
import os

root = pathlib.Path(__file__).resolve().parents[1]
package_root = root / '.validation' / 'package'
candidate = os.environ.get('AVATAR_TOOLKIT_TEST_PACKAGE')
archive_path = pathlib.Path(candidate) if candidate else root / f"avatar_toolkit-{tomllib.loads((root / 'blender_manifest.toml').read_text())['version']}.zip"
with zipfile.ZipFile(archive_path) as archive:
    names = archive.namelist()
    assert 'blender_manifest.toml' in names
    assert not any('.validation/' in n or '__pycache__/' in n or n.endswith('.zip') for n in names)
    archive.extractall(package_root)
wheel_root = root / '.validation' / 'wheel'
manifest = tomllib.loads((package_root / 'blender_manifest.toml').read_text())
wheel_tag = {'Windows': 'win_amd64', 'Linux': 'manylinux', 'Darwin': 'macosx'}[platform.system()]
wheel = next(path for path in manifest['wheels'] if wheel_tag in path
             and (platform.system() != 'Darwin' or platform.machine() in path))
with zipfile.ZipFile(package_root / wheel) as archive:
    archive.extractall(wheel_root)
sys.path.insert(0, str(wheel_root))
import lz4.frame
data = b'Avatar Toolkit Blender 5.2.2' * 20
assert lz4.frame.decompress(lz4.frame.compress(data)) == data
for name in ('bl_ext', 'bl_ext.validation'):
    module = types.ModuleType(name)
    module.__path__ = []
    sys.modules[name] = module
name = 'bl_ext.validation.avatar_toolkit'
spec = importlib.util.spec_from_file_location(name, package_root / '__init__.py', submodule_search_locations=[str(package_root)])
addon = importlib.util.module_from_spec(spec)
sys.modules[name] = addon
spec.loader.exec_module(addon)
addon.register()
assert hasattr(bpy.types.Scene, 'avatar_toolkit')
assert bpy.ops.mmd_tools.import_vmd.get_rna_type()
addon.unregister()
assert not hasattr(bpy.types.Scene, 'avatar_toolkit')
print('PACKAGED EXTENSION AND LZ4 WHEEL PASSED', bpy.app.version_string)
