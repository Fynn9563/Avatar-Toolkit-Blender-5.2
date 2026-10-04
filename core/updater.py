import bpy
import os
import subprocess
import tempfile
import tomllib
import re
from queue import Queue
from urllib.parse import urlparse
import json
import shutil
import pathlib
import zipfile
import time 
from urllib import request
from threading import Thread
from bpy.app.handlers import persistent
from .translations import t
from .addon_preferences import get_preference, get_current_version, save_preference
from ..ui.main_panel import AvatarToolKit_PT_AvatarToolkitPanel, CATEGORY_NAME
from typing import Dict, List, Tuple, Optional, Set, Any

GITHUB_REPO = "Fynn9563/Avatar-Toolkit-Blender-5.2"
update_error = ""
_pending_checks = Queue()

# Define which version series this installation can update to
# For example: ["0.1"] means only look for 0.1.x updates
# ["0.2", "0.3"] would look for both 0.2.x and 0.3.x
ALLOWED_VERSION_SERIES = ["0.5"]

is_checking_for_update: bool = False
update_needed: bool = False
latest_version: Optional[str] = None
latest_version_str: str = ''
version_list: Optional[Dict[str, List[str]]] = None
last_manual_check_time: float = 0

main_dir: str = os.path.dirname(os.path.dirname(__file__))


class AvatarToolkit_OT_CheckForUpdate(bpy.types.Operator):
    bl_idname = 'avatar_toolkit.check_for_update'
    bl_label = t('CheckForUpdateButton.label')
    bl_description = t('CheckForUpdateButton.desc')
    bl_options = {'INTERNAL'}

    def execute(self, context: bpy.types.Context) -> Set[str]:
        global last_manual_check_time
        check_for_update_background()
        last_manual_check_time = time.time()  # Reset the timer on manual check
        return {'FINISHED'}


class AvatarToolkit_OT_UpdateToLatest(bpy.types.Operator):
    bl_idname = 'avatar_toolkit.update_latest'
    bl_label = t('UpdateToLatestButton.label')
    bl_description = t('UpdateToLatestButton.desc')
    bl_options = {'INTERNAL'}

    latest: bpy.props.BoolProperty(default=True, options={'HIDDEN'})

    def execute(self, context: bpy.types.Context) -> Set[str]:
        return {'FINISHED'} if update_now(latest=self.latest) else {'CANCELLED'}


class AvatarToolkit_OT_UpdateNotificationPopup(bpy.types.Operator):
    bl_idname = "avatar_toolkit.update_notification_popup"
    bl_label = t('UpdateNotificationPopup.label')
    bl_description = t('UpdateNotificationPopup.desc')
    bl_options = {'INTERNAL'}

    def execute(self, context: bpy.types.Context) -> Set[str]:
        update_now(latest=True)
        self.report({'INFO'}, "Update started. Please wait for the process to complete.")
        return {'FINISHED'}

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> Set[str]:
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        col = layout.column(align=True)
        col.label(text=t('UpdateNotificationPopup.newUpdate', default="New update available: {version}").format(version=latest_version_str))


class AvatarToolkit_PT_UpdaterPanel(bpy.types.Panel):
    bl_label = t("Updater.label")
    bl_idname = "OBJECT_PT_avatar_toolkit_updater"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CATEGORY_NAME
    bl_parent_id = AvatarToolKit_PT_AvatarToolkitPanel.bl_idname
    bl_order = 9
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context: bpy.types.Context) -> None:
        global last_manual_check_time
        layout = self.layout
        
        # Auto-check for updates when panel is drawn, but not too frequently
        current_time = time.time()
        if current_time - last_manual_check_time > 300:  # 5 minutes between auto-checks
            if not is_checking_for_update and not update_needed:
                check_for_update_background()
                last_manual_check_time = current_time
            
        draw_updater_panel(context, layout)


class AvatarToolkit_OT_RestartBlenderPopup(bpy.types.Operator):
    bl_idname = "avatar_toolkit.restart_blender_popup"
    bl_label = t('RestartBlenderPopup.label', default="Restart Blender")
    bl_description = t('RestartBlenderPopup.desc', default="Restart Blender to complete the update")
    bl_options = {'INTERNAL'}

    def execute(self, context: bpy.types.Context) -> Set[str]:
        return {'FINISHED'}

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> Set[str]:
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        col = layout.column(align=True)
        col.label(text=t('RestartBlenderPopup.message', default="Update successful! Please restart Blender."))

@persistent
def check_for_update_on_start(dummy: Any) -> None:
    if get_preference("check_for_updates_on_startup", True):
        current_time = time.time()
        last_check = get_preference("last_update_check", 0)
        if current_time - last_check > 86400:  # 24 hours
            check_for_update_background()
            save_preference("last_update_check", current_time)

