"""Guard Party's post-load callback when a failed map load leaves no world.

Original bounded patcher for the marked UE4.15.0 CL3228288 browser checkout.
Default is read-only validation. Use --apply only when main has stopped builds.
Licensed source is read in place, never bundled here or printed. No build runs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

SOURCE_PATH = Path('UnrealTournament/Plugins/Online/OnlineFramework/Source/Party/Private/Party.cpp')
BACKUP_SUFFIX = '.before-tournament-browser-party'
MARKER = 'TOURNAMENT_BROWSER_PARTY_WORLD_V1'
INSERT = '''// TOURNAMENT_BROWSER_PARTY_WORLD_V1
if (GetWorld() == nullptr)
{
    UE_LOG(LogParty, Warning, TEXT("Party registration deferred: post-load callback has no owning world."));
    return;
}
'''


def scan(text):
    """Mask comments/literals without changing offsets; retain code punctuation."""
    tokens = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\r\n]*|/\*[\s\S]*?\*/'
    return re.sub(tokens, lambda m: re.sub(r'[^\r\n]', ' ', m.group()), text)


def method_span(text, name):
    code = scan(text)
    matches = list(re.finditer(r'\bvoid\s+UParty::' + re.escape(name) + r'\s*\(\s*\)\s*\{', code))
    if len(matches) != 1:
        raise ValueError('Expected one definition of UParty::' + name)
    left = matches[0].end() - 1
    depth = 0
    for pos in range(left, len(code)):
        if code[pos] == '{':
            depth += 1
        elif code[pos] == '}':
            depth -= 1
            if depth == 0:
                return left, pos + 1
    raise ValueError('Unclosed method: ' + name)


def transform(text):
    left, right = method_span(text, 'OnPostLoadMap')
    body = text[left:right]
    newline = '\r\n' if '\r\n' in text else '\n'
    if '\n' in text.replace('\r\n', '') and newline == '\r\n':
        raise ValueError('Mixed source line endings')
    anchor = re.search(r'(?m)^([ \t]*)RegisterIdentityDelegates\(\);[ \t]*\r?$', scan(body))
    if anchor is None:
        raise ValueError('Missing standalone identity-registration call')
    indent = anchor[1]
    insertion = ''.join(indent + line + newline for line in INSERT.splitlines())
    marked = MARKER in text
    if marked:
        if text.count(MARKER) != 1 or body.count(insertion) != 1:
            raise ValueError('Incomplete or altered Party patch marker')
        clean_body = body.replace(insertion, '', 1)
    else:
        clean_body = body

    # Accept only the inspected callback control flow, allowing formatting/comments.
    shape = (r'\{\s*if\s*\(\s*!\s*HasAnyFlags\s*\(\s*RF_ClassDefaultObject\s*\)\s*\)\s*\{\s*'
             r'RegisterIdentityDelegates\s*\(\s*\)\s*;\s*'
             r'RegisterPartyDelegates\s*\(\s*\)\s*;\s*\}\s*\}')
    if re.fullmatch(shape, scan(clean_body)) is None:
        raise ValueError('Unknown OnPostLoadMap callback shape')
    for name in ('RegisterIdentityDelegates', 'RegisterPartyDelegates'):
        a, b = method_span(text, name)
        if len(re.findall(r'\bensure\s*\(\s*World\s*\)', scan(text[a:b]))) != 1:
            raise ValueError('Expected existing world ensure in ' + name)
    if marked:
        # Marker must guard the calls, not appear elsewhere inside the callback.
        clean_anchor = re.search(r'(?m)^([ \t]*)RegisterIdentityDelegates\(\);[ \t]*\r?$', scan(clean_body))
        expected = clean_body[:clean_anchor.start()] + insertion + clean_body[clean_anchor.start():]
        if body != expected:
            raise ValueError('Party guard is not at the registration boundary')
        return text
    updated_body = body[:anchor.start()] + insertion + body[anchor.start():]
    return text[:left] + updated_body + text[right:]


def physical(root, relative, missing=False):
    """Reject junctions/symlinks and multiply-linked files on every target segment."""
    path = root
    for part in (None, *Path(relative).parts):
        if part is not None:
            path = path / part
        try:
            info = path.lstat()
        except FileNotFoundError:
            if missing and path == root / relative:
                return path
            raise ValueError('Required physical path missing: ' + str(path))
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Refusing linked/reparse path: ' + str(path))
        if stat.S_ISREG(info.st_mode):
            if info.st_nlink != 1:
                raise ValueError('Refusing multiply-linked file: ' + str(path))
        elif not stat.S_ISDIR(info.st_mode):
            raise ValueError('Refusing non-regular path: ' + str(path))
    return path


def patch(root, apply=False):
    root = Path(os.path.abspath(root))
    marker = physical(root, Path('.tournament-browser-port'))
    if not marker.is_file():
        raise ValueError('Use only a marked isolated browser checkout')
    version_path = physical(root, Path('Engine/Build/Build.version'))
    version = json.loads(version_path.read_text(encoding='utf-8-sig'))
    if tuple(version.get(k) for k in ('MajorVersion', 'MinorVersion', 'PatchVersion', 'Changelist')) != (4, 15, 0, 3228288):
        raise ValueError('Unsupported engine revision; expected UE4.15.0 CL3228288')
    path = physical(root, SOURCE_PATH)
    original = path.read_bytes()
    encoding = 'utf-8-sig' if original.startswith(b'\xef\xbb\xbf') else 'utf-8'
    updated = transform(original.decode(encoding)).encode(encoding)
    backup = physical(root, Path(str(SOURCE_PATH) + BACKUP_SUFFIX), missing=True)
    if backup.exists():
        saved = backup.read_bytes()
        if original != updated:
            if saved != original:
                raise ValueError('Conflicting backup; no writes performed')
        elif MARKER in saved.decode(encoding) or transform(saved.decode(encoding)).encode(encoding) != original:
            raise ValueError('Backup does not match the patched source')
    elif original == updated:
        raise ValueError('Patched source is missing its original backup')
    status = 'already-patched' if original == updated else 'would-patch'
    if apply and original != updated:
        if not backup.exists():
            with backup.open('xb') as stream:
                stream.write(original)
        # Replace the directory entry, never truncate a possibly shared source inode.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.party-patch-', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(updated)
            physical(root, SOURCE_PATH)
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
    parser.add_argument('--apply', action='store_true', help='write the guarded callback and one private source backup')
    args = parser.parse_args()
    try:
        patch(args.source_root, args.apply)
    except (ValueError, OSError, UnicodeError) as error:
        parser.exit(1, str(error) + '\n')
