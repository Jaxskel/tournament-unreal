"""Initialize the browser canvas tile view's default mobile lighting buffer.

Read-only unless --apply; accepts only a marked isolated UE4.15 CL3228288 tree.
No shader assertions, material graphs, world lighting or native paths are changed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

SOURCE_PATH = Path('Engine/Source/Runtime/Renderer/Private/Renderer.cpp')
BACKUP_SUFFIX = '.before-tournament-browser-tile-light'
MARKER = 'TOURNAMENT_BROWSER_TILE_LIGHT_V1'
EXPECTED_BODY_SHA256 = '649c26f648361bd5fb6b66e2191c09ff3f3432e308c697e73c41458328a84bc9'
ANCHOR = 'GSystemTextures.InitializeTextures(RHICmdList, FeatureLevel);'
INSERT = """// TOURNAMENT_BROWSER_TILE_LIGHT_V1
#if PLATFORM_HTML5_BROWSER
// Canvas tiles have no primitive lighting channel and use entry zero.
// World views initialize this buffer in CreateDirectionalLightUniformBuffers.
if (FeatureLevel < ERHIFeatureLevel::SM4 && !View.MobileDirectionalLightUniformBuffers[0].IsValid())
{
    View.MobileDirectionalLightUniformBuffers[0] = TUniformBufferRef<FMobileDirectionalLightShaderParameters>::CreateUniformBufferImmediate(FMobileDirectionalLightShaderParameters(), UniformBuffer_SingleFrame);
}
#endif
"""


def scan(text):
    tokens = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\r\n]*|/\*[\s\S]*?\*/'
    return re.sub(tokens, lambda m: re.sub(r'[^\r\n]', ' ', m.group()), text)


def body_span(text):
    code = scan(text)
    matches = list(re.finditer(r'void\s+FRendererModule::DrawTileMesh\s*\([^{}]*\)\s*\{', code))
    if len(matches) != 1:
        raise ValueError('Expected one canvas tile method')
    left = matches[0].end() - 1
    depth = 0
    for pos in range(left, len(code)):
        if code[pos] == '{': depth += 1
        elif code[pos] == '}':
            depth -= 1
            if depth == 0: return left, pos + 1
    raise ValueError('Unclosed canvas tile method')


def transform(text):
    newline = '\r\n' if '\r\n' in text else '\n'
    if newline == '\r\n' and '\n' in text.replace('\r\n', ''):
        raise ValueError('Mixed line endings')
    left, right = body_span(text)
    body = text[left:right]
    anchors = list(re.finditer(r'(?m)^([ \t]*)' + re.escape(ANCHOR) + r'\r?$', scan(body)))
    if len(anchors) != 1:
        raise ValueError('Expected one system-texture initialization in tile method')
    anchor = anchors[0]
    insertion = ''.join(anchor[1] + line + newline for line in INSERT.splitlines())
    marked = MARKER in text
    if marked and (text.count(MARKER) != 1 or body.count(insertion) != 1):
        raise ValueError('Altered or misplaced tile-light initialization')
    clean = body.replace(insertion, '', 1) if marked else body
    if hashlib.sha256(clean.replace('\r\n','\n').encode()).hexdigest() != EXPECTED_BODY_SHA256:
        raise ValueError('Canvas tile method differs from inspected CL3228288 source')
    code = scan(clean)
    anchor = re.search(r'(?m)^([ \t]*)' + re.escape(ANCHOR) + r'\r?$', code)
    boundary = anchor.end() + 1
    expected = clean[:boundary] + insertion + clean[boundary:]
    if marked and expected != body:
        raise ValueError('Tile-light block is not at its inspected boundary')
    return text[:left] + expected + text[right:]


def physical(path, missing_leaf=False):
    """Check every ancestor before reading/writing: no reparse or hardlinked files."""
    path = Path(os.path.abspath(path))
    chain = [*reversed(path.parents), path]
    for item in chain:
        try:
            info = item.lstat()
        except FileNotFoundError:
            if missing_leaf and item == path:
                return path
            raise ValueError('Required physical path missing: ' + str(item))
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Refusing linked/reparse path: ' + str(item))
        if stat.S_ISREG(info.st_mode):
            if info.st_nlink != 1:
                raise ValueError('Refusing multiply-linked file: ' + str(item))
            if item != path:
                raise ValueError('Non-directory ancestor: ' + str(item))
        elif not stat.S_ISDIR(info.st_mode):
            raise ValueError('Refusing non-regular path: ' + str(item))
    return path


def patch(root, apply=False):
    root = Path(os.path.abspath(root))
    marker = physical(root / '.tournament-browser-port')
    if not marker.is_file():
        raise ValueError('Use only a marked isolated browser checkout')
    version = json.loads(physical(root / 'Engine/Build/Build.version').read_text(encoding='utf-8-sig'))
    if tuple(version.get(k) for k in ('MajorVersion', 'MinorVersion', 'PatchVersion', 'Changelist')) != (4, 15, 0, 3228288):
        raise ValueError('Expected UE4.15.0 CL3228288')
    path = physical(root / SOURCE_PATH)
    original = path.read_bytes()
    encoding = 'utf-8-sig' if original.startswith(b'\xef\xbb\xbf') else 'utf-8'
    updated = transform(original.decode(encoding)).encode(encoding)
    backup = physical(Path(str(path) + BACKUP_SUFFIX), missing_leaf=True)
    if backup.exists():
        saved = backup.read_bytes()
        saved_encoding = 'utf-8-sig' if saved.startswith(b'\xef\xbb\xbf') else 'utf-8'
        if MARKER in saved.decode(saved_encoding):
            raise ValueError('Backup must contain original, unpatched source')
        if original != updated:
            if saved != original:
                raise ValueError('Conflicting original backup')
        elif transform(saved.decode(saved_encoding)).encode(saved_encoding) != original:
            raise ValueError('Patched source does not match original backup')
    elif original == updated:
        raise ValueError('Patched source is missing its original backup')
    status = 'already-patched' if original == updated else 'would-patch'
    if apply and original != updated:
        if not backup.exists():
            with backup.open('xb') as stream:
                stream.write(original)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.tile-light-patch-', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(updated)
            physical(path)
            if path.read_bytes() != original:
                raise ValueError('Source changed during patch; refusing replacement')
            os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
            os.replace(temporary, path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
        status = 'patched'
    result = {'status': status, 'file': str(SOURCE_PATH), 'sha256': hashlib.sha256(updated).hexdigest()}
    print(json.dumps(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_root')
    parser.add_argument('--apply', action='store_true', help='save the original and apply the browser-only canvas tile lighting initialization')
    args = parser.parse_args()
    try:
        patch(args.source_root, args.apply)
    except (ValueError, OSError, UnicodeError) as error:
        parser.exit(1, str(error) + '\n')