def _version(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", value or "")
    return tuple(map(int, match.groups())) if match else None


def _compatible(value):
    parsed = _version(value)
    return parsed is not None and f"{parsed[0]}.{parsed[1]}" in ALLOWED_VERSION_SERIES


def _github_headers(asset=False):
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        try:
            result = subprocess.run(
                ["gh", "auth", "token", "--hostname", "github.com"],
                capture_output=True, text=True, timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode == 0:
                token = result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    if not token:
        raise RuntimeError("Private updates require gh auth login or GH_TOKEN.")
    return {"Authorization": f"Bearer {token}",
            "Accept": "application/octet-stream" if asset else "application/vnd.github+json",
            "User-Agent": "Avatar-Toolkit", "X-GitHub-Api-Version": "2022-11-28"}


class _SafeRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected and urlparse(newurl).hostname != "api.github.com":
            redirected.remove_header("Authorization")
        return redirected


def _open_github(url, asset=False):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "api.github.com":
        raise ValueError("Updates must originate from the GitHub HTTPS API.")
    if not bpy.app.online_access:
        raise RuntimeError("Enable Blender Online Access to check for updates.")
    # Use normal certificate validation; strip credentials on cross-host redirects.
    return request.build_opener(_SafeRedirect()).open(
        request.Request(url, headers=_github_headers(asset)), timeout=30)


def check_for_update_background() -> None:
    global is_checking_for_update
    if is_checking_for_update:
        return
    is_checking_for_update = True
    bpy.app.timers.register(_finish_pending_check, first_interval=0.1)
    Thread(target=check_for_update, daemon=True).start()


def _finish_pending_check():
    if _pending_checks.empty():
        return 0.1
    finish_update_checking(error=_pending_checks.get())
    return None


def check_for_update() -> None:
    global update_needed
    # Worker performs network/JSON work only; all Blender UI calls run in timer.
    success = get_github_releases()
    update_needed = check_for_update_available() if success else False
    _pending_checks.put("" if success else update_error)


def get_github_releases() -> bool:
    global version_list, update_error
    version_list = {}
    try:
        with _open_github(f'https://api.github.com/repos/{GITHUB_REPO}/releases?per_page=100') as response:
            releases = json.loads(response.read().decode())
        for release in releases:
            tag = release.get('tag_name', '')
            if release.get('draft') or release.get('prerelease') or not _compatible(tag):
                continue
            expected = f"avatar_toolkit-{'.'.join(map(str, _version(tag)))}.zip"
            asset = next((a for a in release.get('assets', []) if a['name'] == expected), None)
            if asset:
                version_list[tag] = [asset['url'], release.get('body') or '',
                                     (release.get('published_at') or '').split('T')[0]]
        update_error = ""
        return True
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        update_error = f"Could not check private repository updates: {exc}"
        return False


def check_for_update_available() -> bool:
    global latest_version, latest_version_str
    candidates = [v for v in (version_list or {}) if _compatible(v)]
    latest_version = max(candidates, key=_version) if candidates else None
    latest_version_str = latest_version or ''
    current = _version(get_current_version())
    return bool(current and latest_version and _version(latest_version) > current)


def finish_update_checking(error: str = '') -> None:
    global is_checking_for_update, update_error
    is_checking_for_update = False
    update_error = error
    if update_needed and not error and not bpy.app.background:
        bpy.ops.avatar_toolkit.update_notification_popup('INVOKE_DEFAULT')
    ui_refresh()


def update_now(latest: bool = False) -> bool:
    global latest_version_str
    candidates = [v for v in (version_list or {}) if _compatible(v)]
    if not candidates:
        return False
    selected = max(candidates, key=_version) if latest else bpy.context.scene.avatar_toolkit.avatar_toolkit_updater_version_list
    if selected not in candidates:
        return False
    latest_version_str = selected
    success = download_file(version_list[selected][0])
    ui_refresh()
    return success


_UPDATE_PATHS = {'core', 'functions', 'ui', 'resources', 'wheels', '__init__.py',
                 'blender_manifest.toml', 'README.md', 'LICENSE', 'LICENSE.txt'}


def install_update(archive, destination):
    """Validate and stage a release before replacing files, restoring on failure."""
    destination = pathlib.Path(destination).resolve()
    with tempfile.TemporaryDirectory(prefix='avatar-toolkit-update-') as temporary:
        staging = pathlib.Path(temporary) / 'staging'
        backup = pathlib.Path(temporary) / 'backup'
        with zipfile.ZipFile(archive) as package:
            for entry in package.infolist():
                path = pathlib.PurePosixPath(entry.filename)
                if path.is_absolute() or '..' in path.parts or '\\' in entry.filename or ':' in entry.filename:
                    raise ValueError('Unsafe path in update archive')
                if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('Symbolic links are not supported in update archives')
            if 'blender_manifest.toml' not in package.namelist() or '__init__.py' not in package.namelist():
                raise ValueError('Expected a Blender extension package, not a source archive')
            manifest = tomllib.loads(package.read('blender_manifest.toml').decode())
            if manifest.get('id') != 'avatar_toolkit' or not _compatible(manifest.get('version')):
                raise ValueError('Incorrect addon or unsupported update version')
            if latest_version_str and _version(manifest['version']) != _version(latest_version_str):
                raise ValueError('Package version differs from selected release')
            minimum = _version(manifest.get('blender_version_min', '0.0.0'))
            maximum = _version(manifest.get('blender_version_max', '999.0.0'))
            if minimum is None or maximum is None or not minimum <= bpy.app.version < maximum:
                raise ValueError('Package does not support this Blender version')
            wheel_paths = manifest.get('wheels', [])
            if any(w.removeprefix('./') not in package.namelist() for w in wheel_paths):
                raise ValueError('Package is missing a required dependency wheel')
            package.extractall(staging)
        names = sorted(p.name for p in staging.iterdir() if p.name in _UPDATE_PATHS)
        backup.mkdir()
        replaced = []
        try:
            for name in names:
                target = destination / name
                saved = backup / name
                if target.exists():
                    if target.is_dir():
                        shutil.copytree(target, saved)
                    else:
                        shutil.copy2(target, saved)
                replaced.append(name)
                if target.is_dir():
                    shutil.rmtree(target)
                elif target.exists():
                    target.unlink()
                source = staging / name
                if source.is_dir():
                    shutil.copytree(source, target)
                else:
                    shutil.copy2(source, target)
        except Exception:
            for name in reversed(replaced):
                target, saved = destination / name, backup / name
                if target.is_dir():
                    shutil.rmtree(target)
                elif target.exists():
                    target.unlink()
                if saved.is_dir():
                    shutil.copytree(saved, target)
                elif saved.exists():
                    shutil.copy2(saved, target)
            raise
        return manifest['version']


def download_file(update_url: str) -> bool:
    try:
        with tempfile.TemporaryDirectory(prefix='avatar-toolkit-download-') as temporary:
            archive = pathlib.Path(temporary) / 'update.zip'
            with _open_github(update_url, asset=True) as response, archive.open('wb') as output:
                shutil.copyfileobj(response, output)
            installed_version = install_update(archive, main_dir)
        save_preference('version', installed_version)
        finish_update()
        return True
    except Exception as exc:
        finish_update(error=str(exc))
        return False


def finish_update(error: str = '') -> None:
    global update_error
    update_error = error
    if error:
        print(f"Update failed: {error}")
    elif not bpy.app.background:
        bpy.ops.avatar_toolkit.restart_blender_popup('INVOKE_DEFAULT')
    ui_refresh()

def get_version_list(self, context: bpy.types.Context) -> List[Tuple[str, str, str]]:
    if not version_list:
        return []
    
    return [(v, v, '') for v in sorted(version_list, key=lambda v: _version(v) or (0,0,0), reverse=True) if _compatible(v)]


def draw_updater_panel(context: bpy.types.Context, layout: bpy.types.UILayout) -> None:
    box = layout.box()
    col = box.column(align=True)
    
    # Header
    row = col.row()
    row.scale_y = 1.2
    row.label(text=t('Updater.label'), icon='DOWNARROW_HLT')
    
    col.separator()
    
    # Show compatibility info
    col.label(text=f"Update series: {', '.join(s + '.x' for s in ALLOWED_VERSION_SERIES)}", icon='INFO')
    col.label(text=f"Blender version: {bpy.app.version_string}", icon='BLENDER')
    
    col.separator()
    
    # Update check/status section
    if is_checking_for_update:
        col.operator(AvatarToolkit_OT_CheckForUpdate.bl_idname, 
                    text=t('Updater.CheckForUpdateButton.label'),
                    icon='SORTTIME')
    elif update_needed:
        update_row = col.row(align=True)
        update_row.scale_y = 1.5
        update_row.alert = True
        update_row.operator(AvatarToolkit_OT_UpdateToLatest.bl_idname, 
                          text=t('Updater.UpdateToLatestButton.label', name=latest_version_str),
                          icon='IMPORT')
    else:
        col.operator(AvatarToolkit_OT_CheckForUpdate.bl_idname, 
                    text=t('Updater.CheckForUpdateButton.label_alt'),
                    icon='FILE_REFRESH')

    # Version selection section
    col.separator()
    box_inner = col.box()
    box_inner.label(text=t('Updater.selectVersion'), icon='SETTINGS')
    row = box_inner.row(align=True)
    row.prop(context.scene.avatar_toolkit, 'avatar_toolkit_updater_version_list', text='')
    row.operator(AvatarToolkit_OT_UpdateToLatest.bl_idname, 
                text=t('Updater.UpdateToSelectedButton.label'),
                icon='IMPORT').latest = False

    if update_error:
        col.label(text=update_error, icon='ERROR')
    col.label(text='Private repo: gh auth login or GH_TOKEN', icon='LOCKED')

    # Current version info
    col.separator()
    curr_ver_row = col.row()
    curr_ver_row.label(text=t('Updater.currentVersion').format(name=get_current_version()),
                      icon='CHECKMARK')

def ui_refresh() -> None:
    for windowManager in bpy.data.window_managers:
        for window in windowManager.windows:
            for area in window.screen.areas:
                area.tag_redraw()


def register():
    while not _pending_checks.empty():
        _pending_checks.get_nowait()


def unregister():
    global is_checking_for_update
    if bpy.app.timers.is_registered(_finish_pending_check):
        bpy.app.timers.unregister(_finish_pending_check)
    is_checking_for_update = False
