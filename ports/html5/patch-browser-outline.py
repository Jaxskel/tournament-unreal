"""Exclude the legacy constant-black Outline postprocess from browser cameras.

Only marked UE4.15.0 CL3228288 checkouts are accepted. Default: read-only
preflight; --apply saves the original privately beside the target and replaces
only the two OutlineMat blendable insertions. No engine build or remote command is launched.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

SOURCE_PATH = Path('UnrealTournament/Source/UnrealTournament/Private/UTPlayerCameraManager.cpp')
BACKUP_SUFFIX = '.before-tournament-browser-outline'
MARKER = 'TOURNAMENT_BROWSER_SKIP_OUTLINE_V1'
CALLS = ('DefaultPPSettings.AddBlendable(OutlineMat, 1.0f);',
         'BlendableOverrides.AddBlendable(OutlineMat, 1.0f);')


def scan(text):
    """Mask comments and literals without moving code offsets."""
    tokens = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\r\n]*|/\*[\s\S]*?\*/'
    return re.sub(tokens, lambda m: re.sub(r'[^\r\n]', ' ', m.group()), text)


def body_span(text, constructor=False):
    signature = (r'AUTPlayerCameraManager::AUTPlayerCameraManager\s*\(\s*const\s+class\s+FObjectInitializer&\s+ObjectInitializer\s*\)\s*:\s*Super\(ObjectInitializer\)'
                 if constructor else
                 r'void\s+AUTPlayerCameraManager::ApplyCameraModifiers\s*\(\s*float\s+DeltaTime,\s*FMinimalViewInfo&\s+InOutPOV\s*\)')
    code = scan(text)
    matches = list(re.finditer(signature + r'\s*\{', code))
    if len(matches) != 1:
        raise ValueError('Expected one inspected camera method definition')
    left = matches[0].end()-1
    depth = 0
    for pos in range(left, len(code)):
        if code[pos] == '{': depth += 1
        elif code[pos] == '}':
            depth -= 1
            if depth == 0: return left, pos+1
    raise ValueError('Unclosed camera method')


def guarded(call, indent, newline):
    return newline.join((indent + '// ' + MARKER,
                         '#if !PLATFORM_HTML5_BROWSER', indent + call, '#endif'))


def transform(text):
    newline = '\r\n' if '\r\n' in text else '\n'
    if newline == '\r\n' and '\n' in text.replace('\r\n', ''):
        raise ValueError('Mixed source line endings')
    marked = MARKER in text
    clean = text
    if marked:
        if text.count(MARKER) != 2:
            raise ValueError('Partial or duplicate Outline patch markers')
        for call in CALLS:
            pattern = (r'(?m)^(?P<indent>[ \t]*)// ' + MARKER + re.escape(newline)
                       + re.escape('#if !PLATFORM_HTML5_BROWSER' + newline)
                       + r'(?P=indent)' + re.escape(call + newline + '#endif'))
            matches = list(re.finditer(pattern, clean))
            if len(matches) != 1:
                raise ValueError('Altered or misplaced Outline guard')
            m = matches[0]
            clean = clean[:m.start()] + m['indent'] + call + clean[m.end():]
    code = scan(clean)
    if len(re.findall(r'\bAddBlendable\s*\(\s*OutlineMat\b', code)) != 2:
        raise ValueError('Expected only the two inspected OutlineMat insertion sites')
    spans = (body_span(clean, True), body_span(clean))
    replacements = []
    for call, (left, right) in zip(CALLS, spans):
        matches = list(re.finditer(r'(?m)^([ \t]*)' + re.escape(call) + r'\r?$', code))
        if len(matches) != 1 or not left < matches[0].start() < right:
            raise ValueError('Missing or moved standalone OutlineMat call')
        m = matches[0]
        # Do not accept an unmarked prior guard or a call hidden in a preprocessor branch.
        if re.search(r'(?m)^\s*#\s*(if|ifdef|ifndef|else|elif|endif)\b', code[left:right]):
            raise ValueError('Unexpected conditional compilation in camera method')
        replacements.append((m.start(), m.start()+len(m[1])+len(call), guarded(call, m[1], newline)))
    # The second site must remain inside the existing map-volume branch.
    if not re.search(r'if\s*\(GetWorld\(\)->PostProcessVolumes.Num\(\) > 0\)\s*\{\s*'
                     + re.escape(CALLS[1]) + r'\s*\}', code[spans[1][0]:spans[1][1]]):
        raise ValueError('Unknown map-volume Outline insertion context')
    expected = clean
    for left, right, replacement in sorted(replacements, reverse=True):
        expected = expected[:left] + replacement + expected[right:]
    if marked and expected != text:
        raise ValueError('Outline guard is not at its inspected insertion boundary')
    return expected


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
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.outline-patch-', delete=False) as stream:
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
    parser.add_argument('--apply', action='store_true', help='save the original and apply the browser-only OutlineMat exclusion')
    args = parser.parse_args()
    try:
        patch(args.source_root, args.apply)
    except (ValueError, OSError, UnicodeError) as error:
        parser.exit(1, str(error) + '\n')
