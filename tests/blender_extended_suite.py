"""Run feature suite plus file-format and public updater integration tests."""
import pathlib
import sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
source = (ROOT / 'tests/blender_full_suite.py').read_text(encoding='utf-8')
features, finish = source.split('# Inventory all registered operators.', 1)
exec(compile(features, str(ROOT / 'tests/blender_full_suite.py'), 'exec'))

@case('Public updater release selection and anonymous requests')
def updater_releases(arm, mesh, props):
    import io
    from unittest.mock import patch
    from avatar_toolkit.core import updater
    releases = [
        {'tag_name':'v0.6.1', 'assets':[{'name':'avatar_toolkit-0.6.1.zip','url':'https://api.github.com/repos/test/releases/assets/1'}]},
        {'tag_name':'0.6.99', 'prerelease':True, 'assets':[]},
        {'tag_name':'0.6.2-beta', 'assets':[]},
        {'tag_name':'0.7.0', 'assets':[]},
        {'tag_name':'0.5.7', 'assets':[{'name':'avatar_toolkit-0.5.7.zip','url':'https://api.github.com/repos/test/releases/assets/2'}]},
        {'tag_name':'0.6.2', 'assets':[]}]
    with patch.object(updater, '_open_github', return_value=io.BytesIO(json.dumps(releases).encode())), patch.object(updater, 'get_current_version', return_value='0.6.0'):
        assert updater.get_github_releases()
        assert list(updater.version_list) == ['v0.6.1']
        assert updater.check_for_update_available()
    with patch.dict(updater.os.environ, {'GH_TOKEN':'test-token'}):
        assert 'Authorization' not in updater._github_headers()
        assert 'Authorization' not in updater._github_headers(asset=True)
    from urllib.request import Request
    redirected = updater._SafeRedirect().redirect_request(Request('https://api.github.com/asset', headers={'Authorization':'Bearer secret'}), None,302,'',{},'https://release-assets.githubusercontent.com/file')
    assert redirected.get_header('Authorization') is None
    captured = []
    props.avatar_toolkit_updater_version_list = 'v0.6.1'
    with patch.object(updater, 'download_file', side_effect=lambda url: captured.append(url) or True):
        assert updater.update_now(latest=False)
    assert len(captured) == 1

@case('Updater validates archives, preserves user files and rolls back failures')
def updater_install(arm, mesh, props):
    import zipfile
    from unittest.mock import patch
    from avatar_toolkit.core import updater
    destination = OUT / 'update-target'
    destination.mkdir(exist_ok=True)
    (destination / '__init__.py').write_text('old')
    (destination / 'user-file.txt').write_text('preserve')
    archive = OUT / 'update-test.zip'
    manifest = 'id = "avatar_toolkit"\nversion = "0.6.1"\nblender_version_min = "5.0.0"\nblender_version_max = "5.3.0"\n'
    def package(extra=None):
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('blender_manifest.toml', manifest)
            z.writestr('__init__.py','new')
            if extra: z.writestr(extra,'bad')
    package('../escape.py')
    try: updater.install_update(archive,destination)
    except ValueError: pass
    else: raise AssertionError('Unsafe archive accepted')
    assert (destination / '__init__.py').read_text() == 'old'
    package()
    original_copy = updater.shutil.copy2
    def fail_manifest(source, target, *args, **kwargs):
        if pathlib.Path(source).parent.name == 'staging' and pathlib.Path(source).name == 'blender_manifest.toml':
            raise OSError('simulated replacement failure')
        return original_copy(source,target,*args,**kwargs)
    with patch.object(updater.shutil, 'copy2', side_effect=fail_manifest):
        try: updater.install_update(archive,destination)
        except OSError: pass
        else: raise AssertionError('Expected install failure')
    assert (destination / '__init__.py').read_text() == 'old'
    assert updater.install_update(archive,destination) == '0.6.1'
    assert (destination / '__init__.py').read_text() == 'new'
    assert (destination / 'user-file.txt').read_text() == 'preserve'

@case('AnimX binary primitives and Unicode serialization')
def animx_types(arm, mesh, props):
    from io import BytesIO
    from avatar_toolkit.core.resonite_loader import common, resonite_animx, resonite_types
    for value in (0,1,127,128,65535,2**63):
        stream = BytesIO(); common.write7bitEncoded_ulong(stream,value); stream.seek(0)
        assert common.read7bitEncoded_ulong(stream) == value
    stream = BytesIO(); common.WriteCSharp_str(stream,'\u5de6\u76ee'); stream.seek(0)
    assert common.ReadCSharp_str(stream) == '\u5de6\u76ee'
    for name in resonite_animx.elementTypes:
        cls = getattr(resonite_types,name.split('.')[-1]); value = cls(); stream = BytesIO()
        fields = {}
        for base in reversed(cls.__mro__): fields.update(getattr(base, "__annotations__", {}))
        for i, field in enumerate(fields):
            if hasattr(value, field):
                setattr(value, field, "UTF8" if name.endswith(".string") else (True if "bool" in name else i+1))
        value.write(stream); length = stream.tell(); stream.seek(0); decoded = cls(); decoded.read(stream)
        assert stream.tell() == length, name
        for field in fields:
            if hasattr(value, field): assert getattr(decoded, field) == getattr(value, field), (name, field)
    for value in (None, resonite_types.string('hello')):
        stream = BytesIO(); resonite_types.writeNullable(stream,value); stream.seek(0)
        decoded = resonite_types.string(); resonite_types.readNullable(stream,decoded)
        assert stream.tell() == len(stream.getvalue())

