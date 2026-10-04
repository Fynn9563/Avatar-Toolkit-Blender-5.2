"""Live anonymous public-release download/install test in an isolated directory."""
import importlib.util
import pathlib
import sys
import tomllib
import bpy
ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/'.validation'
spec=importlib.util.spec_from_file_location('avatar_toolkit',ROOT/'__init__.py',submodule_search_locations=[str(ROOT)])
addon=importlib.util.module_from_spec(spec); sys.modules[spec.name]=addon; spec.loader.exec_module(addon); addon.register()
from avatar_toolkit.core import updater, addon_preferences
addon_preferences.PREFERENCES_FILE=str(OUT/'public-update-preferences.json')
pathlib.Path(addon_preferences.PREFERENCES_FILE).write_text('{}')
assert updater.get_github_releases(), updater.update_error
assert 'Authorization' not in updater._github_headers()
assert 'Authorization' not in updater._github_headers(asset=True)
expected=tomllib.loads((ROOT/'blender_manifest.toml').read_text())['version']
assert expected in updater.version_list, list(updater.version_list)
assert not updater.check_for_update_available(), 'Published version should equal current installation'
target=OUT/'public-update-target'; target.mkdir(exist_ok=True)
(target/'user-file.txt').write_text('preserved')
updater.main_dir=str(target)
assert updater.update_now(latest=True), updater.update_error
manifest=tomllib.loads((target/'blender_manifest.toml').read_text())
assert manifest['version']==expected
assert (target/'core/updater.py').is_file()
assert (target/'core/updater.py').read_bytes()==(ROOT/'core/updater.py').read_bytes(), 'Published updater differs from the local updater'
assert updater.GITHUB_REPO in (target/'core/updater.py').read_text()
assert (target/'user-file.txt').read_text()=='preserved'
assert not (target/'.git').exists()
addon.unregister()
print('LIVE ANONYMOUS UPDATE CHECK, DOWNLOAD AND ISOLATED INSTALL PASSED',expected)
