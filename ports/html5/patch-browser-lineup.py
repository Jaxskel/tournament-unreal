"""Bound the existing intro timer by its own delay schedule after late joins.

Only a marked isolated UE4.15.0 CL3228288 checkout and the inspected callback
are accepted. Default is read-only preflight; --apply saves a private original
backup and replaces the source atomically. No engine/compiler/process commands.
Licensed source is read from the target, never bundled or printed.

Usage: python3 patch-browser-lineup.py SOURCE_ROOT [--apply]
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

SOURCE_PATH = Path('UnrealTournament/Source/UnrealTournament/Private/UTLineUpHelper.cpp')
SOURCE_SHA256 = '0f34749824656bdd1e5d1486e62994c49036bcbae555f34c0b66d8b2163a2f56'
BACKUP_SUFFIX = '.before-tournament-browser-lineup'
MARKER = 'TOURNAMENT_BROWSER_LINEUP_BOUNDS_V1'
CURRENT = 'LineUpSlots.IsValidIndex(Intro_TotalSpawnedPlayers)'
PREVIOUS = 'LineUpSlots.IsValidIndex(Intro_TotalSpawnedPlayers - 1)'
BOUNDED_CURRENT = CURRENT + ' && Intro_TimeDelaysOnAnims.IsValidIndex(Intro_TotalSpawnedPlayers)'
BOUNDED_PREVIOUS = 'Intro_TimeDelaysOnAnims.IsValidIndex(Intro_TotalSpawnedPlayers - 1)'


def scan(text):
    """Mask comments/literals, preserving offsets for structural extraction."""
    tokens = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\r\n]*|/\*[\s\S]*?\*/'
    return re.sub(tokens, lambda m: re.sub(r'[^\r\n]', ' ', m.group()), text)


def method_span(text):
    code = scan(text)
    pattern = r'\bvoid\s+AUTLineUpHelper::IntroSpawnDelayedCharacter\s*\(\s*\)\s*\{'
    matches = list(re.finditer(pattern, code))
    if len(matches) != 1:
        raise ValueError('Expected one IntroSpawnDelayedCharacter definition')
    match = matches[0]
    depth = 1
    for pos in range(match.end(), len(code)):
        depth += (code[pos] == '{') - (code[pos] == '}')
        if depth == 0:
            return match.start(), pos + 1
    raise ValueError('Unclosed IntroSpawnDelayedCharacter definition')


def digest_method(method):
    # Allow the checkout's LF/CRLF choice; otherwise pin the entire method,
    # including comments, ordering, declarations and the first spawn block.
    return hashlib.sha256(method.replace('\r\n', '\n').encode('utf-8')).hexdigest()


def edit_method(method, newline):
    guard = 'if (' + CURRENT + ')'
    if method.count(guard) != 2 or method.count(PREVIOUS) != 1:
        raise ValueError('Unexpected inspected scheduling anchors')
    start = method.rindex(guard)
    line_start = method.rfind('\n', 0, start) + 1
    indent = method[line_start:start]
    if indent.strip():
        raise ValueError('Expected standalone rescheduling guard')
    # The first character-selection guard remains byte-for-byte unchanged.
    changed = method[:start] + method[start:].replace(CURRENT, BOUNDED_CURRENT, 1)
    changed = changed.replace(PREVIOUS, BOUNDED_PREVIOUS, 1)
    return changed[:line_start] + indent + '// ' + MARKER + newline + changed[line_start:]


def transform(text):
    newline = '\r\n' if '\r\n' in text else '\n'
    if '\r' in text.replace('\r\n', '') or (newline == '\r\n' and '\n' in text.replace('\r\n', '')):
        raise ValueError('Mixed or unsupported source line endings')
    left, right = method_span(text)
    method = text[left:right]
    if MARKER in text:
        if text.count(MARKER) != 1 or method.count(MARKER) != 1:
            raise ValueError('Duplicate or misplaced lineup marker')
        clean, count = re.subn(r'(?m)^[ \t]*// ' + MARKER + r'\r?\n', '', method)
        if count != 1 or clean.count(BOUNDED_CURRENT) != 1 or clean.count(BOUNDED_PREVIOUS) != 1:
            raise ValueError('Incomplete lineup bounds patch')
        clean = clean.replace(BOUNDED_CURRENT, CURRENT, 1).replace(BOUNDED_PREVIOUS, PREVIOUS, 1)
        if digest_method(clean) != SOURCE_SHA256 or edit_method(clean, newline) != method:
            raise ValueError('Altered lineup patch or unsupported callback revision')
        return text
    if digest_method(method) != SOURCE_SHA256:
        raise ValueError('Unsupported IntroSpawnDelayedCharacter source fingerprint')
    return text[:left] + edit_method(method, newline) + text[right:]


def physical(path, missing_leaf=False):
    """Reject symlinks/junctions on all ancestors and hardlinks on files."""
    path = Path(os.path.abspath(path))
    for item in [*reversed(path.parents), path]:
        try:
            info = item.lstat()
        except FileNotFoundError:
            if missing_leaf and item == path:
                return path
            raise ValueError('Required physical path missing: ' + str(item))
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Refusing linked/reparse path: ' + str(item))
        if stat.S_ISREG(info.st_mode):
            if info.st_nlink != 1 or item != path:
                raise ValueError('Refusing shared file or non-directory ancestor: ' + str(item))
        elif not stat.S_ISDIR(info.st_mode):
            raise ValueError('Refusing non-regular path: ' + str(item))
    return path


def decode(data):
    encoding = 'utf-8-sig' if data.startswith(b'\xef\xbb\xbf') else 'utf-8'
    return data.decode(encoding), encoding


def patch(root, apply=False):
    root = Path(os.path.abspath(root))
    marker = physical(root / '.tournament-browser-port')
    if not marker.is_file():
        raise ValueError('Use only a marked isolated browser checkout')
    version = json.loads(physical(root / 'Engine/Build/Build.version').read_text(encoding='utf-8-sig'))
    if not isinstance(version, dict) or tuple(version.get(k) for k in ('MajorVersion', 'MinorVersion', 'PatchVersion', 'Changelist')) != (4, 15, 0, 3228288):
        raise ValueError('Expected UE4.15.0 CL3228288')
    path = physical(root / SOURCE_PATH)
    if not path.is_file():
        raise ValueError('Expected a regular source file')
    original = path.read_bytes()
    text, encoding = decode(original)
    updated = transform(text).encode(encoding)
    backup = physical(Path(str(path) + BACKUP_SUFFIX), missing_leaf=True)
    if backup.exists():
        if not backup.is_file():
            raise ValueError('Expected a regular original backup')
        saved = backup.read_bytes()
        saved_text, saved_encoding = decode(saved)
        if MARKER in saved_text:
            raise ValueError('Backup must contain unpatched source')
        if original != updated:
            if saved != original:
                raise ValueError('Conflicting original backup')
        elif transform(saved_text).encode(saved_encoding) != original:
            raise ValueError('Patched source does not match original backup')
    elif original == updated:
        raise ValueError('Patched source is missing its original backup')

    status = 'already-patched' if original == updated else 'would-patch'
    if apply and original != updated:
        if not backup.exists():
            # Exclusive creation cannot follow an unexpected pre-existing link.
            with os.fdopen(os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
                stream.write(original)
                stream.flush()
                os.fsync(stream.fileno())
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.lineup-patch-', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(updated)
                stream.flush()
                os.fsync(stream.fileno())
            physical(path)
            physical(backup)
            if path.read_bytes() != original or backup.read_bytes() != original:
                raise ValueError('Source or backup changed during patch; refusing replacement')
            os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
            os.replace(temporary, path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
        status = 'patched'
    result = {'status': status, 'file': str(SOURCE_PATH),
              'sha256': hashlib.sha256(updated).hexdigest(), 'originalMethodSha256': SOURCE_SHA256}
    print(json.dumps(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_root')
    parser.add_argument('--apply', action='store_true', help='save original privately and patch only the intro rescheduling bounds')
    args = parser.parse_args()
    try:
        patch(args.source_root, args.apply)
    except (ValueError, OSError, UnicodeError) as error:
        parser.exit(1, str(error) + '\n')
