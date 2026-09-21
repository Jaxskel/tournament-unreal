"""Keep browser render resolution independent of the canvas's CSS size.

Only marked UE4.15.0 CL3228288 checkouts are accepted. Default: read-only
preflight; --apply saves the original privately beside the target and replaces
one window-flags expression. No engine build or remote command is launched.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

SOURCE_PATH = Path('Engine/Source/Runtime/OpenGLDrv/Private/HTML5/HTML5OpenGL.cpp')
BACKUP_SUFFIX = '.before-tournament-browser-window'
MARKER = 'TOURNAMENT_BROWSER_FIXED_WINDOW_V1'
VARIABLE = 'TournamentBrowserWindowFlags'
FLAGS = r'SDL_WINDOW_OPENGL\s*\|\s*SDL_WINDOW_SHOWN\s*\|\s*SDL_WINDOW_RESIZABLE'
# Independently written conditional; preserve explicit SDL_SetWindowSize support.
INSERT = '''// TOURNAMENT_BROWSER_FIXED_WINDOW_V1
// Browser CSS layout must not resize the render buffer; explicit sizes still work.
#if PLATFORM_HTML5_BROWSER
const Uint32 TournamentBrowserWindowFlags = SDL_WINDOW_OPENGL | SDL_WINDOW_SHOWN;
#else
const Uint32 TournamentBrowserWindowFlags = SDL_WINDOW_OPENGL | SDL_WINDOW_SHOWN | SDL_WINDOW_RESIZABLE;
#endif
'''


def transform(text):
    newline = '\r\n' if '\r\n' in text else '\n'
    if newline == '\r\n' and '\n' in text.replace('\r\n', ''):
        raise ValueError('Mixed source line endings')
    marked = MARKER in text
    expr = VARIABLE if marked else FLAGS
    pattern = (r'(?m)^(?P<indent>[ \t]*)WindowHandle\s*=\s*SDL_CreateWindow\(\s*"HTML5"\s*,\s*'
               r'SDL_WINDOWPOS_CENTERED\s*,\s*SDL_WINDOWPOS_CENTERED\s*,\s*800\s*,\s*600\s*,\s*'
               r'(?P<flags>' + expr + r')\s*\);')
    matches = list(re.finditer(pattern, text))
    if len(matches) != 1 or len(re.findall(r'\bWindowHandle\s*=\s*SDL_CreateWindow\s*\(', text)) != 1:
        raise ValueError('Expected exactly the inspected HTML5 window creation call')
    match = matches[0]
    block = ''.join(match['indent'] + line + newline for line in INSERT.splitlines())
    if marked:
        start = match.start() - len(block)
        if text.count(MARKER) != 1 or text.count(VARIABLE) != 3 or start < 0 or text[start:match.start()] != block:
            raise ValueError('Altered, partial or misplaced browser-window patch')
        return text
    if VARIABLE in text:
        raise ValueError('Unexpected existing window-flags variable')
    return (text[:match.start()] + block + text[match.start():match.start('flags')]
            + VARIABLE + text[match.end('flags'):])


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
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.window-patch-', delete=False) as stream:
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
    parser.add_argument('--apply', action='store_true', help='save the original and apply the browser-only window flag change')
    args = parser.parse_args()
    try:
        patch(args.source_root, args.apply)
    except (ValueError, OSError, UnicodeError) as error:
        parser.exit(1, str(error) + '\n')
