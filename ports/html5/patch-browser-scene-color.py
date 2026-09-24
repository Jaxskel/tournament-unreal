"""Apply the pinned experimental browser SceneColor source patch.

Default operation is read-only. --apply requires an isolated UE4.15 source
root, creates exclusive original-byte backups first, then installs four exact
reversible source changes. It does not build or modify assets/configuration.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

MARKER = 'TOURNAMENT_BROWSER_SCENE_COLOR_HDR64_V1'
BACKUP = '.before-tournament-browser-scene-color'
SPECS = (
    {
        'path': 'Engine/Source/Runtime/Engine/Private/Materials/HLSLMaterialTranslator.h',
        'source_sha256': '7fda4c45fbd10f8193e6f07dbd9b7c4eb54492d2cef556df1271bb80772eeb69',
        'source_bytes': 168446,
        'output_sha256': 'd2346724dc2e8a06290702fa9f1e15d1a16bc80503e3ec2df18885bb5d06314f',
        'output_bytes': 169041,
        'edits': ((
            '\t\tif (ErrorUnlessFeatureLevelSupported(ERHIFeatureLevel::SM4) == INDEX_NONE)\n'
            '\t\t{\n\t\t\treturn INDEX_NONE;\n\t\t}\n\n'
            '\t\tMaterialCompilationOutput.bRequiresSceneColorCopy = true;',
            '\t\t// TOURNAMENT_BROWSER_SCENE_COLOR_HDR64_V1: preserve pixel/domain/blend gates.\n'
            '\t\tif (Platform == SP_OPENGL_ES2_WEBGL && FeatureLevel == ERHIFeatureLevel::ES2)\n'
            '\t\t{\n'
            '\t\t\tconst auto* HDR = IConsoleManager::Get().FindTConsoleVariableDataInt(TEXT("r.MobileHDR"));\n'
            '\t\t\tconst auto* HDR32 = IConsoleManager::Get().FindTConsoleVariableDataInt(TEXT("r.MobileHDR32bppMode"));\n'
            '\t\t\tif (!HDR || !HDR32 || HDR->GetValueOnAnyThread() != 1 || HDR32->GetValueOnAnyThread() != 0)\n'
            '\t\t\t{\n'
            '\t\t\t\treturn Errorf(TEXT("Browser SceneColor requires linear mobile HDR64 (r.MobileHDR=1, r.MobileHDR32bppMode=0)."));\n'
            '\t\t\t}\n'
            '\t\t}\n'
            '\t\telse if (ErrorUnlessFeatureLevelSupported(ERHIFeatureLevel::SM4) == INDEX_NONE)\n'
            '\t\t{\n\t\t\treturn INDEX_NONE;\n\t\t}\n\n'
            '\t\tMaterialCompilationOutput.bRequiresSceneColorCopy = true;'),),
    },
    {
        'path': 'Engine/Source/Runtime/Renderer/Private/MobileTranslucentRendering.cpp',
        'source_sha256': '43129648392a35d4d41c09b56f8cc85ccc2713d75082639fd15d7d3bc585581a',
        'source_bytes': 25818,
        'output_sha256': '7bbed83fc236407c5d1bcea79f1ea4d1aff50a6f857dd6bb597c8019587e4e84',
        'output_bytes': 27032,
        'edits': ((
            '\t\tFDepthStencilStateRHIParamRef DepthStencilState = nullptr;',
            '\t\t// TOURNAMENT_BROWSER_SCENE_COLOR_HDR64_V1: snapshot immediately before this mesh.\n'
            '\t\tif (ShaderPlatform == SP_OPENGL_ES2_WEBGL && Material->RequiresSceneColorCopy_RenderThread()\n'
            '\t\t\t&& View.Family->GetDebugViewShaderMode() == DVSM_None)\n'
            '\t\t{\n'
            '\t\t\tFSceneRenderTargets& SceneContext = FSceneRenderTargets::Get(RHICmdList);\n'
            '\t\t\tif (FeatureLevel != ERHIFeatureLevel::ES2 || !IsMobileHDR() || IsMobileHDR32bpp()\n'
            '\t\t\t\t|| SceneContext.GetSceneColorFormat() != PF_FloatRGBA\n'
            '\t\t\t\t|| View.bIsMobileMultiViewEnabled || DrawingContext.bRenderingSeparateTranslucency\n'
            '\t\t\t\t|| !DrawRenderState.GetDepthStencilState())\n'
            '\t\t\t{\n'
            '\t\t\t\tUE_LOG(LogTemp, Fatal, TEXT("Browser SceneColor requires an ES2 HDR64 standard translucency view with a valid depth state."));\n'
            '\t\t\t\treturn false;\n'
            '\t\t\t}\n'
            '\t\t\tFTranslucencyDrawingPolicyFactory::CopySceneColor(RHICmdList, View, PrimitiveSceneProxy);\n'
            '\t\t\t// false preserves existing stencil; this also restores the scene target and view rectangle.\n'
            '\t\t\tSceneContext.BeginRenderingTranslucency(RHICmdList, View, false);\n'
            '\t\t\tRHICmdList.SetDepthStencilState(DrawRenderState.GetDepthStencilState(), DrawRenderState.GetStencilRef());\n'
            '\t\t\t// The existing mesh policy sets its blend, rasterizer, shaders and streams below.\n'
            '\t\t}\n\n'
            '\t\tFDepthStencilStateRHIParamRef DepthStencilState = nullptr;'),),
    },
    {
        'path': 'Engine/Source/Runtime/Renderer/Private/TranslucentRendering.cpp',
        'source_sha256': '8ee79fdb78666b7479b0516e1533d34098cf6c28f40ac8d22eebde493f617a02',
        'source_bytes': 52014,
        'output_sha256': 'd90d0367a7c25ef18ebb183afdd59a05bc849ea7f79ef947a95df401fbd73d08',
        'output_bytes': 52223,
        'edits': (
            ('static bool ShouldCache(EShaderPlatform Platform) { return IsFeatureLevelSupported(Platform, ERHIFeatureLevel::SM4); }',
             'static bool ShouldCache(EShaderPlatform Platform) { return IsFeatureLevelSupported(Platform, ERHIFeatureLevel::SM4) || Platform == SP_OPENGL_ES2_WEBGL; } // TOURNAMENT_BROWSER_SCENE_COLOR_HDR64_V1'),
            ('*PrimitiveSceneProxy->GetOwnerName().ToString(), *PrimitiveSceneProxy->GetResourceName().ToString());',
             '(PrimitiveSceneProxy ? *PrimitiveSceneProxy->GetOwnerName().ToString() : TEXT("ViewElement")), (PrimitiveSceneProxy ? *PrimitiveSceneProxy->GetResourceName().ToString() : TEXT("NoProxy"))); // TOURNAMENT_BROWSER_SCENE_COLOR_HDR64_V1'),
        ),
    },
    {
        'path': 'Engine/Source/Runtime/Renderer/Private/ShaderBaseClasses.cpp',
        'source_sha256': 'c9c225d68438e195d12c5521afdcfd8708e3b1e88d32b33b33f70bb515ad3520',
        'source_bytes': 21349,
        'output_sha256': '76fbb81b8b1e9bc5c43676f197d59c0b4f7284c65e7fc46ab3608f6e62c86831',
        'output_bytes': 21443,
        'edits': (('\tif (FeatureLevel >= ERHIFeatureLevel::SM4)\n\t{\n\t\t// for copied scene color',
                   '\tif (FeatureLevel >= ERHIFeatureLevel::SM4 || View.GetShaderPlatform() == SP_OPENGL_ES2_WEBGL) // TOURNAMENT_BROWSER_SCENE_COLOR_HDR64_V1\n\t{\n\t\t// for copied scene color'),),
    },
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _replace_exact(data, old, new, path):
    if b'\r\n' in data:
        if data.replace(b'\r\n', b'').find(b'\n') >= 0:
            raise ValueError('Mixed newline source: ' + path)
        eol = '\r\n'
    else:
        eol = '\n'
    old_b = old.replace('\n', eol).encode('ascii')
    new_b = new.replace('\n', eol).encode('ascii')
    if data.count(old_b) != 1:
        raise ValueError('Patch anchor is absent or duplicated: ' + path)
    return data.replace(old_b, new_b, 1)


def inverse(data, spec):
    if len(data) != spec['output_bytes'] or sha(data) != spec['output_sha256']:
        raise ValueError('Unsupported or altered patched source: ' + spec['path'])
    for old, new in reversed(spec['edits']):
        data = _replace_exact(data, new, old, spec['path'])
    if len(data) != spec['source_bytes'] or sha(data) != spec['source_sha256']:
        raise ValueError('Patch inverse does not recover pinned original: ' + spec['path'])
    return data


def transform(data, spec):
    if len(data) == spec['output_bytes'] and sha(data) == spec['output_sha256']:
        inverse(data, spec)
        return data
    if len(data) != spec['source_bytes'] or sha(data) != spec['source_sha256']:
        raise ValueError('Unsupported or modified complete source: ' + spec['path'])
    original = data
    for old, new in spec['edits']:
        data = _replace_exact(data, old, new, spec['path'])
    if len(data) != spec['output_bytes'] or sha(data) != spec['output_sha256'] or inverse(data, spec) != original:
        raise ValueError('Patched source hash or byte-exact inverse differs: ' + spec['path'])
    return data


def physical(path, missing=False):
    path = Path(os.path.abspath(path))
    for item in (*reversed(path.parents), path):
        try:
            info = item.lstat()
        except FileNotFoundError:
            if missing and item == path:
                return path
            raise ValueError('Missing physical path: ' + str(item))
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Linked/reparse path: ' + str(item))
        if stat.S_ISREG(info.st_mode):
            if item != path or info.st_nlink != 1:
                raise ValueError('Nonphysical or multiply-linked file: ' + str(item))
        elif not stat.S_ISDIR(info.st_mode):
            raise ValueError('Nonregular path: ' + str(item))
    return path


def snapshot(path):
    path = physical(path)
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_nlink)
    if identity(before) != identity(after) or len(data) != after.st_size:
        raise ValueError('File changed during read: ' + str(path))
    return {'path': path, 'data': data, 'identity': identity(after), 'mode': stat.S_IMODE(after.st_mode)}


def recheck(saved):
    current = snapshot(saved['path'])
    if current['identity'] != saved['identity'] or current['data'] != saved['data']:
        raise ValueError('File changed after preflight: ' + str(saved['path']))


def _publish_backup(saved, destination, check_all):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.scene-color-backup-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(saved['data'])
            stream.flush()
            os.fsync(stream.fileno())
        if snapshot(temporary)['data'] != saved['data']:
            raise ValueError('Staged original backup verification failed')
        check_all()
        os.link(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    backup = snapshot(destination)
    if backup['data'] != saved['data']:
        raise ValueError('Published original backup verification failed')
    return backup


def patch(root, apply=False, specs=SPECS):
    root = physical(root)
    marker = snapshot(root / '.tournament-browser-port')
    version = snapshot(root / 'Engine/Build/Build.version')
    version_data = json.loads(version['data'].decode('utf-8-sig'))
    if tuple(version_data.get(k) for k in ('MajorVersion', 'MinorVersion', 'PatchVersion', 'Changelist')) != (4, 15, 0, 3228288):
        raise ValueError('Expected isolated UE4.15.0 CL3228288 source root')
    rows = []
    for spec in specs:
        current = snapshot(root / spec['path'])
        updated = transform(current['data'], spec)
        original = inverse(current['data'], spec) if current['data'] == updated and sha(current['data']) == spec['output_sha256'] else current['data']
        backup_path = physical(Path(str(current['path']) + BACKUP), missing=True)
        backup = snapshot(backup_path) if backup_path.exists() else None
        if backup:
            if backup['data'] != original or sha(backup['data']) != spec['source_sha256'] or len(backup['data']) != spec['source_bytes']:
                raise ValueError('Original backup differs from exact pinned bytes: ' + spec['path'])
        elif current['data'] == updated:
            raise ValueError('Already-patched source requires its exact original backup: ' + spec['path'])
        rows.append({'spec': spec, 'current': current, 'updated': updated, 'backup': backup, 'backup_path': backup_path})

    def check_all():
        recheck(marker)
        recheck(version)
        for row in rows:
            recheck(row['current'])
            if row['backup']:
                recheck(row['backup'])
            elif physical(row['backup_path'], missing=True).exists():
                raise ValueError('Unexpected original backup appeared: ' + str(row['backup_path']))

    check_all()
    if apply:
        # Publish all four durable original copies before the first source write.
        for row in rows:
            if row['backup'] is None:
                row['backup'] = _publish_backup(row['current'], row['backup_path'], check_all)
        check_all()
        for row in rows:
            if row['current']['data'] == row['updated']:
                continue
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=row['current']['path'].parent, prefix='.scene-color-patch-', delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(row['updated'])
                    stream.flush()
                    os.fsync(stream.fileno())
                check_all()
                os.chmod(temporary, row['current']['mode'])
                os.replace(temporary, row['current']['path'])
                row['current'] = snapshot(row['current']['path'])
                if row['current']['data'] != row['updated']:
                    raise ValueError('Installed source differs from exact desired bytes')
            finally:
                if temporary is not None and temporary.exists():
                    temporary.unlink()
        check_all()
    return {
        'apply': apply,
        'experiment': MARKER,
        'originalMaterialsChanged': False,
        'requiresNativeAndBrowserRebuild': True,
        'files': [{'path': row['spec']['path'], 'sourceSha256': sha(row['current']['data']),
                   'proposedSha256': sha(row['updated']), 'alreadyPatched': row['current']['data'] == row['updated']}
                  for row in rows],
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_root')
    parser.add_argument('--apply', action='store_true', help='Create original backups and install the four pinned source edits')
    args = parser.parse_args()
    try:
        print(json.dumps(patch(args.source_root, args.apply), indent=2))
    except (ValueError, OSError, UnicodeError) as error:
        parser.exit(1, str(error) + '\n')
