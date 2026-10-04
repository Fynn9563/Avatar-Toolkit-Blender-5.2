"""Public updater integration test; CI can supply an unpublished candidate ZIP."""
import io
import json
import os
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
expected=tomllib.loads((ROOT/'blender_manifest.toml').read_text())['version']
candidate = os.environ.get('AVATAR_TOOLKIT_TEST_PACKAGE')
if candidate:
    from unittest.mock import patch
    candidate = pathlib.Path(candidate).resolve()
    asset_url = f'https://api.github.com/repos/{updater.GITHUB_REPO}/releases/assets/1'
    releases_url = f'https://api.github.com/repos/{updater.GITHUB_REPO}/releases?per_page=100'
    releases = [{'tag_name': expected, 'assets': [
        {'name': f'avatar_toolkit-{expected}.zip', 'url': asset_url}]}]
    def candidate_response(url, asset=False):
        if url == releases_url and not asset:
            return io.BytesIO(json.dumps(releases).encode())
        if url == asset_url and asset:
            return candidate.open('rb')
        raise AssertionError(f'Unexpected updater request: {url}, asset={asset}')
    candidate_patch = patch.object(updater, '_open_github', side_effect=candidate_response)
    candidate_patch.start()
assert updater.get_github_releases(), updater.update_error
assert 'Authorization' not in updater._github_headers()
assert 'Authorization' not in updater._github_headers(asset=True)
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
if candidate:
    candidate_patch.stop()
print('PUBLIC UPDATE CHECK, DOWNLOAD AND ISOLATED INSTALL PASSED',expected)