@case('AnimX raw, discrete and curve imports in raw, LZ4 and LZMA encodings')
def animx_tracks(arm, mesh, props):
    import struct, lzma
    from io import BytesIO
    from avatar_toolkit.core.resonite_loader import common, resonite_animx as ax
    from avatar_toolkit.core.animation import ensure_channelbag
    for tracktype in (0,1,2):
        for encoding in (0,1,2):
            header=BytesIO(); common.WriteCSharp_str(header,'AnimX'); header.write(bytes([1,1])); header.write(struct.pack('<f',1)); common.WriteCSharp_str(header,'Fixture'); header.write(bytes([encoding]))
            payload=BytesIO(); payload.write(bytes([tracktype,23])); common.WriteCSharp_str(payload,'Hips'); common.WriteCSharp_str(payload,'Position'); payload.write(bytes([2]))
            if tracktype==0:
                payload.write(struct.pack('<f',1)); payload.write(struct.pack('<ffffff',1,2,3,4,5,6))
            elif tracktype==1:
                payload.write(struct.pack('<ffffffff',0,1,2,3,1,4,5,6))
            else:
                payload.write(bytes([0,1])); payload.write(struct.pack('<ffffffff',1,2,3,0,4,5,6,1))
            body=payload.getvalue()
            if encoding==1:
                from lz4.frame import compress
                body=compress(body)
            elif encoding==2:
                filters=[{'id':lzma.FILTER_LZMA1,'dict_size':2097152,'lc':3,'lp':0,'pb':2}]
                body=b'\x5d'+struct.pack('<I',2097152)+struct.pack('<QQ',len(body),0)+lzma.compress(body,format=lzma.FORMAT_RAW,filters=filters)
            path=OUT/f'track-{tracktype}-{encoding}.animx'; path.write_bytes(header.getvalue()+body)
            activate(arm); bpy.context.scene.render.fps=30
            op('avatar_toolkit.animx_importer',filepath=str(path))
            bag=ensure_channelbag(arm.animation_data.action,arm)
            assert len(bag.fcurves)==3
            x=bag.fcurves.find('pose.bones["Hips"].location',index=0)
            assert abs(x.evaluate(30)-4)<1e-5
            assert x.keyframe_points[0].interpolation == ('CONSTANT' if tracktype==1 else 'LINEAR')
            loaded=ax.AnimX(); assert loaded.read(str(path))
            copy=OUT/'roundtrip.animx'; assert loaded.write(str(copy))
            decoded=ax.AnimX(); assert decoded.read(str(copy)); assert len(decoded.tracks[0].keyframes)==2

@case('Safe merge doubles preserves differences between shape keys')
def doubles(arm, mesh, props):
    from types import SimpleNamespace
    from avatar_toolkit.functions.optimization.remove_doubles import AvatarToolkit_OT_RemoveDoubles as cls
    data=bpy.data.meshes.new('Duplicates'); data.from_pydata([(0,0,0),(0,0,0),(1,0,0),(1,0,0)],[],[])
    obj=bpy.data.objects.new('Duplicates',data); bpy.context.collection.objects.link(obj); obj.parent=arm
    obj.shape_key_add(name='Basis'); shape=obj.shape_key_add(name='Different'); shape.data[3].co.z=1
    activate(obj)
    for v in data.vertices: v.select=True
    holder=SimpleNamespace(merge_distance=.001,report=lambda *args:None)
    holder.objects_to_do=[cls.setup_mesh_entry(holder,bpy.context,obj)]
    assert cls.modal(holder,bpy.context,None)=={'RUNNING_MODAL'}
    bpy.ops.object.mode_set(mode='OBJECT')
    assert len(data.vertices)==3
    assert len(data.shape_keys.key_blocks['Different'].data)==3
    assert any(v.co.z>.9 for v in data.shape_keys.key_blocks['Different'].data)
    assert cls.modal(holder,bpy.context,None)=={'FINISHED'}
    covered.add(cls.bl_idname)

@case('Flip selected pose frames uses Blender 5 pose selection')
def flip(arm, mesh, props):
    activate(arm); bpy.ops.object.mode_set(mode='POSE')
    bone=arm.pose.bones['Hips']; bone.location.x=1; bone.keyframe_insert(data_path='location',frame=1)
    from avatar_toolkit.core.animation import ensure_channelbag
    bag=ensure_channelbag(arm.animation_data.action,arm)
    for curve in bag.fcurves:
        for point in curve.keyframe_points: point.select_control_point=True
    bone.select=True
    op('avatar_toolkit.flip_pose_frames')
    assert bone.select
    assert abs(bag.fcurves.find(bone.path_from_id('location'),index=0).evaluate(1)+1)<1e-5

@case('Explode disconnected geometry restores transform settings')
def explode(arm, mesh, props):
    activate(mesh)
    bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT'); bpy.ops.mesh.duplicate(); bpy.ops.transform.translate(value=(4,0,0)); bpy.ops.object.mode_set(mode='OBJECT')
    settings=bpy.context.scene.tool_settings; previous=settings.transform_pivot_point
    op('avatar_toolkit.explode_mesh',split_on_seams=False,distance=2)
    pieces=[o for o in bpy.context.selected_objects if o.type=='MESH']
    assert len(pieces)==2
    assert abs((pieces[0].location-pieces[1].location).length-8)<1e-4
    assert settings.transform_pivot_point==previous

exec(compile((ROOT / 'tests/blender_ui_suite.py').read_text(encoding='utf-8-sig'), str(ROOT / 'tests/blender_ui_suite.py'), 'exec'))

exec(compile('# Inventory all registered operators.' + finish, str(ROOT / 'tests/blender_full_suite.py'), 'exec'))
